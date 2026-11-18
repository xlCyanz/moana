"""Shared fixtures of the project tests: documents, PNG bytes and a branched project."""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

import pytest
from PIL import Image

from moana.api import load_document
from moana.editing import History
from moana.project import Asset, Project, _fs
from moana.schema import Document, snapshot_digest

ROOT = Path(__file__).resolve().parents[3]
MINIMAL = ROOT / "examples/specs/minimal.moana.json"

type PngFactory = Callable[..., bytes]
type BatchFactory = Callable[..., dict[str, object]]


def encode_png(
    width: int = 4,
    height: int = 3,
    color: tuple[int, int, int, int] = (10, 20, 30, 40),
    mode: str = "RGBA",
    **options: object,
) -> bytes:
    """A PNG made by Pillow in memory; ``options`` go to ``Image.save``."""
    fill: tuple[int, ...] = color if mode == "RGBA" else color[:3]
    image = Image.new(mode, (width, height), fill)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", **options)
    return buffer.getvalue()


def make_batch(document: Document, *commands: Mapping[str, object]) -> dict[str, object]:
    """An edit batch based on ``document``."""
    return {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": list(commands),
    }


@pytest.fixture(params=[True, False], ids=["dir_fd", "paths"])
def confinement(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[bool]:
    """Run a test with directory descriptors (where available) and with the path fallback."""
    use_fd = bool(request.param)
    if use_fd and not _fs.DIR_FD:  # pragma: no cover - Windows
        pytest.skip("dir_fd is not available")
    monkeypatch.setattr(_fs, "DIR_FD", use_fd)
    yield use_fd


@pytest.fixture
def png() -> PngFactory:
    return encode_png


@pytest.fixture
def batch() -> BatchFactory:
    return make_batch


@pytest.fixture
def document() -> Document:
    return load_document(MINIMAL)


def branched_history(document: Document) -> History:
    """R, then A (undone), then B and C (C undone): cursor B, redo B -> C, A orphaned.

    Snapshots in insertion order: R (revision 0), A (1), B (1), C (2).
    """
    history = History.start(document)
    recolor = {"type": "set_color", "target_id": "body_fill", "color": "ink"}
    history = history.edit(make_batch(document, recolor)).undo()
    move = {"type": "translate", "target_id": "body_fill", "dx": 3, "dy": -2}
    history = history.edit(make_batch(history.document, move))
    hide = {"type": "set_visibility", "target_id": "body", "visible": False}
    return history.edit(make_batch(history.document, hide)).undo()


@pytest.fixture
def project(document: Document) -> Project:
    """A project with a branched history (cursor mid-branch) and two PNG assets."""
    history = branched_history(document)
    gradient = Image.new("RGBA", (3, 2))
    gradient.putdata([(x * 80, y * 120, 7, 255 - x) for y in range(2) for x in range(3)])
    buffer = io.BytesIO()
    gradient.save(buffer, "PNG")
    assets = (
        Asset.from_png("texture", encode_png()),
        Asset.from_png("gradient", buffer.getvalue()),
    )
    return Project(history.document, assets, history)


SHADED_ORB = ROOT / "examples/specs/shaded-orb.moana.json"
BAND_IDS = (
    "band_body",
    "band_shadow",
    "band_lit",
    "band_terminator_ne",
    "band_terminator_sw",
    "band_bounce",
    "band_highlight",
)


@pytest.fixture
def shaded() -> Document:
    """A document with a ``shade`` operation whose seven bands are ``item`` IDs (ADR-028)."""
    return load_document(SHADED_ORB)
