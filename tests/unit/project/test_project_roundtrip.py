"""AC1/T1 of MOANA-020: save and load preserve IDs, revisions, history and RGBA."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from moanart.api import render
from moanart.core.errors import ExportError, ReadError
from moanart.editing import History, HistoryLimits
from moanart.project import (
    DEFAULT_PROJECT_LIMITS,
    MANIFEST_NAME,
    Asset,
    Project,
    ProjectLimits,
    asset_path,
    batch_path,
    encode_project,
    load_project,
    save_document,
    save_project,
    save_project_archive,
    snapshot_path,
)
from moanart.schema import Document, canonical_json, snapshot_digest

from .conftest import BAND_IDS, BatchFactory, PngFactory


def _ids(document: Document) -> list[str]:
    ids = [document.id, document.palette.id, *(c.id for c in document.palette.colors)]
    for layer in document.layers:
        ids += [layer.id, *(operation.id for operation in layer.operations)]
    return ids


def _assert_same_project(loaded: Project, original: Project) -> None:
    """Semantic equality: ``HistoryLimits`` is the loader's configuration, not data."""
    assert loaded.document == original.document
    assert loaded.assets == original.assets
    assert _ids(loaded.document) == _ids(original.document)
    assert loaded.document.revision == original.document.revision
    assert canonical_json(loaded.document) == canonical_json(original.document)
    assert [a.id for a in loaded.assets] == [a.id for a in original.assets]
    for got, expected in zip(loaded.assets, original.assets, strict=True):
        assert got.data == expected.data
        assert (got.width, got.height, got.rgba) == (expected.width, expected.height, expected.rgba)
    assert original.history is not None and loaded.history is not None
    old, new = original.history, loaded.history
    assert (new.root, new.cursor, new.total_bytes) == (old.root, old.cursor, old.total_bytes)
    assert list(new.snapshots) == list(old.snapshots)
    assert dict(new.redo_children) == dict(old.redo_children)
    assert dict(new.children) == dict(old.children)
    for digest, snapshot in old.snapshots.items():
        stored = new.snapshots[digest]
        assert (stored.parent, stored.batch, stored.affected_ids, stored.size, stored.revision) == (
            snapshot.parent,
            snapshot.batch,
            snapshot.affected_ids,
            snapshot.size,
            snapshot.revision,
        )
        assert render(stored.document).rgba == render(snapshot.document).rgba


def test_ac1_directory_roundtrip_preserves_ids_revisions_history_and_rgba(
    tmp_path: Path, project: Project
) -> None:
    report = save_project(project, tmp_path / "hero")
    loaded = load_project(tmp_path / "hero")
    _assert_same_project(loaded, project)
    assert report.written[-1] == MANIFEST_NAME
    assert report.reused == ()
    # Oracle by hand: the 4 x 3 texture is one colour, the gradient was set per pixel.
    assert loaded.assets[0].rgba == bytes((10, 20, 30, 40)) * 12
    expected = [(x * 80, y * 120, 7, 255 - x) for y in range(2) for x in range(3)]
    assert loaded.assets[1].rgba == bytes(v for pixel in expected for v in pixel)
    # The cursor's branch and revisions: root 0, the undone edit 1, B 1 and C 2.
    assert loaded.history is not None
    assert [s.revision for s in loaded.history.snapshots.values()] == [0, 1, 1, 2]
    assert loaded.history.can_redo and loaded.history.can_undo


def test_ac1_history_limits_are_the_loader_configuration(tmp_path: Path, project: Project) -> None:
    """ADR-029 section 7: ``HistoryLimits`` is not persisted; the loader's apply."""
    assert project.history is not None
    tight = HistoryLimits(max_snapshots=10, max_bytes=1 << 20)
    custom = History(
        root=project.history.root,
        cursor=project.history.cursor,
        limits=tight,
        snapshots=project.history.snapshots,
        children=project.history.children,
        redo_children=project.history.redo_children,
        total_bytes=project.history.total_bytes,
    )
    saved = Project(project.document, project.assets, custom)
    save_project(saved, tmp_path / "p")
    assert encode_project(saved) == encode_project(project)
    loaded = load_project(tmp_path / "p")
    _assert_same_project(loaded, saved)
    assert loaded.history is not None
    assert loaded.history.limits == DEFAULT_PROJECT_LIMITS.history
    host = ProjectLimits(history=HistoryLimits(max_snapshots=5))
    reloaded = load_project(tmp_path / "p", limits=host)
    assert reloaded.history is not None
    assert reloaded.history.limits == host.history


def test_ac1_loaded_history_keeps_navigating_and_editing(
    tmp_path: Path, project: Project, batch: BatchFactory
) -> None:
    save_project(project, tmp_path / "p")
    history = load_project(tmp_path / "p").history
    assert history is not None and project.history is not None
    assert history.redo().document == project.history.redo().document
    assert history.undo().document.revision == 0
    edited = history.edit(
        batch(history.document, {"type": "set_color", "target_id": "body_fill", "color": "ink"})
    )
    assert edited.document.revision == history.document.revision + 1


def test_ac1_archive_roundtrip_is_deterministic(tmp_path: Path, project: Project) -> None:
    first = save_project_archive(project, tmp_path / "a.moanart")
    second = save_project_archive(project, tmp_path / "b.moanart")
    assert first.sha256 == second.sha256
    assert (tmp_path / "a.moanart").read_bytes() == (tmp_path / "b.moanart").read_bytes()
    _assert_same_project(load_project(tmp_path / "a.moanart"), project)


def test_t1_geometric_document_roundtrip(tmp_path: Path, document: Document) -> None:
    report = save_document(document, tmp_path / "sprite.moanart.json")
    data = (tmp_path / "sprite.moanart.json").read_bytes()
    assert data == canonical_json(document)
    assert report.sha256 == hashlib.sha256(data).hexdigest()
    assert report.written == ("sprite.moanart.json",)
    loaded = load_project(str(tmp_path / "sprite.moanart.json"))
    assert loaded == Project(document)
    assert render(loaded.document).rgba == render(document).rgba


def test_t1_project_without_assets_or_history(tmp_path: Path, document: Document) -> None:
    save_project(Project(document), tmp_path / "plain")
    manifest = json.loads((tmp_path / "plain" / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["kind"] == "moanart-project"
    assert manifest["project_version"] == "1.0"
    assert manifest["assets"] == [] and manifest["history"] == []
    assert sorted(p.name for p in (tmp_path / "plain").iterdir()) == [MANIFEST_NAME]
    assert load_project(tmp_path / "plain") == Project(document)
    archive = tmp_path / "plain.moanart"
    save_project_archive(Project(document), archive)
    assert load_project(archive) == Project(document)


def test_t1_png_asset_roundtrip_keeps_source_bytes(
    tmp_path: Path, document: Document, png: PngFactory
) -> None:
    data = png(5, 2, (255, 0, 128, 0), optimize=True)
    asset = Asset.from_png("sky", data)
    save_project(Project(document, (asset,)), tmp_path / "p")
    stored = tmp_path / "p" / asset_path(hashlib.sha256(data).hexdigest())
    assert stored.read_bytes() == data
    loaded = load_project(tmp_path / "p").assets[0]
    assert loaded.data == data and loaded.mime == "image/png"
    assert loaded.rgba == bytes((255, 0, 128, 0)) * 10
    manifest = json.loads((tmp_path / "p" / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["assets"] == [
        {
            "byte_length": len(data),
            "id": "sky",
            "mime": "image/png",
            "path": asset.path,
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    ]


def test_t1_layout_uses_immutable_hash_paths(tmp_path: Path, project: Project) -> None:
    save_project(project, tmp_path / "p")
    assert project.history is not None
    for digest, snapshot in project.history.snapshots.items():
        stored = (tmp_path / "p" / snapshot_path(digest)).read_bytes()
        assert "sha256:" + hashlib.sha256(stored).hexdigest() == digest
        if snapshot.batch is not None:
            name = batch_path("sha256:" + hashlib.sha256(snapshot.batch).hexdigest())
            assert (tmp_path / "p" / name).read_bytes() == snapshot.batch


def test_t1_envelope_file_loads_with_assets_beside_it(tmp_path: Path, project: Project) -> None:
    save_project(project, tmp_path / "p")
    assert load_project(tmp_path / "p" / MANIFEST_NAME) == project


def test_t1_resave_reuses_content_and_needs_overwrite(tmp_path: Path, project: Project) -> None:
    save_project(project, tmp_path / "p")
    before = (tmp_path / "p" / MANIFEST_NAME).read_bytes()
    with pytest.raises(ExportError) as caught:
        save_project(project, tmp_path / "p")
    assert caught.value.context["reason"] == "exists"
    assert (tmp_path / "p" / MANIFEST_NAME).read_bytes() == before
    again = save_project(project, tmp_path / "p", overwrite=True)
    assert again.written == (MANIFEST_NAME,)
    assert len(again.reused) == 2 + 4 + 3  # two assets, four snapshots, three batches
    assert (tmp_path / "p" / MANIFEST_NAME).read_bytes() == before


def test_t1_corrupt_content_file_is_rewritten_on_save(tmp_path: Path, project: Project) -> None:
    save_project(project, tmp_path / "p")
    stored = tmp_path / "p" / project.assets[0].path
    stored.write_bytes(b"corrupt")
    report = save_project(project, tmp_path / "p", overwrite=True)
    assert project.assets[0].path in report.written
    assert stored.read_bytes() == project.assets[0].data


def test_t1_missing_project_is_a_read_error(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(ReadError) as caught:
        load_project(tmp_path / "empty")
    assert caught.value.context["reason"] == "not_found"
    assert caught.value.context["file_name"] == MANIFEST_NAME
    with pytest.raises(ReadError):
        load_project(tmp_path / "absent.moanart")


def test_t1_cursor_document_is_the_manifest_document(tmp_path: Path, project: Project) -> None:
    save_project(project, tmp_path / "p")
    manifest = json.loads((tmp_path / "p" / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert project.history is not None
    assert snapshot_digest(project.document) == project.history.cursor
    assert manifest["document"] == json.loads(canonical_json(project.document))
    redo = [entry for entry in manifest["history"] if entry["redo"]]
    assert {(e["parent"], e["snapshot"]) for e in redo} == set(
        project.history.redo_children.items()
    )


def test_ac1_shaded_document_history_roundtrip(
    tmp_path: Path, shaded: Document, batch: BatchFactory, png: PngFactory
) -> None:
    """Re-applying stored batches covers ``shade`` (ADR-028): band masks and band IDs."""
    move = {"type": "translate", "target_id": "highlight", "dx": 1, "dy": 1}
    history = History.start(shaded).edit(batch(shaded, move))
    assert "highlight" in history.current.affected_ids
    removal = (
        {"type": "remove", "target_id": "orb_shadow"},
        {"type": "remove", "target_id": "orb_shading"},
    )
    history = history.edit(batch(history.document, *removal))
    assert set(BAND_IDS) <= set(history.current.affected_ids)
    history = history.undo()
    project = Project(history.document, (Asset.from_png("orb_texture", png()),), history)
    save_project(project, tmp_path / "p")
    save_project_archive(project, tmp_path / "p.moanart")
    for name in ("p", "p.moanart"):
        loaded = load_project(tmp_path / name)
        _assert_same_project(loaded, project)
        assert loaded.history is not None
        removed = loaded.history.redo().current
        assert set(BAND_IDS) <= set(removed.affected_ids)
        assert render(loaded.document).rgba == render(project.document).rgba
