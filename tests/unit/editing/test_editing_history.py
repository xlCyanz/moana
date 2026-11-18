"""Immutable edit history of MOANA.md section 15 (MOANA-019 AC1, AC2, T1, T2; ADR-026).

Every expected document is a hand-written edit of the literal ``FIXTURE`` tree and
every expected RGBA buffer is built pixel by pixel here, never taken from the
history or the editor.
"""

from __future__ import annotations

import copy
import dataclasses
import gc
import json
import tracemalloc
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.core import errors
from moana.core.limits import MAX_HISTORY_BYTES, MAX_HISTORY_SNAPSHOTS
from moana.editing import (
    DEFAULT_HISTORY_LIMITS,
    History,
    HistoryLimits,
    Snapshot,
    canonical_batch,
    parse_edit_batch,
)
from moana.editing.history import _canonical_json
from moana.render import render
from moana.schema import (
    Document,
    canonical_json,
    normalize_document,
    snapshot_digest,
    validate_document,
)

type Tree = dict[str, Any]

SPECS = Path(__file__).resolve().parents[3] / "examples/specs"
SIZE = 4
COLORS = {"red": "#FF0000FF", "green": "#00FF00FF", "blue": "#0000FFFF"}
CYCLE = ("red", "green", "blue")

FIXTURE: Tree = {
    "schema_version": "1.0",
    "id": "dot_sprite",
    "revision": 1,
    "seed": 0,
    "canvas": {"width": SIZE, "height": SIZE, "profile": "strict"},
    "palette": {
        "id": "pal",
        "colors": [{"id": name, "rgba": rgba} for name, rgba in COLORS.items()],
    },
    "layers": [
        {
            "id": "main",
            "name": "Main",
            "operations": [{"id": "dot", "type": "pixel", "at": [0, 0], "color": "red"}],
        }
    ],
}


# --- independent oracles ------------------------------------------------------------


def position(step: int) -> list[int]:
    """Where edit ``step`` puts the dot: row-major walk of the 4x4 canvas."""
    return [step % SIZE, (step // SIZE) % SIZE]


def color(step: int) -> str:
    return CYCLE[step % len(CYCLE)]


def expected_tree(step: int, revision: int | None = None) -> Tree:
    """The fixture after the edit of :func:`step_commands` for ``step``, by hand.

    ``revision`` defaults to ``1 + step`` (``step`` edits in a row); a branch made
    with the commands of ``step`` at another depth passes its own revision.
    """
    tree = copy.deepcopy(FIXTURE)
    tree["revision"] = 1 + step if revision is None else revision
    if step:
        operation = tree["layers"][0]["operations"][0]
        operation["at"] = position(step)
        operation["color"] = color(step)
    return tree


def expected_rgba(step: int) -> bytes:
    """4x4 transparent RGBA with the single dot of state ``step``."""
    pixels = bytearray(SIZE * SIZE * 4)
    x, y = expected_tree(step)["layers"][0]["operations"][0]["at"]
    offset = (y * SIZE + x) * 4
    rgba = COLORS[expected_tree(step)["layers"][0]["operations"][0]["color"]]
    pixels[offset : offset + 4] = bytes.fromhex(rgba[1:])
    return bytes(pixels)


def expected_json(tree: Tree) -> bytes:
    return canonical_json(validate_document(tree))


def encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def step_commands(step: int) -> list[Tree]:
    return [
        {"type": "set_geometry", "target_id": "dot", "geometry": {"at": position(step)}},
        {"type": "set_color", "target_id": "dot", "color": color(step)},
    ]


def batch_for(document: Document, commands: list[Tree]) -> Tree:
    return {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": commands,
    }


def edited(history: History, commands: list[Tree]) -> History:
    return history.edit(batch_for(history.document, commands))


def start() -> History:
    return History.start(validate_document(FIXTURE))


def assert_state(history: History, step: int, revision: int | None = None) -> None:
    """Document (canonical JSON) and RGBA of the cursor equal the hand oracles."""
    tree = expected_tree(step, revision)
    assert canonical_json(history.document) == expected_json(tree)
    assert render(history.document).rgba == expected_rgba(step)


def walk(steps: int) -> list[History]:
    """Values of a history after 0..steps edits of :func:`step_commands`."""
    values = [start()]
    for step in range(1, steps + 1):
        values.append(edited(values[-1], step_commands(step)))
    return values


# --- AC1: undo and redo restore the exact document and RGBA -------------------------


def test_ac1_undo_and_redo_restore_document_and_rgba() -> None:
    values = walk(3)
    history = values[-1]
    for step in (2, 1, 0):
        history = history.undo()
        assert_state(history, step)
        assert history.document is values[step].document  # the stored object, no inverse
    for step in (1, 2, 3):
        history = history.redo()
        assert_state(history, step)
        assert history.document is values[step].document


def test_ac1_oracles_are_consistent_with_the_fixture() -> None:
    # The hand oracle of state 0 is the fixture itself, rendered: a red top-left dot.
    assert expected_rgba(0)[:4] == bytes.fromhex("FF0000FF")
    assert expected_rgba(0)[4:] == bytes(SIZE * SIZE * 4 - 4)
    assert_state(start(), 0)


# --- AC2: editing after undo invalidates only the active redo -----------------------


def test_ac2_edit_after_undo_replaces_only_the_active_redo() -> None:
    values = walk(2)
    first, second = values[1], values[2]
    rewound = second.undo().undo()
    branched = edited(rewound, step_commands(5))
    assert_state(branched, 5, revision=2)  # commands of step 5, applied at revision 1
    assert branched.document.revision == 2
    assert not branched.can_redo
    # The root's redo now leads to the new branch; the old line is intact.
    assert branched.undo().redo().cursor == branched.cursor
    assert len(branched) == 4
    assert branched.children_of(branched.root) == (first.cursor, branched.cursor)
    assert branched.leaves() == (second.cursor, branched.cursor)
    old = branched.checkout(second.cursor)
    assert_state(old, 2)
    assert old.undo().cursor == first.cursor
    assert old.undo().redo().cursor == second.cursor
    assert branched.snapshot(first.cursor).document is first.document


def test_ac2_undo_of_an_old_branch_reactivates_its_redo() -> None:
    first = walk(1)[1]
    other = edited(first.undo(), step_commands(7))
    back = other.checkout(first.cursor).undo()
    assert back.redo().cursor == first.cursor


# --- T1: 1, 10 and 100 edits and navigation to the limits ---------------------------


@pytest.mark.parametrize("steps", [1, 10, 100])
def test_t1_sequences_and_navigation_limits(steps: int) -> None:
    values = walk(steps)
    history = values[-1]
    assert len(history) == steps + 1
    assert history.document.revision == 1 + steps
    for step in range(steps, -1, -1):
        assert_state(history, step)
        assert history.can_undo == (step > 0)
        if step:
            history = history.undo()
    with pytest.raises(errors.ValidationError) as at_root:
        history.undo()
    assert at_root.value.context["reason"] == "no_parent"
    for step in range(1, steps + 1):
        history = history.redo()
        assert history.document is values[step].document
    assert not history.can_redo
    with pytest.raises(errors.ValidationError) as at_end:
        history.redo()
    assert at_end.value.context["reason"] == "no_redo"
    assert len(history) == steps + 1  # navigation added nothing


def test_t1_snapshot_records_parent_batch_revision_and_size() -> None:
    root, child = walk(1)
    batch = batch_for(root.document, step_commands(1))
    snapshot = child.current
    assert isinstance(snapshot, Snapshot)
    assert snapshot.parent == root.cursor
    assert snapshot.digest == child.cursor == snapshot_digest(child.document)
    assert snapshot.batch == encode(batch)
    assert parse_edit_batch(snapshot.batch) == parse_edit_batch(batch)
    assert snapshot.affected_ids == ("dot",)
    assert snapshot.revision == 2
    assert snapshot.size == len(expected_json(expected_tree(1))) + len(encode(batch))
    assert child.total_bytes == len(expected_json(FIXTURE)) + snapshot.size
    assert root.current.parent is None and root.current.batch is None
    assert root.current.size == root.total_bytes == len(expected_json(FIXTURE))


# --- T2: failed batches, branches, revisions and history budget ---------------------


def test_t2_failed_batch_adds_nothing_and_keeps_the_cursor() -> None:
    history = walk(2)[2].undo()
    unknown = [{"type": "set_color", "target_id": "ghost", "color": "red"}]
    with pytest.raises(errors.ReferenceError):
        edited(history, unknown)
    stale = batch_for(walk(2)[1].undo().document, step_commands(1))
    stale["base_revision"] = 9
    with pytest.raises(errors.EditConflict):
        history.edit(stale)
    assert len(history) == 3
    assert history.can_redo  # the active redo survives a failed edit
    assert_state(history, 1)


def test_t2_branches_with_the_same_revision_have_distinct_digests() -> None:
    first = walk(1)[1]
    second = edited(first.undo(), step_commands(4))
    one, two = second.snapshot(first.cursor), second.current
    assert one.revision == two.revision == 2
    assert one.digest != two.digest
    assert one.parent == two.parent == second.root
    assert_state(second.checkout(one.digest), 1)
    assert_state(second, 4, revision=2)
    # A batch written against one branch is a conflict on the other (MOANA-018 T3).
    batch = batch_for(one.document, step_commands(2))
    with pytest.raises(errors.EditConflict) as conflict:
        second.edit(batch)
    assert conflict.value.context["reason"] == "snapshot_mismatch"


def test_t2_checkout_creates_no_revision() -> None:
    values = walk(3)
    history = values[3]
    selected = history.checkout(values[1].cursor)
    assert len(selected) == len(history)
    assert selected.snapshots is history.snapshots
    assert selected.redo_children is history.redo_children
    assert selected.document is values[1].document
    assert selected.document.revision == 2
    assert selected.redo().cursor == values[2].cursor
    assert history.cursor == values[3].cursor  # the receiver never moves


def test_t2_checkout_of_an_unknown_digest_is_a_reference_error() -> None:
    history = start()
    with pytest.raises(errors.ReferenceError) as unknown:
        history.checkout("sha256:" + "0" * 64)
    assert unknown.value.context["reason"] == "unknown_snapshot"
    with pytest.raises(errors.ReferenceError):
        history.children_of("not-a-digest")
    with pytest.raises(TypeError):
        history.checkout(3)  # type: ignore[arg-type]  # deliberate wrong type


def test_t2_snapshot_budget_rejects_before_adding() -> None:
    history = History.start(validate_document(FIXTURE), limits=HistoryLimits(max_snapshots=2))
    full = edited(history, step_commands(1))
    with pytest.raises(errors.BudgetExceeded) as exceeded:
        edited(full, step_commands(2))
    assert dict(exceeded.value.context) == {
        "resource": "history_snapshots",
        "limit": 2,
        "estimated": 3,
    }
    assert exceeded.value.exit_code == 3
    assert len(full) == 2 and full.cursor == full.current.digest
    # Navigation and re-selecting a stored state never need budget.
    assert edited(full.undo(), step_commands(1)).cursor == full.cursor


def test_t2_byte_budget_rejects_before_adding() -> None:
    root_size = len(expected_json(FIXTURE))
    history = History.start(validate_document(FIXTURE), limits=HistoryLimits(max_bytes=root_size))
    assert history.total_bytes == root_size
    with pytest.raises(errors.BudgetExceeded) as exceeded:
        edited(history, step_commands(1))
    batch_size = len(encode(batch_for(history.document, step_commands(1))))
    assert dict(exceeded.value.context) == {
        "resource": "history_bytes",
        "limit": root_size,
        "estimated": root_size + len(expected_json(expected_tree(1))) + batch_size,
    }
    assert len(history) == 1
    with pytest.raises(errors.BudgetExceeded):
        History.start(validate_document(FIXTURE), limits=HistoryLimits(max_bytes=root_size - 1))


def test_t2_same_edit_after_undo_reuses_the_stored_snapshot() -> None:
    first = walk(1)[1]
    again = edited(first.undo(), step_commands(1))
    assert again.cursor == first.cursor
    assert again.snapshots == first.snapshots
    assert again.total_bytes == first.total_bytes
    assert again.current is first.current
    # Reached again by an edit, a stored state has no active redo, like a new one.
    values = walk(2)
    rewound = edited(values[2].undo().undo(), step_commands(1))
    assert rewound.cursor == values[1].cursor
    assert not rewound.can_redo
    assert len(rewound) == 3
    assert rewound.checkout(values[2].cursor).document is values[2].document


def test_t2_a_digest_reached_from_another_parent_is_rejected() -> None:
    # Two rev-2 siblings, then edits that converge on the same rev-3 document.
    green = edited(start(), [{"type": "set_color", "target_id": "dot", "color": "green"}])
    moved = [{"type": "set_geometry", "target_id": "dot", "geometry": {"at": [1, 1]}}]
    converged = edited(green, moved)
    other = edited(converged.checkout(converged.root), moved)
    with pytest.raises(errors.EditConflict) as existing:
        edited(other, [{"type": "set_color", "target_id": "dot", "color": "green"}])
    assert existing.value.exit_code == 4
    assert existing.value.context["reason"] == "existing_snapshot"
    assert existing.value.context["snapshot"] == converged.cursor
    assert len(other) == 4
    # Retryable: the converged state is one checkout away.
    assert other.checkout(existing.value.context["snapshot"]).document is converged.document


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"max_snapshots": 0}, "out_of_range"),
        ({"max_snapshots": MAX_HISTORY_SNAPSHOTS + 1}, "out_of_range"),
        ({"max_bytes": 0}, "out_of_range"),
        ({"max_bytes": MAX_HISTORY_BYTES + 1}, "out_of_range"),
        ({"max_snapshots": True}, "not_integer"),
        ({"max_bytes": True}, "not_integer"),
        ({"max_bytes": 1.5}, "not_integer"),
    ],
)
def test_t2_history_limits_can_only_be_lowered(arguments: dict[str, Any], reason: str) -> None:
    with pytest.raises(errors.ValidationError) as invalid:
        HistoryLimits(**arguments)
    assert invalid.value.context["reason"] == reason


def test_t2_defaults_and_argument_types() -> None:
    assert HistoryLimits(MAX_HISTORY_SNAPSHOTS, MAX_HISTORY_BYTES) == DEFAULT_HISTORY_LIMITS
    with pytest.raises(TypeError):
        History.start(FIXTURE)  # type: ignore[arg-type]  # deliberate wrong type
    with pytest.raises(TypeError):
        History.start(validate_document(FIXTURE), limits=object())  # type: ignore[arg-type]


def test_t2_history_values_are_frozen() -> None:
    history = start()
    with pytest.raises(FrozenInstanceError):
        history.cursor = "x"  # type: ignore[misc]  # frozen dataclass
    with pytest.raises(TypeError):
        history.snapshots["x"] = history.current  # type: ignore[index]  # read-only mapping
    assert "sha256:" + "0" * 64 not in history
    assert history.cursor in history


# --- T2: reuse, exact budgets, hand-built histories and canonical encoding ----------


def test_t2_reuse_keeps_the_first_batch_and_affected_ids() -> None:
    green: list[Tree] = [{"type": "set_color", "target_id": "dot", "color": "green"}]
    first = edited(start(), green)
    # Another batch with the same result: the visibility command changes nothing.
    other = [*green, {"type": "set_visibility", "target_id": "main", "visible": True}]
    again = edited(first.undo(), other)
    assert again.cursor == first.cursor
    assert again.current.batch == encode(batch_for(start().document, green))
    assert again.current.affected_ids == ("dot",)


def test_t2_exact_byte_budget_accepts_and_one_byte_less_rejects() -> None:
    batch = batch_for(start().document, step_commands(1))
    exact = len(expected_json(FIXTURE)) + len(expected_json(expected_tree(1))) + len(encode(batch))
    fits = History.start(validate_document(FIXTURE), limits=HistoryLimits(max_bytes=exact))
    assert edited(fits, step_commands(1)).total_bytes == exact
    short = History.start(validate_document(FIXTURE), limits=HistoryLimits(max_bytes=exact - 1))
    with pytest.raises(errors.BudgetExceeded):
        edited(short, step_commands(1))


def test_t2_a_single_snapshot_budget_rejects_every_edit() -> None:
    history = History.start(validate_document(FIXTURE), limits=HistoryLimits(max_snapshots=1))
    with pytest.raises(errors.BudgetExceeded) as exceeded:
        edited(history, step_commands(1))
    assert exceeded.value.context["resource"] == "history_snapshots"


def fields(history: History) -> dict[str, Any]:
    return {
        "root": history.root,
        "cursor": history.cursor,
        "limits": history.limits,
        "snapshots": dict(history.snapshots),
        "children": dict(history.children),
        "redo_children": dict(history.redo_children),
        "total_bytes": history.total_bytes,
    }


def branched_history() -> History:
    """Root with two children (one with a child of its own), cursor on the first."""
    values = walk(2)
    return edited(values[2].undo().undo(), step_commands(6)).checkout(values[1].cursor)


def test_t2_hand_built_history_is_validated() -> None:
    history = branched_history()
    arguments = fields(history)
    built = History(**arguments)
    assert built == history
    assert hash(built) == hash(history)
    arguments["snapshots"].clear()  # aliasing: the history keeps its own copy
    arguments["redo_children"].clear()
    assert len(built) == 4 and built.can_redo
    with pytest.raises(TypeError):
        built.redo_children["x"] = "y"  # type: ignore[index]  # read-only mapping
    assert built.undo().redo().cursor == history.cursor


def corrupt(arguments: dict[str, Any], digest_of: str, **changes: object) -> None:
    snapshots = arguments["snapshots"]
    key = arguments.get(digest_of, digest_of)
    snapshots[key] = dataclasses.replace(snapshots[key], **changes)


CORRUPTIONS: dict[str, Any] = {
    "unknown_cursor": lambda a: a.update(cursor="sha256:" + "1" * 64),
    "unknown_root": lambda a: a.update(root="sha256:" + "1" * 64),
    "total_plus_one": lambda a: a.update(total_bytes=a["total_bytes"] + 1),
    "total_negative": lambda a: a.update(total_bytes=-5),
    "not_a_snapshot": lambda a: a["snapshots"].update({a["cursor"]: "x"}),
    "wrong_key": lambda a: a["snapshots"].update({"sha256:" + "2" * 64: a["snapshots"][a["root"]]}),
    "wrong_document": lambda a: corrupt(a, "cursor", document=FIXTURE),
    "bool_size": lambda a: corrupt(a, "cursor", size=True),
    "negative_size": lambda a: corrupt(a, "cursor", size=-1),
    "wrong_digest": lambda a: corrupt(a, "cursor", document=validate_document(FIXTURE)),
    "root_with_parent": lambda a: corrupt(a, "root", parent=a["cursor"]),
    "child_without_batch": lambda a: corrupt(a, "cursor", batch=None),
    "child_without_parent": lambda a: corrupt(a, "cursor", parent=None),
    "parent_not_stored": lambda a: corrupt(a, "cursor", parent="sha256:" + "3" * 64),
    "wrong_revision": lambda a: corrupt(a, a["children"][a["root"]][1], parent=a["cursor"]),
    "child_before_parent": lambda a: a.update(snapshots=dict(reversed(a["snapshots"].items()))),
    "children_mismatch": lambda a: a["children"].pop(a["root"]),
    "redo_not_a_child": lambda a: a["redo_children"].update({a["cursor"]: a["root"]}),
}


@pytest.mark.parametrize("name", sorted(CORRUPTIONS))
def test_t2_hand_built_history_rejects_corruption(name: str) -> None:
    arguments = fields(branched_history())
    CORRUPTIONS[name](arguments)
    with pytest.raises(errors.ValidationError) as invalid:
        History(**arguments)
    assert invalid.value.context["reason"] == "invalid_history"


def test_t2_hand_built_history_types_and_budget() -> None:
    arguments = fields(branched_history())
    with pytest.raises(TypeError):
        History(**{**arguments, "limits": object()})
    with pytest.raises(TypeError):
        History(**{**arguments, "children": [("a", ("b",))]})
    with pytest.raises(errors.BudgetExceeded):
        History(**{**arguments, "limits": HistoryLimits(max_snapshots=3)})
    with pytest.raises(errors.BudgetExceeded):
        History(**{**arguments, "limits": HistoryLimits(max_bytes=arguments["total_bytes"] - 1)})


def test_canonical_batch_uses_the_canonical_document_encoding() -> None:
    tree = copy.deepcopy(FIXTURE)
    tree["layers"][0]["name"] = "Ñandú ✓"  # non-ASCII stays UTF-8, never escaped
    documents = [validate_document(tree)]
    for path in sorted(SPECS.glob("*.moana.json")):
        documents.append(validate_document(path.read_bytes()))
    for document in documents:
        assert _canonical_json(normalize_document(document)) == canonical_json(document)
    recolor = {
        "schema_version": "1.0",
        "base_revision": 1,
        "base_snapshot": "sha256:" + "a" * 64,
        "commands": [{"type": "replace_palette_color", "target_id": "red", "rgba": "#abcdefff"}],
    }
    parsed = parse_edit_batch(recolor)
    assert canonical_batch(parsed) == encode(recolor)
    assert parse_edit_batch(canonical_batch(parsed)) == parsed


def large_tree(operations: int) -> Tree:
    tree = copy.deepcopy(FIXTURE)
    tree["canvas"] = {"width": 128, "height": 128, "profile": "strict"}
    tree["layers"][0]["operations"] = [
        {"id": f"p{i}", "type": "pixel", "at": [i % 128, i // 128], "color": "red"}
        for i in range(operations)
    ]
    return tree


TRACED_FACTOR = 24
"""Documented ceiling of traced memory per canonical byte (ADR-026 §5; ~10-17x seen)."""


@pytest.mark.slow
def test_t2_traced_memory_is_proportional_to_total_bytes() -> None:
    source = large_tree(400)
    gc.collect()
    tracemalloc.start()
    try:
        history = History.start(validate_document(source))
        for step in range(20):
            change = [{"type": "set_color", "target_id": "p0", "color": CYCLE[(step + 1) % 3]}]
            history = edited(history, change)
        gc.collect()
        traced, _ = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(history) == 21
    assert history.total_bytes <= traced <= TRACED_FACTOR * history.total_bytes


# --- invariants checked after every step of the properties --------------------------


def assert_invariants(previous: History, history: History) -> None:
    assert set(previous.snapshots) <= set(history.snapshots)  # nothing is ever lost
    assert len(history) <= history.limits.max_snapshots
    assert history.total_bytes == sum(item.size for item in history.snapshots.values())
    for digest in set(history.snapshots) - set(previous.snapshots):
        assert digest == snapshot_digest(history.snapshot(digest).document)
    for item in history.snapshots.values():
        if item.parent is not None:
            assert item.revision == history.snapshot(item.parent).revision + 1
            assert item.digest in history.children_of(item.parent)
    for parent, child in history.redo_children.items():
        assert child in history.children_of(parent)
    assert sum(len(children) for children in history.children.values()) == len(history) - 1


# --- property 1: edit/undo/redo against a list-and-cursor model ---------------------

Action = tuple[str, int]
EDIT_UNDO_REDO = st.one_of(
    st.tuples(st.just("edit"), st.integers(0, 2)),
    st.tuples(st.just("undo"), st.just(0)),
    st.tuples(st.just("redo"), st.just(0)),
)


def model_tree(path: tuple[int, ...]) -> Tree:
    """Fixture plus one inserted pixel per edit of ``path``, written by hand."""
    tree = copy.deepcopy(FIXTURE)
    tree["revision"] = 1 + len(path)
    operations = tree["layers"][0]["operations"]
    for depth, choice in enumerate(path):
        operations.append(
            {"id": f"op_{depth}_{choice}", "type": "pixel", "at": [choice, 1], "color": "blue"}
        )
    return tree


def insert_commands(path: tuple[int, ...], choice: int) -> list[Tree]:
    after = f"op_{len(path) - 1}_{path[-1]}" if path else "dot"
    operation = {"id": f"op_{len(path)}_{choice}", "type": "pixel", "at": [choice, 1]}
    return [
        {
            "type": "insert_operation",
            "layer_id": "main",
            "after_id": after,
            "operation": {**operation, "color": "blue"},
        }
    ]


def step_model(states: list[tuple[int, ...]], cursor: int, action: Action) -> tuple[bool, int]:
    """Apply ``action`` to the linear model in place; whether it is allowed."""
    kind, choice = action
    if kind == "undo":
        return cursor > 0, max(cursor - 1, 0)
    if kind == "redo":
        return cursor < len(states) - 1, min(cursor + 1, len(states) - 1)
    del states[cursor + 1 :]
    states.append((*states[cursor], choice))
    return True, cursor + 1


def step_history(history: History, path: tuple[int, ...], action: Action) -> History:
    kind, choice = action
    if kind == "undo":
        return history.undo()
    if kind == "redo":
        return history.redo()
    return edited(history, insert_commands(path, choice))


@settings(max_examples=200, deadline=None)
@given(st.lists(EDIT_UNDO_REDO, max_size=80))
def test_property_history_matches_a_list_and_cursor_model(actions: list[Action]) -> None:
    states: list[tuple[int, ...]] = [()]
    cursor = 0
    history = start()
    for action in actions:
        path = states[cursor]
        allowed, cursor = step_model(states, cursor, action)
        previous = history
        if allowed:
            history = step_history(history, path, action)
        else:
            with pytest.raises(errors.ValidationError):
                step_history(history, path, action)
        assert_invariants(previous, history)
        assert canonical_json(history.document) == expected_json(model_tree(states[cursor]))
        assert history.can_undo == (cursor > 0)
        assert history.can_redo == (cursor < len(states) - 1)
    assert History(**fields(history)) == history  # the validator accepts every real state


# --- property 2: with random checkouts, against a tree of paths ---------------------
#
# A checkout leaves the line of a list model, so this model keeps every stored path
# (a state is its path of choices), the active redo of each path and a cursor path.


def step_tree_model(
    stored: list[tuple[int, ...]],
    redo: dict[tuple[int, ...], tuple[int, ...]],
    cursor: tuple[int, ...],
    action: Action,
) -> tuple[bool, tuple[int, ...]]:
    kind, choice = action
    if kind == "checkout":
        return True, stored[choice % len(stored)]
    if kind == "undo":
        if not cursor:
            return False, cursor
        redo[cursor[:-1]] = cursor
        return True, cursor[:-1]
    if kind == "redo":
        return cursor in redo, redo.get(cursor, cursor)
    child = (*cursor, choice)
    if child not in stored:
        stored.append(child)
    redo[cursor] = child
    redo.pop(child, None)
    return True, child


def model_digest(path: tuple[int, ...]) -> str:
    return snapshot_digest(validate_document(model_tree(path)))


@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.one_of(EDIT_UNDO_REDO, st.tuples(st.just("checkout"), st.integers(0, 63))),
        max_size=80,
    )
)
def test_property_history_with_checkouts_matches_a_path_tree(actions: list[Action]) -> None:
    stored: list[tuple[int, ...]] = [()]
    redo: dict[tuple[int, ...], tuple[int, ...]] = {}
    cursor: tuple[int, ...] = ()
    history = start()
    for action in actions:
        path = cursor
        allowed, cursor = step_tree_model(stored, redo, cursor, action)
        previous = history
        if action[0] == "checkout":
            history = history.checkout(model_digest(cursor))
        elif allowed:
            history = step_history(history, path, action)
        else:
            with pytest.raises(errors.ValidationError):
                step_history(history, path, action)
        assert_invariants(previous, history)
        assert canonical_json(history.document) == expected_json(model_tree(cursor))
        assert len(history) == len(stored)
        assert history.can_redo == (cursor in redo)
        assert history.can_undo == bool(cursor)
    assert History(**fields(history)) == history
