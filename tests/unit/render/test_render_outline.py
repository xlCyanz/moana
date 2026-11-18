"""Render, budget and editing of ``outline`` operations (MOANA-014, ADR-027).

T2: the editable ``outline`` operation reproduces the outline mask exactly: its
render paints the hand-computed ring and nothing else. AC1 at document level: holes,
widths 1 and 2 and the canvas edge. ``budget-v6`` figures are computed by hand.
"""

from __future__ import annotations

import tracemalloc
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.api import inspect_document
from moana.core import errors
from moana.core.budget import RenderLimits
from moana.core.coordinates import Dimensions
from moana.core.limits import MAX_MORPHOLOGY_RADIUS
from moana.core.morphology import MORPHOLOGY_FIXED_BYTES
from moana.editing import History, apply_batch
from moana.render import ESTIMATOR_VERSION, estimate_cost, plan_budget, render
from moana.render.budget import OUTLINE_PASSES, fill_count, mask_estimates, outline_cost
from moana.render.pipeline import _outline, _plan_masks
from moana.schema import Document, OutlineOperation, snapshot_digest, validate_document

RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)
INK: RGBA = (16, 24, 32, 255)
BODY: RGBA = (200, 120, 40, 255)
COLORS = {"ink": "#101820FF", "body": "#C87828FF", "red": "#FF0000FF"}


def outline_op(op_id: str, mask_id: str, *, width: int, side: str) -> dict[str, Any]:
    return {
        "id": op_id,
        "type": "outline",
        "mask_id": mask_id,
        "width": width,
        "side": side,
        "color": "ink",
    }


def tree(
    width: int,
    height: int,
    operations: list[dict[str, Any]],
    masks: list[dict[str, Any]],
    *,
    body: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    layers: list[dict[str, Any]] = []
    if body:
        layers.append({"id": "base", "name": "Base", "operations": body})
    layers.append({"id": "lines", "name": "Lines", "operations": operations})
    return {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": width, "height": height},
        "palette": {
            "id": "pal",
            "colors": [{"id": key, "rgba": value} for key, value in COLORS.items()],
        },
        "masks": masks,
        "layers": layers,
    }


def painted(document: Document, color: RGBA = INK) -> set[tuple[int, int]]:
    result = render(document)
    return {
        (x, y)
        for y in range(result.height)
        for x in range(result.width)
        if result.pixel(x, y) == color
    }


def square(x0: int, y0: int, x1: int, y1: int) -> set[tuple[int, int]]:
    return {(x, y) for x in range(x0, x1) for y in range(y0, y1)}


# A 6 x 6 square with a 2 x 2 hole: ``subtract`` of two rect masks.
HOLED: list[dict[str, Any]] = [
    {"id": "outer_sq", "type": "rect", "box": [2, 2, 8, 8]},
    {"id": "hole", "type": "rect", "box": [4, 4, 6, 6]},
    {"id": "shape", "type": "subtract", "masks": ["outer_sq", "hole"]},
]


# --- T2: the editable operation reproduces the outline mask --------------------------------


def test_t2_outer_width_1_paints_exactly_the_ring_and_the_hole() -> None:
    document = validate_document(
        tree(10, 10, [outline_op("o", "shape", width=1, side="outer")], HOLED)
    )
    expected = (square(1, 1, 9, 9) - square(2, 2, 8, 8)) | square(4, 4, 6, 6)
    result = render(document)
    for y in range(10):
        for x in range(10):
            assert result.pixel(x, y) == (INK if (x, y) in expected else CLEAR), (x, y)


def test_t2_inner_width_2_over_a_body_keeps_the_rest_of_the_body() -> None:
    body = [{"id": "fill", "type": "rect", "box": [1, 1, 11, 11], "color": "body"}]
    masks = [{"id": "sq", "type": "rect", "box": [1, 1, 11, 11]}]
    ops = [outline_op("o", "sq", width=2, side="inner")]
    document = validate_document(tree(12, 12, ops, masks, body=body))
    ring = square(1, 1, 11, 11) - square(3, 3, 9, 9)
    assert painted(document) == ring
    assert painted(document, BODY) == square(3, 3, 9, 9)


def test_ac1_document_outline_at_the_canvas_edge() -> None:
    masks = [{"id": "corner", "type": "rect", "box": [-3, -3, 4, 4]}]
    ops = [
        outline_op("out", "corner", width=2, side="outer"),
        outline_op("in", "corner", width=1, side="inner"),
    ]
    document = validate_document(tree(8, 8, ops, masks))
    assert painted(document) == (square(0, 0, 6, 6) - square(0, 0, 4, 4)) | (
        square(0, 0, 4, 4) - square(1, 1, 3, 3)
    )


def test_empty_mask_warns_and_paints_nothing() -> None:
    masks = [{"id": "far", "type": "rect", "box": [40, 40, 44, 44]}]
    document = validate_document(tree(4, 4, [outline_op("o", "far", width=1, side="outer")], masks))
    result = render(document)
    assert [w.code for w in result.warnings] == ["empty_bounds"]
    assert result.rgba == bytes(4 * 16)


def test_editing_recolours_the_outline_but_cannot_move_it() -> None:
    document = validate_document(
        tree(10, 10, [outline_op("o", "shape", width=1, side="outer")], HOLED)
    )
    batch = {
        "schema_version": "1.0",
        "base_revision": 0,
        "base_snapshot": snapshot_digest(document),
        "commands": [{"type": "set_color", "target_id": "o", "color": "red"}],
    }
    edited = apply_batch(document, batch).document
    assert painted(edited, (255, 0, 0, 255)) == painted(document)
    batch["commands"] = [{"type": "translate", "target_id": "o", "dx": 1, "dy": 0}]
    with pytest.raises(errors.ValidationError) as raised:
        apply_batch(document, batch)
    assert (raised.value.json_pointer, raised.value.context["reason"]) == (
        "/commands/0/target_id",
        "not_geometric",
    )
    batch["commands"] = [{"type": "remove", "target_id": "shape"}]
    with pytest.raises(errors.ReferenceError) as live:
        apply_batch(document, batch)
    assert live.value.details[0].context["reason"] == "live_reference"


def test_history_recolours_an_outline_and_undo_redo_restore_the_pixels() -> None:
    document = validate_document(
        tree(10, 10, [outline_op("o", "shape", width=1, side="outer")], HOLED)
    )
    ring = painted(document)
    history = History.start(document)
    batch = {
        "schema_version": "1.0",
        "base_revision": 0,
        "base_snapshot": snapshot_digest(document),
        "commands": [{"type": "set_color", "target_id": "o", "color": "red"}],
    }
    edited = history.edit(batch)
    assert painted(edited.document, (255, 0, 0, 255)) == ring
    assert painted(edited.document) == set()
    undone = edited.undo()
    assert undone.document == document and painted(undone.document) == ring
    redone = undone.redo()
    assert redone.current.digest == edited.current.digest
    assert painted(redone.document, (255, 0, 0, 255)) == ring


# --- budget-v6 ----------------------------------------------------------------------------


def test_budget_v6_hand_oracle() -> None:
    """8 x 8 canvas (A = 64), a 3 x 3 rect mask, outer outline of width 1."""
    masks = [{"id": "sq", "type": "rect", "box": [2, 2, 5, 5]}]
    document = validate_document(tree(8, 8, [outline_op("o", "sq", width=1, side="outer")], masks))
    estimate = plan_budget(document)
    # mask: floor 1 + raster 9 = 10 visits, 9 bytes; work box 5 x 5, padded 8 x 8 = 64
    assert estimate.operation_costs[0].pixel_visits == 10 + OUTLINE_PASSES * 64 == 1034
    # bytes: 9 + 9 + (2*25 + 4*64 + 4*25 + 12*min(64, 8192) + fixed) + 2*25
    morphology = 50 + 256 + 100 + 768 + MORPHOLOGY_FIXED_BYTES
    assert estimate.operation_costs[0].mask_bytes == 9 + 9 + morphology + 50 == 5338
    assert estimate.pixel_visits == 3 * 64 + 2 * 64 + 1034
    # working max(40A, 14A + 80 x 16) = 2560, plus the outline peak, plus one result 4A
    assert estimate.buffer_bytes == 2560 + 5338 + 256
    assert estimate.estimator_version == ESTIMATOR_VERSION == "budget-v6"
    assert estimate.fills == fill_count(document) == 1


def test_inner_outline_works_on_the_mask_box() -> None:
    masks = [{"id": "sq", "type": "rect", "box": [2, 2, 5, 5]}]
    document = validate_document(tree(8, 8, [outline_op("o", "sq", width=2, side="inner")], masks))
    estimate = mask_estimates(document)["sq"]
    visits, peak = outline_cost(estimate, 2, "inner", Dimensions(8, 8))
    # work box 3 x 3, padded 8 x 8 (buffers 12 * 64)
    assert visits == 10 + OUTLINE_PASSES * 64
    assert peak == 9 + 9 + (18 + 4 * 64 + 36 + 768 + MORPHOLOGY_FIXED_BYTES) + 18


def test_outline_cost_of_an_empty_mask_is_the_mask_floor() -> None:
    masks = [{"id": "far", "type": "rect", "box": [40, 40, 44, 44]}]
    document = validate_document(tree(4, 4, [outline_op("o", "far", width=3, side="outer")], masks))
    estimate = mask_estimates(document)["far"]
    assert outline_cost(estimate, 3, "outer", Dimensions(4, 4)) == (estimate.pixel_visits, 0)


def test_cost_plan_of_an_unvalidated_outline_fails_fast() -> None:
    source = tree(4, 4, [outline_op("o", "ghost", width=1, side="outer")], [])
    document = Document.model_validate(source)
    for plan in (estimate_cost, plan_budget):
        with pytest.raises(errors.ReferenceError) as raised:
            plan(document)
        assert raised.value.context["reason"] == "unknown_mask"


def test_inspect_summarises_the_outline() -> None:
    masks = [{"id": "sq", "type": "rect", "box": [2, 2, 5, 5]}]
    report = inspect_document(
        validate_document(tree(8, 8, [outline_op("o", "sq", width=1, side="outer")], masks))
    )
    summary = report.layers[0].operations[0]
    assert (summary.id, summary.type, summary.color) == ("o", "outline", "ink")
    assert report.budget.fills == 1 and report.budget.estimator_version == "budget-v6"


def test_peak_memory_with_outlines_stays_within_the_estimate() -> None:
    size = 200
    masks: list[dict[str, Any]] = [
        {"id": "big", "type": "ellipse", "box": [10, 10, 190, 190]},
        {"id": "hole", "type": "ellipse", "box": [60, 60, 140, 140]},
        {"id": "ring", "type": "subtract", "masks": ["big", "hole"]},
    ]
    ops = [
        outline_op("a", "ring", width=16, side="outer"),
        outline_op("b", "ring", width=3, side="inner"),
    ]
    document = validate_document(tree(size, size, ops, masks))
    estimate = plan_budget(document)
    tracemalloc.start()
    try:
        render(document)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= estimate.buffer_bytes


@pytest.mark.parametrize("width", [1, 3, MAX_MORPHOLOGY_RADIUS])
@pytest.mark.parametrize("side", ["outer", "inner"])
@pytest.mark.parametrize(
    "box", [[10, 10, 50, 90], [10, 10, 110, 110], [0, 0, 128, 128], [-5, 60, 200, 64]]
)
def test_outline_fill_peak_stays_within_its_cost(box: list[int], side: str, width: int) -> None:
    """One outline fill (mask evaluation + morphology + subtraction) on a 128² canvas."""
    masks = [{"id": "m", "type": "rect", "box": box}]
    document = validate_document(
        tree(128, 128, [outline_op("o", "m", width=width, side=side)], masks)
    )
    dims = Dimensions(128, 128)
    node = _plan_masks(document, dims)["m"]
    operation = document.layers[0].operations[0]
    assert isinstance(operation, OutlineOperation)
    _, bound = outline_cost(mask_estimates(document)["m"], width, side, dims)
    tracemalloc.start()
    try:
        result = _outline(operation, node, dims, None)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.is_empty == (side == "outer" and box == [0, 0, 128, 128])
    assert peak <= bound


box_strategy = st.tuples(
    st.integers(-3, 6), st.integers(-3, 6), st.integers(1, 6), st.integers(1, 6)
)


@settings(max_examples=40, deadline=None)
@given(
    width=st.integers(1, 8),
    height=st.integers(1, 8),
    boxes=st.lists(box_strategy, min_size=1, max_size=3),
    radius=st.integers(1, 4),
    side=st.sampled_from(["outer", "inner"]),
    layer_mask=st.booleans(),
)
def test_plan_budget_admission_means_render_succeeds_with_outline(
    width: int,
    height: int,
    boxes: list[tuple[int, int, int, int]],
    radius: int,
    side: str,
    layer_mask: bool,
) -> None:
    """With limits exactly at the plan, the compositor's own check never rejects."""
    masks: list[dict[str, Any]] = [
        {"id": f"s{i}", "type": "ellipse" if i % 2 else "rect", "box": [x, y, x + w, y + h]}
        for i, (x, y, w, h) in enumerate(boxes)
    ]
    target = "s0"
    if len(masks) > 1:
        masks.append({"id": "top", "type": "xor", "masks": [m["id"] for m in masks]})
        target = "top"
    source = tree(width, height, [outline_op("o", target, width=radius, side=side)], masks)
    if layer_mask:
        source["layers"][0]["mask_id"] = "s0"
    document = validate_document(source)
    estimate = plan_budget(document)
    exact = RenderLimits(
        max_pixel_visits=estimate.pixel_visits,
        max_buffer_bytes=estimate.buffer_bytes,
        max_frame_pixels=estimate.frame_pixels,
        max_operations=fill_count(document),
        max_layers=1,
    )
    assert render(document, limits=exact).width == width
