"""Animated documents persist, migrate and keep history like any other (MOANA-022 T2).

The timeline is document data (ADR-032): saving, loading, migrating and editing must
keep every animation, frame and override byte for byte, and the frames must render
the same after a roundtrip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from moanart.animation import render_animation
from moanart.api import load_document
from moanart.core import errors
from moanart.editing import History
from moanart.project import (
    Project,
    load_project,
    migrate_project,
    save_document,
    save_project,
    save_project_archive,
)
from moanart.schema import Document, canonical_json

from .conftest import ROOT, make_batch

SLIME = ROOT / "examples/specs/bouncing-slime.moanart.json"


@pytest.fixture
def slime() -> Document:
    return load_document(SLIME)


def frames(document: Document) -> list[tuple[str, str]]:
    rendered = render_animation(document, "bounce")
    return [(frame.frame_id, frame.result.digest) for frame in rendered.frames]


def save(kind: str, project: Project, directory: Path) -> Path:
    if kind == "directory":
        save_project(project, directory / "slime")
        return directory / "slime"
    if kind == "archive":
        save_project_archive(project, directory / "slime.moanart")
        return directory / "slime.moanart"
    save_document(project.document, directory / "slime.moanart.json")
    return directory / "slime.moanart.json"


@pytest.mark.parametrize("kind", ["directory", "archive", "json"])
def test_t2_an_animated_document_survives_every_format(
    kind: str, slime: Document, tmp_path: Path
) -> None:
    directory = tmp_path / "out"
    directory.mkdir()
    history = History.start(slime) if kind != "json" else None
    loaded = load_project(save(kind, Project(slime, (), history), directory))
    assert canonical_json(loaded.document) == canonical_json(slime)
    assert loaded.document.animations == slime.animations
    assert frames(loaded.document) == frames(slime)


def test_t2_migrating_a_current_animated_document_changes_nothing(
    slime: Document, tmp_path: Path
) -> None:
    source = tmp_path / "slime.moanart.json"
    save_document(slime, source)
    original = source.read_bytes()
    report = migrate_project(source, tmp_path / "migrated")
    assert report.steps == ()
    assert report.save is None  # a current source writes nothing (identity)
    assert not (tmp_path / "migrated").exists()
    assert source.read_bytes() == original


def test_t2_history_edits_an_animated_document(slime: Document) -> None:
    history = History.start(slime)
    batch = make_batch(slime, {"type": "translate", "target_id": "eye_l", "dx": 1, "dy": 0})
    edited = history.edit(batch)
    assert edited.document.revision == slime.revision + 1
    assert edited.document.animations == slime.animations
    assert edited.undo().document == slime
    # The eye is animated: removing it would leave dangling overrides.
    with pytest.raises(errors.ReferenceError) as raised:
        history.edit(make_batch(slime, {"type": "remove", "target_id": "eye_l"}))
    assert raised.value.context["reason"] == "live_reference"
    assert history.document == slime
