"""Edit entry points of the facade: apply_edit, edit_document, load_edit_batch (MOANA-018)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import moana.api
from moana.api import (
    Document,
    EditBatch,
    EditConflict,
    EditResult,
    ParseLimits,
    ReadError,
    apply_edit,
    edit_document,
    load_document,
    load_edit_batch,
)
from moana.core import errors

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "specs" / "minimal.moana.json"
BATCH = ROOT / "examples" / "specs" / "recolor.edit.json"


def test_apply_edit_returns_a_new_document_with_the_next_revision() -> None:
    document = load_document(EXAMPLE)
    edited = apply_edit(document, BATCH)
    assert isinstance(edited, Document)
    assert (document.revision, edited.revision) == (0, 1)
    assert edited.layers[0].operations[0].model_dump()["color"] == "ink"
    assert document.layers[0].operations[0].model_dump()["color"] == "cloth"


def test_every_batch_source_is_equivalent(tmp_path: Path) -> None:
    raw = BATCH.read_bytes()
    from_path = load_edit_batch(BATCH)
    assert isinstance(from_path, EditBatch)
    assert load_edit_batch(str(BATCH)) == from_path
    assert load_edit_batch(raw) == from_path
    assert load_edit_batch(json.loads(raw)) == from_path
    assert load_edit_batch(from_path) is from_path
    result = edit_document(load_document(EXAMPLE), from_path)
    assert isinstance(result, EditResult)
    assert result.affected_ids == ("body_fill",)


def test_unreadable_batch_is_a_read_error_without_the_path(tmp_path: Path) -> None:
    with pytest.raises(ReadError) as caught:
        load_edit_batch(tmp_path / "missing batch.json")
    error = caught.value
    assert error.message == "the edit batch file could not be read"
    assert (error.context["reason"], error.context["file_name"]) == (
        "not_found",
        "missing batch.json",
    )
    assert str(tmp_path) not in repr(dict(error.context))
    with pytest.raises(errors.ValidationError):
        load_edit_batch('{"schema_version": "1.0"}')
    with pytest.raises(TypeError, match="ParseLimits"):
        load_edit_batch(BATCH, limits=3)  # type: ignore[arg-type]


def test_conflict_is_exported_with_exit_code_4() -> None:
    document = load_document(EXAMPLE)
    newer = apply_edit(document, BATCH)
    with pytest.raises(EditConflict) as caught:
        edit_document(newer, BATCH)
    assert caught.value.exit_code == 4
    assert moana.api.EditConflict is errors.EditConflict


def test_limits_bound_the_batch_read(tmp_path: Path) -> None:
    with pytest.raises(errors.ValidationError) as caught:
        load_edit_batch(BATCH, limits=ParseLimits(max_bytes=16))
    assert caught.value.context["reason"] == "too_large"
