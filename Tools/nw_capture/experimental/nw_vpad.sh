#!/usr/bin/env sh
# Run nw_vpad.py with the repository virtualenv (python-evdev lives there, not in system python).
# usage: nw_vpad.sh --seq "forward:6,stop:3,forward:6" [--shot-prefix /tmp/nw_vpad]
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
exec "$repo/.venv-capture/bin/python" "$here/nw_vpad.py" "$@"
