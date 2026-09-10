# YouTube OAuth: reproducible setup

Decision: use the official YouTube Data API v3 with Desktop OAuth, not Apps Script
or automated YouTube Studio. No API key. The stream key sends audio/video; the
refresh token authorizes broadcast creation, titles, links and closure.
Keep this procedure reproducible on local gaming hosts and VMs. Documentation,
comments, UI text and future examples must be in English. Historical identifiers
and session names below are preserved verbatim as verification evidence.

## 1. Google prerequisites (once)

1. Select your own project in [Google Cloud Console](https://console.cloud.google.com/).
   Prefer a dedicated project without provisioning VMs or other paid services.
   If your project quota is exhausted, create a dedicated client in an existing
   project without changing other applications' clients, keys or branding.
2. Enable **YouTube Data API v3** in the project's API library.
3. Configure Branding and Audience in **Google Auth Platform**. For a personal
   account, choose External. In Testing, add the authorizing account as a test
   user. For a Brand Account, authenticate its Google owner and then select the
   intended channel on the authorization screen.
4. Declare `https://www.googleapis.com/auth/youtube.force-ssl` in Data Access.
   This is the required official scope. Google's description includes permission
   to edit/delete videos and comments; there is no stream-key-only scope for
   broadcast management. Our code restricts changes to its own session broadcasts.
5. Under **Clients > Create client**, select **Desktop app**, named `New World Capture`.
   Download the client JSON and store it privately. It is not an API key.
   Do not select Web application or use the obsolete copy/paste OOB flow.
6. The channel must have live streaming enabled. Initial YouTube activation can
   take up to 24 hours. This procedure uses an existing reusable stream key;
   it does not create or reset other keys.

The consent screen displays the **project's branding**, not the client name.
Google may show an unverified-app warning for personal use: continue only for
an application you control and the intended channel. Public distribution may
require Google verification and your own terms/privacy policy.

**Token expiry:** External + Testing normally issues seven-day refresh tokens
for this scope. For ongoing use, check Audience and In production status.
Publishing does not mean Google has verified the application. Revocation,
account changes, Google policy or prolonged inactivity can still invalidate
access. Repeat authorization when necessary; do not extract browser cookies.

## 2. Authorize on a computer with a browser

From the repository root, using Python 3 and its standard library:

```sh
install -d -m 700 "$HOME/.config/new-world-capture"
# Store the downloaded client JSON and YOUR stream key here, not in shell history.
chmod 600 "$HOME/.config/new-world-capture/client.json" \
          "$HOME/.config/new-world-capture/stream.key"
python3 Tools/nw_capture/web/youtube_auth.py \
  --client "$HOME/.config/new-world-capture/client.json" \
  --key-file "$HOME/.config/new-world-capture/stream.key" \
  --channel 'YOUR_EXACT_CHANNEL_ID_OR_NAME' \
  --output "$HOME/.config/new-world-capture/oauth.json"
```

Google opens in the browser. Select the account, then channel/Brand Account, and
approve the YouTube scope. The callback listens only on `127.0.0.1:8765`, uses
state and PKCE, expires after ten minutes and does not log authorization codes.
The script verifies the channel and finds the stream matching the private key.
Only then does it save `oauth.json` with mode 0600. It never prints tokens or keys.
The output file must be new; existing authorizations are not overwritten.

To renew consent, use a new `--output` filename, verify the result and update the
service configuration while stopped. Preserve the old configuration's ownership
file if it contains an unfinished session.

## 3. Remote gaming host: two options

**A. Authorize on your computer**, then transfer only `oauth.json` and `stream.key`
over SSH. The downloaded client JSON is not needed during captures.

```sh
ssh YOUR_GAMING_HOST 'install -d -m 700 "$HOME/.config/new-world-capture"'
scp "$HOME/.config/new-world-capture/"{oauth.json,stream.key} \
  YOUR_GAMING_HOST:.config/new-world-capture/
ssh YOUR_GAMING_HOST 'chmod 600 "$HOME/.config/new-world-capture/"{oauth.json,stream.key}'
```

Use the Steam user on the host. If transferring as an administrator, explicitly
assign the files and directory to that user. Do not run the same configuration
on two servers concurrently: this implementation owns one session per host/stream.

**B. Authorize directly on the gaming host** with `--no-browser`. First open the
callback tunnel in a local terminal, then run the section 2 command remotely:

```sh
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 YOUR_GAMING_HOST
```

Open the URL printed by the remote process in your local browser. Keep the tunnel
open until configuration is saved. If changing `--port`, change both tunnel ports.
Do not expose the callback on `0.0.0.0` or expose Chrome/CDP.

## 4. Start the capture service

On the gaming host, as the Steam user, with the game and desktop already running:

```sh
export CAPTURE_VIDEO=1
export YOUTUBE_KEY_FILE="$HOME/.config/new-world-capture/stream.key"
export YOUTUBE_OAUTH_CONFIG="$HOME/.config/new-world-capture/oauth.json"
# Select the gameplay PulseAudio monitor, not necessarily the microphone.
export VIDEO_AUDIO_SOURCE='YOUR_AUDIO_MONITOR_NAME'
bash Tools/nw_capture/web/run.sh
```

Configure other paths/display settings as described in [README.md](README.md).
For a VM, open the page through the documented port 8787 tunnel. Captures do not
require an authenticated Google browser, Apps Script, Studio, an API key or the
original client JSON. Access tokens are renewed automatically with the refresh token.

START creates a fresh **unlisted** broadcast using the session name, binds the
configured stream and verifies channel, title, privacy and binding **before**
starting the collector/encoder. The monitor stream is disabled; otherwise Google
requires the testing stage before live, even with enableAutoStart. YouTube state
is checked every ten seconds.

STOP waits for collector/encoder exit, closes the broadcast through the API and
saves its link in `metadata.json` and `youtube.txt`. The ZIP never embeds the video;
`gameplay.mkv` remains on the host only.
If stopped before going live, the draft is deleted: state CANCELLED, with no link
to a nonexistent replay. If capture had already started, a YouTube error is shown
and local video remains on the host, outside the ZIP. Live replays may require processing time.

## 5. Credentials, shutdown and recovery

- Keep configuration, stream key and `oauth.json.sessions.json` outside the
  repository and capture root, in a private directory. Never paste them into
  tickets, browser forms or public logs.
- `.sessions.json` preserves only owned broadcast IDs across restarts. It is not
  included in archives. Never remove it during a live session.
- `CAPTURE_DATA/owner` prevents restart after a crash or uncertain cleanup. Check
  the PID, collector, Frida, encoder and broadcast before removing a lock.
- To close a persisted session after a crash, **first stop its encoder and owning
  server**. Read the session ID/name from `.sessions.json`, without printing OAuth
  configuration. From the repository root, with `YOUTUBE_OAUTH_CONFIG` set:

  ```sh
  node --input-type=module -e '
  import { youtube } from "./Tools/nw_capture/web/youtube.ts";
  console.log(await youtube("stop", process.argv[1], process.argv[2]));
  ' SESSION_ID 'EXACT_SESSION_NAME'
  ```

  This affects only the owned broadcast. Never run bulk live-stream cleanup.
  A Google transition in progress may require retrying after it settles.
- If a creation response is lost, Stop searches for the session marker in up to
  150 broadcasts. If unresolved, it retains the error/lock instead of creating duplicates.
- Ownership retention is limited to 100 records. With the service stopped, remove
  **only** verified `ended: true` records from that JSON. This does not delete
  archived YouTube videos.
- `401`/revoked token: repeat consent. `403`: check API enablement, scope, channel
  live eligibility and quota. Google `500`: remote failure, not successful consent.
  The UI never exposes raw Google responses, to prevent credential leakage.
- The page is loopback/tunnel only, without its own authentication. Do not publish
  it. Unlisted is not private: anyone with the link can watch.
- The VM remains running and billable until separately shut down by the operator.

## 6. Reproducible checks

```sh
node Tools/nw_capture/web/test_youtube.ts
node Tools/nw_capture/web/test.ts
CAPTURE_TEST_YOUTUBE=1 node Tools/nw_capture/web/test.ts
python3 -m unittest discover -s Tools/nw_capture/web -p 'test_*.py'
```

Mock coverage: token refresh, identity/title/privacy/binding, wrong key, idempotent
Stop, lost creation response, failed binding, 401, response size limits, actual
loopback HTTP callback with simulated Google, state/PKCE and private 0600 files.
Server checks cover concurrency, STARTING cancellation, ZIP and cleanup. These
checks do not prove actual YouTube ingestion.

Real verification procedure: confirm the display shows gameplay, not login screens;
START with a recognizable name, wait for YouTube LIVE and inspect playback through
the unlisted watch URL. Reload the capture page, STOP, verify ENDED, download the
ZIP and check its CRC and matching metadata URL. Confirm encoder/Frida exit without
stopping Steam, the game or Sunshine.

### Verification on this host

Desktop client `New World Capture` was created in existing project `iot-casa-giusto`
because the new-project quota was exhausted. Existing branding
`Home Assistant Google Action` was left unchanged. Authorized channel:
`ElektronVolt LIVE` (`UCAV3KgR3tR9kW1kK_XTAgqw`). No new API key.
Audience verified in the console: **External, In production**, without changing
project status. The seven-day Testing limit does not apply to this configuration;
revocation and other Google expiry conditions still apply.

Real test on 2026-09-10, session `53dea53a-b6d4-401a-9fa4-5336eeb2b754`:

- Historical session title: `New World OAuth - live verificata`.
- URL: https://www.youtube.com/watch?v=2kU6HOnlLnQ
- API: correct title/channel, `unlisted`, stream `active`, health `good`, then
  `complete` + `recorded`, stream `inactive` after Stop.
- Capture page: Start, refresh retaining ID/name, LIVE; Stop -> STOPPED/ENDED,
  zero errors. Screenshots of the actual page and player were inspected.
- YouTube player: 1920x1080 gameplay playing, time advancing from 12.8 to 61.7
  seconds; over 1 MB of decoded audio. This is not a subjective audio-quality
  assessment or an hours-long streaming stability test.
- Full lifecycle: 82.618 seconds, 2947 batches, 927134 ledger bytes; acknowledged
  flush and successful sinks. MKV: 78.300 seconds, H.264 1080p, AAC stereo 48 kHz.
- Historical ZIP, before the link-only requirement: `New-World-OAuth---live-verificata.zip`, 61109207 bytes,
  13 entries, valid CRC. Matching URL in metadata/youtube.txt; video/raw present;
  no OAuth, stream-key or keylog files. Raw traffic may contain other game tokens.
- Collector/encoder exited, Frida port 27943 closed; Steam PID 37253,
  New World PID 41097 and Sunshine PID 37725 unchanged.

Observed problems: the first authorization attempt returned HTTP 500; the second
succeeded. The default monitor stream kept a draft in READY; it is now explicitly
disabled and tested. Some preparation attempts failed without transmitting; their
exact cause was not logged at the time. Failures now have private-log diagnostics.
One closure during YouTube startup was not confirmed: the encoder stopped, the
lock was retained, and a subsequent OAuth recovery Stop confirmed closure.
The final test above closed automatically. Google errors or in-progress transitions
can still require operator recovery.

Host configuration/key: `/home/gamer/.config/new-world-capture/`; private log:
`server.log`; active capture root:
`/home/gamer/Aeternum-World/Tools/nw_capture/captures/web-oauth`.
Earlier captures remain in `captures/web`; none were deleted.
At verification completion, the app was available at `http://127.0.0.1:8787`,
with the latest session STOPPED and its ZIP available. The nohup-launched service
is not configured to start automatically after reboot.

## Official references

- [Desktop OAuth, loopback and PKCE](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Refresh-token expiry/revocation](https://developers.google.com/identity/protocols/oauth2#expiration)
- [Create a broadcast](https://developers.google.com/youtube/v3/live/docs/liveBroadcasts/insert)
- [Bind a stream](https://developers.google.com/youtube/v3/live/docs/liveBroadcasts/bind)
- [Live/complete transitions](https://developers.google.com/youtube/v3/live/docs/liveBroadcasts/transition)
