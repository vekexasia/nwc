# Local and remote play/capture setup

Run from the root of this repository. Do not run a second capture service against
an already owned game session. Setup is explicit; nothing here starts on boot.

## Dependencies

- Node >=22.18 for native TypeScript stripping; the tested workstation uses 26.7.0.
- Python 3 with venv/pip, or uv. Use a private environment, never system pip.
- Steam, New World (app 1063730), Proton 11.0 and SteamLinuxRuntime_4.
- Windows x64 Frida server **17.9.10**, matching the Python dependency.
- For video: `gpu-screen-recorder` with a working GPU encoder (NVENC, VA-API) and
  PipeWire or PulseAudio audio. It records on X11 and Wayland; on Wayland it needs
  its `gsr-kms-server` helper, installed by the distribution package.

One command performs the two steps below, including checksum verification:

```sh
bash Tools/nw_capture/setup.sh
```

To do it by hand instead:

```sh
umask 077
python3 -m venv .venv-capture
.venv-capture/bin/python -m pip install -r Tools/nw_capture/requirements.txt
```

If the distribution disables ensurepip, create the environment with
`python3 -m venv --without-pip .venv-capture` and use an available pip's
`--python .venv-capture` option. Do not install into the system environment.

Download `frida-server-17.9.10-windows-x86_64.exe.xz` from the official
[Frida release](https://github.com/frida/frida/releases/tag/17.9.10), verify the
release asset/checksum, decompress it and place it at
`Tools/nw_capture/frida-server.exe`. This dependency is intentionally not vendored
or tracked. Do not substitute native Linux attachment to NewWorld.exe; that path
previously terminated the game. The CLI guide documents hook/build checks.

## Play locally on Omarchy

1. Start Steam normally, install the game, select the required Proton version and
   complete login/Steam Guard yourself. Launch New World through Steam.
2. Verify the game is actually playable before attaching the collector.
3. For capture controls without video, leave `CAPTURE_VIDEO` unset and run:

   ```sh
   export STEAM_DIR="$HOME/.local/share/Steam"
   export CAPTURE_PYTHON="$PWD/.venv-capture/bin/python"
   bash Tools/nw_capture/web/run.sh
   ```

4. Open `http://127.0.0.1:8787`, enter a session name and use START/STOP. Closing
   the browser does not stop collection. Stop the service with SIGTERM/Ctrl+C on
   its Node process and wait for owned-worker cleanup.

The optional `Tools/launch_new_world.sh` uses uv/evdev and Hyprland, grim,
ImageMagick and Tesseract to automate only the verified English 1920x1080 game
screens. It requires input-device permissions, refuses an already open game and
is not necessary for capture. It is not a Steam credential/login bypass. To run
its standalone checks in the project venv, install its declared dependency with
`.venv-capture/bin/python -m pip install evdev==2.0.0` (Linux only).

The capture-only path can run under Omarchy/Proton. Video records on X11 and
Wayland through gpu-screen-recorder; check the produced `gameplay.mkv` once on a
new host before trusting a session.

## Run the web service remotely

Copy this repository's source to the gaming host, install the dependencies there
and launch as the Steam user inside its graphical session. Use absolute paths:

```sh
cd /YOUR/REPO/new-world-capture
export STEAM_DIR="$HOME/.local/share/Steam"  # Adjust if Steam uses another root.
export CAPTURE_PYTHON="$PWD/.venv-capture/bin/python"
export CAPTURE_DATA="$HOME/.local/share/new-world-capture/captures"
# For an SSH shell, set these to the actual running graphical user's session.
export DISPLAY=:0
export XAUTHORITY="$HOME/.Xauthority"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
bash Tools/nw_capture/web/run.sh
```

`run.sh` uses Steam's official `--alongside-steam` service. Direct Proton startup
over SSH hit Ubuntu AppArmor restrictions; do not weaken AppArmor/sysctls.
Use an operator-owned persistent terminal if the service must survive SSH exit.
Do not add automatic restarts while a stale capture owner could exist.

From the viewing computer:

```sh
ssh -N -L 127.0.0.1:8787:127.0.0.1:8787 YOUR_GAMING_HOST
```

Open `http://127.0.0.1:8787`. Do not expose the unauthenticated capture service
publicly. Local and remote services cannot occupy the same forwarded port.

## Video

Install `gpu-screen-recorder` on the gaming host, then list the capture targets and
audio sources it offers:

```sh
gpu-screen-recorder --list-monitors
gpu-screen-recorder --list-audio-devices
```

A typical play session, with the game on one monitor:

```sh
export CAPTURE_VIDEO=1
export VIDEO_TARGET=screen            # or a monitor name such as DP-1
export VIDEO_AUDIO_SOURCE=default_output
```

Do not point `VIDEO_AUDIO_SOURCE` at a microphone by accident. The ZIP includes the
video file itself, so keep at least twice the recording size free on disk.
A session has no time limit: it runs until STOP or until the storage ceiling.
YouTube streaming was removed: the server refuses to start when `YOUTUBE_KEY_FILE`
or `YOUTUBE_OAUTH_CONFIG` is set.

## Validation and recovery

Run the README checks before real capture. Then verify one named capture in the
actual browser, final flush, ZIP CRC, a playable `gameplay.mkv` and absence
of owned workers/Frida after Stop. Do not infer anti-cheat safety from mocked tests.

The server reclaims `CAPTURE_DATA/owner` only when the recorded PID is gone; check
owned workers and Frida before forcing anything else. See the web guide for recovery. Raw captures remain
private even when keylog files are excluded. Stop/delete paid cloud resources
separately when appropriate; this service does not manage billing or VM shutdown.
