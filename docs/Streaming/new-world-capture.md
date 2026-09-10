# New World streaming host

## Host and access

- Scaleway `new-world-capture`, `YOUR_GAMING_HOST`, Ubuntu 24.04, NVIDIA L4.
- SSH host key accepted by the operator via TOFU; the fingerprint is kept in the local, uncommitted `.env`.
- Reuse the authenticated master. Hardware-backed private keys remain local.

```sh
ssh -S ~/.ssh/new-world-control -o BatchMode=yes root@YOUR_GAMING_HOST 'hostname'
```

No automatic shutdown is configured. The running VM continues to incur charges.

## Installed configuration

Parsec only advertises hosting on Windows/macOS, so this host uses Sunshine and the existing local Moonlight client.

- XFCE/Xorg and LightDM autologin as `gamer`, a password-locked account without sudo.
- NVIDIA Ubuntu `580-server` graphics, encoding and i386 libraries. Installing the missing graphics stack updated the driver to `580.173.02`; kernel modules were reloaded without rebooting or dropping the SSH master.
- Sunshine official Ubuntu 24.04 package, release `v2025.924.154138`, verified working with this driver. The latest documentation lists a newer CUDA/driver requirement; this setup pins the tested release rather than changing driver branches.
- Steam from Ubuntu `steam-installer`, then Valve's client bootstrap/update.
- PulseAudio: Sunshine currently captures `sink-sunshine-stereo.monitor`. The earlier `audio_sink = game_audio` override broke live audio and was removed from Sunshine and the provisioning script; do not restore it.
- `uinput` and `uhid` available to `gamer` through the `input` group. `linux-modules-extra-6.8.0-106-generic` supplies UHID.

Provisioning commands and configuration are retained on the VM in `/root/new-world-install.sh` and `/root/new-world-configure.sh`. Install logs: `/var/log/new-world-install.log` and `/var/log/new-world-input-install.log`. The configuration script is for initial provisioning and overwrites the listed configuration files.

Key configuration files:

- `/etc/X11/xorg.conf.d/20-nvidia-headless.conf`: NVIDIA device `PCI:1:0:0`, `AllowEmptyInitialConfiguration`, 24-bit screen with virtual size 1920x1080. Do not set `UseDisplayDevice=none`: the L4 driver rejects it with its virtual display subsystem.
- `/etc/lightdm/lightdm.conf.d/50-gaming.conf`: autologin user `gamer`, session `xfce`, X server `-nolisten tcp`.
- `/home/gamer/.config/autostart/gaming-stream.desktop`: selects `DVI-D-0` at 1920x1080/60 Hz, disables X blanking/DPMS, imports `DISPLAY` and `XAUTHORITY` into the user manager, starts `sunshine.service`.
- `/home/gamer/.config/autostart/steam.desktop`: starts Steam.
- `/home/gamer/.config/pulse/default.pa`: includes the system default, loads `module-null-sink sink_name=game_audio rate=48000 channels=2`, sets it as default.
- `/home/gamer/.config/sunshine/apps.json`: Desktop and Steam Big Picture only; the shipped example for a nonexistent HDMI output was removed.

`/home/gamer/.config/sunshine/sunshine.conf`:

```ini
sunshine_name = new-world-capture
origin_web_ui_allowed = pc
upnp = disabled
capture = x11
encoder = nvenc
wan_encryption_mode = 2
lan_encryption_mode = 2
```

UFW is enabled, allowing SSH, and allowing TCP 47984/47989/48010 plus UDP 47998:48000 only from the observed client public IPv4 `YOUR_CLIENT_IP`. If that IP changes, update those source restrictions over SSH. Port 47990 is not allowed publicly, including over IPv6. Sunshine also restricts its admin UI to localhost. No public X11, VNC or RDP service is configured.

## Human gates

The admin tunnel was installed into the existing SSH master, listening only on local loopback. If it is absent, restore it with:

```sh
ssh -S ~/.ssh/new-world-control -o BatchMode=yes \
  -O forward -L 127.0.0.1:47990:127.0.0.1:47990 root@YOUR_GAMING_HOST
```

1. Open `https://127.0.0.1:47990`, accept Sunshine's self-signed certificate warning for this tunneled endpoint, and create the Sunshine admin username/password yourself. Do not send credentials to the agent.
2. Open the existing Moonlight client, add `YOUR_GAMING_HOST`, and select the host. Enter Moonlight's pairing PIN in Sunshine's **PIN** page yourself.
3. Start **Desktop**, initially at 1080p/60, SDR, H.264, around 20 Mbps. Verify moving video, keyboard, mouse and sound.
4. Open Steam on the streamed desktop and complete login/Steam Guard yourself. Install New World from the library. Configure Steam Play/Proton as needed for the Windows game, then launch it and verify the actual game session. Neither the game nor Proton has been downloaded in this setup stage.

Do not infer game compatibility, anti-cheat acceptance or playability from the streaming host tests.

## Initial provisioning checks on 2026-09-10 (historical)

- NVIDIA L4, driver `580.173.02`, OpenGL 4.6 hardware rendering, Vulkan device API 1.4.312.
- Actual XFCE desktop inspected before Steam login. `DVI-D-0` runs at 1920x1080, 60.01 Hz.
- LightDM and Sunshine return to active after restarting the desktop session, with the correct resolution. Full VM reboot was not tested.
- Sunshine initializes H.264, HEVC and AV1 NVENC encoders. An independent three-second X11-to-H.264 NVENC test encoded 180 frames, with timestamp warnings in the null muxer; this verifies encoding, not smooth frame pacing or a network stream.
- Synthetic audio played into `game_audio` and captured from its monitor with nonzero measured levels. Client audio has not been tested.
- `gamer` can write `/dev/uinput` and `/dev/uhid`; streamed input has not been tested.
- Steam client `1788652215` downloaded, installed, verified and started. The `Sign in to Steam` window was mapped and verified visible without capturing the login screen. No Steam account login performed.
- Admin tunnel returns HTTP 200; public 47990 and 6000 connection attempts time out. Streaming TCP ports are reachable from the allowed client address. UDP media traffic still requires a real paired stream test.
- No pairing, streamed video/input, New World installation or game launch completed.

## Cloud capture smoke test, 2026-09-10 07:07 UTC

This later check supersedes the initial login/install gates above: Steam was
logged in, Moonlight paired, and New World already running. No restart or input
automation was used. Sources only plus Windows x64 Frida server 17.9.10 were
deployed to `/home/gamer/Aeternum-World/Tools/nw_capture`, owned by `gamer`.
Private `.venv-capture` contains `frida==17.9.10` and `lz4==4.4.5`. Ubuntu's
ensurepip was unavailable; created the venv with `python3 -m venv --without-pip`
and installed with `python3 -m pip --python <venv> install ...`, not system pip.

`capture_proton.py` now accepts `--steam-dir` and `--timeout`. Proton 11.0 and
SteamLinuxRuntime_4 remain required. Direct runtime startup over SSH failed
Ubuntu's AppArmor user-namespace policy. Use Steam's existing official launch
service instead; no AppArmor/sysctl/security configuration was changed.
Windows server `--version` returned 17.9.10 through this service.

Tested command inside the SSH session (redirect all output privately; it can
contain tokens, plaintext and keys). Check port 27943 and absence of another
Frida server first. Do not use `--launch` with the game open:

```sh
cd /home/gamer/Aeternum-World
umask 077
runuser -u gamer -- env HOME=/home/gamer XDG_RUNTIME_DIR=/run/user/1001 \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus \
  /home/gamer/.steam/debian-installation/steamapps/common/SteamLinuxRuntime_4/pressure-vessel/bin/steam-runtime-launch-client \
  --alongside-steam -- env HOME=/home/gamer DISPLAY=:0 \
  XAUTHORITY=/home/gamer/.Xauthority XDG_RUNTIME_DIR=/run/user/1001 \
  timeout --signal=INT --kill-after=15s 180s \
  /home/gamer/Aeternum-World/.venv-capture/bin/python -B \
  Tools/nw_capture/capture_proton.py \
  --steam-dir /home/gamer/.steam/debian-installation --timeout 120 \
  > smoke-console.log 2>&1
```

The 120-second runner timeout stops producers, flushes, unloads and detaches.
The outer deadline is a watchdog, not proof of graceful cleanup if it fires:
then treat the capture as incomplete and check/remove only its Frida server.
It did not fire in this test; exit was 0 and port 27943 was closed afterward.

Evidence for session `proton_20260910_070734`:

- Sink interval 07:07:36.624 to 07:09:38.446 UTC, final flush acknowledged,
  sink writes successful, no error events. Three fixed DTLS hook checks passed.
- Game ledger: 1,229,813 bytes, 4,739 batches, 9,999 structurally valid records
  (7,432 incoming, 2,567 outgoing), exact EOF and final count agreement.
  Offline decoder reports 0 errors and 19,984 messages, but 9,625 records have
  trailing bytes: full gameplay protocol decoding is NOT validated.
- HTTPS: 2 closed requests with known hosts and HTTP 304 response headers;
  no response bodies, consistent with 304 semantics. Response-body capture
  remains untested. WinHTTP reports 10 hooks armed, but its nominal count includes
  unavailable `WinHttpReadDataEx` (one trace, not an error). Authentication bootstrap was
  not captured; late attachment also produced 0 keylog lines. A fresh auth
  capture requires operator approval before restarting the game.
- Six session files, five nonempty, JSON parsed successfully. Empty keylog is
  expected for this late attach, not evidence of key capture.
- Local existing regression suite before/after changes: 15 tests, one decoder
  subcheck skipped because local lz4 is absent. Node agent tests and all three
  JS syntax checks passed. Live offline decoding used remote isolated lz4.
- Private archive copied over the existing SSH master to
  `Tools/nw_capture/captures/cloud-smoke-20260910/cloud-smoke-20260910.tar`,
  gitignored, mode 0600 in a 0700 directory. SHA-256 matched remotely; all 14
  archive members have private permissions. Includes session and raw logs;
  never publish it. Remote archive and originals retained privately.
- Game PID 41097, Steam 37253 and Sunshine 37725 unchanged; Sunshine active,
  monitor `sink-sunshine-stereo.monitor` RUNNING and source outputs unmuted.
  No capturer or Frida server remains. Actual client playback was not inspected
  during this test; this does not prove anti-cheat safety or long-run stability.
  Local desktop completion notification sent. VM remains running and billable.

## Official references

- https://parsec.app/downloads
- https://docs.lizardbyte.dev/projects/sunshine/latest/md_docs_2getting__started.html
- https://github.com/LizardByte/Sunshine/releases/tag/v2025.924.154138
- https://github.com/LizardByte/Sunshine/blob/v2025.924.154138/docs/configuration.md
