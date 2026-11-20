"""Atomic edit batches of MOANA.md section 15 (MOANA-018 AC1, AC2, T1, T2, T3).

Expected trees are edits of the hand-written ``FIXTURE`` below (or of the published
examples), never the editor's own output.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.core import errors
from moana.core.limits import MAX_EDIT_COMMANDS
from moana.editing import MAX_TRANSLATION, EditBatch, EditResult, SetColor, apply, apply_batch
from moana.editing._tree import index_nodes
from moana.render import render
from moana.schema import (
    Document,
    ParseLimits,
    canonical_json,
    normalize_document,
    snapshot_digest,
    validate_document,
)
from moana.schema.models import MAX_REVISION

type Tree = dict[str, Any]

# The fixture tree below is written by hand, not produced by the editor, so expected
# results are independent oracles (edits of this literal tree).
FIXTURE: Tree = {
    "schema_version": "1.0",
    "id": "hero",
    "revision": 1,
    "seed": 7,
    "canvas": {"width": 16, "height": 16, "profile": "strict"},
    "palette": {
        "id": "pal",
        "colors": [
            {"id": "ink", "rgba": "#101010FF"},
            {"id": "cloth", "rgba": "#36AFA5FF"},
            {"id": "spare", "rgba": "#AA0000FF"},
        ],
        "ramps": [{"id": "shade", "colors": ["ink", "cloth"]}],
    },
    "layers": [
        {
            "id": "body",
            "name": "Body",
            "operations": [
                {"id": "body_fill", "type": "rect", "box": [2, 2, 10, 12], "color": "cloth"},
                {"id": "belt", "type": "line", "start": [2, 8], "end": [9, 8], "color": "ink"},
                {"id": "button", "type": "pixel", "at": [5, 5], "color": "ink"},
            ],
        },
        {
            "id": "head",
            "name": "Head",
            "mask_id": "head_mask",
            "operations": [
                {"id": "head_fill", "type": "ellipse", "box": [3, 0, 9, 5], "color": "cloth"},
                {
                    "id": "hat",
                    "type": "polygon",
                    "points": [[3, 0], [9, 0], [6, 2]],
                    "color": "ink",
                },
                {
                    "id": "feather",
                    "type": "path",
                    "backend": "aggdraw-v1",
                    "commands": [["M", 256, 256], ["L", 768, 256], ["L", 512, 768], ["Z"]],
                    "color": "ink",
                },
            ],
        },
        {
            "id": "frame",
            "name": "Frame",
            "locked": True,
            "operations": [{"id": "frame_px", "type": "pixel", "at": [0, 0], "color": "ink"}],
        },
    ],
    "masks": [
        {"id": "head_mask", "type": "union", "masks": ["head_box", "head_dot"]},
        {"id": "head_box", "type": "rect", "box": [2, 0, 10, 6]},
        {"id": "head_dot", "type": "pixel", "at": [12, 12]},
        {"id": "free_mask", "type": "ellipse", "box": [0, 0, 4, 4]},
        {
            "id": "wing",
            "type": "path",
            "backend": "aggdraw-v1",
            "commands": [["M", 0, 0], ["L", 512, 0], ["L", 0, 512], ["Z"]],
        },
        {"id": "seam", "type": "line", "start": [0, 15], "end": [15, 15]},
        {"id": "tri", "type": "polygon", "points": [[0, 0], [3, 0], [0, 3]]},
    ],
    "regions": [
        {"id": "belt_region", "mask_id": "head_box", "operation_ids": ["belt"]},
        {"id": "wing_region", "mask_id": "wing"},
    ],
}


def tree() -> Tree:
    """A fresh deep copy of the hand-written fixture."""
    return copy.deepcopy(FIXTURE)


def apply_edit(document: Document, source: Tree) -> Document:
    """The new document only (the facade signature of MOANA.md section 13)."""
    return apply_batch(document, source).document


def fixture_document() -> Document:
    """The fixture validated into a frozen document."""
    return validate_document(tree())


def batch(document: Document, *commands: Tree) -> Tree:
    """A batch whose base is exactly ``document``."""
    return {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": list(commands),
    }


def changed_pointers(before: object, after: object, pointer: str = "") -> set[str]:
    """Every JSON Pointer whose value differs between two JSON trees (field by field)."""
    if isinstance(before, dict) and isinstance(after, dict):
        found: set[str] = set()
        for key in before.keys() | after.keys():
            if key not in before or key not in after:
                found.add(f"{pointer}/{key}")
            else:
                found |= changed_pointers(before[key], after[key], f"{pointer}/{key}")
        return found
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        found = set()
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            found |= changed_pointers(left, right, f"{pointer}/{index}")
        return found
    return set() if before == after and type(before) is type(after) else {pointer}


ROOT = Path(__file__).resolve().parents[3]
SPECS = ROOT / "examples" / "specs"


def load(name: str) -> Tree:
    loaded: Tree = json.loads((SPECS / name).read_text(encoding="utf-8"))
    return loaded


def edited(*commands: Tree) -> tuple[Document, EditResult]:
    document = fixture_document()
    return document, apply_batch(document, batch(document, *commands))


def expect_tree(result: EditResult, expected: Tree) -> None:
    """The result equals the hand-edited fixture (normalised) plus one revision."""
    expected = copy.deepcopy(expected)
    expected["revision"] = 2
    assert normalize_document(result.document) == normalize_document(validate_document(expected))


def failure(kind: type[errors.MoanaError], *commands: Tree) -> errors.MoanaError:
    document = fixture_document()
    before = canonical_json(document)
    with pytest.raises(kind) as caught:
        apply_batch(document, batch(document, *commands))
    assert canonical_json(document) == before
    return caught.value


def op(layer: int, index: int, source: Tree) -> Tree:
    operation: Tree = source["layers"][layer]["operations"][index]
    return operation


# --- AC1 ---------------------------------------------------------------------------


def test_ac1_recolor_changes_only_its_reference_and_the_revision() -> None:
    document = validate_document(load("minimal.moana.json"))
    edit = load("recolor.edit.json")
    result = apply_batch(document, edit)
    before, after = normalize_document(document), normalize_document(result.document)
    assert changed_pointers(before, after) == {"/revision", "/layers/0/operations/0/color"}
    assert after["revision"] == 1
    assert op(0, 0, after)["color"] == "ink"
    assert result.affected_ids == ("body_fill",)
    assert result.base_snapshot == edit["base_snapshot"] == snapshot_digest(document)
    assert result.snapshot == snapshot_digest(result.document) != result.base_snapshot


def test_ac1_ids_order_and_untouched_members_are_preserved() -> None:
    document, result = edited({"type": "set_color", "target_id": "hat", "color": "spare"})
    before, after = normalize_document(document), normalize_document(result.document)
    assert changed_pointers(before, after) == {"/revision", "/layers/1/operations/1/color"}


# --- AC2 ---------------------------------------------------------------------------


def test_ac2_an_invalid_second_command_rolls_back_the_first() -> None:
    first = {"type": "set_color", "target_id": "body_fill", "color": "ink"}
    error = failure(
        errors.ReferenceError, first, {"type": "set_color", "target_id": "nope", "color": "ink"}
    )
    assert error.json_pointer == "/commands/1/target_id"
    assert error.context["reason"] == "unknown_target"
    _, alone = edited(first)  # the first command alone was valid
    assert op(0, 0, normalize_document(alone.document))["color"] == "ink"


def test_ac2_stale_revision_is_an_edit_conflict() -> None:
    document = fixture_document()
    stale = batch(document, {"type": "set_visibility", "target_id": "body", "visible": False})
    stale["base_revision"] = 0
    with pytest.raises(errors.EditConflict) as caught:
        apply_batch(document, stale)
    error = caught.value
    assert (error.code, error.exit_code, error.json_pointer) == (
        "EDIT_CONFLICT",
        4,
        "/base_revision",
    )
    assert error.context["reason"] == "stale_revision"
    assert error.context["current_revision"] == 1


def test_ac2_a_previous_revision_cannot_be_reused_after_an_edit() -> None:
    document = fixture_document()
    edit = batch(document, {"type": "set_visibility", "target_id": "body", "visible": False})
    newer = apply_edit(document, edit)
    with pytest.raises(errors.EditConflict):
        apply_edit(newer, edit)


# --- T3 ----------------------------------------------------------------------------


def test_t3_branches_with_the_same_revision_reject_each_other() -> None:
    other = tree()
    other["palette"]["colors"][2]["rgba"] = "#00AA00FF"  # same revision, other content
    branch_a, branch_b = fixture_document(), validate_document(other)
    assert branch_a.revision == branch_b.revision == 1
    command = {"type": "set_color", "target_id": "button", "color": "spare"}
    for source, target in ((branch_a, branch_b), (branch_b, branch_a)):
        with pytest.raises(errors.EditConflict) as caught:
            apply_batch(target, batch(source, command))
        assert caught.value.context["reason"] == "snapshot_mismatch"
        assert caught.value.json_pointer == "/base_snapshot"
        assert caught.value.context["current_snapshot"] == snapshot_digest(target)
        assert apply_batch(source, batch(source, command)).revision == 2


# --- T2 ----------------------------------------------------------------------------


def test_t2_source_document_is_byte_identical_after_success_and_failure() -> None:
    path = SPECS / "minimal.moana.json"
    raw = path.read_bytes()
    document = validate_document(raw)
    canonical = canonical_json(document)
    apply_batch(document, load("recolor.edit.json"))
    with pytest.raises(errors.ReferenceError):
        apply_batch(
            document,
            batch(document, {"type": "set_color", "target_id": "body_fill", "color": "nope"}),
        )
    assert canonical_json(document) == canonical
    assert path.read_bytes() == raw
    assert document == validate_document(raw)


def rgba_at(result: Any, x: int, y: int) -> bytes:
    start = (y * result.width + x) * 4
    pixels: bytes = result.rgba[start : start + 4]
    return pixels


def test_t2_render_before_and_after_a_recolor() -> None:
    document = validate_document(load("minimal.moana.json"))
    edited_document = apply_edit(document, load("recolor.edit.json"))
    before, after = render(document), render(edited_document)
    assert rgba_at(before, 40, 32) == bytes.fromhex("36AFA5FF")  # cloth
    assert rgba_at(after, 40, 32) == bytes.fromhex("182338FF")  # ink
    assert rgba_at(after, 39, 32) == rgba_at(before, 39, 32) == bytes(4)
    assert before.digest != after.digest


@pytest.mark.parametrize(
    "commands",
    [
        [{"type": "reorder", "target_id": "white", "after_id": "iris"}],
        [{"type": "reorder", "target_id": "eyes_open", "after_id": "face_shape"}],
        [{"type": "reorder", "target_id": "eye_right", "after_id": None}],
        [{"type": "set_visibility", "target_id": "face", "visible": True}],
        [
            {"type": "translate", "target_id": "iris_left", "dx": 3, "dy": 0},
            {"type": "translate", "target_id": "iris_left", "dx": -3, "dy": 0},
        ],
    ],
)
def test_t2_batch_without_visual_change_keeps_the_visual_digest(commands: list[Tree]) -> None:
    document = validate_document(load("masked-eyes.moana.json"))
    result = apply_batch(document, batch(document, *commands))
    assert render(result.document).digest == render(document).digest
    assert result.revision == document.revision + 1
    assert result.snapshot != snapshot_digest(document)


# --- T1: set_color -----------------------------------------------------------------


def test_t1_set_color_negative_cases() -> None:
    error = failure(
        errors.ReferenceError, {"type": "set_color", "target_id": "belt", "color": "nope"}
    )
    assert (error.json_pointer, error.context["reason"]) == ("/commands/0/color", "unknown_color")
    error = failure(
        errors.ValidationError, {"type": "set_color", "target_id": "body", "color": "ink"}
    )
    assert error.context["reason"] == "invalid_target"
    assert (error.context["kind"], error.context["expected"]) == ("layer", ("operation",))
    error = failure(
        errors.ValidationError, {"type": "set_color", "target_id": "frame_px", "color": "cloth"}
    )
    assert (error.json_pointer, error.context["reason"]) == ("/commands/0", "locked_layer")


# --- T1: set_geometry --------------------------------------------------------------

GEOMETRIES: list[tuple[str, Tree, tuple[str, ...], str]] = [
    ("body_fill", {"box": [1, 1, 3, 3]}, ("layers", "0", "operations", "0"), "box"),
    ("belt", {"start": [0, 0], "end": [4, 4]}, ("layers", "0", "operations", "1"), "start"),
    ("button", {"at": [7, 7]}, ("layers", "0", "operations", "2"), "at"),
    ("head_fill", {"box": [0, 0, 8, 4]}, ("layers", "1", "operations", "0"), "box"),
    ("hat", {"points": [[0, 0], [4, 0], [0, 4]]}, ("layers", "1", "operations", "1"), "points"),
    (
        "feather",
        {"commands": [["M", 0, 0], ["Q", 256, 0, 256, 256], ["Z"]]},
        ("layers", "1", "operations", "2"),
        "commands",
    ),
    ("head_box", {"box": [0, 0, 16, 6]}, ("masks", "1"), "box"),
]


def node_at(source: Tree, path: tuple[str, ...]) -> Tree:
    node: Any = source
    for key in path:
        node = node[int(key)] if isinstance(node, list) else node[key]
    assert isinstance(node, dict)
    return node


@pytest.mark.parametrize(("target", "geometry", "path", "member"), GEOMETRIES)
def test_t1_set_geometry_replaces_the_geometric_members(
    target: str, geometry: Tree, path: tuple[str, ...], member: str
) -> None:
    _, result = edited({"type": "set_geometry", "target_id": target, "geometry": geometry})
    expected = tree()
    node_at(expected, path).update(copy.deepcopy(geometry))
    expect_tree(result, expected)
    assert result.affected_ids == (target,)


@pytest.mark.parametrize(
    ("geometry", "reason"),
    [
        ({"box": [1, 1, 3, 3], "color": "ink"}, "geometry_members"),
        ({"at": [1, 1]}, "geometry_members"),
        ({}, "geometry_members"),
    ],
)
def test_t1_set_geometry_needs_exactly_the_members_of_the_type(geometry: Tree, reason: str) -> None:
    error = failure(
        errors.ValidationError,
        {"type": "set_geometry", "target_id": "body_fill", "geometry": geometry},
    )
    assert (error.json_pointer, error.context["reason"]) == ("/commands/0/geometry", reason)
    assert error.context["expected"] == ("box",)


def test_t1_set_geometry_validates_with_the_schema_rules() -> None:
    error = failure(
        errors.ValidationError,
        {"type": "set_geometry", "target_id": "body_fill", "geometry": {"box": [5, 5, 1, 1]}},
    )
    assert error.json_pointer == "/commands/0/geometry/box"
    assert error.context["reason"] == "invalid_node"
    assert error.details[0].context["reason"] == "box_empty_or_inverted"
    error = failure(
        errors.ValidationError,
        {"type": "set_geometry", "target_id": "feather", "geometry": {"commands": [["Z"]]}},
    )
    assert (error.json_pointer, error.context["reason"]) == (
        "/commands/0/geometry/commands",
        "invalid_node",
    )
    assert [d.context["reason"] for d in error.details] == ["too_short"]
    error = failure(
        errors.ValidationError,
        {"type": "set_geometry", "target_id": "head_mask", "geometry": {"masks": ["a", "b"]}},
    )
    assert (error.json_pointer, error.context["reason"]) == (
        "/commands/0/target_id",
        "not_geometric",
    )


# --- T1: translate -----------------------------------------------------------------


def test_t1_translate_moves_every_geometric_member() -> None:
    names = ("body_fill", "belt", "button", "head_fill", "hat", "feather", "head_dot")
    _, result = edited(*({"type": "translate", "target_id": n, "dx": 1, "dy": -1} for n in names))
    expected = tree()
    body, head = expected["layers"][0]["operations"], expected["layers"][1]["operations"]
    body[0]["box"] = [3, 1, 11, 11]
    body[1]["start"], body[1]["end"] = [3, 7], [10, 7]
    body[2]["at"] = [6, 4]
    head[0]["box"] = [4, -1, 10, 4]
    head[1]["points"] = [[4, -1], [10, -1], [7, 1]]
    head[2]["commands"] = [["M", 512, 0], ["L", 1024, 0], ["L", 768, 512], ["Z"]]
    expected["masks"][2]["at"] = [13, 11]
    expect_tree(result, expected)
    assert result.affected_ids == names


def test_t1_translate_negative_cases() -> None:
    error = failure(
        errors.ValidationError,
        {"type": "translate", "target_id": "head_mask", "dx": 1, "dy": 1},
    )
    assert error.context["reason"] == "not_geometric"
    error = failure(
        errors.ValidationError, {"type": "translate", "target_id": "frame_px", "dx": 1, "dy": 1}
    )
    assert error.context["reason"] == "locked_layer"


# --- T1: set_visibility and replace_palette_color ----------------------------------


def test_t1_set_visibility() -> None:
    _, result = edited({"type": "set_visibility", "target_id": "head", "visible": False})
    expected = tree()
    expected["layers"][1]["visible"] = False
    expect_tree(result, expected)
    error = failure(
        errors.ValidationError, {"type": "set_visibility", "target_id": "belt", "visible": False}
    )
    assert error.context["reason"] == "invalid_target"
    error = failure(
        errors.ValidationError, {"type": "set_visibility", "target_id": "frame", "visible": False}
    )
    assert error.context["reason"] == "locked_layer"


def test_t1_replace_palette_color_changes_every_consumer() -> None:
    document = validate_document(load("minimal.moana.json"))
    command = {"type": "replace_palette_color", "target_id": "cloth", "rgba": "#ff0000ff"}
    result = apply_batch(document, batch(document, command))
    assert result.document.palette.colors[1].rgba == "#FF0000FF"
    assert rgba_at(render(result.document), 50, 50) == bytes.fromhex("FF0000FF")
    error = failure(
        errors.ValidationError,
        {"type": "replace_palette_color", "target_id": "belt", "rgba": "#FF0000FF"},
    )
    assert error.context["reason"] == "invalid_target"


def test_t1_replace_palette_color_result_must_respect_the_profile() -> None:
    error = failure(
        errors.ValidationError,
        {"type": "replace_palette_color", "target_id": "spare", "rgba": "#FF000080"},
    )
    assert error.context["reason"] == "invalid_result"
    assert error.json_pointer == "/palette/colors/2/rgba"
    assert error.details[0].context["reason"] == "partial_alpha"


# --- T1: insert_operation ----------------------------------------------------------

NEW_OP: Tree = {"id": "patch", "type": "rect", "box": [0, 0, 2, 2], "color": "spare"}


def insert(after_id: str | None, operation: Tree = NEW_OP, layer_id: str = "body") -> Tree:
    return {
        "type": "insert_operation",
        "layer_id": layer_id,
        "after_id": after_id,
        "operation": copy.deepcopy(operation),
    }


def test_t1_insert_operation_at_the_start_and_after_a_sibling() -> None:
    _, result = edited(insert(None))
    expected = tree()
    expected["layers"][0]["operations"].insert(0, copy.deepcopy(NEW_OP))
    expect_tree(result, expected)
    assert result.affected_ids == ("patch",)
    _, result = edited(insert("belt"))
    expected = tree()
    expected["layers"][0]["operations"].insert(2, copy.deepcopy(NEW_OP))
    expect_tree(result, expected)


@pytest.mark.parametrize(
    ("command", "kind", "pointer", "reason"),
    [
        (
            insert(None, {**NEW_OP, "id": "belt"}),
            errors.ValidationError,
            "/operation/id",
            "duplicate_id",
        ),
        (
            insert(None, {**NEW_OP, "color": "nope"}),
            errors.ReferenceError,
            "/operation/color",
            "unknown_color",
        ),
        (insert("hat"), errors.ValidationError, "/after_id", "not_in_container"),
        (insert("nope"), errors.ReferenceError, "/after_id", "unknown_target"),
        (insert(None, layer_id="frame"), errors.ValidationError, "", "locked_layer"),
        (insert(None, layer_id="belt"), errors.ValidationError, "/layer_id", "invalid_target"),
        (
            insert(None, {**NEW_OP, "box": [3, 3, 1, 1]}),
            errors.ValidationError,
            "/operation/box",
            "invalid_node",
        ),
        (
            insert(None, {"id": "fill", "type": "flood_fill", "color": "ink"}),
            errors.UnsupportedOperation,
            "/operation/type",
            "invalid_node",
        ),
    ],
)
def test_t1_insert_operation_negative_cases(
    command: Tree, kind: type[errors.MoanaError], pointer: str, reason: str
) -> None:
    error = failure(kind, command)
    assert type(error) is kind
    assert (error.json_pointer, error.context["reason"]) == (f"/commands/0{pointer}", reason)


# --- T1: remove and live references ------------------------------------------------


@pytest.mark.parametrize(
    ("target", "removed"),
    [
        ("button", ("button",)),
        ("free_mask", ("free_mask",)),
        ("belt_region", ("belt_region",)),
        ("spare", ("spare",)),
        ("shade", ("shade",)),
        ("head", ("head", "head_fill", "hat", "feather")),
    ],
)
def test_t1_remove_unreferenced_nodes(target: str, removed: tuple[str, ...]) -> None:
    _, result = edited({"type": "remove", "target_id": target})
    assert result.affected_ids == removed
    expected = tree()
    collections = (
        expected["palette"]["colors"],
        expected["palette"]["ramps"],
        expected["layers"],
        expected["layers"][0]["operations"],
        expected["masks"],
        expected["regions"],
    )
    for collection in collections:
        collection[:] = [item for item in collection if item["id"] != target]
    expect_tree(result, expected)


@pytest.mark.parametrize(
    ("target", "references"),
    [
        ("belt", ["/regions/0/operation_ids/0"]),
        ("body", ["/regions/0/operation_ids/0"]),
        ("head_box", ["/masks/0/masks/0", "/regions/0/mask_id"]),
        ("head_mask", ["/layers/1/mask_id"]),
        (
            "cloth",
            [
                "/palette/ramps/0/colors/1",
                "/layers/0/operations/0/color",
                "/layers/1/operations/0/color",
            ],
        ),
    ],
)
def test_t1_remove_rejects_live_references(target: str, references: list[str]) -> None:
    error = failure(errors.ReferenceError, {"type": "remove", "target_id": target})
    assert (error.json_pointer, error.context["reason"]) == (
        "/commands/0/target_id",
        "live_reference",
    )
    assert [detail.json_pointer for detail in error.details] == references
    assert error.context["reference_count"] == len(references)


def test_t1_remove_after_the_referrer_is_gone() -> None:
    _, result = edited(
        {"type": "remove", "target_id": "belt_region"}, {"type": "remove", "target_id": "belt"}
    )
    assert result.affected_ids == ("belt_region", "belt")
    assert [o.id for o in result.document.layers[0].operations] == ["body_fill", "button"]


def test_t1_remove_negative_cases() -> None:
    error = failure(errors.ValidationError, {"type": "remove", "target_id": "frame"})
    assert error.context["reason"] == "locked_layer"
    error = failure(errors.ValidationError, {"type": "remove", "target_id": "hero"})
    assert (error.context["reason"], error.context["kind"]) == ("invalid_target", "document")
    error = failure(errors.ValidationError, {"type": "remove", "target_id": "pal"})
    assert error.context["kind"] == "palette"
    error = failure(errors.ReferenceError, {"type": "remove", "target_id": "ghost"})
    assert error.context["reason"] == "unknown_target"
    error = failure(
        errors.ReferenceError,
        {"type": "remove", "target_id": "button"},
        {"type": "set_color", "target_id": "button", "color": "ink"},
    )
    assert error.json_pointer == "/commands/1/target_id"


# --- T1: reorder -------------------------------------------------------------------


def reorder(target: str, after: str | None) -> Tree:
    return {"type": "reorder", "target_id": target, "after_id": after}


def test_t1_reorder_to_the_start_and_after_a_sibling() -> None:
    _, result = edited(reorder("button", None))
    expected = tree()
    body = expected["layers"][0]["operations"]
    body.insert(0, body.pop(2))
    expect_tree(result, expected)
    _, result = edited(reorder("body_fill", "button"), reorder("body", "head"))
    expected = tree()
    body = expected["layers"][0]["operations"]
    body.append(body.pop(0))
    expected["layers"].insert(1, expected["layers"].pop(0))
    expect_tree(result, expected)
    assert [layer.id for layer in result.document.layers] == ["head", "body", "frame"]


def test_t1_reorder_layers_masks_colors_and_regions() -> None:
    _, result = edited(
        reorder("head", None),
        reorder("ink", "spare"),
        reorder("head_mask", "free_mask"),
        reorder("belt_region", None),
        reorder("shade", None),
        reorder("hat", "feather"),
    )
    expected = tree()
    expected["layers"].insert(0, expected["layers"].pop(1))
    colors = expected["palette"]["colors"]
    colors.append(colors.pop(0))
    expected["masks"].insert(3, expected["masks"].pop(0))
    head = expected["layers"][0]["operations"]
    head.append(head.pop(1))
    expect_tree(result, expected)


@pytest.mark.parametrize(
    ("command", "kind", "pointer", "reason"),
    [
        (reorder("belt", "belt"), errors.ValidationError, "/after_id", "after_self"),
        (reorder("belt", "hat"), errors.ValidationError, "/after_id", "not_in_container"),
        (reorder("belt", "head"), errors.ValidationError, "/after_id", "not_in_container"),
        (reorder("belt", "ghost"), errors.ReferenceError, "/after_id", "unknown_target"),
        (reorder("frame", None), errors.ValidationError, "", "locked_layer"),
        (reorder("frame_px", None), errors.ValidationError, "", "locked_layer"),
        (reorder("hero", None), errors.ValidationError, "/target_id", "invalid_target"),
    ],
)
def test_t1_reorder_negative_cases(
    command: Tree, kind: type[errors.MoanaError], pointer: str, reason: str
) -> None:
    error = failure(kind, command)
    assert (error.json_pointer, error.context["reason"]) == (f"/commands/0{pointer}", reason)


def test_t1_reorder_keeps_references_alive() -> None:
    document = validate_document(load("masked-eyes.moana.json"))
    commands = [reorder("lid", None), reorder("eyes", "face_shape"), reorder("iris_right", None)]
    result = apply_batch(document, batch(document, *commands))
    assert {m.id for m in result.document.masks} == {m.id for m in document.masks}
    assert result.document.regions == document.regions


# --- result, limits and arguments --------------------------------------------------


def test_result_mapping_and_unique_affected_ids() -> None:
    _, result = edited(
        {"type": "set_color", "target_id": "belt", "color": "spare"},
        {"type": "translate", "target_id": "belt", "dx": 1, "dy": 0},
    )
    assert result.affected_ids == ("belt",)
    mapping = result.to_mapping()
    assert list(mapping) == sorted(mapping)
    assert mapping["document"] == normalize_document(result.document)
    assert (mapping["revision"], mapping["base_revision"], mapping["document_id"]) == (2, 1, "hero")
    assert mapping["snapshot_digest"] == result.snapshot


def test_revision_overflow_is_rejected_before_any_command() -> None:
    source = tree()
    source["revision"] = MAX_REVISION
    document = validate_document(source)
    with pytest.raises(errors.ValidationError) as caught:
        apply_batch(document, batch(document, {"type": "remove", "target_id": "ghost"}))
    assert (caught.value.json_pointer, caught.value.context["reason"]) == (
        "/base_revision",
        "revision_overflow",
    )


def test_result_over_the_parse_limits_is_an_invalid_result() -> None:
    document = validate_document(load("minimal.moana.json"))
    edit = load("recolor.edit.json")
    with pytest.raises(errors.ValidationError) as caught:
        apply_batch(document, edit, limits=ParseLimits(max_nodes=20))
    error = caught.value
    assert error.context["reason"] == "invalid_result"
    assert [detail.context["reason"] for detail in error.details] == ["too_many_nodes"]


def test_arguments_are_type_checked() -> None:
    document = fixture_document()
    with pytest.raises(TypeError, match="Document"):
        apply_batch(normalize_document(document), {})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ParseLimits"):
        apply_batch(document, {}, limits=1)  # type: ignore[arg-type]


def test_the_largest_batch_is_accepted() -> None:
    document = fixture_document()
    toggles = [
        {"type": "set_visibility", "target_id": "body", "visible": i % 2 == 0}
        for i in range(MAX_EDIT_COMMANDS)
    ]
    assert apply_batch(document, batch(document, *toggles)).revision == 2


# --- property: any failing batch leaves the document intact -------------------------

VALID_COMMANDS = st.one_of(
    st.builds(
        lambda target, color: {"type": "set_color", "target_id": target, "color": color},
        st.sampled_from(["body_fill", "belt", "button", "head_fill", "hat", "feather"]),
        st.sampled_from(["ink", "cloth", "spare"]),
    ),
    st.builds(
        lambda target, dx, dy: {"type": "translate", "target_id": target, "dx": dx, "dy": dy},
        st.sampled_from(["body_fill", "belt", "button", "hat", "head_dot", "free_mask"]),
        st.integers(-8, 8),
        st.integers(-8, 8),
    ),
    st.builds(
        lambda target, visible: {"type": "set_visibility", "target_id": target, "visible": visible},
        st.sampled_from(["body", "head"]),
        st.booleans(),
    ),
    st.builds(reorder, st.sampled_from(["body_fill", "belt", "button"]), st.none()),
)
INVALID_COMMANDS = st.sampled_from(
    [
        {"type": "set_color", "target_id": "belt", "color": "nope"},
        {"type": "remove", "target_id": "cloth"},
        {"type": "set_visibility", "target_id": "frame", "visible": False},
        {"type": "translate", "target_id": "button", "dx": MAX_TRANSLATION, "dy": 0},
        reorder("belt", "hat"),
    ]
)


@settings(max_examples=60, deadline=None)
@given(prefix=st.lists(VALID_COMMANDS, max_size=8), last=INVALID_COMMANDS)
def test_property_failing_batch_is_all_or_nothing(prefix: list[Tree], last: Tree) -> None:
    document = fixture_document()
    before = canonical_json(document)
    with pytest.raises(errors.MoanaError):
        apply_batch(document, batch(document, *prefix, last))
    assert canonical_json(document) == before
    if prefix:
        result = apply_batch(document, batch(document, *prefix))
        assert result.revision == document.revision + 1
        assert {o.id for layer in result.document.layers for o in layer.operations} == {
            o.id for layer in document.layers for o in layer.operations
        }


# --- review additions: member table, masks, ranges, reuse and robustness -----------


@pytest.mark.parametrize(
    ("target", "member", "dx"),
    [
        ("button", "at", MAX_TRANSLATION),
        ("body_fill", "box", 1_048_576 - 2),  # x0 reaches the maximum, x1 passes it
        ("hat", "points", -MAX_TRANSLATION),
        ("feather", "commands", MAX_TRANSLATION),
    ],
)
def test_translate_out_of_range_names_the_member(target: str, member: str, dx: int) -> None:
    error = failure(
        errors.ValidationError, {"type": "translate", "target_id": target, "dx": dx, "dy": 0}
    )
    assert (error.json_pointer, error.context["reason"]) == ("/commands/0", "out_of_range")
    assert error.context["member"] == member


def test_translate_and_set_geometry_on_mask_leaves() -> None:
    _, result = edited(
        {"type": "translate", "target_id": "wing", "dx": 2, "dy": 1},
        {"type": "translate", "target_id": "seam", "dx": 0, "dy": -1},
        {"type": "translate", "target_id": "tri", "dx": 1, "dy": 1},
        {"type": "translate", "target_id": "free_mask", "dx": 1, "dy": 0},
    )
    expected = tree()
    masks = expected["masks"]
    masks[4]["commands"] = [["M", 512, 256], ["L", 1024, 256], ["L", 512, 768], ["Z"]]
    masks[5]["start"], masks[5]["end"] = [0, 14], [15, 14]
    masks[6]["points"] = [[1, 1], [4, 1], [1, 4]]
    masks[3]["box"] = [1, 0, 5, 4]
    expect_tree(result, expected)
    wing = {"commands": [["M", 0, 0], ["L", 256, 0], ["L", 0, 256], ["Z"]]}
    seam = {"start": [1, 1], "end": [2, 2]}
    tri = {"points": [[0, 0], [1, 0], [0, 1]]}
    _, result = edited(
        {"type": "set_geometry", "target_id": "wing", "geometry": wing},
        {"type": "set_geometry", "target_id": "seam", "geometry": seam},
        {"type": "set_geometry", "target_id": "tri", "geometry": tri},
        {"type": "set_geometry", "target_id": "free_mask", "geometry": {"box": [0, 0, 2, 2]}},
    )
    expected = tree()
    masks = expected["masks"]
    masks[4].update(copy.deepcopy(wing))
    masks[5].update(copy.deepcopy(seam))
    masks[6].update(copy.deepcopy(tri))
    masks[3]["box"] = [0, 0, 2, 2]
    expect_tree(result, expected)


def test_path_mask_referenced_by_a_region_is_live() -> None:
    error = failure(errors.ReferenceError, {"type": "remove", "target_id": "wing"})
    assert [d.json_pointer for d in error.details] == ["/regions/1/mask_id"]
    _, result = edited(
        {"type": "remove", "target_id": "wing_region"}, {"type": "remove", "target_id": "wing"}
    )
    assert [m.id for m in result.document.masks][-2:] == ["seam", "tri"]


@pytest.mark.parametrize(
    "command",
    [
        {"type": "translate", "target_id": "belt_region", "dx": 1, "dy": 0},
        {"type": "set_geometry", "target_id": "belt_region", "geometry": {"box": [0, 0, 1, 1]}},
    ],
)
def test_regions_are_not_geometric_targets(command: Tree) -> None:
    error = failure(errors.ValidationError, command)
    assert error.json_pointer == "/commands/0/target_id"
    assert (error.context["reason"], error.context["kind"]) == ("invalid_target", "region")


def test_replace_palette_color_reaches_locked_layers() -> None:
    command = {"type": "replace_palette_color", "target_id": "ink", "rgba": "#000000FF"}
    _, result = edited(command)
    expected = tree()
    expected["palette"]["colors"][0]["rgba"] = "#000000FF"
    expect_tree(result, expected)
    assert rgba_at(render(result.document), 0, 0) == bytes.fromhex("000000FF")  # frame_px


@pytest.mark.parametrize("layer_id", ["body", "head"])
def test_removed_id_cannot_be_reinserted_in_the_same_batch(layer_id: str) -> None:
    again = {"id": "button", "type": "pixel", "at": [1, 1], "color": "ink"}
    error = failure(
        errors.ValidationError,
        {"type": "remove", "target_id": "button"},
        insert(None, again, layer_id=layer_id),
    )
    assert error.json_pointer == "/commands/1/operation/id"
    assert error.context["reason"] == "reused_id"


@pytest.mark.parametrize("taken", ["hero", "pal", "ink", "shade", "belt_region", "head_mask"])
def test_inserted_id_must_be_new_in_the_whole_document(taken: str) -> None:
    error = failure(errors.ValidationError, insert(None, {**NEW_OP, "id": taken}))
    assert error.json_pointer == "/commands/0/operation/id"
    assert error.context["reason"] == "duplicate_id"


def test_inserted_id_must_be_new_within_the_batch() -> None:
    error = failure(errors.ValidationError, insert(None), insert("belt"))
    assert error.json_pointer == "/commands/1/operation/id"
    assert error.context["reason"] == "duplicate_id"


def test_a_failure_in_the_final_validation_rolls_everything_back() -> None:
    error = failure(
        errors.ValidationError,
        {"type": "set_color", "target_id": "belt", "color": "spare"},
        {"type": "replace_palette_color", "target_id": "spare", "rgba": "#FF000080"},
    )
    assert error.context["reason"] == "invalid_result"


def minimal_document() -> Document:
    return validate_document(load("minimal.moana.json"))


NO_OPS: list[tuple[Any, list[Tree], set[str]]] = [
    (fixture_document, [reorder("belt", "body_fill")], {"/revision"}),
    (
        fixture_document,
        [
            {"type": "set_color", "target_id": "belt", "color": "spare"},
            {"type": "set_color", "target_id": "belt", "color": "cloth"},
        ],
        {"/revision", "/layers/0/operations/1/color"},
    ),
    (
        fixture_document,
        [{"type": "translate", "target_id": "button", "dx": 100, "dy": -50}],
        {"/revision", "/layers/0/operations/2/at/0", "/layers/0/operations/2/at/1"},
    ),
    (minimal_document, [{"type": "remove", "target_id": "body"}], {"/revision", "/layers"}),
]


@pytest.mark.parametrize(("source", "commands", "changed"), NO_OPS)
def test_no_op_and_off_canvas_batches_still_bump_the_revision(
    source: Any, commands: list[Tree], changed: set[str]
) -> None:
    document: Document = source()
    result = apply_batch(document, batch(document, *commands))
    before, after = normalize_document(document), normalize_document(result.document)
    assert changed_pointers(before, after) == changed
    assert result.document.revision == document.revision + 1


def test_off_canvas_translate_and_empty_layers_render_as_expected() -> None:
    document = fixture_document()
    moved = apply_edit(
        document, batch(document, {"type": "translate", "target_id": "button", "dx": 100, "dy": 0})
    )
    gone = apply_edit(document, batch(document, {"type": "remove", "target_id": "button"}))
    assert op(0, 2, normalize_document(moved))["at"] == [105, 5]
    assert render(moved).rgba == render(gone).rgba
    empty = minimal_document()
    cleared = apply_edit(empty, batch(empty, {"type": "remove", "target_id": "body"}))
    assert render(cleared).rgba == bytes(128 * 128 * 4)


def test_unvalidated_models_fail_cleanly() -> None:
    document = fixture_document()
    snapshot = snapshot_digest(document)
    unknown = EditBatch.model_construct(
        schema_version="1.0", base_revision=1, base_snapshot=snapshot, commands=(object(),)
    )
    with pytest.raises(errors.ValidationError) as caught:
        apply_batch(document, unknown)
    assert caught.value.json_pointer == "/commands/0"
    assert caught.value.context["reason"] == "unknown_command"
    broken = SetColor.model_construct(type="set_color", color="ink")  # no target_id
    malformed = EditBatch.model_construct(
        schema_version="1.0", base_revision=1, base_snapshot=snapshot, commands=(broken,)
    )
    with pytest.raises(errors.ValidationError) as caught:
        apply_batch(document, malformed)
    assert caught.value.json_pointer == "/commands/0"
    assert caught.value.context["reason"] == "invalid_source"


def corrupted(layer_index: int, index: int, member: str, value: object) -> Document:
    """The fixture with one operation member replaced without validation."""
    valid = fixture_document()
    layer = valid.layers[layer_index]
    operation = layer.operations[index]
    bad = operation.model_construct(**{**dict(operation), member: value})
    operations = tuple(bad if i == index else o for i, o in enumerate(layer.operations))
    bad_layer = layer.model_construct(**{**dict(layer), "operations": operations})
    layers = tuple(bad_layer if i == layer_index else x for i, x in enumerate(valid.layers))
    return valid.model_construct(**{**dict(valid), "layers": layers})


@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings:UserWarning")
@pytest.mark.parametrize(
    ("layer", "index", "member", "value", "target"),
    [(0, 2, "at", "x", "button"), (1, 1, "points", "x", "hat")],
)
def test_unvalidated_documents_fail_cleanly(
    layer: int, index: int, member: str, value: object, target: str
) -> None:
    document = corrupted(layer, index, member, value)
    command = {"type": "translate", "target_id": target, "dx": 1, "dy": 0}
    with pytest.raises(errors.ValidationError) as caught:
        apply_batch(document, batch(document, command))
    assert caught.value.context["reason"] == "invalid_source"


def test_worst_case_translate_batch_stays_linear(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-024 point 9: per command one linear reindex, no node revalidation.

    The cost is bounded by counting the expensive steps, not by wall-clock time (a
    30 s threshold failed on loaded CI runners under coverage): revalidating the
    3001-command path on every ``translate`` is what made this batch take tens of
    seconds, and a single full validation of the result is the only one allowed.
    """
    calls = {"index_nodes": 0, "node_validation": 0, "document_validation": 0}

    def counting(name: str, original: Any) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            calls[name] += 1
            return original(*args, **kwargs)

        return call

    monkeypatch.setattr(apply, "index_nodes", counting("index_nodes", index_nodes))
    monkeypatch.setattr(apply, "_validated", counting("node_validation", apply._validated))
    monkeypatch.setattr(
        apply, "validate_document", counting("document_validation", validate_document)
    )
    source = load("minimal.moana.json")
    commands: list[list[object]] = [["M", 0, 0]]
    commands += [["L", (i % 50) * 256, (i // 50) * 256] for i in range(2999)]
    commands.append(["Z"])
    path = {"id": "big", "type": "path", "backend": "aggdraw-v1", "color": "ink"}
    source["layers"][0]["operations"].append({**path, "commands": commands})
    document = validate_document(source)
    for size in (MAX_EDIT_COMMANDS // 4, MAX_EDIT_COMMANDS):  # counts must scale linearly
        calls.update(dict.fromkeys(calls, 0))
        moves = [
            {"type": "translate", "target_id": "big", "dx": 1 if i % 2 else -1, "dy": 0}
            for i in range(size)
        ]
        started = time.perf_counter()
        result = apply_batch(document, batch(document, *moves))
        elapsed = time.perf_counter() - started
        assert calls == {"index_nodes": size, "node_validation": 0, "document_validation": 1}
        assert elapsed < 300  # hang guard only: about 2 s on a laptop, 33 s on a CI runner
        layers = normalize_document(result.document)["layers"]
        assert layers == normalize_document(document)["layers"]


ORACLE_COMMANDS = st.one_of(
    st.builds(
        lambda target, color: {"type": "set_color", "target_id": target, "color": color},
        st.sampled_from(["body_fill", "belt", "button", "head_fill", "hat", "feather"]),
        st.sampled_from(["ink", "cloth", "spare"]),
    ),
    st.builds(
        lambda target, visible: {"type": "set_visibility", "target_id": target, "visible": visible},
        st.sampled_from(["body", "head"]),
        st.booleans(),
    ),
)


def oracle(commands: list[Tree]) -> Tree:
    """Minimal independent model of set_color and set_visibility on the fixture."""
    expected = tree()
    by_id = {o["id"]: o for layer in expected["layers"] for o in layer["operations"]}
    layers = {layer["id"]: layer for layer in expected["layers"]}
    for command in commands:
        if command["type"] == "set_color":
            by_id[command["target_id"]]["color"] = command["color"]
        else:
            layers[command["target_id"]]["visible"] = command["visible"]
    return expected


@settings(max_examples=60, deadline=None)
@given(commands=st.lists(ORACLE_COMMANDS, min_size=1, max_size=10))
def test_property_matches_a_minimal_oracle(commands: list[Tree]) -> None:
    _, result = edited(*commands)
    expect_tree(result, oracle(commands))
