"""batch → documento: stale or partially invalid batches leave no trace (T2, AC1).

A batch is all or nothing (MOANART.md section 15, ADR-024): if any command fails, the
document, its canonical JSON and the history (cursor, snapshots, redo) are exactly
what they were. The failing command's position is drawn by Hypothesis, so a batch
that already applied valid commands to its working copy is exercised every time.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from moanart.api import apply_edit, load_document, render
from moanart.core.errors import BudgetExceeded, EditConflict, MoanArtError
from moanart.editing import History, HistoryLimits
from moanart.schema import Document, canonical_json, snapshot_digest

from .corpus import MINIMAL, ROOT, SECRET
from .guards import assert_clean_error, bounded_settings, forbid_allocation, forbid_effects

pytestmark = pytest.mark.security

BOUNDED = bounded_settings(40)

_VALID = (
    {"type": "translate", "target_id": "body_fill", "dx": 1, "dy": 0},
    {"type": "set_color", "target_id": "body_fill", "color": "ink"},
    {"type": "set_visibility", "target_id": "body", "visible": False},
    {"type": "translate", "target_id": "body_fill", "dx": 0, "dy": -2},
)
_FAILING = (
    {"type": "translate", "target_id": SECRET.replace("-", "_"), "dx": 1, "dy": 0},
    {"type": "set_color", "target_id": "body_fill", "color": "not_in_palette"},
    {"type": "translate", "target_id": "body_fill", "dx": 2_000_000, "dy": 0},
    {"type": "set_visibility", "target_id": "body_fill", "visible": False},
)


def _document() -> Document:
    return load_document(MINIMAL)


def _batch(document: Document, commands: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": commands,
    }


def _history_state(history: History) -> tuple[object, ...]:
    return (
        history.cursor,
        len(history),
        history.can_undo,
        history.can_redo,
        tuple(sorted(history.snapshots)),
        history.total_bytes,
    )


@BOUNDED
@given(
    valid=st.lists(st.sampled_from(_VALID), max_size=12),
    failing=st.sampled_from(_FAILING),
    data=st.data(),
)
def test_t2_property_failing_command_anywhere_mutates_nothing(
    valid: list[dict[str, Any]], failing: dict[str, Any], data: st.DataObject
) -> None:
    document = _document()
    canonical = canonical_json(document)
    position = data.draw(st.integers(0, len(valid)), label="failing position")
    commands = [*valid[:position], failing, *valid[position:]]
    history = History.start(document)
    state = _history_state(history)
    with forbid_effects(), pytest.raises(MoanArtError) as caught:
        history.edit(_batch(document, commands))
    error = assert_clean_error(caught.value, SECRET)
    pointers = {error.json_pointer, *(detail.json_pointer for detail in error.details)}
    assert any(p is not None and p.startswith(f"/commands/{position}") for p in pointers)
    assert _history_state(history) == state
    assert canonical_json(history.document) == canonical == canonical_json(document)
    with forbid_effects(), pytest.raises(MoanArtError):
        apply_edit(document, _batch(document, commands))
    assert canonical_json(document) == canonical


@pytest.mark.parametrize("field", ["base_revision", "base_snapshot"])
def test_t2_stale_batch_is_a_conflict_without_side_effects(field: str) -> None:
    document = _document()
    history = History.start(document).edit(_batch(document, [dict(_VALID[0])]))
    state = _history_state(history)
    stale = _batch(document, [dict(_VALID[1])])  # based on the root, cursor is its child
    if field == "base_revision":
        stale["base_snapshot"] = snapshot_digest(history.document)
    else:
        stale["base_revision"] = history.document.revision
    with forbid_effects(), pytest.raises(EditConflict):
        history.edit(stale)
    assert _history_state(history) == state


def test_t2_history_budget_rejects_before_adding() -> None:
    document = _document()
    history = History.start(document, limits=HistoryLimits(max_snapshots=1))
    state = _history_state(history)
    with forbid_effects(), pytest.raises(BudgetExceeded) as caught:
        history.edit(_batch(document, [dict(_VALID[0])]))
    assert caught.value.context["resource"] == "history_snapshots"
    assert _history_state(history) == state


def test_t2_hostile_frame_override_fails_before_any_frame_buffer() -> None:
    tree = json.loads((ROOT / "examples/specs/bouncing-slime.moanart.json").read_bytes())
    frame = tree["animations"][0]["frames"][1]
    frame["overrides"].append({"type": "translate", "target_id": "eye_l", "dx": 2_000_000, "dy": 0})
    document = load_document(tree)  # overrides are evaluated, like batches, per frame
    with forbid_allocation(), pytest.raises(MoanArtError) as caught:
        render(document, frame_id=frame["id"])
    assert_clean_error(caught.value, SECRET)
    pointer = caught.value.json_pointer or ""
    assert pointer.startswith("/animations/0/frames/1/overrides/")
