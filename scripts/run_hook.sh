#!/bin/sh
# Git provides sh on Windows too; select the checkout venv without PATH assumptions.
set -eu
MOANART_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -x "$MOANART_ROOT/.venv/bin/python" ]; then
    exec "$MOANART_ROOT/.venv/bin/python" -m "$@"
elif [ -x "$MOANART_ROOT/.venv/Scripts/python.exe" ]; then
    exec "$MOANART_ROOT/.venv/Scripts/python.exe" -m "$@"
fi
echo "MoanArt: run uv sync --locked before committing." >&2
exit 1
