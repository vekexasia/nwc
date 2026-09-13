#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export STEAM_DIR=${STEAM_DIR:-"$HOME/.local/share/Steam"}
export CAPTURE_PYTHON=${CAPTURE_PYTHON:-"$(cd "$here/../../.." && pwd)/.venv-capture/bin/python"}
steam_pid=$(pgrep -x steam | head -1 || true)
[[ -n $steam_pid ]] || { echo "Steam is not running; start Steam and the game first" >&2; exit 1; }
# An SSH shell has no graphical session: take it from the Steam process that has one.
if [[ -z ${WAYLAND_DISPLAY:-}${DISPLAY:-} ]]; then
    while IFS= read -r -d '' entry; do
        case $entry in
            DISPLAY=*|WAYLAND_DISPLAY=*|XDG_SESSION_TYPE=*|XAUTHORITY=*|XDG_RUNTIME_DIR=*|DBUS_SESSION_BUS_ADDRESS=*) export "${entry?}" ;;
        esac
    done < "/proc/$steam_pid/environ"
fi
node=$(command -v "${CAPTURE_NODE:-node}" || true)
[[ -n $node ]] || { echo "node is not on PATH; install Node 22.18 or newer, or set CAPTURE_NODE" >&2; exit 1; }
client="$STEAM_DIR/steamapps/common/SteamLinuxRuntime_4/pressure-vessel/bin/steam-runtime-launch-client"
# Enter Steam's official launch context, not a direct Proton launch over SSH.
settings=("STEAM_DIR=$STEAM_DIR" "CAPTURE_PYTHON=$CAPTURE_PYTHON")
if [[ ${CAPTURE_VIDEO:-1} != 0 ]]; then
    # Resolved here: the launch context may not share this PATH.
    export VIDEO_RECORDER=${VIDEO_RECORDER:-$(command -v gpu-screen-recorder || true)}
    [[ -x ${VIDEO_RECORDER:-} ]] || { echo "video is on by default; install gpu-screen-recorder or set CAPTURE_VIDEO=0" >&2; exit 1; }
fi
for name in HOME DISPLAY WAYLAND_DISPLAY XDG_SESSION_TYPE XAUTHORITY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS PORT CAPTURE_SECONDS CAPTURE_DATA CAPTURE_VIDEO CAPTURE_EXPORT_RAW CAPTURE_STORAGE_GB VIDEO_RECORDER VIDEO_TARGET VIDEO_FPS VIDEO_BITRATE VIDEO_AUDIO_SOURCE PULSE_SERVER PULSE_COOKIE; do
    if [[ -v $name ]]; then settings+=("$name=${!name}"); fi
done
exec "$client" --alongside-steam -- env "${settings[@]}" "$node" "$here/server.ts"
