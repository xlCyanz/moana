"""Install the built wheel away from the checkout and verify its public surface."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Support the documented direct invocation as well as python -m scripts.check_wheel.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate import ROOT, tool_environment, uv_executable


def main() -> int:
    wheels = sorted((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(
            "Expected exactly one wheel in dist; build first and remove stale outputs"
        )
    with tempfile.TemporaryDirectory(prefix="moana-wheel-") as temporary:
        root = Path(temporary)
        venv = root / "venv"
        uv = uv_executable()
        subprocess.run(
            [uv, "venv", str(venv), "--python", sys.executable],
            env=tool_environment(),
            check=True,
        )
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [uv, "pip", "install", "--python", str(python), "--no-deps", str(wheels[0])],
            env=tool_environment(),
            check=True,
        )
        probe = (
            "import moana, moana.core; from importlib.metadata import version; "
            "from importlib.resources import files; "
            "assert version('moana-pixel-engine') == moana.__version__; "
            "assert files('moana').joinpath('py.typed').is_file(); "
            "assert moana.core.Box(0, 0, 1, 1).area == 1; "
            "assert files('moana').joinpath('schema/models.py').is_file(); "
            "assert files('moana').joinpath('render/budget.py').is_file(); "
            "assert files('moana').joinpath('core/canvas.py').is_file(); "
            "assert files('moana').joinpath('core/pillow_adapter.py').is_file(); "
            "print('Isolated wheel OK:', moana.__version__)"
        )
        subprocess.run([str(python), "-I", "-c", probe], cwd=root, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
