# Local and remote play/capture setup

Run from the root of this repository. Do not run a second capture service against
an already owned game session. Setup is explicit; nothing here starts on boot.

## Dependencies

- Node >=22.18 for native TypeScript stripping; the tested workstation uses 26.7.0.
- Python 3 with venv/pip, or uv. Use a private environment, never system pip.
- Steam, New World (app 1063730), Proton 11.0 and SteamLinuxRuntime_4.
- Windows x64 Frida server **17.9.10**, matching the Python dependency.
- For the existing video backend: X11, FFmpeg with H.264 NVENC, a compatible
  NVIDIA driver, PulseAudio and libavformat/libavutil. It is not a native Wayland
  recorder and has no implicit software-encoder fallback.

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

The capture-only path can run under Omarchy/Proton. Do not assume that setting
`CAPTURE_VIDEO=1` on a Wayland session will record the correct full game window:
the current video implementation expects an actual X11 source.

## Remote play with Sunshine and Moonlight

Use an operator-provisioned GPU host, a dedicated non-root Steam user and a
working Xorg desktop. The previously tested host was Ubuntu 24.04, NVIDIA L4,
XFCE/LightDM, driver 580.173.02 and Sunshine v2025.924.154138. These are historical
tested versions, not an unconditional recommendation for every GPU or new host.

1. Install a supported NVIDIA graphics/NVENC driver, Xorg desktop, Steam and
   Sunshine from their official sources. Validate hardware rendering/encoding.
2. Configure a real/headless display at the desired size (tested: 1920x1080).
   Do not blindly copy PCI IDs or output names from another machine. On the
   tested L4, `UseDisplayDevice=none` failed with its virtual display subsystem.
3. Configure Sunshine's X11/NVENC backend and input permissions for the Steam user.
   Verify keyboard, mouse, moving video and audio through Moonlight.
4. Keep the Sunshine admin UI loopback-only and pair through an SSH tunnel:

   ```sh
   ssh -N -L 127.0.0.1:47990:127.0.0.1:47990 YOUR_GAMING_HOST
   ```

   Open `https://127.0.0.1:47990`, verify the tunneled endpoint, configure admin
   credentials yourself and enter Moonlight's pairing PIN. Do not publish 47990.
5. Restrict streaming ports to your client/VPN. The tested policy allowed TCP
   47984/47989/48010 and UDP 47998:48000; verify against your Sunshine version.
   Keep UPnP disabled, transport encryption enabled and X11 TCP disabled.
6. Start Steam on the remote desktop, complete authentication and launch the game.
   Capture runs on this gaming host, not on the Moonlight viewing computer.

The existing machine-specific setup and verification history is preserved in
[Streaming/new-world-capture.md](Streaming/new-world-capture.md). Its old paths,
IPs and service instructions describe that deployment; they are not portable
new-host defaults. This migration has not reconfigured that machine.

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

## Video and YouTube

On a supported X11/NVENC host, choose the actual gameplay audio monitor from
`pactl list short sources`; do not accidentally stream a microphone. Then set:

```sh
export CAPTURE_VIDEO=1
export VIDEO_SIZE=1920x1080
export VIDEO_AUDIO_SOURCE='YOUR_GAMEPLAY_MONITOR'
```

For automatic unlisted broadcasts, follow the complete
[OAuth guide](../Tools/nw_capture/web/YOUTUBE.md). Credentials stay in private host
configuration outside this repository. Set `YOUTUBE_KEY_FILE` and
`YOUTUBE_OAUTH_CONFIG` before starting the service. No Google browser is needed
while capturing. The ZIP includes the video link, not the video file.

## Validation and recovery

Run the README checks before real capture. Then verify one named capture in the
actual browser, final flush, ZIP CRC, YouTube closure (when enabled) and absence
of owned workers/Frida after Stop. Do not infer anti-cheat safety from mocked tests.

Never clear `CAPTURE_DATA/owner` without checking its PID, owned workers/Frida and
broadcast state. See the web and OAuth guides for recovery. Raw captures remain
private even when keylog files are excluded. Stop/delete paid cloud resources
separately when appropriate; this service does not manage billing or VM shutdown.
