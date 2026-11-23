"""T3 of MOANA-020: the strict envelope and the verified history of a saved project."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from moanart.core.errors import (
    BudgetExceeded,
    EditConflict,
    MoanArtError,
    UnsupportedVersion,
    ValidationError,
)
from moanart.editing import History, HistoryLimits
from moanart.project import (
    MANIFEST_NAME,
    Project,
    ProjectLimits,
    ProjectManifest,
    batch_path,
    load_project,
    save_project,
    snapshot_path,
)
from moanart.project.manifest import parse_manifest
from moanart.schema import DEFAULT_PARSE_LIMITS, Document, ParseLimits, document_json_schema

from .conftest import BatchFactory

SCHEMA = Path(__file__).resolve().parents[3] / "schemas/moanart-document-1.0.schema.json"


def _saved(tmp_path: Path, project: Project) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "p"
    save_project(project, root)
    tree: dict[str, Any] = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    return root, tree


def _rewrite(root: Path, tree: dict[str, Any]) -> None:
    (root / MANIFEST_NAME).write_text(json.dumps(tree), encoding="utf-8")


def _load_error(root: Path, error: type[MoanArtError] = ValidationError) -> MoanArtError:
    with pytest.raises(error) as caught:
        load_project(root)
    return caught.value


# --- the envelope ---------------------------------------------------------------------


def test_t3_envelope_rejects_extra_fields_without_touching_document_schema(
    tmp_path: Path, project: Project
) -> None:
    root, tree = _saved(tmp_path, project)
    _rewrite(root, {**tree, "previews": ["../x"]})
    error = _load_error(root)
    assert error.context["reason"] == "invalid_manifest"
    assert [(d.json_pointer, d.context["reason"]) for d in error.details] == [
        ("", "extra_forbidden")
    ]
    assert "previews" not in str(error.details)
    # Document keeps its own strict schema: no envelope member leaks into it.
    assert "assets" not in Document.model_fields and "kind" not in Document.model_fields
    schema = document_json_schema()
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert "assets" not in properties and "history" not in properties
    assert json.loads(SCHEMA.read_text(encoding="utf-8")) == schema
    assert set(ProjectManifest.model_fields) == {
        "kind",
        "project_version",
        "document",
        "assets",
        "history",
        "migrations",  # optional, omitted when empty (MOANA-021, ADR-031)
    }


def test_t3_extra_document_member_keeps_its_document_error(
    tmp_path: Path, project: Project
) -> None:
    root, tree = _saved(tmp_path, project)
    tree["document"]["assets"] = []
    _rewrite(root, tree)
    error = _load_error(root)
    assert error.json_pointer is not None and error.json_pointer.startswith("/document")
    assert all(
        d.json_pointer is not None and d.json_pointer.startswith("/document/")
        for d in error.details
    )
    tree["document"].pop("assets")
    tree["document"]["schema_version"] = "9.0"
    _rewrite(root, tree)
    assert _load_error(root, UnsupportedVersion).json_pointer is not None


@pytest.mark.parametrize(
    ("change", "pointer", "reason"),
    [
        ({"kind": "moanart-document"}, "/kind", None),
        ({"project_version": 2}, "/project_version", "literal_error"),
        ({"assets": None}, "/assets", "tuple_type"),
        ({"document": []}, "/document", "model_type"),
        (
            {"history": [{"snapshot": "x", "parent": None, "batch": None, "redo": False}]},
            "/history/0/snapshot",
            "string_pattern_mismatch",
        ),
    ],
)
def test_t3_envelope_members_are_strict(
    tmp_path: Path,
    project: Project,
    change: dict[str, Any],
    pointer: str,
    reason: str | None,
) -> None:
    root, tree = _saved(tmp_path, project)
    _rewrite(root, {**tree, **change})
    error = _load_error(root)
    assert error.context["reason"] == "invalid_manifest"
    assert error.details[0].json_pointer == pointer
    if reason is not None:
        assert error.details[0].context["reason"] == reason


def test_t3_missing_history_defaults_to_empty(tmp_path: Path, project: Project) -> None:
    root, tree = _saved(tmp_path, project)
    tree.pop("history")
    _rewrite(root, tree)
    assert load_project(root) == Project(project.document, project.assets)


def test_t3_parse_manifest_requires_an_object() -> None:
    with pytest.raises(ValidationError) as caught:
        parse_manifest([], limits=DEFAULT_PARSE_LIMITS)
    assert caught.value.context["reason"] == "invalid_manifest"


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"\xff", "invalid_utf8"),
        (b'{"kind": 1, "kind": 2}', "duplicate_key"),
        (b'{"kind": NaN}', "non_finite_number"),
        (b'{"kind": -Infinity}', "non_finite_number"),
        (b'{"kind": 1e999}', "non_finite_number"),
        (b"{", "invalid_json"),
        (b"[" * 40 + b"]" * 40, "too_deep"),
        (b"[" + b"0," * 40_000 + b"0]", "too_many_nodes"),
    ],
)
def test_t3_manifest_reading_is_bounded(tmp_path: Path, data: bytes, reason: str) -> None:
    (tmp_path / MANIFEST_NAME).write_bytes(data)
    with pytest.raises(ValidationError) as caught:
        load_project(tmp_path)
    assert caught.value.context["reason"] == reason


def test_t3_manifest_byte_limit(tmp_path: Path, project: Project) -> None:
    root, _ = _saved(tmp_path, project)
    with pytest.raises(ValidationError) as caught:
        load_project(root, limits=ProjectLimits(max_manifest_bytes=100))
    assert caught.value.context["reason"] == "too_large"
    with pytest.raises(BudgetExceeded) as budget:
        save_project(project, tmp_path / "q", limits=ProjectLimits(max_manifest_bytes=100))
    assert budget.value.context["resource"] == "manifest_bytes"
    assert not (tmp_path / "q").exists()


def test_t3_plain_json_files_are_documents_or_envelopes(tmp_path: Path) -> None:
    target = tmp_path / "x.moanart.json"
    target.write_bytes(b"[1]")
    with pytest.raises(ValidationError) as caught:
        load_project(target)
    assert caught.value.context["reason"] == "root_not_object"
    target.write_bytes(b'{"kind": "other"}')
    with pytest.raises(ValidationError) as caught:
        load_project(target)
    assert caught.value.details[0].json_pointer == "/kind"


# --- the history -----------------------------------------------------------------------


def _entries(tree: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = tree["history"]
    return entries


def test_t3_tampered_snapshot_file_is_a_checksum_mismatch(tmp_path: Path, project: Project) -> None:
    root, tree = _saved(tmp_path, project)
    path = root / snapshot_path(_entries(tree)[2]["snapshot"])
    path.write_bytes(path.read_bytes().replace(b'"revision":1', b'"revision":5'))
    error = _load_error(root)
    assert error.context == {"reason": "checksum_mismatch", "entry": 2}


def _store(root: Path, folder: str, data: bytes) -> str:
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    target = root / (snapshot_path(digest) if folder == "snapshots" else batch_path(digest))
    target.write_bytes(data)
    return digest


def test_t3_batch_that_does_not_reproduce_its_snapshot(
    tmp_path: Path, project: Project, batch: BatchFactory
) -> None:
    root, tree = _saved(tmp_path, project)
    assert project.history is not None
    root_document = project.history.snapshots[tree["history"][0]["snapshot"]].document
    other = json.dumps(
        batch(root_document, {"type": "set_color", "target_id": "body_fill", "color": "cloth"}),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _entries(tree)[1]["batch"] = _store(root, "batches", other)
    _rewrite(root, tree)
    error = _load_error(root)
    assert error.context == {"reason": "invalid_history", "entry": 1}


@pytest.mark.parametrize("kind", ["not_canonical", "invalid_json", "wrong_base"])
def test_t3_unusable_batches_are_rejected(
    tmp_path: Path, project: Project, batch: BatchFactory, kind: str
) -> None:
    root, tree = _saved(tmp_path, project)
    stored = (root / batch_path(_entries(tree)[1]["batch"])).read_bytes()
    data = {
        "not_canonical": json.dumps(json.loads(stored), indent=1).encode("utf-8"),
        "invalid_json": b"{",
        "wrong_base": stored.replace(b'"base_revision":0', b'"base_revision":7'),
    }[kind]
    _entries(tree)[1]["batch"] = _store(root, "batches", data)
    _rewrite(root, tree)
    assert _load_error(root).context["reason"] == "invalid_history"


@pytest.mark.parametrize("kind", ["not_canonical", "invalid_document"])
def test_t3_unusable_snapshots_are_rejected(tmp_path: Path, project: Project, kind: str) -> None:
    root, tree = _saved(tmp_path, project)
    stored = (root / snapshot_path(_entries(tree)[0]["snapshot"])).read_bytes()
    data = {
        "not_canonical": json.dumps(json.loads(stored), indent=1).encode("utf-8"),
        "invalid_document": b'{"schema_version": "1.0"}',
    }[kind]
    _entries(tree)[0]["snapshot"] = _store(root, "snapshots", data)
    _rewrite(root, tree)
    assert _load_error(root).context == {"reason": "invalid_history", "entry": 0}


def _edit(tree: dict[str, Any], kind: str) -> None:
    entries = _entries(tree)
    if kind == "child_first":
        entries[0], entries[1] = entries[1], entries[0]
    elif kind == "duplicate":
        entries.append(dict(entries[1], redo=False))
    elif kind == "two_roots":
        entries.append(dict(entries[0]))
    elif kind == "unknown_parent":
        entries[3]["parent"] = "sha256:" + "0" * 64
    elif kind == "two_redo":
        entries[1]["redo"] = True
    elif kind == "no_cursor":
        entries.pop()  # C is not the cursor; drop B instead after it
        entries.pop()
    elif kind == "root_with_batch":
        entries[0]["batch"] = entries[1]["batch"]
    else:
        entries[0]["redo"] = True


@pytest.mark.parametrize(
    ("kind", "error"),
    [
        ("child_first", "invalid_history"),
        ("duplicate", "invalid_history"),
        ("two_roots", "invalid_history"),
        ("unknown_parent", "invalid_history"),
        ("two_redo", "invalid_history"),
        ("no_cursor", "invalid_history"),
        ("root_with_batch", "invalid_manifest"),
        ("root_redo", "invalid_manifest"),
    ],
)
def test_t3_inconsistent_history_entries_are_rejected(
    tmp_path: Path, project: Project, kind: str, error: str
) -> None:
    root, tree = _saved(tmp_path, project)
    _edit(tree, kind)
    _rewrite(root, tree)
    assert _load_error(root).context["reason"] == error


def test_t3_history_budgets_are_checked_while_reading(tmp_path: Path, project: Project) -> None:
    root, _ = _saved(tmp_path, project)
    cases = [
        (ProjectLimits(history=HistoryLimits(max_snapshots=3)), "history_snapshots"),
        (ProjectLimits(history=HistoryLimits(max_bytes=1500)), "history_bytes"),
        (ProjectLimits(parse=ParseLimits(max_bytes=300)), "history_file_bytes"),
    ]
    for limits, resource in cases:
        with pytest.raises(BudgetExceeded) as caught:
            load_project(root, limits=limits)
        assert caught.value.context["resource"] == resource


def test_t3_convergent_branches_stay_rejected_after_loading(
    tmp_path: Path, document: Document, batch: BatchFactory
) -> None:
    """ADR-029 keeps ADR-026 §4: a digest has a single parent, also after a save."""
    recolor = {"type": "set_color", "target_id": "body_fill", "color": "ink"}
    move = {"type": "translate", "target_id": "body_fill", "dx": 1, "dy": 0}
    history = History.start(document)
    history = history.edit(batch(document, recolor))
    history = history.edit(batch(history.document, move)).undo().undo()
    history = history.edit(batch(document, move))
    save_project(Project(history.document, (), history), tmp_path / "p")
    loaded = load_project(tmp_path / "p").history
    assert loaded is not None
    with pytest.raises(EditConflict) as caught:
        loaded.edit(batch(loaded.document, recolor))
    assert caught.value.context["reason"] == "existing_snapshot"
