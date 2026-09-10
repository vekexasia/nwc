#!/usr/bin/env sh
# Bash wrapper: hold keys in the focused game window with the repository virtualenv.
#   nw_vkeys.sh "w:6,release:2,w:6"
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
exec "$repo/.venv-capture/bin/python" "$here/nw_vkeys.py" --seq "${1:?usage: nw_vkeys.sh \"w:6,release:2,w:6\"}" ${2:+--shot-prefix "$2"}
