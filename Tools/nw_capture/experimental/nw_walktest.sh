#!/usr/bin/env sh
# Bash wrapper: run the walk test with the repository virtualenv.
#   nw_walktest.sh "forward:6,stop:3,forward:6" 40
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
exec "$repo/.venv-capture/bin/python" "$here/nw_walktest.py" --seq "${1:-forward:6,stop:3,forward:6}" --capture "${2:-40}"
