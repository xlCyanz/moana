"""AC2 (MOANA-015): editing a shadow mask keeps geometry and IDs and gives a local diff.

A ``shade`` (ADR-028) has no colour member, one ramp reference and ``bands`` whose
IDs are global and whose masks are ordinary document masks. Moving the shadow
terminator is a ``set_geometry`` on the shadow band's mask: nothing else in the
document changes, and the render changes only inside ``old mask | new mask``.
Expected trees and pixels are written by hand.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moanart.core import errors
from moanart.editing import History, apply_batch
from moanart.render import render
from moanart.schema import Document, normalize_document, snapshot_digest, validate_document

type Tree = dict[str, Any]

T0, T2, T4 = "#202040FF", "#6060A0FF", "#D0D0F0FF"
SOURCE: Tree = {
    "schema_version": "1.0",
    "id": "doc",
    "canvas": {"width": 8, "height": 8},
    "palette": {
        "id": "pal",
        "colors": [{"id": "t0", "rgba": T0}, {"id": "t2", "rgba": T2}, {"id": "t4", "rgba": T4}],
        "ramps": [{"id": "ramp", "colors": ["t0", "t2", "t4"]}],
    },
    "masks": [
        {"id": "whole", "type": "rect", "box": [0, 0, 8, 8]},
        {"id": "shadow", "type": "rect", "box": [4, 0, 8, 8]},
    ],
    "regions": [{"id": "shadow_region", "mask_id": "shadow", "operation_ids": ["shading"]}],
    "layers": [
        {
            "id": "volume",
            "name": "Volumen",
            "operations": [
                {
                    "id": "shading",
                    "type": "shade",
                    "ramp": "ramp",
                    "ramp_order": "monotonic",
                    # body faces nothing: ambient 1 (t2); shadow faces se: 1 - 1 = 0 (t0)
                    "light": {"direction": "nw", "height": 0, "intensity": 1, "ambient": 1},
                    "bands": [
                        {"id": "body", "mask_id": "whole", "facing": "none", "offset": 0},
                        {"id": "core_shadow", "mask_id": "shadow", "facing": "se", "offset": 0},
                    ],
                }
            ],
        }
    ],
}
DARK, MID = (0x20, 0x20, 0x40, 0xFF), (0x60, 0x60, 0xA0, 0xFF)


def document() -> Document:
    return validate_document(copy.deepcopy(SOURCE))


def batch(base: Document, *commands: Tree) -> Tree:
    return {
        "schema_version": "1.0",
        "base_revision": base.revision,
        "base_snapshot": snapshot_digest(base),
        "commands": list(commands),
    }


def move_shadow(box: list[int]) -> Tree:
    return {"type": "set_geometry", "target_id": "shadow", "geometry": {"box": box}}


def pixels(source: Document) -> dict[tuple[int, int], tuple[int, int, int, int]]:
    result = render(source)
    return {(x, y): result.pixel(x, y) for x in range(8) for y in range(8)}


def ids(tree: object) -> list[str]:
    """Every ``id`` member of a JSON tree, in document order."""
    found: list[str] = []
    if isinstance(tree, dict):
        if isinstance(tree.get("id"), str):
            found.append(tree["id"])
        for value in tree.values():
            found.extend(ids(value))
    elif isinstance(tree, list):
        for value in tree:
            found.extend(ids(value))
    return found


def test_ac2_moving_the_shadow_mask_keeps_ids_and_changes_one_column() -> None:
    base = document()
    before = pixels(base)
    assert {before[(x, 0)] for x in range(4)} == {MID} and before[(4, 0)] == DARK
    result = apply_batch(base, batch(base, move_shadow([5, 0, 8, 8])))
    assert result.affected_ids == ("shadow",)
    # the tree is the source with one box changed (and the revision bumped), by hand
    expected = normalize_document(base)
    expected["masks"][1]["box"] = [5, 0, 8, 8]  # type: ignore[index]  # JSON tree
    expected["revision"] = 1
    edited = normalize_document(result.document)
    assert edited == expected
    assert ids(edited) == ids(normalize_document(base))
    # documented local diff: column x = 4 goes from the shadow tone to the body tone
    after = pixels(result.document)
    diff = {point for point in before if before[point] != after[point]}
    assert diff == {(4, y) for y in range(8)}
    assert all(before[p] == DARK and after[p] == MID for p in diff)


@settings(max_examples=60, deadline=None)
@given(
    x0=st.integers(-2, 8),
    y0=st.integers(-2, 8),
    width=st.integers(1, 6),
    height=st.integers(1, 6),
)
def test_ac2_any_shadow_edit_only_changes_pixels_of_the_old_or_new_mask(
    x0: int, y0: int, width: int, height: int
) -> None:
    base = document()
    new_box = [x0, y0, x0 + width, y0 + height]
    edited = apply_batch(base, batch(base, move_shadow(new_box))).document
    before, after = pixels(base), pixels(edited)
    old_mask = {(x, y) for x in range(4, 8) for y in range(8)}
    new_mask = {
        (x, y)
        for x in range(max(x0, 0), min(x0 + width, 8))
        for y in range(max(y0, 0), min(y0 + height, 8))
    }
    diff = {point for point in before if before[point] != after[point]}
    assert diff == old_mask ^ new_mask  # symmetric difference: exactly the moved terminator
    assert set(after.values()) <= {DARK, MID}


def test_history_undoes_and_redoes_a_shadow_edit() -> None:
    base = document()
    history = History.start(base)
    edited = history.edit(batch(base, move_shadow([6, 0, 8, 8])))
    undone = edited.undo()
    assert undone.document == base and pixels(undone.document) == pixels(base)
    assert pixels(undone.redo().document) == pixels(edited.document)


def failure(kind: type[errors.MoanArtError], *commands: Tree) -> errors.MoanArtError:
    base = document()
    with pytest.raises(kind) as caught:
        apply_batch(base, batch(base, *commands))
    return caught.value


@pytest.mark.parametrize(
    ("target", "pointer"),
    [
        ("shadow", "/layers/0/operations/0/bands/1/mask_id"),
        ("ramp", "/layers/0/operations/0/ramp"),
    ],
)
def test_masks_and_ramps_used_by_a_shade_are_live_references(target: str, pointer: str) -> None:
    error = failure(errors.ReferenceError, {"type": "remove", "target_id": target})
    pointers = [detail.json_pointer for detail in error.details]
    assert pointer in pointers
    assert {detail.context["reason"] for detail in error.details} == {"live_reference"}


def test_removing_the_shade_releases_its_band_masks() -> None:
    base = document()
    edited = apply_batch(
        base,
        batch(
            base,
            {"type": "remove", "target_id": "shadow_region"},
            {"type": "remove", "target_id": "shading"},
            {"type": "remove", "target_id": "shadow"},
        ),
    )
    # a removed operation contributes its band IDs, which are retired with it (ADR-028 §6)
    assert edited.affected_ids == ("shadow_region", "shading", "body", "core_shadow", "shadow")


def test_commands_that_do_not_apply_to_a_shade() -> None:
    recolour = failure(
        errors.ValidationError, {"type": "set_color", "target_id": "shading", "color": "t0"}
    )
    assert recolour.context["reason"] == "multiple_colors"
    assert recolour.context["color_members"] == 0
    moved = failure(
        errors.ValidationError, {"type": "translate", "target_id": "shading", "dx": 1, "dy": 0}
    )
    assert moved.context["reason"] == "not_geometric"
    band = failure(errors.ValidationError, {"type": "remove", "target_id": "body"})
    assert (band.context["reason"], band.context["kind"]) == ("invalid_target", "item")


def test_a_new_operation_cannot_reuse_a_band_id() -> None:
    error = failure(
        errors.ValidationError,
        {
            "type": "insert_operation",
            "layer_id": "volume",
            "after_id": "shading",
            "operation": {"id": "core_shadow", "type": "pixel", "at": [0, 0], "color": "t4"},
        },
    )
    assert (error.json_pointer, error.context["reason"]) == (
        "/commands/0/operation/id",
        "duplicate_id",
    )


def test_inserting_a_shade_is_validated_like_any_operation() -> None:
    shade = copy.deepcopy(SOURCE["layers"][0]["operations"][0])
    shade["id"] = "shading_2"
    shade["bands"] = [{"id": "rim", "mask_id": "whole", "facing": "n", "offset": 1}]
    base = document()
    edited = apply_batch(
        base,
        batch(
            base,
            {
                "type": "insert_operation",
                "layer_id": "volume",
                "after_id": "shading",
                "operation": shade,
            },
        ),
    )
    assert edited.affected_ids == ("shading_2", "rim")
    # n under a nw light at height 0: exposure 3 * 1, level round(3/6) = 1, so
    # 1 + 1 + 1 = 3, clamped to 2 (t4); the new shade covers the whole canvas
    assert set(pixels(edited.document).values()) == {(0xD0, 0xD0, 0xF0, 0xFF)}


def new_shade(operation_id: str, band_id: str) -> Tree:
    shade = copy.deepcopy(SOURCE["layers"][0]["operations"][0])
    shade["id"] = operation_id
    shade["bands"] = [{"id": band_id, "mask_id": "whole", "facing": "n", "offset": 1}]
    return {
        "type": "insert_operation",
        "layer_id": "volume",
        "after_id": None,
        "operation": shade,
    }


def test_removing_a_shade_retires_its_band_ids() -> None:
    release = (
        {"type": "remove", "target_id": "shadow_region"},
        {"type": "remove", "target_id": "shading"},
    )
    pixel = {"id": "core_shadow", "type": "pixel", "at": [0, 0], "color": "t4"}
    as_operation = failure(
        errors.ValidationError,
        *release,
        {"type": "insert_operation", "layer_id": "volume", "after_id": None, "operation": pixel},
    )
    assert (as_operation.json_pointer, as_operation.context["reason"]) == (
        "/commands/2/operation/id",
        "reused_id",
    )
    as_band = failure(errors.ValidationError, *release, new_shade("shading_2", "body"))
    assert (as_band.json_pointer, as_band.context["reason"]) == (
        "/commands/2/operation/bands/0/id",
        "reused_id",
    )


@pytest.mark.parametrize(
    "band_id",
    [
        "whole",  # a mask ID already in the document
        "core_shadow",  # a band ID of the existing shade
        "shading_2",  # the inserted operation's own ID
    ],
)
def test_an_inserted_band_id_must_be_new(band_id: str) -> None:
    error = failure(errors.ValidationError, new_shade("shading_2", band_id))
    assert (error.json_pointer, error.context["reason"]) == (
        "/commands/0/operation/bands/0/id",
        "duplicate_id",
    )


def test_two_bands_of_one_inserted_shade_cannot_share_an_id() -> None:
    command = new_shade("shading_2", "rim")
    command["operation"]["bands"].append(dict(command["operation"]["bands"][0]))
    error = failure(errors.ValidationError, command)
    assert (error.json_pointer, error.context["reason"]) == (
        "/commands/0/operation/bands/1/id",
        "duplicate_id",
    )


def test_removing_a_layer_reports_the_band_ids_of_its_shades() -> None:
    source = copy.deepcopy(SOURCE)
    source["layers"].append(
        {
            "id": "ink",
            "name": "Tinta",
            "operations": [{"id": "dot", "type": "pixel", "at": [0, 0], "color": "t0"}],
        }
    )
    base = validate_document(source)
    edited = apply_batch(
        base,
        batch(
            base,
            {"type": "remove", "target_id": "shadow_region"},
            {"type": "remove", "target_id": "volume"},
        ),
    )
    assert edited.affected_ids == ("shadow_region", "volume", "shading", "body", "core_shadow")
    assert {"body", "core_shadow"}.isdisjoint(ids(normalize_document(edited.document)))
