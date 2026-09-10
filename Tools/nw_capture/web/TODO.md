# Capture web POC - TODO

## Operating rules

- Work directly, without workflows or subagents.
- Do not use YouTube Studio, including browser automation.
- One shared server-owned session; refreshing or reopening the page does not stop capture.
- Reproducible setup on local or remote gaming hosts, without hardcoded IPs/users.
- Keep credentials out of the repository, logs, HTTP responses and ZIP archives.
- Keep documentation, comments, UI text and future examples in English.
- Preserve historical session names, filenames and IDs verbatim as evidence.

## Named sessions

- [x] Required name field at Start, validated on the server (1-100 characters).
- [x] Name preserved in shared state and ZIP metadata.
- [x] ZIP filename derived from the session name and sanitized for filesystem use.
- [x] Unique internal ID, including for sessions with identical names.
- [x] Automated lifecycle, invalid input, filename and metadata checks.
- [x] Browser test with simulated collector: Start, refresh, Stop and download.
- [x] Deploy the update to the VM and inspect the actual page (8787, IDLE, name field present).

## YouTube without Studio

- [x] Integrate the existing RTMPS encoder, with a stream key configured once on the gaming host.
- [x] Shared Start/Stop for collector and encoder, including error/timeout cleanup.
- [x] Encoder state and errors visible on the page without exposing secrets.
- [x] Archive support for youtubeUrl metadata and youtube.txt, tested with a mock URL.
- [x] Associate the actual broadcast URL with session metadata.
- [x] Verify a real encoder/capture run without disrupting the game or Moonlight.
- [x] Document portable configuration using the operator's own credentials.

Original constraint: RTMPS and a stream key transport audio/video, but do not set
YouTube titles or create/return a new broadcast and its URL. Do not claim automatic
titles, broadcast creation or link discovery from a stream key alone.
Direct OAuth was subsequently authorized: see the current decision below.

## Follow-up work outside the current scope

- [x] Video is represented only by its YouTube link in the ZIP. Local backup stays on the host; storage thresholds are documented.
- [x] Optional raw payload export enabled on the VM; TLS keylog and runtime logs excluded. Archive remains sensitive.
- [ ] Cloudflare Access and Tunnel.
- [ ] Browser gameplay through a gateway, separate from capture controls.

## Initial verification

- `node Tools/nw_capture/web/test.ts`: passed.
- `python3 -m unittest discover -s Tools/nw_capture/web -p 'test_*.py'`: 4 tests passed at this stage.
- Temporary browser on 18788: historical test name "Spedizione serale à / test"
  preserved after refresh; filename `Spedizione-serale-a-test.zip`; no real capture started.

## Integrated video and capture test

- Session `a092b19d-daf0-45fa-ac48-32091b5b0b42`, historical name "Video capture stop verificato".
- Start/refresh/Stop in a real browser: STOPPED, zero errors, 357825 bytes, 929 batches.
- MKV duration 27.466 seconds, H.264 1920x1080 and AAC; encoder exit 0.
- ZIP CRC valid; contains video, raw ledger and metadata. No YouTube transmission in this test.
- The first test exposed repeated encoder signals: fixed with idempotent stop,
  regression test added; the second real test passed.
- RTMPS/automation were not verified at this stage; the later OAuth test is recorded below.

## YouTube constraint verified against an official source

`liveBroadcasts.insert` creates a broadcast and requires OAuth authorization with
scope `youtube` or `youtube.force-ssl`; it requires a title, schedule and privacy
setting, and returns the broadcast ID. An RTMPS stream key cannot authorize it.
Source: https://developers.google.com/youtube/v3/live/docs/liveBroadcasts/insert

Under the original constraints (no Studio, no supplied OAuth credentials), automatic
broadcast/title/URL creation could not be verified. Do not transmit a new session
without first verifying its broadcast and privacy setting. This initial limitation
was superseded by the OAuth test below.

## Current decision: direct OAuth, explicitly requested by the user

- Apps Script abandoned: no gateway deployment remains to be completed.
- Use YouTube Data API v3 with a Desktop OAuth client and private refresh token.
- No API key or Studio during automated setup/capture.
- Document and maintain reproducible local and remote setup in **YOUTUBE.md**.
- The user explicitly requested that reproducibility be remembered and documented.
- [x] Direct OAuth client, loopback callback with state/PKCE, private 0600 credentials.
- [x] Local creation/binding/title/privacy/Stop, refresh, error and callback tests.
- [x] Actual channel authorization and stream-key verification through Desktop OAuth.
- [x] Complete live test: Start, page refresh, Stop, ZIP with URL, playback.
  Session `53dea53a-b6d4-401a-9fa4-5336eeb2b754`, video:
  https://www.youtube.com/watch?v=2kU6HOnlLnQ. Evidence and limitations are in YOUTUBE.md.
