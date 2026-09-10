# Shared capture web POC

Run on the Linux gaming host as the Steam user, with Steam and New World already
running. No game launch or login automation. Optional local video and RTMPS encoder.
Uses the existing `capture_proton.py` collector, not a simulated collector.

## Run

Requires Node >=22.18 (native TypeScript stripping; tested 26.7.0), Python with
`../requirements.txt` in a private venv, matching Windows Frida server beside
`capture_proton.py`, Proton 11.0 and SteamLinuxRuntime_4. No npm packages/build.
Prepare the existing isolated Python environment as in
[the host guide](../../../docs/SETUP.md).

From the repository root, one command:

```sh
bash Tools/nw_capture/web/run.sh
```

Optional operator environment, not browser inputs:

- `STEAM_DIR`: Steam installation containing steamapps; default `$HOME/.local/share/Steam`.
- `CAPTURE_PYTHON`: absolute Python executable; default repo `.venv-capture/bin/python`.
- `CAPTURE_VIDEO`: `1` records gameplay video alongside the collector (default off).
- `VIDEO_SIZE`: X11 capture size, default `1920x1080` at 30 fps.
- `VIDEO_AUDIO_SOURCE`: PulseAudio source, default `default`; select the gameplay monitor.
- `YOUTUBE_KEY_FILE`: optional private 0600 stream-key file, outside capture output.
- `YOUTUBE_OAUTH_CONFIG`: private JSON produced by `youtube_auth.py`. Enables direct OAuth broadcast lifecycle; see [replication guide](YOUTUBE.md).
- `YOUTUBE_WATCH_URL`: required with key only without OAuth; URL of an independently verified unlisted broadcast.
  A key alone does not create/rename a broadcast. No Studio automation is used.
- `CAPTURE_EXPORT_RAW`: `1` adds capture payloads to ZIP. Sensitive: do not share publicly.
- `CAPTURE_NODE`: Node executable; default resolved `node` on the launching PATH.
- `PORT`: loopback HTTP port, default 8787.
- `CAPTURE_SECONDS`: maximum collection seconds, default 600, range 1..3600.
- `CAPTURE_DATA`: private output root; default `Tools/nw_capture/captures/web` (gitignored).
- For SSH launches, configure `HOME`, `DISPLAY`, `XAUTHORITY`, `XDG_RUNTIME_DIR`
  and `DBUS_SESSION_BUS_ADDRESS` for the gaming user. Start in a directory that
  user can read. No fixed IP, user, display or Steam path is built into the app.

The script enters Steam's official `--alongside-steam` launch context. Do not
replace it with a direct Proton SSH launch or weaken AppArmor. If already inside
that context, `node Tools/nw_capture/web/server.ts` is sufficient.

Open `http://127.0.0.1:8787`. For a remote host, forward the **same port**:

```sh
ssh -N -L 127.0.0.1:8787:127.0.0.1:8787 YOUR_GAMING_HOST
```

Run the page server in a persistent terminal/service. Stop it with SIGTERM or
Ctrl+C on the Node process and wait for exit. Closing the browser only ends polling.

## Behavior and limits

Enter a session name before START (1-100 characters). The shared snapshot preserves
the original name; the ZIP attachment uses a filesystem-safe form of it. Internal
directories retain unique IDs, so repeated names cannot overwrite captures.

One server-owned session, shared by all tabs. Polling/reopening reads the same ID,
state, timestamps and counters. START is serialized; duplicate starts return 409.
STOP is idempotent even during STARTING. STOPPING remains visible until the owned
collector exits, its final metadata confirms flush/sink success, and ZIP creation
exits successfully. No successful download is offered for incomplete captures; video failures can still yield a valid capture archive flagged ERROR.

Duration is time since the server accepted START, including setup and cleanup,
not just time hooked. The browser extrapolates from server time, not its wall clock.
Count means **DTLS batches**, not packets or decoded messages. Error status is the
collector's nonzero exit/error status, not a count of individual logged events.
Raw payloads, target addresses and exception details are never sent to the UI.

Each observing page attempts one automatic download per completed ID, including a
newly opened page observing completion. No local/session storage controls capture.
Browser download policies can block the automatic attempt; the explicit button
always permits retry. Only the latest session is addressable through HTTP.

ZIP always contains aggregate `metadata.json`, including the session name. When
configured it also contains `youtube.txt` and raw `captures/` files. Video is linked,
never embedded: `gameplay.mkv` stays on the host and is excluded from the ZIP.
Raw export excludes `keylog.txt` and runtime logs but HTTPS payloads/metadata can
still contain credentials. Only enable it on a trusted local/tunnel endpoint.
Stream keys and browser credentials are never copied into the output directory.
Without OAuth the YouTube URL is operator configuration; RTMPS alone cannot verify
visibility or lifecycle. With OAuth, Start creates and verifies a fresh unlisted
broadcast and Stop confirms its closure through the official YouTube API.

Video and collector start together, and Stop waits for both before archiving.
The frame count means locally encoded frames, not confirmed YouTube playback.
Video errors preserve an otherwise valid capture ZIP and remain visible as ERROR.
The first implementation records 1080p30 H.264 NVENC + AAC stereo; no software
encoding fallback is silently used. No video source is configured through HTTP.

Limits: 10 retained session directories, 1 GiB admission storage ceiling,
256 MiB per-session soft stop threshold (1 GiB with video) sampled every 500 ms, 128 MiB hard limit
per worker file, 32 HTTP connections, 5-second request/header deadlines, 30-second
startup deadline. Storage thresholds are stop/admission limits, not filesystem
quotas; writes and extraction can overshoot between checks. Use a filesystem quota
if a hard total-disk limit is required. Old captures are never automatically deleted;
operator removal is required when admission limits are reached. The collector's
existing extraction is not a streaming, constant-memory pipeline.

After STOP, the watchdog requests termination of only the owned detached child
process group at 30 seconds and SIGKILL at 45 seconds. A watchdog intervention
marks cleanup uncertain, prohibits further starts and retains the owner lock.
Never interpret forced termination as successful flush. Inspect the owned Frida
server/port 27943 before clearing the lock; do not kill Steam, the game, Sunshine,
or all Wine processes. Existing port occupation is rejected before launch.
Do not run independent capturers concurrently: this lock coordinates this web app,
not external CLI users.

## Persistence and security

State is **in memory**, not a database. Refresh/reopening/another tab survives;
server restart does not restore the session or its download route. Private files
remain. Clean server shutdown first stops and waits for the owned worker. If the
server crashes, a worker in its collection loop detects parent loss and flushes;
its configured timeout remains a fallback. A crash during startup or an unresponsive
Frida RPC may require operator cleanup. A leftover `CAPTURE_DATA/owner` refuses
restart: inspect the recorded Node PID, owned worker and Frida server first, then
remove that file only after they are absent. No automatic stale-lock guessing.

Loopback only, no authentication, no TLS, no multi-user isolation. Any local user
or tunnel user can control the shared session and read aggregate metadata. Do not
publish through a reverse proxy or expose the port. Host and exact Origin checks,
a bounded JSON POST body and custom action header protect mutations against ordinary
cross-origin browser requests; they are not authentication. The browser supplies only a session display name, never a command or filesystem path. Static/download routes are exact
allowlists; downloads never resolve a requested path. CSP denies framing and
third-party resources. New output uses umask 077. Use a fresh private output root;
do not point it at shared/untrusted directories. Host-local users with the same
Unix identity remain trusted. Steam profile/credential files and browser login
data are not read or copied. The collector's private output can contain credentials.

## Checks

```sh
node Tools/nw_capture/web/test.ts
python -m unittest discover -s Tools/nw_capture/web -p 'test_*.py'
python -m unittest discover -s Tools/nw_capture -p 'test_*.py'
```

The dependency-free web test uses a fake **owned subprocess**, never the local
game. Covers concurrent starts/stops, STARTING cancellation, snapshot identity,
STOPPING before child exit, ZIP allowlist/credential exclusion, traversal routes,
Origin rejection, failed spawn/collector result and SIGTERM shutdown. Native Node
executes TypeScript but does not type-check it; no TypeScript compiler is installed
in this project.

Live verification on the authorized VM, 2026-09-10:

- Actual browser via CDP 9222: START, reload, second tab same ID, duplicate START
  409, live counters and duration within 2 seconds of server timestamps, STOP,
  visible download link. Actual screenshot inspected, not only HTTP/build output.
- Session `f8eb588c-f90b-41a7-983d-03c4fa517ae9`: 20.376 seconds between sink
  timestamps; UI duration 22.8 seconds including lifecycle. 268185 ledger bytes,
  735 batches, 1576 structurally readable ledger records. Final flush acknowledged,
  sink writes successful, error status 0. Downloaded ZIP CRC verified and safe
  metadata matched the real capture. Two browser-created ZIP files verified, one
  per observing page. No gameplay payload was printed.
- Failed Python launch also tested on an actual temporary browser page: ERROR,
  error status 1 and configuration message visible; page/server then closed.
- Existing collector tests: 15 tests, one local lz4 decoder subcheck skipped.
  Remote ledger validation used the existing isolated venv's decoder.
- Steam PID 37253, game PID 41097, Sunshine PID 37725 unchanged; Frida port 27943
  closed after stop. No game restart, input, upload or security-policy changes.
- Final code and `run.sh` retested in session
  `fab51a7a-28d6-4e7e-b4d5-be099498e79c`: 18.356 seconds between sink timestamps,
  20.8 seconds including lifecycle, 234049 bytes, 654 batches, 1413 readable
  records, acknowledged flush and successful sinks. Closed the second tab during
  capture and reopened it: same running ID. ZIP CRC and metadata revalidated;
  two automatic browser downloads. Session directory 0700, ledger 0600.
  The page server remains available through the existing tunnel at
  `http://127.0.0.1:8787`, collector stopped. VM remains running and billable.

These checks do not prove anti-cheat safety, long-run stability, exhaustive HTTP
payload capture, full gameplay decoding, forced native-RPC cleanup, or playback
quality. Video/YouTube and raw credential-safe export are deferred.

## YouTube without Studio

Use [YOUTUBE.md](YOUTUBE.md) for the reproducible Desktop OAuth setup, local/SSH
commands, credential handling, troubleshooting, and verification evidence.
Apps Script was abandoned after authorization problems and is no longer used.

```sh
node Tools/nw_capture/web/test_youtube.ts
CAPTURE_TEST_YOUTUBE=1 node Tools/nw_capture/web/test.ts
```

Automated checks mock Google, but use the real local lifecycle and OAuth callback.
They are not proof of actual YouTube ingestion or playback.
