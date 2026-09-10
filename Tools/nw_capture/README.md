# NW capture

Run commands from `Tools/nw_capture`. Install `requirements.txt` in your own
Python environment. Client/server Frida versions should match (17.9.10).

For shared browser START/STOP on the gaming host, see the functional
[TypeScript web POC](web/README.md). Page reloads and other tabs observe the same
server-owned session. Raw sensitive capture files stay private on the host.

## Omarchy / Proton launcher

From the repository root, with New World already starting or running through Steam:

```sh
uv run Tools/nw_capture/capture_proton.py
```

For a fresh launch, close New World and use `uv run Tools/nw_capture/capture_proton.py --launch`.
Steam starts asynchronously; the launcher checks for NewWorld.exe every 50 ms
and starts Frida as soon as it appears. The 120-second startup limit is not a
capture timeout. This reduces attach delay but does not guarantee the first request.

Place Windows x64 `frida-server.exe` version 17.9.10 alongside this script.
The binary is ignored by Git. This launcher uses the standard Steam location,
Proton 11.0, SteamLinuxRuntime_4 and app prefix 1063730. It starts the server,
attaches without a capture timeout, and writes under `nw_capture/logs/` and
`nw_capture/captures/`. Ctrl+C flushes and detaches before closing the server;
the game stays running. Do not run a second server on port 27943.
Start Steam first: a server already running in this prefix blocked Steam startup
in our test. Attach during game startup to include authentication and host mappings.
Use `--timeout 120` for a bounded capture and `--steam-dir PATH` to override
the Steam installation root (containing `steamapps`). Defaults remain unlimited
capture and `~/.local/share/Steam`. For the tested Ubuntu cloud launch service
and its AppArmor constraint, see [cloud setup](../../docs/SETUP.md).

`Tools/launch_new_world.sh` is separate, optional login automation. It uses
window-relative coordinates, but only supports the verified English 1920x1080 UI.
Other window sizes receive no clicks. The capturer itself does not click or OCR.

## Remote attachment

Use an already-running **Windows x64 frida-server**, reachable on a trusted
loopback/tunneled endpoint. This tool does not start a server. For example,
if that server listens on `127.0.0.1:27943`:

```sh
frida-ps -H 127.0.0.1:27943
python nw_capture.py --host 127.0.0.1:27943 --pid 123 --timeout 600 --session remote_capture --no-extract
```

Replace `123` with the **Windows PID reported by that server**, not the Linux
PID from `ps`. `--host` and `--pid` must be used together and cannot be combined
with `--target`. Remote connection failures never fall back to local attach.
The runner checks the server's reported Windows/x64 platform before attaching,
then validates the target inside the agent before interception.

Never use native Linux Frida attachment to NewWorld.exe: the previous attempt
failed with ptrace EIO and terminated the game. Isolated Notepad passed two
Windows-server attach/hook/unload/detach cycles under Proton 11.0 and
SteamLinuxRuntime_4, but that does **not** establish game capture safety.
Subsequent five-minute game captures completed with acknowledged flush and detach;
these observations do not establish anti-cheat safety or long-session stability.
Do not change anti-cheat or installed prefixes to use this tool.

Attached processes are never spawned, resumed, or killed; attachment never
writes `steam_appid.txt`. Timeout and Ctrl+C stop capture only. The agent stops
hook producers and its ledger timer, flushes pending records, and sends a final
marker. Python waits for receipt and verifies DTLS byte/batch/keylog counts
before unload/detach and sink closure. Missing acknowledgment (10-second wait),
transport loss, or process exit can leave an incomplete capture and produce a
nonzero result; check `final_flush_acknowledged` in `dtls/meta.json`. Sink
flush/close errors also produce a nonzero result and `sink_write_succeeded: false`.
The wait limit does not bound an unresponsive Frida RPC itself.

## Existing Windows spawn mode

```powershell
python nw_capture.py --target "C:\SteamLibrary\steamapps\common\New World\Bin64\NewWorld.exe" --timeout 600 --session spawn_capture
```

Local spawning requires Windows. It retains the existing `steam_appid.txt`
write, suspended spawn, hook installation, resume, and owned-process cleanup.
The owned spawn is killed after capture shutdown, unlike remote attachment.
All timeout values are **seconds**; the default is 600 (10 minutes), not
milliseconds. Values must be finite and nonnegative; `--timeout 0` waits until
Ctrl+C or detach without a capture deadline.

## Validation and capture limits

- Windows, x64, 8-byte pointers and x64 PE headers are required.
- Fixed DTLS hooks require image size 183214080 and exact pre-interception
  16-byte sequences for SSL_read, SSL_write and nss_keylog, plus executable,
  in-image ranges. Evidence is the first two events of the upstream
  `logs/20260611-024200_nw_https_tap.log` (not included here; see docs/REFERENCES.md). All three sites are checked before
  any interception. A mismatch aborts; there is no override.
- These checks validate the recorded hook sites, **not an entire build**. The
  available log has no full executable hash or full-function fingerprints.
  Matching prologues cannot prove unchanged function bodies, ABI, or keylog
  argument layout. Independent current-build verification and an authorized
  live lifecycle test remain blockers for declaring a real capture safe.
- WinHTTP export hooks observe application-owned callback addresses without
  replacing registration arguments, callback pointers, or return values. The
  application callback executes normally, with request correlation by its
  actual handle. No script-owned callback pointer remains after unload.
- Late attachment cannot recover earlier requests, handles, callback
  registrations, DTLS plaintext, or keylog events. Callbacks registered before
  attachment are only observed if their address is registered again later.
  Existing connections may have unknown hosts; partial requests and missing
  async bodies/keys are expected. Stop can omit operations still in flight.

## Output and offline tools

Raw HTTPS events go to `logs/`; plaintext ledger and keys go to
`captures/<session>/dtls/`. Unless `--no-extract` is supplied, HTTPS bundles are
extracted automatically. Use a fresh session name: DTLS files append, while
extracted output can overwrite earlier bundles.

```sh
python extract_https_pairs.py logs/YOUR_CAPTURE.log --out captures --session extracted_capture
python decode_dtls_ledger.py captures/remote_capture/dtls/ledger.bin --out decoded_session.jsonl
```

Logs, console output, extracted bodies and keylogs may contain Steam tickets,
bearer tokens, account identifiers, credentials and decrypted private traffic.
Use restrictive permissions (for example `umask 077` on Linux), private storage,
and a loopback/tunneled server. Do not publish raw output or commit it. Redact
before sharing and delete sensitive captures when no longer needed.

## Mocked regression checks

Requires Python and Node.js; the decoder check also requires `lz4`.
No server, process attachment, or game launch occurs:

```sh
# From the repository root
python -m unittest discover -s Tools/nw_capture -p 'test_*.py' -v
node --check Tools/nw_capture/_common.js
node --check Tools/nw_capture/_dtls_ledger.js
node --check Tools/nw_capture/nw_https_tap.js
```

Checks cover mode validation, wrong-server rejection before attach, no local
fallback, timeout/Ctrl+C/error cleanup, preserved spawn behavior, callback
observation/correlation, pre-hook validation, final flush ordering, late-callback
suppression, and synthetic ledger/extractor compatibility. They do not prove
native callback ABI behavior, live concurrency, remote transport ordering, or
game stability.

See [capture checklist](CAPTURES_TODO.MD).
