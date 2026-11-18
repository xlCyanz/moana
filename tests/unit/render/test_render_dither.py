"""Render of ``dither`` operations (MOANA-016, MOANA.md section 10, ADR-025).

AC1: coverage 0 paints only colour A and coverage N^2 only colour B inside the mask,
and nothing outside it. AC2: negative origins and translations by the period give
identical bytes. T1/T2 at document level: every coverage against the literal Bayer
matrices, non-rectangular masks, seams between tiles and repeated renders.
Expected pixels are computed here from MOANA.md sections 6 and 10 (ellipse inclusion
formula, literal matrices, floor modulo); ``budget-v5`` figures by hand.
"""

from __future__ import annotations

import tracemalloc
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.api import capabilities, inspect_document
from moana.core.budget import RenderLimits
from moana.core.coordinates import Box, Dimensions
from moana.core.errors import BudgetExceeded, ReferenceError
from moana.core.limits import MAX_OPERATIONS, GeometryLimits
from moana.geometry import rasterize_rect
from moana.layers import MaskShape, evaluate_mask
from moana.render import ESTIMATOR_VERSION, estimate_cost, plan_budget, render
from moana.render import pipeline as pipeline_module
from moana.render.budget import (
    DITHER_FIXED_BYTES,
    dither_cost,
    fill_count,
    mask_estimates,
)
from moana.schema import Document, validate_document

RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)
BG: RGBA = (10, 20, 30, 255)
A: RGBA = (200, 0, 0, 255)
B: RGBA = (0, 0, 220, 255)
SPEC = {2: [[0, 2], [3, 1]], 4: [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]}
COLORS = {"bg": "#0A141EFF", "ca": "#C80000FF", "cb": "#0000DCFF", "none": "#00000000"}


def dither_op(
    op_id: str, mask_id: str, *, size: int, coverage: int, origin: tuple[int, int], **extra: Any
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": op_id,
        "type": "dither",
        "size": size,
        "coverage": coverage,
        "origin": list(origin),
        "color_a": "ca",
        "color_b": "cb",
        "mask_id": mask_id,
    }
    return fields | extra


def tree(
    width: int,
    height: int,
    operations: list[dict[str, Any]],
    masks: list[dict[str, Any]],
    *,
    background: bool = True,
    profile: str = "strict",
) -> dict[str, Any]:
    layers: list[dict[str, Any]] = []
    if background:
        bg = {"id": "bg_fill", "type": "rect", "box": [0, 0, width, height], "color": "bg"}
        layers.append({"id": "back", "name": "Back", "operations": [bg]})
    layers.append({"id": "shade", "name": "Shade", "operations": operations})
    return {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": width, "height": height, "profile": profile},
        "palette": {
            "id": "pal",
            "colors": [{"id": key, "rgba": value} for key, value in COLORS.items()],
        },
        "masks": masks,
        "layers": layers,
    }


def doc(*args: Any, **kwargs: Any) -> Document:
    return validate_document(tree(*args, **kwargs))


def grid(document: Document) -> dict[tuple[int, int], RGBA]:
    result = render(document)
    return {(x, y): result.pixel(x, y) for y in range(result.height) for x in range(result.width)}


def ellipse_pixels(box: tuple[int, int, int, int], w: int, h: int) -> set[tuple[int, int]]:
    """MOANA.md section 6: include (x, y) when A^2 h^2 + B^2 w^2 <= w^2 h^2."""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    found = set()
    for y in range(max(0, y0), min(h, y1)):
        for x in range(max(0, x0), min(w, x1)):
            ax, by = 2 * x + 1 - x0 - x1, 2 * y + 1 - y0 - y1
            if ax * ax * bh * bh + by * by * bw * bw <= bw * bw * bh * bh:
                found.add((x, y))
    return found


def expected(
    w: int, h: int, inside: set[tuple[int, int]], size: int, coverage: int, ox: int, oy: int
) -> dict[tuple[int, int], RGBA]:
    out: dict[tuple[int, int], RGBA] = {}
    for y in range(h):
        for x in range(w):
            if (x, y) not in inside:
                out[(x, y)] = BG
            else:
                threshold = SPEC[size][(y - oy) % size][(x - ox) % size]
                out[(x, y)] = B if threshold < coverage else A
    return out


ELLIPSE = {"id": "blob", "type": "ellipse", "box": [1, 2, 14, 11]}


# --- AC1 / T1 at document level ---------------------------------------------------------


@pytest.mark.parametrize("size", [2, 4])
def test_ac1_extreme_coverages_paint_only_a_or_only_b_inside_the_mask(size: int) -> None:
    inside = ellipse_pixels((1, 2, 14, 11), 16, 12)
    for coverage, color in ((0, A), (size * size, B)):
        op = dither_op("d", "blob", size=size, coverage=coverage, origin=(-5, -3))
        painted = grid(doc(16, 12, [op], [ELLIPSE]))
        assert {xy for xy, rgba in painted.items() if rgba == color} == inside
        assert all(painted[xy] == BG for xy in painted if xy not in inside)


@pytest.mark.parametrize("size", [2, 4])
def test_t1_every_coverage_matches_the_literal_matrix(size: int) -> None:
    inside = ellipse_pixels((1, 2, 14, 11), 16, 12)
    for coverage in range(size * size + 1):
        op = dither_op("d", "blob", size=size, coverage=coverage, origin=(-3, 7))
        painted = grid(doc(16, 12, [op], [ELLIPSE]))
        assert painted == expected(16, 12, inside, size, coverage, -3, 7)


def test_t2_combined_non_rectangular_mask() -> None:
    masks = [
        {"id": "round", "type": "ellipse", "box": [0, 0, 12, 12]},
        {"id": "cut", "type": "polygon", "points": [[6, 0], [12, 0], [12, 6]]},
        {"id": "shape", "type": "subtract", "masks": ["round", "cut"]},
    ]
    # Even-odd over centres (x + 1/2, y + 1/2) of the triangle (6,0)-(12,0)-(12,6): the
    # slanted edge crosses row y at x = y + 6.5, which counts only when strictly to the
    # right of the centre, so a centre on it is inside: y <= x - 6 and x < 12.
    cut = {(x, y) for y in range(12) for x in range(12) if y <= x - 6}
    inside = ellipse_pixels((0, 0, 12, 12), 12, 12) - cut
    op = dither_op("d", "shape", size=4, coverage=6, origin=(-1, -2))
    assert grid(doc(12, 12, [op], masks)) == expected(12, 12, inside, 4, 6, -1, -2)


def test_transparent_colour_b_keeps_the_background() -> None:
    op = dither_op("d", "blob", size=2, coverage=2, origin=(0, 0), color_b="none")
    painted = grid(doc(16, 12, [op], [ELLIPSE]))
    inside = ellipse_pixels((1, 2, 14, 11), 16, 12)
    oracle = expected(16, 12, inside, 2, 2, 0, 0)
    assert painted == {xy: BG if rgba == B else rgba for xy, rgba in oracle.items()}


def test_dither_without_background_leaves_outside_transparent() -> None:
    op = dither_op("d", "blob", size=2, coverage=1, origin=(0, 0))
    painted = grid(doc(16, 12, [op], [ELLIPSE], background=False))
    inside = ellipse_pixels((1, 2, 14, 11), 16, 12)
    assert all(painted[xy] == CLEAR for xy in painted if xy not in inside)
    assert {painted[xy] for xy in inside} == {A, B}


# --- AC2: negative origins and translations by the period -------------------------------


@pytest.mark.parametrize("size", [2, 4])
def test_ac2_origin_translations_by_the_period_give_identical_bytes(size: int) -> None:
    def rgba(origin: tuple[int, int]) -> bytes:
        op = dither_op("d", "blob", size=size, coverage=size * size // 2 + 1, origin=origin)
        return render(doc(16, 12, [op], [ELLIPSE])).rgba

    reference = rgba((2, 1))
    for kx, ky in ((-1, 0), (0, -1), (-3, -5), (7, 2), (-262_144, 262_143)):
        assert rgba((2 + kx * size, 1 + ky * size)) == reference
    assert rgba((3, 1)) != reference  # a shift that is not a period does change it


# --- T2: seams between tiles and repetition without flicker -----------------------------


@pytest.mark.parametrize("size", [2, 4])
def test_t2_adjacent_tiles_with_a_shared_anchor_have_no_seam(size: int) -> None:
    masks = [
        {"id": "left", "type": "rect", "box": [0, 0, 7, 12]},
        {"id": "right", "type": "rect", "box": [7, 0, 16, 12]},
        {"id": "whole", "type": "rect", "box": [0, 0, 16, 12]},
    ]
    for coverage in range(size * size + 1):
        kw: dict[str, Any] = {"size": size, "coverage": coverage, "origin": (-9, 5)}
        tiles = [dither_op("l", "left", **kw), dither_op("r", "right", **kw)]
        whole = [dither_op("w", "whole", **kw)]
        assert render(doc(16, 12, tiles, masks)).rgba == render(doc(16, 12, whole, masks)).rgba


def test_t2_repeated_renders_never_flicker() -> None:
    op = dither_op("d", "blob", size=4, coverage=9, origin=(-7, -2))
    document = doc(16, 12, [op], [ELLIPSE])
    first = render(document)
    for _ in range(4):
        again = render(document)
        assert (again.rgba, again.digest) == (first.rgba, first.digest)


# --- Pipeline details -------------------------------------------------------------------


def test_mask_outside_the_canvas_warns_and_builds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        pipeline_module, "_dither_part", lambda *args: calls.append("built")
    )  # never called: the declared box is empty
    masks = [{"id": "far", "type": "rect", "box": [40, 40, 44, 44]}]
    op = dither_op("d", "far", size=2, coverage=2, origin=(0, 0))
    result = render(doc(4, 4, [op], masks))
    assert [w.json_pointer for w in result.warnings] == ["/layers/1/operations/0"]
    assert calls == []
    assert {result.pixel(x, y) for y in range(4) for x in range(4)} == {BG}


def test_layer_mask_and_dither_mask_share_the_same_nodes() -> None:
    masks = [
        {"id": "top", "type": "rect", "box": [0, 0, 4, 2]},
        {"id": "left", "type": "rect", "box": [0, 0, 2, 4]},
    ]
    op = dither_op("d", "top", size=2, coverage=4, origin=(0, 0))
    source = tree(4, 4, [op], masks)
    source["layers"][1]["mask_id"] = "left"
    painted = grid(validate_document(source))
    assert {xy for xy, rgba in painted.items() if rgba == B} == {(0, 0), (1, 0), (0, 1), (1, 1)}


def test_evaluate_mask_rejects_wrong_types() -> None:
    leaf = MaskShape("m", rasterize_rect(Box(0, 0, 2, 2), Dimensions(4, 4)))
    assert evaluate_mask(leaf, Dimensions(4, 4)).count == 4
    with pytest.raises(TypeError):
        evaluate_mask("m", Dimensions(4, 4))  # type: ignore[arg-type]  # not a mask node
    with pytest.raises(TypeError):
        evaluate_mask(leaf, (4, 4))  # type: ignore[arg-type]  # not Dimensions


def test_facade_lists_and_summarises_dither() -> None:
    assert "dither" in capabilities().operations
    assert "dither" not in capabilities().planned_operations
    op = dither_op("d", "blob", size=2, coverage=1, origin=(0, 0))
    report = inspect_document(doc(16, 12, [op], [ELLIPSE]))
    summary = report.layers[1].operations[0]
    assert (summary.id, summary.type, summary.color) == ("d", "dither", "ca")
    assert report.budget.operations == 2  # document operations: background rect + dither


# --- budget-v5 --------------------------------------------------------------------------


def test_budget_v5_hand_oracle() -> None:
    """4 x 4 canvas (A = 16), one layer, a 4 x 2 rect mask, size 2, coverage 2."""
    masks = [{"id": "top", "type": "rect", "box": [0, 0, 4, 2]}]
    op = dither_op("d", "top", size=2, coverage=2, origin=(0, 0))
    document = doc(4, 4, [op], masks, background=False)
    estimate = plan_budget(document)
    # mask: floor 1 + raster 8 = 9 visits, 8 bytes; dither: 2 x (9 + 4 x 8) = 82 visits
    # and 8 + 8 + 8 x (4 + 2) + 2 x 4 + 4096 = 4168 bytes
    assert estimate.operation_costs[0].pixel_visits == 82
    assert estimate.operation_costs[0].mask_bytes == 8 + 8 + 48 + 8 + DITHER_FIXED_BYTES
    assert estimate.pixel_visits == 3 * 16 + 2 * 16 + 82
    # working max(40A, 14A + 80 x 4) = 640, plus the dither peak, plus one result 4A
    assert estimate.buffer_bytes == 640 + 4168 + 64
    assert estimate.estimator_version == ESTIMATOR_VERSION == "budget-v8"
    assert estimate.operations == 1 and estimate.fills == fill_count(document) == 2


def test_dither_cost_of_an_empty_mask_is_the_floor() -> None:
    masks = [{"id": "far", "type": "rect", "box": [40, 40, 44, 44]}]
    document = doc(4, 4, [dither_op("d", "far", size=4, coverage=1, origin=(0, 0))], masks)
    estimate = mask_estimates(document)["far"]
    assert estimate.box is None
    assert dither_cost(estimate, 4) == (2 * estimate.pixel_visits, estimate.buffer_bytes)


def test_operations_budget_counts_two_fills_per_dither() -> None:
    masks = [{"id": "top", "type": "rect", "box": [0, 0, 4, 2]}]
    ops = [
        {"id": f"p{i}", "type": "pixel", "at": [0, 0], "color": "ca"}
        for i in range(MAX_OPERATIONS - 2)
    ]
    ops.append(dither_op("d", "top", size=2, coverage=2, origin=(0, 0)))
    # 10 000 operations are within the document limit; the reader's node limit only
    # lets a model built in Python reach it, which is what plan_budget may receive.
    document = Document.model_validate(tree(4, 4, ops, masks))
    with pytest.raises(BudgetExceeded) as raised:
        plan_budget(document)
    assert raised.value.context == {
        "resource": "operations",
        "limit": MAX_OPERATIONS,
        "estimated": MAX_OPERATIONS + 1,
    }
    single = doc(4, 4, [ops[-1]], masks, background=False)
    with pytest.raises(BudgetExceeded):
        render(single, limits=RenderLimits(max_operations=1))
    assert render(single, limits=RenderLimits(max_operations=2)).width == 4


def test_dither_origin_is_checked_against_geometry_limits() -> None:
    masks = [{"id": "top", "type": "rect", "box": [0, 0, 4, 2]}]
    op = dither_op("d", "top", size=2, coverage=2, origin=(-900, 3))
    document = doc(4, 4, [op], masks)
    limits = RenderLimits(geometry=GeometryLimits(max_coordinate=512))
    with pytest.raises(BudgetExceeded) as raised:
        plan_budget(document, limits)
    assert raised.value.json_pointer == "/layers/1/operations/0"
    assert raised.value.context["resource"] == "coordinate"
    assert raised.value.context["estimated"] == 900


def test_cost_plan_of_an_unvalidated_dither_fails_fast() -> None:
    source = tree(4, 4, [dither_op("d", "ghost", size=2, coverage=1, origin=(0, 0))], [])
    document = Document.model_validate(source)
    for plan in (estimate_cost, plan_budget):
        with pytest.raises(ReferenceError) as raised:
            plan(document)
        assert raised.value.context["reason"] == "unknown_mask"
    with pytest.raises(ReferenceError) as raised:
        render(document)  # validation runs first and locates the reference
    assert raised.value.json_pointer == "/layers/1/operations/0/mask_id"


def test_peak_memory_with_dither_stays_within_the_estimate() -> None:
    size = 160
    masks = [
        {"id": f"r{i}", "type": "ellipse", "box": [i, i, size - i, size - i]} for i in range(4)
    ]
    masks.append({"id": "rings", "type": "xor", "masks": [f"r{i}" for i in range(4)]})
    ops = [
        dither_op(f"d{i}", "rings", size=4, coverage=3 + i, origin=(-i, 2 * i)) for i in range(3)
    ]
    document = doc(size, size, ops, masks)
    estimate = plan_budget(document)
    tracemalloc.start()
    try:
        render(document)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= estimate.buffer_bytes


box_strategy = st.tuples(
    st.integers(-3, 6), st.integers(-3, 6), st.integers(1, 6), st.integers(1, 6)
)


@settings(max_examples=40, deadline=None)
@given(
    width=st.integers(1, 7),
    height=st.integers(1, 7),
    boxes=st.lists(box_strategy, min_size=1, max_size=3),
    size=st.sampled_from([2, 4]),
    data=st.data(),
    origin=st.tuples(st.integers(-9, 9), st.integers(-9, 9)),
    layer_mask=st.booleans(),
)
def test_plan_budget_admission_means_render_succeeds_with_dither(
    width: int,
    height: int,
    boxes: list[tuple[int, int, int, int]],
    size: int,
    data: Any,
    origin: tuple[int, int],
    layer_mask: bool,
) -> None:
    """With limits exactly at the plan, the compositor's own check never rejects."""
    coverage = data.draw(st.integers(0, size * size))
    masks: list[dict[str, Any]] = [
        {"id": f"s{i}", "type": "ellipse" if i % 2 else "rect", "box": [x, y, x + w, y + h]}
        for i, (x, y, w, h) in enumerate(boxes)
    ]
    target = "s0"
    if len(masks) > 1:
        masks.append({"id": "top", "type": "xor", "masks": [m["id"] for m in masks]})
        target = "top"
    source = tree(
        width,
        height,
        [dither_op("d", target, size=size, coverage=coverage, origin=origin)],
        masks,
        background=False,
    )
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


def test_report_separates_operations_from_fills_on_the_example() -> None:
    """dither-dusk: 8 operations (5 sky, 3 dune), 4 of them dithers, so 12 fills."""
    source = Path(__file__).resolve().parents[3] / "examples/specs/dither-dusk.moana.json"
    document = validate_document(source.read_bytes())
    estimate = estimate_cost(document)
    assert (estimate.operations, estimate.fills) == (8, 12)
    report = inspect_document(document, limits=RenderLimits(max_operations=8))
    assert (report.budget.operations, report.budget.fills) == (8, 12)
    assert not report.budget.within_limits
    (exceeded,) = report.budget.exceeded
    assert (exceeded.resource, exceeded.limit, exceeded.estimated) == ("operations", 8, 12)
    assert inspect_document(document, limits=RenderLimits(max_operations=12)).budget.within_limits
