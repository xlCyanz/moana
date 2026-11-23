"""Install the built wheel and sdist away from the checkout and verify their surface.

``uv build`` (run by ``scripts/validate.py``) leaves exactly one sdist and one wheel in
``dist/``, the wheel built from the sdist. Both are audited first (MOANA-035): the sdist
must hold the licence, the metadata (``License-Expression: MIT``) and the sources, and
none of the environment, cache, output, worktree or secret paths; the wheel must carry
the licence file and expression and nothing outside the package. Each artifact then goes
into its own fresh virtual environment with only the runtime dependencies pinned by
``uv.lock`` (hash-checked, no development tools; offline from the uv cache when
possible, otherwise downloaded from the package index); the sdist is built in isolation
with the build backend pinned by the lock. In each environment the probe imports the
package, then the installed ``moanart`` command validates the normative example and
exports it as a 128 x 128 PNG from a directory outside the repository whose paths
contain spaces (MOANA-012 AC1). It then runs the ``sh`` blocks of
``docs/guides/ai-workflows.md`` in order through :mod:`scripts.tutorial` with the
installed ``moanart`` and the venv interpreter in isolated mode, checking every
documented exit code and the recolored pixels (MOANA-033 T1), and
:mod:`scripts.install_smoke` migrates a legacy copy with the original preserved and
renders a copy of the corpus against its pinned digests (MOANA-035 T1). The wheel run
copies these inputs (examples, guide and smoke script) from the checkout; the sdist run
copies them from the extracted sdist itself, which proves the sdist ships them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Final

# Support the documented direct invocation as well as python -m scripts.check_wheel.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.legacy_name import legacy_name_errors
from scripts.tutorial import INPUTS, check_outputs, command_runner, parse_steps, run_steps
from scripts.validate import ROOT, tool_environment, uv_executable

EXAMPLE: Final = "examples/specs/minimal.moanart.json"
EDIT_EXAMPLE: Final = "examples/specs/recolor.edit.json"
SMOKE: Final = "scripts/install_smoke.py"
CORPUS: Final = "examples/corpus"
GUIDE: Final = "docs/guides/ai-workflows.md"
"""Inputs read relative to a *source* tree: the checkout for the wheel, and the
extracted sdist for the sdist, which proves the sdist ships them."""
DECODE_PROBE = (
    "import sys; from PIL import Image; image = Image.open(sys.argv[1]); "
    "assert image.format == 'PNG' and image.mode == 'RGBA', image.mode; "
    "assert image.size == (128, 128), image.size; "
    "assert image.getpixel((40, 32)) == (0x36, 0xAF, 0xA5, 0xFF); "
    "assert image.getpixel((39, 32)) == (0, 0, 0, 0)"
)
PACKAGE_FILES: Final = (
    "py.typed",
    "schema/models.py",
    "schema/migrations.py",
    "render/budget.py",
    "core/canvas.py",
    "core/pillow_adapter.py",
    "geometry/primitives.py",
    "geometry/fill.py",
    "geometry/__init__.py",
    "geometry/mask.py",
    "geometry/transform.py",
    "layers/__init__.py",
    "layers/nodes.py",
    "layers/composite.py",
    "render/pipeline.py",
    "render/result.py",
    "core/procedural.py",
    "core/digest.py",
    "export/__init__.py",
    "export/png.py",
    "export/atomic.py",
    "editing/apply.py",
    "project/migrate.py",
)
"""Installed package files the probe requires (layout regressions of the build)."""

SDIST_FORBIDDEN_DIRECTORIES: Final = frozenset(
    {
        ".venv",
        ".tools",
        ".cache",
        "." + "git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        "__pycache__",
        "artifacts",
        "dist",
        "build",
        "htmlcov",
        "worktrees",
        "node_modules",
    }
)
"""Directory names that never belong in the sdist (environments, caches, outputs)."""
SDIST_FORBIDDEN_NAMES: Final = frozenset(
    {".DS_Store", "settings.local.json", "coverage.xml", ".coverage", ".netrc", ".pypirc"}
)
SDIST_FORBIDDEN_SUFFIXES: Final = (".pyc", ".pyo", ".pem", ".key", ".whl", ".tar.gz")
SDIST_REQUIRED: Final = (
    "PKG-INFO",
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "uv.lock",
    "src/moanart/__init__.py",
    "src/moanart/py.typed",
    "schemas/moanart-document-1.0.schema.json",
    "docs/RELEASE.md",
    EXAMPLE,
    EDIT_EXAMPLE,
    SMOKE,
    GUIDE,
    *INPUTS,
)
LICENSE_EXPRESSION: Final = "License-Expression: MIT"

CLI_TIMEOUT = 300
ISOLATION_VARIABLES = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTHONSTARTUP")


def isolated_environment() -> dict[str, str]:
    """Tool environment without variables that could import the checkout or another venv."""
    environment = tool_environment()
    for name in ISOLATION_VARIABLES:
        environment.pop(name, None)
    return environment


def run_cli(
    command: Path, arguments: list[str], cwd: Path, *, exit_code: int = 0
) -> dict[str, object]:
    """Run the installed command, check its exit code and return its JSON stdout object."""
    completed = subprocess.run(
        [str(command), *arguments],
        cwd=cwd,
        env=isolated_environment(),
        check=False,
        capture_output=True,
        encoding="utf-8",
        timeout=CLI_TIMEOUT,
    )
    if completed.returncode != exit_code:
        raise RuntimeError(
            f"moanart {arguments[0]} exited {completed.returncode}\n"
            f"--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}"
        )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict) or payload.get("ok") is not (exit_code == 0):
        ok = payload.get("ok") if isinstance(payload, dict) else None
        raise RuntimeError(
            f"moanart {arguments[0]}: unexpected ok={ok} (expected exit {exit_code}): "
            f"{completed.stdout}"
        )
    return payload


def check_cli(python: Path, root: Path, source: Path) -> None:
    """AC1: the installed command validates the example and exports a 128 x 128 PNG."""
    scripts = python.parent
    command = scripts / ("moanart.exe" if os.name == "nt" else "moanart")
    if not command.is_file():
        raise RuntimeError("the installation did not provide the moanart console script")
    work = root / "work dir"
    (work / "input files").mkdir(parents=True)
    (work / "output files").mkdir()
    document = Path("input files") / "mini sprite.moanart.json"
    shutil.copyfile(source / EXAMPLE, work / document)
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
    batch = Path("input files") / "recolor edit.json"
    shutil.copyfile(source / EDIT_EXAMPLE, work / batch)
    edited = run_cli(command, ["edit", str(document), str(batch)], work)
    summary = edited.get("edit")
    if not isinstance(summary, dict) or summary.get("revision") != 1:
        raise RuntimeError(f"edit did not produce revision 1: {edited}")
    print("Installed CLI OK:", json.dumps(validated["document"], sort_keys=True))
    check_tutorial(python, command, root, source)


def check_tutorial(python: Path, command: Path, root: Path, source: Path) -> None:
    """MOANA-033 T1: the guide's commands work with the installed package only."""
    work = root / "tutorial work"
    for name in INPUTS:  # the files the guide reads, at their repository paths
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    environment = isolated_environment()
    outcomes = run_steps(
        parse_steps((source / GUIDE).read_text(encoding="utf-8")),
        work,
        moanart=command_runner([str(command)], environment),
        python=[str(python), "-I"],
        environment=environment,
    )
    check_outputs(work)
    flow = next(outcome for outcome in outcomes if "potion_flow.py" in outcome.step.line)
    print(f"Installed tutorial OK: {len(outcomes)} documented steps;", flow.stdout.strip())


def check_smoke(python: Path, root: Path, source: Path) -> None:
    """MOANA-035 T1: migrations and corpus from copies, with the installed package only."""
    work = root / "migration work"
    work.mkdir()
    document = work / "current sprite.moanart.json"
    shutil.copyfile(source / EXAMPLE, document)
    corpus = root / "corpus copy"
    shutil.copytree(source / CORPUS, corpus)
    for arguments in (["migrations", str(work), str(document)], ["corpus", str(corpus)]):
        subprocess.run(
            [str(python), "-I", str(source / SMOKE), *arguments],
            cwd=root,
            env=isolated_environment(),
            check=True,
            timeout=CLI_TIMEOUT,
        )


def sdist_member_errors(name: str) -> list[str]:
    """Why one sdist member (path relative to the sdist root) must not be shipped."""
    path = PurePosixPath(name)
    errors = []
    if path.is_absolute() or ".." in path.parts:
        errors.append(f"unsafe sdist path: {name}")
    if SDIST_FORBIDDEN_DIRECTORIES.intersection(path.parts[:-1]):
        errors.append(f"environment, cache or output directory in sdist: {name}")
    file = path.name
    if file in SDIST_FORBIDDEN_NAMES or file.endswith(SDIST_FORBIDDEN_SUFFIXES):
        errors.append(f"forbidden file in sdist: {name}")
    if file.startswith(".env") and file != ".env.example":
        errors.append(f"environment file in sdist: {name}")
    return errors


def audit_sdist(sdist: Path) -> list[str]:
    """Errors of the sdist contents: forbidden members, missing files, licence metadata
    and occurrences of the old name outside the audited exceptions (ADR-041)."""
    with tarfile.open(sdist, "r:gz") as archive:
        members = archive.getmembers()
        roots = {PurePosixPath(member.name).parts[0] for member in members}
        if len(roots) != 1:
            return [f"sdist must have one top-level directory, found {sorted(roots)}"]
        (prefix,) = roots
        inside = {
            PurePosixPath(*PurePosixPath(member.name).parts[1:]).as_posix(): member
            for member in members
            if len(PurePosixPath(member.name).parts) > 1
        }
        errors = [error for name in sorted(inside) for error in sdist_member_errors(name)]
        errors.extend(
            f"sdist member is a link: {name}"
            for name, member in sorted(inside.items())
            if member.issym() or member.islnk()
        )
        errors.extend(
            f"missing from sdist: {name}" for name in SDIST_REQUIRED if name not in inside
        )
        if "PKG-INFO" in inside:
            stream = archive.extractfile(f"{prefix}/PKG-INFO")
            metadata = stream.read().decode("utf-8") if stream is not None else ""
            if LICENSE_EXPRESSION not in metadata.splitlines():
                errors.append(f"sdist PKG-INFO lacks {LICENSE_EXPRESSION!r}")
        files: dict[str, bytes] = {}
        for name, member in inside.items():
            stream = archive.extractfile(member) if member.isfile() else None
            if stream is not None:
                files[name] = stream.read()
        errors.extend(f"sdist: {error}" for error in legacy_name_errors(files))
        errors.extend(f"sdist: {error}" for error in legacy_name_errors({prefix: b""}))
    return errors


def audit_wheel(wheel: Path) -> list[str]:
    """Errors of the wheel licence metadata (PEP 639), members outside the package and
    occurrences of the old name outside the audited exceptions (ADR-041)."""
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_name = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        if metadata_name is None:
            return ["wheel has no METADATA"]
        metadata = archive.read(metadata_name).decode("utf-8")
        # Package files are matched against the exceptions by their repository path.
        files = {
            (f"src/{name}" if name.startswith("moanart/") else name): archive.read(name)
            for name in names
            if not name.endswith("/")
        }
    errors = [f"wheel: {error}" for error in legacy_name_errors(files)]
    if LICENSE_EXPRESSION not in metadata.splitlines():
        errors.append(f"wheel METADATA lacks {LICENSE_EXPRESSION!r}")
    if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
        errors.append("wheel does not carry dist-info/licenses/LICENSE")
    errors.extend(
        f"unexpected wheel member: {name}"
        for name in names
        if not name.startswith(("moanart/", "moanart-"))
    )
    return errors


def built_artifacts(dist: Path) -> tuple[Path, Path]:
    """The single wheel and the single sdist of ``dist``."""
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError(
            "Expected exactly one wheel and one sdist in dist; run `uv build` "
            "(or scripts/validate.py) and remove stale outputs"
        )
    return wheels[0], sdists[0]


def install_cache_first(command: list[str], what: str) -> None:
    """Run a ``uv pip install`` offline from the uv cache, online only if it must.

    The offline attempt needs no network when ``uv sync`` already filled the cache; on a
    cold cache the same pinned set is downloaded from the package index.
    """
    offline = subprocess.run([*command, "--offline"], env=tool_environment(), check=False)
    if offline.returncode != 0:
        print(
            f"{what} not all in the uv cache; retrying online "
            "(network access to the package index is required).",
            flush=True,
        )
        subprocess.run(command, env=tool_environment(), check=True)


def export_lock(uv: str, destination: Path, *, build: bool = False) -> Path:
    """Write requirements pinned by ``uv.lock``: hashed runtime set, or build constraints.

    The build constraints are the pinned ``dev`` group, which holds the build backend
    (``hatchling``) and its dependencies; constraints never install anything by
    themselves.
    """
    selection = ["--only-group", "dev", "--no-hashes"] if build else ["--no-dev"]
    subprocess.run(
        [
            uv,
            "export",
            "--frozen",
            *selection,
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--output-file",
            str(destination),
        ],
        cwd=ROOT,
        env=tool_environment(),
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return destination


def probe(python: Path, cwd: Path, label: str) -> None:
    """Import the installed package and check its metadata and public files."""
    code = (
        "import sys, moanart, moanart.core; from importlib.metadata import metadata, version; "
        "from importlib.resources import files; "
        "assert version('moanart') == moanart.__version__; "
        "assert metadata('moanart')['License-Expression'] == 'MIT'; "
        "assert moanart.core.Box(0, 0, 1, 1).area == 1; "
        "import moanart.palette; assert moanart.palette.Rgba.parse('#000000FF').a == 255; "
        "missing = [p for p in sys.argv[1:] if not files('moanart').joinpath(p).is_file()]; "
        "assert not missing, missing; "
        "import moanart.api, moanart.cli; assert callable(moanart.api.apply_edit); "
        f"print('Isolated {label} OK:', moanart.__version__)"
    )
    subprocess.run([str(python), "-I", "-c", code, *PACKAGE_FILES], cwd=cwd, check=True)


def extract_sdist(sdist: Path, destination: Path) -> Path:
    """Extract an audited sdist with the ``data`` filter; return its top-level directory."""
    with tarfile.open(sdist, "r:gz") as archive:
        archive.extractall(destination, filter="data")
    (top,) = destination.iterdir()
    return top


def check_installation(
    uv: str,
    label: str,
    artifact: Path,
    root: Path,
    requirements: tuple[Path, Path],
    source: Path,
) -> None:
    """Install one artifact in a fresh venv and run every installed-package check.

    ``requirements`` are the hashed runtime set and the build constraints; ``source``
    is the tree the example inputs are copied from.
    """
    runtime, build = requirements
    root.mkdir(exist_ok=True)
    venv = root / "venv"
    subprocess.run(
        [uv, "venv", str(venv), "--python", sys.executable], env=tool_environment(), check=True
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    install = [uv, "pip", "install", "--python", str(python)]
    install_cache_first(
        [*install, "--require-hashes", "-r", str(runtime)], "Runtime dependencies are"
    )
    install_cache_first(
        [*install, "--no-deps", "--build-constraints", str(build), str(artifact)],
        f"Build dependencies of the {label} are",
    )
    probe(python, root, label)
    check_cli(python, root, source)
    check_smoke(python, root, source)


def main() -> int:
    wheel, sdist = built_artifacts(ROOT / "dist")
    errors = audit_sdist(sdist) + audit_wheel(wheel)
    if errors:
        raise RuntimeError("Artifact audit failed:\n" + "\n".join(errors))
    print(f"Artifact audit OK: {sdist.name}, {wheel.name}", flush=True)
    uv = uv_executable()
    with tempfile.TemporaryDirectory(prefix="moanart-wheel-") as temporary:
        root = Path(temporary)
        runtime = export_lock(uv, root / "runtime-requirements.txt")
        build = export_lock(uv, root / "build-constraints.txt", build=True)
        requirements = (runtime, build)
        check_installation(uv, "wheel", wheel, root / "wheel", requirements, ROOT)
        (root / "sdist").mkdir()
        unpacked = extract_sdist(sdist, root / "sdist" / "unpacked")
        check_installation(uv, "sdist", sdist, root / "sdist", requirements, unpacked)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
