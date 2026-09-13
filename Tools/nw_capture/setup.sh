#!/usr/bin/env bash
# One-time host setup: private Python environment plus the matching Frida server.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
version=17.9.10
asset=frida-server-$version-windows-x86_64.exe.xz
digest=ff4c0c12b96a38e79cbe480392b0d1d8e1631e95644ed47472aec5874b701b95
cd "$root"
umask 077

[[ -x .venv-capture/bin/python ]] || python3 -m venv .venv-capture
.venv-capture/bin/python -m pip install --quiet --upgrade pip
.venv-capture/bin/python -m pip install --quiet -r Tools/nw_capture/requirements.txt
client=$(.venv-capture/bin/python -c 'import frida; print(frida.__version__)')
# Client and server speak the same protocol only at the same version.
[[ $client == "$version" ]] || { echo "frida client $client does not match server $version; update this script" >&2; exit 1; }

if [[ ! -f Tools/nw_capture/frida-server.exe ]]; then
    work=$(mktemp -d)
    trap 'rm -rf "$work"' EXIT
    # The Windows build: it is injected into NewWorld.exe inside the Proton prefix.
    curl -fsSL -o "$work/$asset" "https://github.com/frida/frida/releases/download/$version/$asset"
    echo "$digest  $work/$asset" | sha256sum -c -
    unxz "$work/$asset"
    mv "$work/${asset%.xz}" Tools/nw_capture/frida-server.exe
    chmod 600 Tools/nw_capture/frida-server.exe
fi

echo "frida client and server: $version"
node --version 2>/dev/null | sed 's/^/node: /' || echo 'node: MISSING, 22.18 or newer is required'
command -v gpu-screen-recorder >/dev/null || echo 'gpu-screen-recorder: MISSING, required for CAPTURE_VIDEO=1'
ls "$HOME/.local/share/Steam/steamapps/common/SteamLinuxRuntime_4/run" >/dev/null 2>&1 \
    || echo 'SteamLinuxRuntime_4: MISSING, install it through Steam'
echo 'Setup complete. Start a session with: bash Tools/nw_capture/web/run.sh'
