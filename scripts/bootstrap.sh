#!/bin/sh
# Installs project-local tools only. Run with: sh scripts/bootstrap.sh
set -eu
MOANA_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$MOANA_ROOT"
if ! command -v uv >/dev/null 2>&1 && [ ! -x .tools/bootstrap/bin/uv ]; then
    "${MOANA_BOOTSTRAP_PYTHON:-python3}" -m venv .tools/bootstrap
    .tools/bootstrap/bin/python -m pip install --no-cache-dir "uv==$(cat .uv-version)"
fi
sh scripts/uv.sh python install "$(cat .python-version)"
sh scripts/uv.sh sync --locked
sh scripts/uv.sh run python scripts/validate.py
