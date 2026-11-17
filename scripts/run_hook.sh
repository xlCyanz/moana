#!/bin/sh
# Git provides sh on Windows too; select the checkout venv without PATH assumptions.
set -eu
MOANA_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -x "$MOANA_ROOT/.venv/bin/python" ]; then
    exec "$MOANA_ROOT/.venv/bin/python" -m "$@"
elif [ -x "$MOANA_ROOT/.venv/Scripts/python.exe" ]; then
    exec "$MOANA_ROOT/.venv/Scripts/python.exe" -m "$@"
fi
echo "Moana: run uv sync --locked before committing." >&2
exit 1
