"""Incremental ID index of an edit batch (MOANA-036 AC1, AC2, T1; ADR-040).

Two oracles written apart from the incremental index:

* :func:`moanart.editing._tree.index_nodes`, the full rebuild the editor ran before
  every command, recomputed from the working tree after every command;
* :class:`RebuildingIndex`, the editor as it was before ADR-040: every lookup
  rebuilds the index from the tree and palette membership scans the palette, and
  the structural updates do nothing. A batch must give the same document, revision,
  snapshot, ``affected_ids`` and error (type, code, message, pointer, context and
  details) under both.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from moanart.animation import evaluate_animation, render_animation
from moanart.core.errors import MoanArtError
from moanart.editing import (
    SetColor,
    Translate,
    apply,
    apply_batch,
    apply_commands,
    parse_edit_batch,
)
from moanart.editing._tree import (
    OPERATION_MEMBERS,
    JsonObject,
    Node,
    WorkingIndex,
    index_nodes,
    node_members,
)
from moanart.render import render
from moanart.schema import (
    Document,
    canonical_json,
    normalize_document,
    snapshot_digest,
    validate_document,
)
from tests.benchmarks.corpus import animation_document

type Tree = dict[str, Any]

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
DOCUMENT_PATHS = sorted(
    [
        *(EXAMPLES / "specs").glob("*.moanart.json"),
        *(EXAMPLES / "corpus").glob("*/*.moanart.json"),
        *(EXAMPLES / "desk").glob("*.moanart.json"),
        EXAMPLES / "tiles" / "meadow.moanart.json",
        EXAMPLES / "tutorial" / "potion.moanart.json",
    ]
)
EDIT_PATHS = sorted(EXAMPLES.rglob("*.edit.json"))
SNAPSHOT = "sha256:" + "0" * 64


def read(path: Path) -> Tree:
    loaded: Tree = json.loads(path.read_text(encoding="utf-8"))
    return loaded


DOCUMENTS: dict[str, Document] = {
    path.relative_to(EXAMPLES).as_posix(): validate_document(read(path)) for path in DOCUMENT_PATHS
}


# --- oracles ------------------------------------------------------------------------


class RebuildingIndex(WorkingIndex):
    """The lookups of the editor before ADR-040: a full ``index_nodes`` every time."""

    __slots__ = ()

    def get(self, key: str) -> Node | None:
        return index_nodes(self._tree).get(key)

    def __contains__(self, key: str) -> bool:
        return key in index_nodes(self._tree)

    def entries(self) -> dict[str, Node]:
        return index_nodes(self._tree)

    def is_color(self, key: str) -> bool:
        return key in {color["id"] for color in self._tree["palette"]["colors"]}

    def inserted(
        self, operation: JsonObject, container: list[JsonObject], layer: JsonObject
    ) -> None:
        pass

    def removed(self, keys: object) -> None:
        pass

    def replaced(self, node: Node, value: JsonObject) -> None:
        pass

    def reordered(self) -> None:
        pass


def mismatches(actual: dict[str, Node], expected: dict[str, Node]) -> list[str]:
    """IDs whose entries differ by kind or by the identity of value, list or layer."""
    keys = sorted(actual.keys() | expected.keys())
    return [
        key
        for key in keys
        if key not in actual
        or key not in expected
        or actual[key].kind != expected[key].kind
        or actual[key].value is not expected[key].value
        or actual[key].container is not expected[key].container
        or actual[key].layer is not expected[key].layer
    ]


Apply = Callable[[apply._Work, object, str], tuple[str, ...]]


def verifying(original: Apply, log: list[str]) -> Apply:
    """``_apply`` that checks the index against a fresh rebuild after every command."""

    def call(work: apply._Work, command: object, pointer: str) -> tuple[str, ...]:
        try:
            result = original(work, command, pointer)
        except MoanArtError:
            log.append(f"{type(command).__name__}:failed")
            raise
        else:
            log.append(f"{type(command).__name__}:ok")
            return result
        finally:
            assert mismatches(work.index.entries(), index_nodes(work.tree)) == [], pointer

    return call


def error_key(error: MoanArtError) -> tuple[object, ...]:
    return (
        type(error),
        error.code,
        error.message,
        error.json_pointer,
        dict(error.context),
        tuple(error.details),
    )


def outcome(run: Callable[[], Any], *, reference: bool, log: list[str] | None = None) -> Any:
    """``run()`` with the incremental index (verified) or with the old lookups."""
    with pytest.MonkeyPatch.context() as patch:
        if reference:
            patch.setattr(apply, "WorkingIndex", RebuildingIndex)
        else:
            patch.setattr(apply, "_apply", verifying(apply._apply, [] if log is None else log))
        try:
            return run()
        except MoanArtError as error:
            return ("error", *error_key(error))


def batch_outcome(document: Document, source: Tree) -> Any:
    result = apply_batch(document, source)
    return (
        canonical_json(result.document),
        result.revision,
        result.base_snapshot,
        result.snapshot,
        result.affected_ids,
    )


# --- T1: random batches -------------------------------------------------------------


def pools(document: Document) -> dict[str, list[Any]]:
    """IDs and payloads of a document, drawn from by the command strategy."""
    nodes = index_nodes(normalize_document(document))
    of = {
        kind: [key for key, node in nodes.items() if node.kind == kind]
        for kind in (
            "color",
            "layer",
            "operation",
            "shape_mask",
            "combination_mask",
            "region",
            "ramp",
        )
    }
    geometric = [
        (key, {member: node.value[member] for member in node_members(node).geometry})
        for key, node in nodes.items()
        if node.kind in ("operation", "shape_mask", "combination_mask")
        and node_members(node).geometry
    ]
    parametric = [
        (key, {m: node.value[m] for m in node_members(node).parameters if m in node.value})
        for key, node in nodes.items()
        if node.kind == "operation" and node_members(node).parameters
    ]
    return {
        **of,
        "all": [*nodes, "ghost"],
        "removable": [
            *of["color"],
            *of["ramp"],
            *of["layer"],
            *of["operation"],
            *of["shape_mask"],
            *of["combination_mask"],
            *of["region"],
        ],
        "geometric": geometric,
        "parametric": parametric,
        "operations": [nodes[key].value for key in of["operation"]],
        "siblings": [
            (key, [item["id"] for item in node.container])
            for key, node in nodes.items()
            if node.container is not None and node.kind not in ("item", "animation", "frame")
        ],
        "layer_operations": [
            (key, [operation["id"] for operation in node.value["operations"]])
            for key, node in nodes.items()
            if node.kind == "layer"
        ],
    }


def renamed(operation: JsonObject, suffix: str) -> JsonObject:
    """A copy of ``operation`` whose ID and item IDs end in ``suffix``."""
    copied = copy.deepcopy(operation)
    copied["id"] += suffix
    for member, _ in OPERATION_MEMBERS[copied["type"]].items:
        for item in copied[member]:
            item["id"] += suffix
    return copied


def commands(pool: dict[str, list[Any]]) -> st.SearchStrategy[Tree]:
    def ids(*kinds: str) -> st.SearchStrategy[str]:
        return st.sampled_from([key for kind in kinds for key in pool[kind]] + ["ghost"])

    def anchored(pairs: list[Any]) -> st.SearchStrategy[tuple[str, str | None]]:
        """An ID and ``None`` or, mostly, the ID of a node in the same container."""
        return st.sampled_from(pairs).flatmap(
            lambda pair: st.tuples(
                st.just(pair[0]), st.none() | st.sampled_from([*pair[1], "ghost"])
            )
        )

    choices = [
        st.builds(
            lambda target, color: {"type": "set_color", "target_id": target, "color": color},
            ids("operation"),
            st.one_of(ids("color"), ids("color"), ids("layer", "ramp")),
        ),
        st.builds(
            lambda target, visible: {
                "type": "set_visibility",
                "target_id": target,
                "visible": visible,
            },
            ids("layer"),
            st.booleans(),
        ),
        st.builds(
            lambda target, dx, dy: {"type": "translate", "target_id": target, "dx": dx, "dy": dy},
            ids("operation", "shape_mask", "combination_mask"),
            st.sampled_from([-2, -1, 1, 3]),
            st.sampled_from([-1, 1, 2]),
        ),
        st.builds(
            lambda target, rgba: {
                "type": "replace_palette_color",
                "target_id": target,
                "rgba": rgba,
            },
            ids("color"),
            st.sampled_from(["#000000FF", "#12345678"]),
        ),
        st.builds(
            lambda place, operation, suffix: {
                "type": "insert_operation",
                "layer_id": place[0],
                "after_id": place[1],
                "operation": renamed(operation, suffix),
            },
            anchored(pool["layer_operations"]),
            st.sampled_from(pool["operations"]),
            st.sampled_from(["", "_n0", "_n1", "_n2"]),
        ),
        st.builds(lambda target: {"type": "remove", "target_id": target}, ids("removable")),
        st.builds(
            lambda move: {"type": "reorder", "target_id": move[0], "after_id": move[1]},
            anchored(pool["siblings"]),
        ),
    ]
    if pool["geometric"]:
        choices.append(
            st.builds(
                lambda target, donor: {
                    "type": "set_geometry",
                    "target_id": target[0],
                    "geometry": donor[1],
                },
                st.sampled_from(pool["geometric"]),
                st.sampled_from(pool["geometric"]),
            )
        )
    if pool["parametric"]:
        choices.append(
            st.builds(
                lambda target, donor: {
                    "type": "set_parameters",
                    "target_id": target[0],
                    "parameters": donor[1],
                },
                st.sampled_from(pool["parametric"]),
                st.sampled_from(pool["parametric"]),
            )
        )
    return st.one_of(choices)


POOLS = {name: pools(document) for name, document in DOCUMENTS.items()}


@settings(max_examples=1000, deadline=None, derandomize=True)
@given(st.data())
def test_t1_index_matches_a_fresh_rebuild_after_every_command(data: st.DataObject) -> None:
    """After each command, failing or not, the index is ``index_nodes`` of the tree,
    and the batch ends exactly as with the per-command rebuild (AC1)."""
    name = data.draw(st.sampled_from(sorted(DOCUMENTS)), label="document")
    document = DOCUMENTS[name]
    drawn = data.draw(st.lists(commands(POOLS[name]), min_size=1, max_size=10), label="commands")
    source = {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": drawn,
    }
    log: list[str] = []
    actual = outcome(lambda: batch_outcome(document, source), reference=False, log=log)
    expected = outcome(lambda: batch_outcome(document, source), reference=True)
    assert actual == expected
    assert log  # the verifying wrapper ran
    for entry in log:
        event(entry)


ORB = "specs/shaded-orb.moanart.json"
SHADE = index_nodes(normalize_document(DOCUMENTS[ORB]))["orb_shading"].value

STRUCTURAL: list[tuple[str, Tree]] = [
    # (document, command) pairs that succeed and change the structure of the index.
    (
        ORB,
        {
            "type": "insert_operation",
            "layer_id": "orb_layer",
            "after_id": "orb_shading",
            "operation": renamed(SHADE, "_copy"),
        },
    ),
    ("specs/material-wood.moanart.json", {"type": "remove", "target_id": "wood_outline"}),
    ("specs/minimal.moanart.json", {"type": "remove", "target_id": "body"}),
    (ORB, {"type": "reorder", "target_id": "orb_outline", "after_id": None}),
    (
        ORB,
        {
            "type": "set_parameters",
            "target_id": "orb_shading",
            "parameters": {"ramp_order": "monotonic"},
        },
    ),
    (
        "specs/material-wood.moanart.json",
        {"type": "set_parameters", "target_id": "wood_material", "parameters": {"density": 32}},
    ),
    (
        "specs/masked-eyes.moanart.json",
        {"type": "set_geometry", "target_id": "eye_left_shape", "geometry": {"box": [4, 6, 8, 9]}},
    ),
]


def structural_cases() -> list[Any]:
    return [
        pytest.param(name, command, id=f"{name}:{command['type']}") for name, command in STRUCTURAL
    ]


@pytest.mark.parametrize(("name", "command"), structural_cases())
def test_t1_every_structural_command_keeps_the_index_exact(name: str, command: Tree) -> None:
    """Each structural update (insert with items, remove of an operation with items
    and of a layer, reorder, replace of an operation with items and of a mask) keeps
    the index equal to a fresh rebuild, with the same result as before ADR-040."""
    document = DOCUMENTS[name]
    source: Tree = {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": [command, {"type": "remove", "target_id": "ghost"}],
    }
    log: list[str] = []
    actual = outcome(lambda: batch_outcome(document, source), reference=False, log=log)
    assert log[0].endswith(":ok")  # the structural command applied, the next one failed
    assert log[1].endswith(":failed")
    assert actual == outcome(lambda: batch_outcome(document, source), reference=True)
    del source["commands"][1]
    actual = outcome(lambda: batch_outcome(document, source), reference=False)
    assert actual[0] != "error"
    assert actual == outcome(lambda: batch_outcome(document, source), reference=True)


def test_t1_structural_cases_name_existing_targets() -> None:
    """The hand-written targets above are what they claim (guards against drift)."""
    kinds = {
        "orb_shading": "operation",
        "orb_outline": "operation",
        "body": "layer",
        "wood_material": "operation",
        "wood_outline": "operation",
        "eye_left_shape": "shape_mask",
    }
    for name, command in STRUCTURAL:
        target = command.get("target_id")
        if target is not None:
            node = index_nodes(normalize_document(DOCUMENTS[name])).get(target)
            assert node is not None and node.kind == kinds[target], (name, target)
    assert len(SHADE["bands"]) > 1  # removing or replacing it touches its items


# --- duplicate IDs (only an unvalidated source has them) ---------------------------


def duplicated_tree() -> Tree:
    """Two operations ``x`` in two layers and a palette whose ID is also a colour's."""
    return {
        "schema_version": "1.0",
        "id": "doc",
        "revision": 0,
        "seed": 0,
        "canvas": {"width": 8, "height": 8, "profile": "strict"},
        "palette": {
            "id": "ink",
            "colors": [{"id": "ink", "rgba": "#000000FF"}, {"id": "red", "rgba": "#FF0000FF"}],
            "ramps": [],
        },
        "layers": [
            {
                "id": "a",
                "name": "A",
                "visible": True,
                "locked": False,
                "opacity": 255,
                "blend_mode": "normal",
                "operations": [{"id": "x", "type": "rect", "box": [0, 0, 2, 2], "color": "ink"}],
            },
            {
                "id": "b",
                "name": "B",
                "visible": True,
                "locked": False,
                "opacity": 255,
                "blend_mode": "normal",
                "operations": [
                    {"id": "x", "type": "pixel", "at": [1, 1], "color": "red"},
                    {"id": "y", "type": "pixel", "at": [2, 2], "color": "red"},
                ],
            },
        ],
        "masks": [],
        "regions": [],
        "animations": [],
    }


DUPLICATE_FREE: Tree = {
    **duplicated_tree(),
    "palette": {
        "id": "pal",
        "colors": [{"id": "ink", "rgba": "#000000FF"}, {"id": "red", "rgba": "#FF0000FF"}],
        "ramps": [],
    },
    "layers": [duplicated_tree()["layers"][1]],
}
"""The same tree with every ID unique: one layer ``b`` with ``x`` and ``y``."""

DUPLICATE_BATCHES: list[list[Tree]] = [
    [
        {"type": "set_color", "target_id": "x", "color": "ink"},
        {"type": "reorder", "target_id": "b", "after_id": None},  # b's ``x`` now wins
        {"type": "translate", "target_id": "x", "dx": 1, "dy": 1},
        {"type": "set_geometry", "target_id": "x", "geometry": {"at": [3, 3]}},
        {"type": "remove", "target_id": "x"},  # a's ``x`` becomes the only one
        {"type": "set_geometry", "target_id": "x", "geometry": {"box": [1, 1, 3, 3]}},
        {
            "type": "insert_operation",
            "layer_id": "b",
            "after_id": "y",
            "operation": {"id": "z", "type": "pixel", "at": [0, 0], "color": "ink"},
        },
        {"type": "remove", "target_id": "z"},
        {"type": "reorder", "target_id": "x", "after_id": None},
    ],
    [
        {"type": "remove", "target_id": "x"},
        {"type": "set_color", "target_id": "x", "color": "red"},
        {"type": "remove", "target_id": "x"},
        {"type": "set_color", "target_id": "x", "color": "red"},  # unknown_target
    ],
    [
        {
            "type": "insert_operation",
            "layer_id": "a",
            "after_id": None,
            "operation": {"id": "x", "type": "pixel", "at": [0, 0], "color": "ink"},
        },
    ],
]


@pytest.mark.parametrize("raw", DUPLICATE_BATCHES)
def test_t1_duplicate_ids_keep_first_declaration_wins(raw: list[Tree]) -> None:
    """With a duplicate ID the index rebuilds after each structural change, so the
    first declaration in document order keeps winning as it moves or disappears."""
    parsed = parse_edit_batch(
        {"schema_version": "1.0", "base_revision": 0, "base_snapshot": SNAPSHOT, "commands": raw}
    ).commands

    def run(tree: Tree) -> Callable[[], Any]:
        def applied() -> Any:
            return apply._applied(apply._Work(tree), parsed), tree

        return applied

    actual_tree, expected_tree = duplicated_tree(), duplicated_tree()
    log: list[str] = []
    actual = outcome(run(actual_tree), reference=False, log=log)
    expected = outcome(run(expected_tree), reference=True)
    assert actual == expected
    assert actual_tree == expected_tree
    assert len(log) == len(raw)


def test_t1_duplicate_ids_are_seen_by_palette_membership() -> None:
    """``ink`` is the palette's ID and a colour's: still a colour while duplicated."""
    index = WorkingIndex(duplicated_tree())
    assert index.get("ink") is not None and index.get("ink").kind == "palette"  # type: ignore[union-attr]
    assert index.is_color("ink") and index.is_color("red") and not index.is_color("x")
    assert "ink" in index and "nope" not in index


def test_t1_the_index_is_built_lazily_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing is indexed until the first lookup; then the tree is walked once."""
    builds: list[int] = []
    rebuild = WorkingIndex._rebuild

    def counted(self: WorkingIndex) -> None:
        builds.append(1)
        rebuild(self)

    monkeypatch.setattr(WorkingIndex, "_rebuild", counted)
    tree = copy.deepcopy(DUPLICATE_FREE)
    index = WorkingIndex(tree)
    assert builds == []
    assert index.get("x") is not None and "y" in index and index.is_color("red")
    assert len(builds) == 1
    malformed = WorkingIndex({**tree, "regions": None})
    with pytest.raises(TypeError):  # a malformed tree only fails when the index is needed
        malformed.get("x")


def test_t1_a_desynchronised_removal_is_not_a_key_error() -> None:
    """``KeyError`` means a malformed source to the editor, so an index update that
    finds no entry fails as an internal error instead."""
    index = WorkingIndex(copy.deepcopy(DUPLICATE_FREE))
    with pytest.raises(AssertionError, match="not indexed"):
        index.removed(["ghost"])


# --- AC1: published examples --------------------------------------------------------


def edit_cases() -> list[Any]:
    by_snapshot = {snapshot_digest(document): name for name, document in DOCUMENTS.items()}
    sources = [(path.name, read(path)) for path in EDIT_PATHS]
    return [
        pytest.param(by_snapshot[source["base_snapshot"]], source, id=name)
        for name, source in sources
    ]


@pytest.mark.parametrize(("name", "source"), edit_cases())
def test_ac1_example_batches_match_the_rebuilding_editor(name: str, source: Tree) -> None:
    """Every published batch: same document, revision, snapshot, IDs or error, and the
    same RGBA, as with the per-command rebuild."""
    document = DOCUMENTS[name]

    def run() -> Any:
        result = apply_batch(document, source)
        return (*batch_outcome(document, source), render(result.document).digest)

    actual = outcome(run, reference=False)
    assert actual == outcome(run, reference=True)


ANIMATIONS: dict[str, Document] = {
    **{name: document for name, document in DOCUMENTS.items() if document.animations},
    "benchmark/animation": validate_document(animation_document()),
}


@pytest.mark.parametrize("name", sorted(ANIMATIONS))
def test_ac1_timelines_match_the_rebuilding_editor(name: str) -> None:
    """Every frame of every published (and benchmark) timeline: same evaluated
    documents and the same RGBA and digests as with the per-command rebuild."""
    document = ANIMATIONS[name]

    def run() -> Any:
        frames: list[object] = []
        for animation in document.animations:
            evaluated = evaluate_animation(document, animation.id)
            rendered = render_animation(document, animation.id)
            frames += [canonical_json(frame.document) for frame in evaluated]
            frames += [(f.frame_id, f.result.rgba, f.result.digest) for f in rendered.frames]
        return frames

    actual = outcome(run, reference=False)
    assert actual and actual[0] != "error"
    assert actual == outcome(run, reference=True)


def test_ac1_failing_override_reports_the_same_error() -> None:
    """A frame override that fails midway raises what the rebuilding editor raised."""
    document = ANIMATIONS["benchmark/animation"]
    base = document.model_copy(update={"animations": ()})
    first = document.animations[0].frames[0]
    commands: list[SetColor | Translate] = [
        Translate(type="translate", target_id=o.target_id, dx=1, dy=0)
        for o in first.overrides
        if o.type == "translate"
    ]
    commands.insert(3, SetColor(type="set_color", target_id="ghost", color="ink"))

    def run() -> Any:
        return apply_commands(base, commands, pointer="/animations/0/frames/0/overrides")

    actual = outcome(run, reference=False)
    assert actual[0] == "error" and actual[5]["reason"] == "unknown_target"
    assert actual == outcome(run, reference=True)
