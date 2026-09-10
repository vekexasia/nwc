#!/usr/bin/env python3
import argparse
import base64
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

SCOPE = 'https://www.googleapis.com/auth/youtube.force-ssl'


def request_json(url, data=None, token=None):
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    request = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        endpoint = urllib.parse.urlsplit(url).path
        raise RuntimeError(f'Google HTTP {error.code} at {endpoint}; check API enablement, consent and channel access') from None
    if len(raw) > 1024 * 1024:
        raise ValueError('Google response too large')
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError('Invalid Google response')
    return result


def private_read(path, limit):
    if path.stat().st_mode & 0o077 or path.stat().st_size > limit:
        raise ValueError(f'{path}: require private mode 0600 and at most {limit} bytes')
    return path.read_text().strip()


def callback_code(path, state):
    parsed = urllib.parse.urlsplit(path)
    query = urllib.parse.parse_qs(parsed.query)
    if parsed.path != '/oauth2callback' or query.get('state') != [state]:
        raise ValueError('Invalid OAuth callback state/path')
    if 'error' in query:
        raise PermissionError('Google authorization denied')
    codes = query.get('code', [])
    if len(codes) != 1 or not codes[0]:
        raise ValueError('Missing OAuth code')
    return codes[0]


def main():
    parser = argparse.ArgumentParser(description='One-time YouTube Desktop OAuth setup; no API key or Studio automation')
    parser.add_argument('--client', type=Path, required=True, help='Downloaded Desktop client JSON, chmod 600')
    parser.add_argument('--key-file', type=Path, required=True, help='Existing reusable stream key, chmod 600')
    parser.add_argument('--channel', required=True, help='Expected exact channel title or ID; reject a different account')
    parser.add_argument('--output', type=Path, required=True, help='New private config file outside the repository/capture data')
    parser.add_argument('--port', type=int, default=8765, help='Loopback callback port; forward this same port for remote setup')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    if args.output.exists() or not 1 <= args.port <= 65535:
        raise ValueError('Output already exists or invalid port; preserve existing authorization')
    client = json.loads(private_read(args.client, 8192)).get('installed', {})
    if not all(isinstance(client.get(key), str) and client[key] for key in ('client_id', 'client_secret')):
        raise ValueError('Download an OAuth Desktop app client, not a Web app or API key')
    stream_key = private_read(args.key_file, 512)
    if not stream_key:
        raise ValueError('Empty stream key')
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    redirect = f'http://127.0.0.1:{args.port}/oauth2callback'
    result = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *_):
            pass  # Never log the callback authorization code.

        def do_GET(self):
            try:
                code = callback_code(self.path, state)
            except PermissionError:
                result['denied'] = True
                self.send_response(403)
            except ValueError:
                self.send_response(400)
            else:
                result['code'] = code
                self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(b'Return to the capture setup terminal. You can close this tab.')

    with http.server.HTTPServer(('127.0.0.1', args.port), Callback) as server:
        server.timeout = 0.5
        url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode({
            'client_id': client['client_id'], 'redirect_uri': redirect, 'response_type': 'code',
            'scope': SCOPE, 'access_type': 'offline', 'prompt': 'consent', 'state': state,
            'code_challenge': challenge, 'code_challenge_method': 'S256'})
        print('Authorize the intended YouTube channel in this URL:\n' + url, flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        deadline = time.monotonic() + 600
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if 'code' not in result:
        raise RuntimeError('Google authorization denied or timed out; no config saved')
    tokens = request_json('https://oauth2.googleapis.com/token', {
        'client_id': client['client_id'], 'client_secret': client['client_secret'],
        'code': result['code'], 'code_verifier': verifier, 'redirect_uri': redirect,
        'grant_type': 'authorization_code'})
    if not all(isinstance(tokens.get(key), str) and tokens[key] for key in ('refresh_token', 'access_token')):
        raise RuntimeError('No offline token granted; no config saved')
    if SCOPE not in tokens.get('scope', '').split():
        raise RuntimeError('Required YouTube scope not granted')
    channels = request_json('https://www.googleapis.com/youtube/v3/channels?part=id,snippet&mine=true', token=tokens['access_token'])
    matches = [item for item in channels.get('items', []) if args.channel in (item['id'], item['snippet']['title'])]
    if len(matches) != 1:
        raise RuntimeError('Authorized channel differs from --channel; repeat setup with the intended channel')
    channel = matches[0]
    stream = None
    page_token = ''
    # ponytail: scan at most 150 reusable streams; increase pagination if this channel needs more.
    for _ in range(3):
        streams = request_json('https://www.googleapis.com/youtube/v3/liveStreams?' + urllib.parse.urlencode({
            'part': 'id,snippet,cdn', 'mine': 'true', 'maxResults': 50, 'pageToken': page_token}), token=tokens['access_token'])
        stream = next((item for item in streams.get('items', []) if item.get('snippet', {}).get('channelId') == channel['id'] and item.get('cdn', {}).get('ingestionInfo', {}).get('streamName') == stream_key), None)
        if stream or not streams.get('nextPageToken'):
            break
        page_token = streams['nextPageToken']
    if not stream:
        raise RuntimeError('No reusable stream matches the private key on the authorized channel')
    config = {key: client[key] for key in ('client_id', 'client_secret')}
    config.update(refresh_token=tokens['refresh_token'], channel_id=channel['id'], stream_id=stream['id'])
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with args.output.open('x') as file:
        json.dump(config, file)
    print(f'Saved private OAuth config: {args.output}\nChannel: {channel["snippet"]["title"]} ({channel["id"]})\nStream: {stream["id"]}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        raise SystemExit(str(error)) from None
