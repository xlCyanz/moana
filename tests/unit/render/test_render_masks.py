"""Render of semantic masks and regions (MOANA-013, ADR-022).

AC1: a masked layer modifies no pixel outside its mask. AC2/T2: cycles and broken
references are rejected before any rasteriser runs; masks outside the canvas are
clipped. Expected pixels come from MOANA.md sections 6 and 11 by hand; ``budget-v3``
figures are computed by hand from the formulas in ``moana.render.budget``.
"""

from __future__ import annotations

import hashlib
import json
import tracemalloc
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.core.budget import RenderLimits
from moana.core.errors import BudgetExceeded, ReferenceError
from moana.core.limits import MAX_MASK_DEPTH, MAX_MASK_OPERANDS, MAX_MASKS, GeometryLimits
from moana.layers import MASK_NODE_VISITS as LAYERS_MASK_NODE_VISITS
from moana.layers import mask_cost
from moana.render import ESTIMATOR_VERSION, estimate_cost, plan_budget, render
from moana.render import budget as budget_module
from moana.render import pipeline as pipeline_module
from moana.render.budget import MASK_NODE_VISITS
from moana.schema import Document, validate_document

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "specs" / "masked-eyes.moana.json"
RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)
INK: RGBA = (16, 32, 48, 255)


def doc(
    width: int,
    height: int,
    layers: list[dict[str, Any]],
    masks: list[Any],
    *,
    colors: dict[str, str] | None = None,
) -> Document:
    palette = colors or {"ink": "#102030FF", "red": "#FF0000FF"}
    return validate_document(
        {
            "schema_version": "1.0",
            "id": "doc",
            "canvas": {"width": width, "height": height, "profile": "rgba"},
            "palette": {
                "id": "pal",
                "colors": [{"id": key, "rgba": value} for key, value in palette.items()],
            },
            "masks": masks,
            "layers": layers,
        }
    )


def fill_layer(name: str, color: str, width: int, height: int, **fields: Any) -> dict[str, Any]:
    operation = {"id": f"{name}_fill", "type": "rect", "box": [0, 0, width, height], "color": color}
    return {"id": name, "name": name.title(), "operations": [operation], **fields}


def pixels(result: Any) -> dict[tuple[int, int], RGBA]:
    return {(x, y): result.pixel(x, y) for y in range(result.height) for x in range(result.width)}


def hand_digest(width: int, height: int, grid: dict[tuple[int, int], RGBA]) -> str:
    data = bytearray(width.to_bytes(4, "big") + height.to_bytes(4, "big"))
    for y in range(height):
        for x in range(width):
            data.extend(grid.get((x, y), CLEAR))
    return "sha256:" + hashlib.sha256(bytes(data)).hexdigest()


# --- Example document ------------------------------------------------------------------


def test_example_renders_to_the_hand_computed_face() -> None:
    document = validate_document(EXAMPLE.read_bytes())
    skin, white, iris = (242, 194, 155, 255), (255, 255, 255, 255), (54, 175, 165, 255)
    expected: dict[tuple[int, int], RGBA] = {}
    for y in range(16):
        for x in range(16):
            # Ellipse [1,1,15,15): w = h = 14, A = 2x - 15, B = 2y - 15.
            a, b = 2 * x - 15, 2 * y - 15
            if a * a * 196 + b * b * 196 <= 196 * 196:
                expected[(x, y)] = skin
    # eyes_open = (rect [4,6,7,9) | rect [9,6,12,9)) minus the lid row y = 6.
    for x in (4, 5, 6, 9, 10, 11):
        for y in (7, 8):
            expected[(x, y)] = white
    # Irises [5,6,6,9) and [10,6,11,9) clipped by eyes_open lose their row y = 6.
    for x in (5, 10):
        for y in (7, 8):
            expected[(x, y)] = iris
    result = render(document)
    assert pixels(result) == {key: expected.get(key, CLEAR) for key in pixels(result)}
    assert result.digest == hand_digest(16, 16, expected)
    assert result.provenance.estimator_version == ESTIMATOR_VERSION == "budget-v6"
    assert result.warnings == ()


# --- AC1 -----------------------------------------------------------------------------


def test_ac1_masked_operation_changes_no_pixel_outside_its_mask() -> None:
    masks = [
        {"id": "eye", "type": "ellipse", "box": [1, 1, 5, 4]},
        {"id": "cut", "type": "line", "start": [0, 2], "end": [7, 2]},
        {"id": "lens", "type": "subtract", "masks": ["eye", "cut"]},
    ]
    base = fill_layer("base", "red", 8, 6)
    paint = fill_layer("paint", "ink", 8, 6, mask_id="lens")
    before = pixels(render(doc(8, 6, [base], masks)))
    after = pixels(render(doc(8, 6, [base, paint], masks)))
    # Ellipse [1,1,5,4): w=4, h=3, A=2x-5, B=2y-4; in if 9A^2 + 16B^2 <= 144, minus row 2.
    inside = {
        (x, y)
        for x in range(1, 5)
        for y in range(1, 4)
        if 9 * (2 * x - 5) ** 2 + 16 * (2 * y - 4) ** 2 <= 144 and y != 2
    }
    assert inside == {(2, 1), (3, 1), (2, 3), (3, 3)}
    for key, value in before.items():
        assert after[key] == (INK if key in inside else value), key


def test_ac1_mask_reaching_outside_the_canvas_is_clipped() -> None:
    masks = [
        {"id": "wide", "type": "rect", "box": [-10, 1, 40, 2]},
        {"id": "dot", "type": "pixel", "at": [99, 99]},
        {"id": "both", "type": "xor", "masks": ["wide", "dot"]},
    ]
    result = render(doc(4, 3, [fill_layer("l", "ink", 4, 3, mask_id="both")], masks))
    assert {key for key, value in pixels(result).items() if value != CLEAR} == {
        (x, 1) for x in range(4)
    }


def test_t2_mask_fully_outside_the_canvas_draws_nothing() -> None:
    masks = [{"id": "far", "type": "rect", "box": [100, 100, 120, 120]}]
    result = render(doc(4, 3, [fill_layer("l", "ink", 4, 3, mask_id="far")], masks))
    assert set(pixels(result).values()) == {CLEAR}
    assert result.warnings == ()  # warnings describe operations, not masks


# --- AC2 / T2: rejected before any raster --------------------------------------------


class _Spy:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[str] = []
        self.planned = False
        original_raster = pipeline_module._rasterize
        original_plan = budget_module.plan_budget

        def raster(operation: Any, dimensions: Any) -> Any:
            self.calls.append(operation.id)
            return original_raster(operation, dimensions)

        def plan(*args: Any, **kwargs: Any) -> Any:
            self.planned = True
            return original_plan(*args, **kwargs)

        monkeypatch.setattr(pipeline_module, "_rasterize", raster)
        monkeypatch.setattr(pipeline_module, "plan_budget", plan)


def _structural(tree: dict[str, Any]) -> Document:
    """A model built without reference checks, as a caller could do by mistake."""
    return Document.model_validate(tree)


@pytest.mark.parametrize(
    ("masks", "mask_id", "pointer"),
    [
        (
            [
                {"id": "a", "type": "union", "masks": ["a", "b"]},
                {"id": "b", "type": "pixel", "at": [0, 0]},
            ],
            "a",
            "/masks/0/masks/0",
        ),
        (
            [
                {"id": "a", "type": "union", "masks": ["b", "c"]},
                {"id": "b", "type": "intersect", "masks": ["a", "c"]},
                {"id": "c", "type": "pixel", "at": [0, 0]},
            ],
            "c",
            "/masks/0/masks/0",
        ),
        ([{"id": "a", "type": "pixel", "at": [0, 0]}], "ghost", "/layers/0/mask_id"),
    ],
)
def test_ac2_cycles_and_broken_references_fail_before_any_raster(
    monkeypatch: pytest.MonkeyPatch, masks: list[dict[str, Any]], mask_id: str, pointer: str
) -> None:
    spy = _Spy(monkeypatch)
    tree = {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": 2, "height": 2},
        "palette": {"id": "pal", "colors": [{"id": "ink", "rgba": "#000000FF"}]},
        "masks": masks,
        "layers": [fill_layer("l", "ink", 2, 2, mask_id=mask_id)],
    }
    with pytest.raises(ReferenceError) as raised:
        render(_structural(tree))
    assert raised.value.json_pointer == pointer
    assert spy.calls == [] and not spy.planned


def test_masks_of_hidden_layers_are_never_rasterised(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _Spy(monkeypatch)
    masks = [
        {"id": "m1", "type": "rect", "box": [0, 0, 1, 1]},
        {"id": "m2", "type": "rect", "box": [1, 0, 2, 1]},
        {"id": "u", "type": "union", "masks": ["m1", "m2"]},
    ]
    layers = [
        fill_layer("hid", "ink", 2, 2, mask_id="u", visible=False),
        fill_layer("vis", "ink", 2, 2, mask_id="m2"),
    ]
    render(doc(2, 2, layers, masks))
    assert spy.calls == ["vis_fill", "m2"]  # fills first, then the layer mask


# --- Budget (budget-v3) ---------------------------------------------------------------


def test_budget_v3_hand_oracle() -> None:
    masks = [
        {"id": "a", "type": "rect", "box": [0, 0, 2, 2]},
        {"id": "b", "type": "rect", "box": [2, 1, 4, 3]},
        {"id": "u", "type": "union", "masks": ["a", "b"]},
    ]
    estimate = estimate_cost(doc(4, 4, [fill_layer("l", "ink", 4, 4, mask_id="u")], masks))
    # A = 16. Frame 3A + layer 2A + rect (16 raster + 16 paint) = 112. Mask: each leaf
    # 1 (floor) + 4 (raster) = 5; union box (0,0)-(4,3) = 12 px ->
    # 1 + 2*12 + (5 + 4) + (5 + 4) = 43, plus 12 (copy of its bits) and A (clear) = 71.
    assert estimate.pixel_visits == 112 + 71
    assert estimate.operation_costs[-1] == budget_module.OperationCost(
        "/layers/0/mask_id", 71, 12 + 4 + 12
    )
    # Working set max(40A, 14A + 80 * 4) = 640, plus max(16, 28) = 668, plus 4A = 732.
    assert estimate.buffer_bytes == 732
    unmasked = estimate_cost(doc(4, 4, [fill_layer("l", "ink", 4, 4)], masks))
    assert unmasked.pixel_visits == 112 and unmasked.buffer_bytes == 640 + 16 + 64


def test_shared_masks_count_once_per_reference() -> None:
    masks = [
        {"id": "a", "type": "rect", "box": [0, 0, 2, 2]},
        {"id": "x", "type": "xor", "masks": ["a", "b"]},
        {"id": "b", "type": "rect", "box": [1, 1, 3, 3]},
        {"id": "y", "type": "union", "masks": ["x", "a"]},
    ]
    estimates = budget_module.mask_estimates(
        doc(4, 4, [fill_layer("l", "ink", 4, 4, mask_id="y")], masks)
    )
    # Leaves: 1 (floor) + 4 (raster) = 5 each.
    # x: box (0,0)-(3,3) = 9 -> 1 + 2*9 + (5 + 4) + (5 + 4) = 37; peak 9 + 4 = 13.
    assert (estimates["x"].pixel_visits, estimates["x"].buffer_bytes) == (37, 13)
    # y: box 9 -> 1 + 2*9 + (37 + 9) + (5 + 4) = 74; peak 9 + 13 = 22. ``a`` counts twice.
    assert (estimates["y"].pixel_visits, estimates["y"].buffer_bytes) == (74, 22)


def _tower_document(leaf_box: list[int], operator: str, *, width: int, levels: int) -> Document:
    """``width`` leaves, then ``levels`` levels of ``width`` combinations, each over
    all ``width`` masks of the level below, and ``top`` over two masks of the last
    level: ``top`` expands to ``2 * width^levels`` references to leaves."""
    masks: list[dict[str, Any]] = [
        {"id": f"l0_{i}", "type": "rect", "box": leaf_box} for i in range(width)
    ]
    for level in range(1, levels + 1):
        below = [f"l{level - 1}_{i}" for i in range(width)]
        masks += [{"id": f"l{level}_{i}", "type": operator, "masks": below} for i in range(width)]
    masks.append({"id": "top", "type": operator, "masks": [f"l{levels}_0", f"l{levels}_1"]})
    assert len(masks) <= MAX_MASKS and levels + 2 <= MAX_MASK_DEPTH
    tree = {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": 4, "height": 4, "profile": "rgba"},
        "palette": {"id": "pal", "colors": [{"id": "ink", "rgba": "#102030FF"}]},
        "masks": masks,
        "layers": [fill_layer("l", "ink", 4, 4, mask_id="top")],
    }
    if width * width * levels > 15_000:
        # Beyond the reader's node limit (20 000): a structurally valid model with
        # correct references, as the cost plan sees it (``render`` would re-read it).
        return Document.model_validate(tree)
    return validate_document(tree)


def _estimated(error: BudgetExceeded) -> int:
    value = error.context["estimated"]
    assert isinstance(value, int)
    return value


# Through ``render`` the reader's node limit caps the DAG near 32 operands x 13
# levels; the cost plan alone is also checked with 64 operands at depth 16.
RENDERABLE_TOWER = {"width": 32, "levels": 13}
WIDEST_TOWER = {"width": MAX_MASK_OPERANDS, "levels": MAX_MASK_DEPTH - 2}


@pytest.mark.parametrize("operator", ["union", "intersect", "subtract", "xor"])
def test_wide_deep_dag_of_empty_masks_costs_the_floor(
    monkeypatch: pytest.MonkeyPatch, operator: str
) -> None:
    """Off-canvas leaves: every empty node costs the floor and evaluates no operand."""
    for shape in (WIDEST_TOWER, RENDERABLE_TOWER):
        document = _tower_document([20, 20, 24, 24], operator, **shape)
        estimate = plan_budget(document)
        # Layer: 112 as in the hand oracle above; mask: floor 1, no bits, A = 16.
        assert estimate.operation_costs[-1] == budget_module.OperationCost(
            "/layers/0/mask_id", MASK_NODE_VISITS + 0 + 16, 0
        )
        assert estimate.pixel_visits == 112 + 1 + 16
    spy = _Spy(monkeypatch)
    assert set(pixels(render(document)).values()) == {CLEAR}
    assert spy.calls == ["l_fill"]  # no mask leaf is rasterised


@pytest.mark.parametrize("operator", ["union", "intersect", "subtract", "xor"])
def test_wide_deep_dag_of_full_masks_is_rejected_before_raster(
    monkeypatch: pytest.MonkeyPatch, operator: str
) -> None:
    widest = _tower_document([0, 0, 4, 4], operator, **WIDEST_TOWER)
    with pytest.raises(BudgetExceeded) as raised:
        plan_budget(widest)
    assert raised.value.context["resource"] == "pixel_visits"
    assert _estimated(raised.value) > 2 * MAX_MASK_OPERANDS ** WIDEST_TOWER["levels"]
    document = _tower_document([0, 0, 4, 4], operator, **RENDERABLE_TOWER)
    spy = _Spy(monkeypatch)
    with pytest.raises(BudgetExceeded) as raised:
        render(document)
    assert raised.value.context["resource"] == "pixel_visits"
    assert raised.value.json_pointer == "/layers/0/mask_id"
    assert _estimated(raised.value) > 2 * 32**13
    assert spy.calls == []


def test_mask_floor_matches_the_compositor() -> None:
    """The plan and the compositor share the floor and the combination formula."""
    assert MASK_NODE_VISITS == LAYERS_MASK_NODE_VISITS
    masks = [
        {"id": "a", "type": "rect", "box": [0, 0, 2, 2]},
        {"id": "far", "type": "pixel", "at": [9, 9]},
        {"id": "e", "type": "xor", "masks": ["far", "far2"]},
        {"id": "far2", "type": "rect", "box": [6, 6, 8, 8]},
        {"id": "u", "type": "union", "masks": ["a", "e"]},
        {"id": "s", "type": "subtract", "masks": ["u", "a"]},
    ]
    document = doc(4, 4, [fill_layer("l", "ink", 4, 4, mask_id="s")], masks)
    estimates = budget_module.mask_estimates(document)
    tree = pipeline_module._plan_masks(document, document.canvas.dimensions)
    # Raster work of each evaluated leaf reference is the only difference: ``a`` is
    # evaluated twice (4 each); the empty ``e`` evaluates neither of its leaves.
    composed = mask_cost(tree["s"], document.canvas.dimensions)
    assert (composed.box, composed.buffer_bytes) == (
        estimates["s"].box,
        estimates["s"].buffer_bytes,
    )
    assert estimates["s"].pixel_visits == composed.pixel_visits + 2 * 4
    assert estimates["e"] == budget_module.MaskEstimate(None, 1, 0)


def test_mask_coordinates_are_checked_against_geometry_limits() -> None:
    masks = [
        {"id": "far", "type": "polygon", "points": [[0, 0], [9000, 0], [0, 5]]},
        {"id": "u", "type": "union", "masks": ["far", "far2"]},
        {"id": "far2", "type": "line", "start": [0, 0], "end": [0, -7000]},
    ]
    document = doc(4, 4, [fill_layer("l", "ink", 4, 4, mask_id="u")], masks)
    limits = RenderLimits(geometry=GeometryLimits(max_coordinate=8000))
    with pytest.raises(BudgetExceeded) as raised:
        plan_budget(document, limits)
    assert [(d.json_pointer, d.context["resource"]) for d in raised.value.details] == [
        ("/masks/0", "coordinate")
    ]


def test_mask_budget_is_enforced_before_raster(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _Spy(monkeypatch)
    masks = [{"id": f"m{i}", "type": "rect", "box": [0, 0, 64, 64]} for i in range(3)]
    masks.append({"id": "u", "type": "union", "masks": ["m0", "m1", "m2"]})
    document = doc(64, 64, [fill_layer("l", "ink", 64, 64, mask_id="u")], masks)
    estimate = plan_budget(document)
    with pytest.raises(BudgetExceeded) as raised:
        render(document, limits=RenderLimits(max_pixel_visits=estimate.pixel_visits - 1))
    assert raised.value.json_pointer == "/layers/0/mask_id"  # the most expensive entry
    assert spy.calls == []


def test_peak_memory_with_masks_stays_within_the_estimate() -> None:
    size = 192
    masks = [{"id": f"r{i}", "type": "rect", "box": [i, i, size - i, size - i]} for i in range(8)]
    previous = "r0"
    for i in range(1, 8):
        masks.append({"id": f"c{i}", "type": "xor", "masks": [previous, f"r{i}"]})
        previous = f"c{i}"
    layers = [fill_layer(f"l{i}", "ink", size, size, mask_id=previous) for i in range(3)]
    document = doc(size, size, layers, masks, colors={"ink": "#10203080"})
    estimate = plan_budget(document)
    tracemalloc.start()
    try:
        render(document)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= estimate.buffer_bytes


box_strategy = st.tuples(
    st.integers(-3, 6), st.integers(-3, 6), st.integers(1, 5), st.integers(1, 5)
)


@settings(max_examples=40, deadline=None)
@given(
    width=st.integers(1, 6),
    height=st.integers(1, 6),
    boxes=st.lists(box_strategy, min_size=2, max_size=4),
    operator=st.sampled_from(["union", "intersect", "subtract", "xor"]),
    nested=st.booleans(),
)
def test_plan_budget_admission_means_render_succeeds_with_masks(
    width: int,
    height: int,
    boxes: list[tuple[int, int, int, int]],
    operator: str,
    nested: bool,
) -> None:
    """With limits exactly at the plan, the compositor's own check never rejects."""
    masks: list[dict[str, Any]] = [
        {"id": f"s{i}", "type": "ellipse" if i % 2 else "rect", "box": [x, y, x + w, y + h]}
        for i, (x, y, w, h) in enumerate(boxes)
    ]
    masks.append({"id": "top", "type": operator, "masks": [m["id"] for m in masks]})
    if nested:
        masks.append({"id": "outer", "type": "subtract", "masks": ["top", "s0"]})
    mask_id = "outer" if nested else "top"
    document = doc(width, height, [fill_layer("l", "ink", width, height, mask_id=mask_id)], masks)
    estimate = plan_budget(document)
    exact = RenderLimits(
        max_pixel_visits=estimate.pixel_visits,
        max_buffer_bytes=estimate.buffer_bytes,
        max_frame_pixels=estimate.frame_pixels,
        max_operations=1,
        max_layers=1,
    )
    assert render(document, limits=exact).width == width


def test_example_spec_is_valid_json() -> None:
    assert json.loads(EXAMPLE.read_text(encoding="utf-8"))["id"] == "masked_eyes"


@pytest.mark.parametrize(
    ("masks", "reason"),
    [
        (
            [
                {"id": "a", "type": "union", "masks": ["b", "leaf"]},
                {"id": "b", "type": "xor", "masks": ["a", "leaf"]},
                {"id": "leaf", "type": "pixel", "at": [0, 0]},
            ],
            "mask_cycle",
        ),
        (
            [
                {"id": "a", "type": "union", "masks": ["leaf", "ghost"]},
                {"id": "leaf", "type": "pixel", "at": [0, 0]},
            ],
            "unknown_mask",
        ),
        ([{"id": "leaf", "type": "pixel", "at": [0, 0]}], "unknown_mask"),
    ],
)
def test_cost_plan_of_unvalidated_documents_fails_fast(
    masks: list[dict[str, Any]], reason: str
) -> None:
    tree = {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": 2, "height": 2},
        "palette": {"id": "pal", "colors": [{"id": "ink", "rgba": "#000000FF"}]},
        "masks": masks,
        "layers": [fill_layer("l", "ink", 2, 2, mask_id="a")],
    }
    document = _structural(tree)
    plans: list[Any] = [estimate_cost, plan_budget]
    if len(masks) > 1:  # the broken reference is inside the masks, not on the layer
        plans.append(budget_module.mask_estimates)
    for plan in plans:
        with pytest.raises(ReferenceError) as raised:
            plan(document)
        assert raised.value.context["reason"] == reason
