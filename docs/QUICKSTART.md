# Capture session quickstart

How to record one New World session on a local Linux machine and end up with a
single ZIP containing the network ledger and the gameplay video.

Two roles are involved:

- The **operator** prepares the machine once, following "One-time setup".
- The **player** runs "Every session" and needs only Steam, the game and a browser tab.

## Requirements

Install these yourself, then let the setup script do the rest.

1. **Linux with a GPU that can encode video.** X11 and Wayland both work.
   NVIDIA (NVENC), AMD or Intel (VA-API) are all supported by the recorder.
2. **Steam, New World (app 1063730), Proton 11.0 and SteamLinuxRuntime_4.** Launch the
   game once by hand and reach the character screen, so no first-run dialog appears later.
3. **Node 22.18 or newer**, for native TypeScript execution: `node --version`.
4. **gpu-screen-recorder**, only when video is wanted. Install it from your
   distribution or as a Flatpak. On Wayland it needs its `gsr-kms-server` helper,
   which the package installs.
5. **Python 3 with venv**, plus `curl`, `xz` and `sha256sum` for the setup script.
6. **Free disk space.** The video is written once during the session and copied once
   into the ZIP. At the default 6000 kbps that is about 45 MB per minute, so budget
   roughly 6 GB for a one-hour session.

Then run the setup script from the repository root:

```sh
bash Tools/nw_capture/setup.sh
```

It creates the private `.venv-capture` environment, installs the pinned capture
dependencies, downloads the Frida server that matches the installed `frida` client,
checks its SHA-256 against the recorded digest and places it at
`Tools/nw_capture/frida-server.exe`. That binary is the Windows build, because it is
injected into NewWorld.exe inside the Proton prefix; it is deliberately not stored in
this repository. The script then reports anything still missing. It is safe to rerun:
an existing environment and an existing server file are left alone.

## One-time setup

Pick the capture target and the audio source from `gpu-screen-recorder --list-monitors`
and `gpu-screen-recorder --list-audio-devices`, then save them in a small file the
player never has to edit, for example
`~/.config/nw-capture.env`:

```sh
CAPTURE_VIDEO=1
VIDEO_TARGET=screen
VIDEO_AUDIO_SOURCE=default_output
```

`VIDEO_TARGET` accepts `screen` for the first monitor, a monitor name such as `DP-1`,
or a single window. Window capture depends on the session type: on X11 use the window
id, on Wayland use `portal`, which asks once which window to share and then reuses that
choice from its saved token. The game runs fullscreen, so a monitor is usually the same
picture, except that alt-tabbing records the desktop instead of the game. `VIDEO_AUDIO_SOURCE` accepts `default_output` for desktop sound; combine
sources with `|`, for example `default_output|default_input` to add the microphone.
Check that it is not pointing at a microphone by mistake.

A session has no time limit: it records until STOP. It also ends on its own when the
output directory passes half of `CAPTURE_STORAGE_GB`, 40 GB by default, which is about
seven hours at the default bitrate.

## Every session

1. Start Steam and New World as usual, and enter the world.
2. Start the capture server from the repository root:
   ```sh
   set -a; . ~/.config/nw-capture.env; set +a
   bash Tools/nw_capture/web/run.sh
   ```
   Leave that terminal open. The server prints its address and keeps running.
3. Open `http://127.0.0.1:8787` in Chrome.
4. Read **Host checks** at the top of the page. Steam, New World, the capture
   environment, the Frida server file, the recorder and the capture port must all
   read OK, and the free space must cover the session. The checks refresh every
   two seconds, so starting the game updates them without reloading the page.
5. Type a session name and press **START**.
6. Check the page shows `RUNNING` within a few seconds, with DTLS batches and video
   bytes increasing. Anything else is a configuration problem, and the page states it.
7. Play. The tab can be closed and reopened; the session lives in the server, not in
   the browser.
8. Press **STOP** when finished, before closing the game. The state stays `STOPPING`
   until the collector and the recorder have both exited and the ZIP is complete.
   Closing New World first also ends the capture, but the collector loses its final
   flush: the session shows ERROR and the archive records
   `final_flush_acknowledged: false`. The ZIP is still produced.
9. The download starts on its own. If Chrome blocks it, use the download link.
10. Press Ctrl+C in the terminal and wait for the server to exit.

## What you get

The ZIP contains:

- `metadata.json`: session name, timestamps and ledger counters.
- `ledger.bin`: the raw captured network ledger.
- `gameplay.mkv`: the recording, stored uncompressed inside the archive.

The same files stay on the machine under `Tools/nw_capture/captures/web/<session-id>/`.
The archive holds raw game traffic, so treat it as private and do not publish it.

## If something goes wrong

- **The page never leaves `STARTING`.** The collector could not attach. The game must be
  running before START, and the terminal running the server shows the reason.
- **A host check reads MISSING.** Steam and New World mean the matching process is not
  running. The capture environment, the Frida server file and the recorder are the
  installation steps above. The capture port means a Frida server from an earlier run
  still holds port 27943.
- **`CAPTURE_VIDEO=1 requires gpu-screen-recorder`.** The recorder is not installed, or
  not on the PATH of the user starting the server.
- **`Capture incomplete or archive failed.`** The ledger never reached the disk, or the
  collector's sink failed. A capture ended by closing the game is still archived.
- **Video state is `ERROR` but the capture finished.** The ZIP is still valid and keeps
  the ledger. Read `Tools/nw_capture/captures/web/<session-id>/video.log`.
- **The server refuses to start because another one owns the directory.** A previous
  server is still running. The lock is released on its own once that process is gone.
- **`Capture port already occupied`.** A Frida server from an earlier run is still on
  port 27943. Close it before starting again.
- **Nothing is recorded and the video is black.** Check `VIDEO_TARGET` against
  `gpu-screen-recorder --list-monitors`.

## Limits

One session at a time, one server for every browser tab. The page is loopback only,
without authentication: anyone with access to the machine, or to a tunnel to that port,
controls the session. Old sessions are never deleted automatically; the server refuses
to start a new one after 10 retained directories or when the storage ceiling is reached.

Full behaviour, security notes and verification history: [web/README.md](../Tools/nw_capture/web/README.md).
