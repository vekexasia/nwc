import contextlib
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.parse
import urllib.request

import youtube_auth


class OAuthSetupTest(unittest.TestCase):
    def test_state_and_errors(self):
        self.assertEqual(youtube_auth.callback_code('/oauth2callback?state=right&code=ok', 'right'), 'ok')
        for path in ['/oauth2callback?state=wrong&code=ok', '/oauth2callback?state=right&code=a&code=b', '/other?state=right&code=ok']:
            with self.assertRaises(ValueError):
                youtube_auth.callback_code(path, 'right')
        with self.assertRaises(PermissionError):
            youtube_auth.callback_code('/oauth2callback?state=right&error=access_denied', 'right')

    def test_loopback_pkce_and_private_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client, key, output = root / 'client.json', root / 'key', root / 'oauth.json'
            client.write_text(json.dumps({'installed': {'client_id': 'client', 'client_secret': 'secret'}}))
            key.write_text('stream-secret')
            for path in (client, key):
                path.chmod(0o600)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            authorize = {}
            threads = []
            callback_results = []

            def browser(url):
                authorize.update(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query))
                self.assertEqual(authorize['scope'], [youtube_auth.SCOPE])
                self.assertEqual(authorize['access_type'], ['offline'])
                callback = authorize['redirect_uri'][0] + '?' + urllib.parse.urlencode({'state': authorize['state'][0], 'code': 'one-time-code'})

                def visit():
                    with urllib.request.urlopen(callback, timeout=5) as response:
                        callback_results.append((response.status, response.read()))
                thread = threading.Thread(target=visit)
                threads.append(thread)
                thread.start()

            def google(url, data=None, token=None):
                if url.endswith('/token'):
                    challenge = youtube_auth.base64.urlsafe_b64encode(youtube_auth.hashlib.sha256(data['code_verifier'].encode()).digest()).rstrip(b'=').decode()
                    self.assertEqual(challenge, authorize['code_challenge'][0])
                    self.assertEqual(data['code'], 'one-time-code')
                    return dict(access_token='access', refresh_token='refresh', scope=youtube_auth.SCOPE)
                self.assertEqual(token, 'access')
                if '/channels?' in url:
                    return {'items': [{'id': 'channel', 'snippet': {'title': 'Test channel'}}]}
                return {'items': [{'id': 'stream', 'snippet': {'channelId': 'channel'}, 'cdn': {'ingestionInfo': {'streamName': 'stream-secret'}}}]}

            argv = ['youtube_auth.py', '--client', str(client), '--key-file', str(key), '--channel', 'channel', '--output', str(output), '--port', str(port)]
            log = io.StringIO()
            with patch('sys.argv', argv), patch.object(youtube_auth.webbrowser, 'open', browser), patch.object(youtube_auth, 'request_json', google), contextlib.redirect_stdout(log):
                youtube_auth.main()
            for thread in threads:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
            self.assertEqual(callback_results[0][0], 200)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            config = json.loads(output.read_text())
            self.assertEqual(config['refresh_token'], 'refresh')
            self.assertEqual(config['stream_id'], 'stream')
            for secret in ['one-time-code', 'stream-secret', '"refresh"', 'access_token']:
                self.assertNotIn(secret, log.getvalue())
            with patch('sys.argv', argv), self.assertRaises(ValueError):
                youtube_auth.main()


if __name__ == '__main__':
    unittest.main()
