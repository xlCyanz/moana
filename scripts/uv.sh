#!/bin/sh
# Keep downloads and caches inside the checkout unless explicitly configured.
set -eu
MOANA_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export UV_CACHE_DIR="${UV_CACHE_DIR:-$MOANA_ROOT/.cache/uv}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$MOANA_ROOT/.tools/python}"
export UV_PYTHON_BIN_DIR="${UV_PYTHON_BIN_DIR:-$MOANA_ROOT/.tools/bin}"
if [ -x "$MOANA_ROOT/.tools/bootstrap/bin/uv" ]; then
    exec "$MOANA_ROOT/.tools/bootstrap/bin/uv" "$@"
fi
exec uv "$@"
