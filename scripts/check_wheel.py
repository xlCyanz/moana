"""Install the built wheel away from the checkout and verify its public surface.

The wheel goes into a fresh virtual environment with only the runtime dependencies
pinned by ``uv.lock`` (hash-checked, no development tools; offline from the uv cache
when possible, otherwise downloaded from the package index). The probe imports the
package, then the installed ``moana`` command validates the normative example and
exports it as a 128 x 128 PNG from a directory outside the repository whose paths
contain spaces (MOANA-012 AC1).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Support the documented direct invocation as well as python -m scripts.check_wheel.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate import ROOT, tool_environment, uv_executable

EXAMPLE = ROOT / "examples" / "specs" / "minimal.moana.json"
DECODE_PROBE = (
    "import sys; from PIL import Image; image = Image.open(sys.argv[1]); "
    "assert image.format == 'PNG' and image.mode == 'RGBA', image.mode; "
    "assert image.size == (128, 128), image.size; "
    "assert image.getpixel((40, 32)) == (0x36, 0xAF, 0xA5, 0xFF); "
    "assert image.getpixel((39, 32)) == (0, 0, 0, 0)"
)


CLI_TIMEOUT = 300
ISOLATION_VARIABLES = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTHONSTARTUP")


def isolated_environment() -> dict[str, str]:
    """Tool environment without variables that could import the checkout or another venv."""
    environment = tool_environment()
    for name in ISOLATION_VARIABLES:
        environment.pop(name, None)
    return environment


def run_cli(command: Path, arguments: list[str], cwd: Path) -> dict[str, object]:
    """Run the installed command and return its single JSON stdout object."""
    completed = subprocess.run(
        [str(command), *arguments],
        cwd=cwd,
        env=isolated_environment(),
        check=False,
        capture_output=True,
        encoding="utf-8",
        timeout=CLI_TIMEOUT,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"moana {arguments[0]} exited {completed.returncode}\n"
            f"--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}"
        )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise RuntimeError(f"moana {arguments[0]} did not succeed: {completed.stdout}")
    return payload


def check_cli(python: Path, root: Path) -> None:
    """AC1: the installed command validates the example and exports a 128 x 128 PNG."""
    scripts = python.parent
    command = scripts / ("moana.exe" if os.name == "nt" else "moana")
    if not command.is_file():
        raise RuntimeError("the wheel did not install the moana console script")
    work = root / "work dir"
    (work / "input files").mkdir(parents=True)
    (work / "output files").mkdir()
    document = Path("input files") / "mini sprite.moana.json"
    shutil.copyfile(EXAMPLE, work / document)
    output = Path("output files") / "mini sprite.png"
    validated = run_cli(command, ["validate", str(document)], work)
    exported = run_cli(command, ["export", str(document), str(output)], work)
    manifest = exported.get("export")
    size = (manifest.get("width"), manifest.get("height")) if isinstance(manifest, dict) else None
    if size != (128, 128):
        raise RuntimeError(f"export manifest is not a 128 x 128 PNG: {exported}")
    subprocess.run(
        [str(python), "-I", "-c", DECODE_PROBE, str(work / output)],
        env=isolated_environment(),
        check=True,
        timeout=CLI_TIMEOUT,
    )
    print("Installed CLI OK:", json.dumps(validated["document"], sort_keys=True))


def install_runtime_dependencies(uv: str, python: Path, requirements: Path) -> None:
    """Hash-checked install of the locked runtime dependencies, from the uv cache if possible.

    The offline attempt needs no network when ``uv sync`` already filled the cache; on a
    cold cache the same pinned, hashed set is downloaded from the package index.
    """
    install = [uv, "pip", "install", "--python", str(python), "--require-hashes"]
    install += ["-r", str(requirements)]
    offline = subprocess.run([*install, "--offline"], env=tool_environment(), check=False)
    if offline.returncode != 0:
        print(
            "Runtime dependencies are not all in the uv cache; retrying online "
            "(network access to the package index is required).",
            flush=True,
        )
        subprocess.run(install, env=tool_environment(), check=True)


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
        requirements = root / "runtime-requirements.txt"
        subprocess.run(
            [
                uv,
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                str(requirements),
            ],
            cwd=ROOT,
            env=tool_environment(),
            check=True,
            stdout=subprocess.DEVNULL,
        )
        install_runtime_dependencies(uv, python, requirements)
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
            "import moana.palette; assert moana.palette.Rgba.parse('#000000FF').a == 255; "
            "assert files('moana').joinpath('geometry/primitives.py').is_file(); "
            "assert files('moana').joinpath('geometry/fill.py').is_file(); "
            "assert files('moana').joinpath('geometry/__init__.py').is_file(); "
            "assert files('moana').joinpath('geometry/mask.py').is_file(); "
            "assert files('moana').joinpath('geometry/transform.py').is_file(); "
            "assert files('moana').joinpath('layers/__init__.py').is_file(); "
            "assert files('moana').joinpath('layers/nodes.py').is_file(); "
            "assert files('moana').joinpath('layers/composite.py').is_file(); "
            "assert files('moana').joinpath('render/pipeline.py').is_file(); "
            "assert files('moana').joinpath('render/result.py').is_file(); "
            "assert files('moana').joinpath('core/procedural.py').is_file(); "
            "assert files('moana').joinpath('core/digest.py').is_file(); "
            "assert files('moana').joinpath('export/__init__.py').is_file(); "
            "assert files('moana').joinpath('export/png.py').is_file(); "
            "assert files('moana').joinpath('export/atomic.py').is_file(); "
            "import moana.api, moana.cli; assert not hasattr(moana.api, 'apply_edit'); "
            "print('Isolated wheel OK:', moana.__version__)"
        )
        subprocess.run([str(python), "-I", "-c", probe], cwd=root, check=True)
        check_cli(python, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
