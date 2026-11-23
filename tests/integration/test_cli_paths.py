"""CLI in a fresh process, outside the repository, with spaces in paths (MOANA-012 T1).

The working directory is a temporary directory (never the checkout) and the document
and PNG names contain spaces and non-ASCII letters, passed both relative to that
directory and absolute. The installed ``moanart`` console script and ``python -m
moanart.cli`` must behave the same. The PNG is decoded with Pillow independently and
compared with the hand oracle of the minimal example (``[40, 32, 88, 104)`` in
#36AFA5FF on transparent).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "specs" / "minimal.moanart.json"
SCRIPT = Path(sysconfig.get_path("scripts")) / ("moanart.exe" if os.name == "nt" else "moanart")


def launchers() -> list[list[str]]:
    found = [[sys.executable, "-m", "moanart.cli"]]
    if SCRIPT.is_file():
        found.append([str(SCRIPT)])
    return found


def run(launcher: list[str], cwd: Path, *arguments: str) -> tuple[int, dict[str, Any], str]:
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [*launcher, *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )
    assert "Traceback" not in completed.stderr
    return completed.returncode, json.loads(completed.stdout), completed.stderr


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    work = tmp_path / "carpeta de trabajo"
    (work / "mis documentos").mkdir(parents=True)
    (work / "salida png").mkdir()
    shutil.copyfile(EXAMPLE, work / "mis documentos" / "sprite mínimo.moanart.json")
    assert ROOT not in work.resolve().parents
    return work


def test_console_script_is_installed() -> None:
    assert SCRIPT.is_file(), "run uv sync so the moanart entry point exists"


@pytest.mark.parametrize("launcher", launchers(), ids=lambda launcher: Path(launcher[-1]).name)
def test_cli_outside_the_repository_with_spaces(launcher: list[str], workspace: Path) -> None:
    relative = os.path.join("mis documentos", "sprite mínimo.moanart.json")
    absolute = str(workspace / relative)
    for document in (relative, absolute):
        status, payload, _ = run(launcher, workspace, "validate", document)
        assert (status, payload["ok"], payload["document"]["width"]) == (0, True, 128)
        status, payload, _ = run(launcher, workspace, "inspect", document)
        assert (status, payload["document"]["layers"][0]["id"]) == (0, "body")
        status, payload, _ = run(launcher, workspace, "render", document)
        assert (status, payload["render"]["height"]) == (0, 128)

    output = os.path.join("salida png", "sprite final ñ.png")
    status, payload, _ = run(launcher, workspace, "export", relative, output)
    assert status == 0
    manifest = payload["export"]
    assert (manifest["path"], manifest["width"], manifest["height"]) == (output, 128, 128)
    with Image.open(workspace / output) as image:
        assert (image.format, image.mode, image.size) == ("PNG", "RGBA", (128, 128))
        for x, y in [(40, 32), (87, 103), (39, 32), (88, 103), (40, 104)]:
            inside = 40 <= x < 88 and 32 <= y < 104
            assert image.getpixel((x, y)) == ((0x36, 0xAF, 0xA5, 0xFF) if inside else (0, 0, 0, 0))

    first = (workspace / output).read_bytes()
    status, payload, stderr = run(launcher, workspace, "export", absolute, output)
    assert (status, payload["error"]["code"]) == (5, "EXPORT_ERROR")
    assert (workspace / output).read_bytes() == first
    assert str(workspace) not in json.dumps(payload["error"]) + stderr

    status, payload, _ = run(launcher, workspace, "export", absolute, str(workspace / output))
    assert status == 5
    status, payload, _ = run(
        launcher, workspace, "export", absolute, str(workspace / output), "--overwrite"
    )
    assert status == 0
    assert manifest["file_sha256"] == payload["export"]["file_sha256"]


@pytest.mark.parametrize("launcher", launchers(), ids=lambda launcher: Path(launcher[-1]).name)
def test_cli_failures_in_a_fresh_process(launcher: list[str], workspace: Path) -> None:
    status, payload, stderr = run(launcher, workspace, "validate", "no existe.moanart.json")
    assert (status, payload["error"]["code"]) == (5, "READ_ERROR")
    assert payload["error"]["context"]["file_name"] == "no existe.moanart.json"
    assert stderr.startswith("moanart: error: READ_ERROR")
    status, payload, _ = run(launcher, workspace, "edit", "a b.json")
    assert (status, payload["error"]["context"]) == (2, {"reason": "usage"})
    status, payload, _ = run(launcher, workspace, "edit", "a b.json", "c d.json")
    assert (status, payload["error"]["code"]) == (5, "READ_ERROR")
    assert payload["error"]["context"]["file_name"] == "a b.json"
    status, payload, _ = run(launcher, workspace, "frobnicate")
    assert (status, payload["error"]["context"]) == (2, {"reason": "usage"})


@pytest.mark.parametrize("launcher", launchers(), ids=lambda launcher: Path(launcher[-1]).name)
def test_cli_edit_in_a_fresh_process(launcher: list[str], workspace: Path) -> None:
    batch = ROOT / "examples" / "specs" / "recolor.edit.json"
    shutil.copyfile(batch, workspace / "mis documentos" / "lote de edición.edit.json")
    document = os.path.join("mis documentos", "sprite mínimo.moanart.json")
    edit = os.path.join("mis documentos", "lote de edición.edit.json")
    before = sorted(p.name for p in (workspace / "mis documentos").iterdir())
    status, payload, stderr = run(launcher, workspace, "edit", document, edit)
    assert (status, payload["ok"], stderr) == (0, True, "")
    assert (payload["edit"]["revision"], payload["edit"]["affected_ids"]) == (1, ["body_fill"])
    assert payload["edit"]["document"]["layers"][0]["operations"][0]["color"] == "ink"
    assert sorted(p.name for p in (workspace / "mis documentos").iterdir()) == before
