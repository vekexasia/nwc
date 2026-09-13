#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export STEAM_DIR=${STEAM_DIR:-"$HOME/.local/share/Steam"}
export CAPTURE_PYTHON=${CAPTURE_PYTHON:-"$(cd "$here/../../.." && pwd)/.venv-capture/bin/python"}
node=$(command -v "${CAPTURE_NODE:-node}")
client="$STEAM_DIR/steamapps/common/SteamLinuxRuntime_4/pressure-vessel/bin/steam-runtime-launch-client"
# Enter Steam's official launch context, not a direct Proton launch over SSH.
settings=("STEAM_DIR=$STEAM_DIR" "CAPTURE_PYTHON=$CAPTURE_PYTHON")
if [[ ${CAPTURE_VIDEO:-} == 1 ]]; then
    # Resolved here: the launch context may not share this PATH.
    export VIDEO_RECORDER=${VIDEO_RECORDER:-$(command -v gpu-screen-recorder || true)}
    [[ -x ${VIDEO_RECORDER:-} ]] || { echo "CAPTURE_VIDEO=1 requires gpu-screen-recorder" >&2; exit 1; }
fi
for name in HOME DISPLAY WAYLAND_DISPLAY XDG_SESSION_TYPE XAUTHORITY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS PORT CAPTURE_SECONDS CAPTURE_DATA CAPTURE_VIDEO CAPTURE_EXPORT_RAW CAPTURE_STORAGE_GB VIDEO_RECORDER VIDEO_TARGET VIDEO_FPS VIDEO_BITRATE VIDEO_AUDIO_SOURCE PULSE_SERVER PULSE_COOKIE; do
    if [[ -v $name ]]; then settings+=("$name=${!name}"); fi
done
exec "$client" --alongside-steam -- env "${settings[@]}" "$node" "$here/server.ts"
