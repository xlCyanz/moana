"""Render and budget of ``shade`` operations (MOANA-015, MOANART.md sections 9-10, ADR-028).

AC1: overlaps take the last listed band and every painted colour is a ramp colour.
T1: empty bands, overlaps, clamp and orientation changes at document level. T2: hand
fixtures with 3- and 5-tone ramps and boundary pixels (canvas edge, band contacts,
diagonals). ``budget-v7`` figures are computed by hand.
"""

from __future__ import annotations

import json
import tracemalloc
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moanart.api import inspect_document
from moanart.core import errors
from moanart.core.budget import RenderLimits
from moanart.core.coordinates import Box, Dimensions
from moanart.palette import RAMP_LUMINANCE_NOT_INCREASING, RAMP_TRANSPARENT_STEP
from moanart.render import ESTIMATOR_VERSION, estimate_cost, plan_budget, render
from moanart.render.budget import (
    SHADE_FIXED_BYTES,
    SHADE_FOLD_BYTES,
    SHADE_PASSES,
    MaskEstimate,
    fill_count,
    mask_estimates,
    shade_cost,
    shade_later,
)
from moanart.render.pipeline import _plan_masks, _shade_band
from moanart.schema import Document, validate_document
from moanart.techniques import ShadeLight, analyze_clusters, band_index

ROOT = Path(__file__).resolve().parents[3]
RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)
TONES: dict[str, RGBA] = {
    "t0": (32, 32, 64, 255),
    "t1": (64, 64, 112, 255),
    "t2": (96, 96, 160, 255),
    "t3": (144, 144, 208, 255),
    "t4": (208, 208, 240, 255),
}
HEX = {key: "#{:02X}{:02X}{:02X}{:02X}".format(*value) for key, value in TONES.items()}
SYMBOL = {value: key[1] for key, value in TONES.items()} | {CLEAR: "."}


def light(direction: str, height: int, intensity: int, ambient: int) -> dict[str, Any]:
    return {"direction": direction, "height": height, "intensity": intensity, "ambient": ambient}


def band(band_id: str, mask_id: str, facing: str, offset: int = 0) -> dict[str, Any]:
    return {"id": band_id, "mask_id": mask_id, "facing": facing, "offset": offset}


def shade(
    bands: list[dict[str, Any]],
    lamp: dict[str, Any],
    *,
    ramp: str = "ramp",
    order: str = "monotonic",
) -> dict[str, Any]:
    return {
        "id": "shading",
        "type": "shade",
        "ramp": ramp,
        "ramp_order": order,
        "light": lamp,
        "bands": bands,
    }


def tree(
    width: int,
    height: int,
    operations: list[dict[str, Any]],
    masks: list[dict[str, Any]],
    *,
    tones: int = 3,
    colors: dict[str, str] | None = None,
    profile: str = "strict",
) -> dict[str, Any]:
    palette = colors if colors is not None else HEX
    ramp = ["t0", "t2", "t4"] if tones == 3 else ["t0", "t1", "t2", "t3", "t4"]
    return {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": width, "height": height, "profile": profile},
        "palette": {
            "id": "pal",
            "colors": [{"id": key, "rgba": value} for key, value in palette.items()],
            "ramps": [{"id": "ramp", "colors": ramp}],
        },
        "masks": masks,
        "layers": [{"id": "volume", "name": "Volumen", "operations": operations}],
    }


def grid(document: Document) -> list[str]:
    result = render(document)
    return [
        "".join(SYMBOL[result.pixel(x, y)] for x in range(result.width))
        for y in range(result.height)
    ]


def rect(mask_id: str, box: list[int]) -> dict[str, Any]:
    return {"id": mask_id, "type": "rect", "box": box}


HALVES = [rect("left", [0, 0, 5, 4]), rect("right", [3, 0, 8, 4])]


# --- AC1 / T1: overlaps, orientation, clamp, empty bands -----------------------------------


def test_ac1_overlap_takes_the_last_band_and_only_ramp_colours() -> None:
    """``nw`` light, height 0, intensity 1, ambient 1, 3-tone ramp ``t0, t2, t4``.

    ``left`` faces nw: 1 + round(6/6) = 2 (t4); ``right`` faces se: 1 - 1 = 0 (t0).
    Columns 3-4 belong to both; ``right`` is listed last and wins.
    """
    bands = [band("lit", "left", "nw"), band("dark", "right", "se")]
    document = validate_document(tree(8, 4, [shade(bands, light("nw", 0, 1, 1))], HALVES))
    assert grid(document) == ["44400000"] * 4
    result = render(document)
    ramp = {TONES["t0"], TONES["t2"], TONES["t4"]}
    assert {result.pixel(x, y) for x in range(8) for y in range(4)} <= ramp
    assert result.warnings == ()


def test_t1_listing_order_decides_the_overlap() -> None:
    bands = [band("dark", "right", "se"), band("lit", "left", "nw")]
    document = validate_document(tree(8, 4, [shade(bands, light("nw", 0, 1, 1))], HALVES))
    assert grid(document) == ["44444000"] * 4


def test_t1_turning_the_light_swaps_the_tones_without_touching_the_masks() -> None:
    bands = [band("lit", "left", "nw"), band("dark", "right", "se")]
    document = validate_document(tree(8, 4, [shade(bands, light("se", 0, 1, 1))], HALVES))
    assert grid(document) == ["00044444"] * 4
    side = validate_document(tree(8, 4, [shade(bands, light("ne", 0, 1, 1))], HALVES))
    assert grid(side) == ["22222222"] * 4  # perpendicular: both at the ambient step


def test_t1_offsets_are_clamped_to_the_ramp() -> None:
    bands = [band("over", "left", "nw", 4095), band("under", "right", "se", -4095)]
    document = validate_document(tree(8, 4, [shade(bands, light("nw", 0, 4095, 4095))], HALVES))
    assert grid(document) == ["44400000"] * 4


def test_t1_empty_bands_paint_nothing() -> None:
    masks = [*HALVES, rect("far", [20, 20, 24, 24])]
    bands = [band("lost", "far", "nw"), band("lit", "left", "front")]
    document = validate_document(tree(8, 4, [shade(bands, light("front", 0, 1, 0))], masks))
    assert grid(document) == ["22222..."] * 4
    empty = validate_document(
        tree(8, 4, [shade([band("lost", "far", "nw")], light("n", 0, 1, 0))], masks)
    )
    result = render(empty)
    assert [w.code for w in result.warnings] == ["empty_bounds"]
    assert result.rgba == bytes(4 * 32)


FIVE = ["t0", "t1", "t2", "t3", "t4"]
FACING_CHOICES = ["n", "ne", "e", "se", "s", "sw", "w", "nw", "front", "none"]
rect_strategy = st.tuples(
    st.integers(-2, 6), st.integers(-2, 6), st.integers(1, 5), st.integers(1, 5)
)


@settings(max_examples=80, deadline=None)
@given(
    rects=st.lists(rect_strategy, min_size=1, max_size=6),
    facings=st.lists(st.sampled_from(FACING_CHOICES), min_size=6, max_size=6),
    offsets=st.lists(st.integers(-3, 3), min_size=6, max_size=6),
    direction=st.sampled_from(["n", "ne", "e", "se", "s", "sw", "w", "nw", "front"]),
    height=st.integers(0, 3),
    intensity=st.integers(0, 4),
    ambient=st.integers(0, 4),
)
def test_ac1_every_pixel_takes_the_ramp_step_of_the_last_band_containing_it(
    rects: list[tuple[int, int, int, int]],
    facings: list[str],
    offsets: list[int],
    direction: str,
    height: int,
    intensity: int,
    ambient: int,
) -> None:
    """Oracle: pixel sets of each rect by hand; the last listed rect containing a pixel
    decides it, and its colour is ``ramp[band_index(...)]``; uncovered pixels stay clear.
    """
    masks = [rect(f"r{i}", [x, y, x + w, y + h]) for i, (x, y, w, h) in enumerate(rects)]
    bands = [band(f"b{i}", f"r{i}", facings[i], offsets[i]) for i in range(len(rects))]
    lamp = light(direction, height, intensity, ambient)
    document = validate_document(tree(6, 6, [shade(bands, lamp)], masks, tones=5))
    result = render(document)
    sources = ShadeLight(direction, height, intensity, ambient)  # type: ignore[arg-type]  # sampled literal
    covers = [
        {(px, py) for px in range(x, x + w) for py in range(y, y + h)} for x, y, w, h in rects
    ]
    for py in range(6):
        for px in range(6):
            owners = [i for i, cover in enumerate(covers) if (px, py) in cover]
            expected = CLEAR
            if owners:
                last = owners[-1]
                step = band_index(facings[last], offsets[last], sources, 5)  # type: ignore[arg-type]  # sampled literal
                expected = TONES[FIVE[step]]
            assert result.pixel(px, py) == expected, (px, py)


def test_ac1_exact_pixels_on_a_one_pixel_canvas() -> None:
    """1 x 1 canvas, ``e`` light, height 0, intensity 2, ambient 2, 5-tone ramp.

    ``lit`` (faces e, +4 step: 2 + round(12/6)= 4) and ``dark`` (faces w, 2 - 2 = 0)
    both cover the pixel; ``far`` covers nothing. ``dark`` is listed after ``lit`` and
    ``far`` is last but empty, so the pixel is t0.
    """
    masks = [rect("dot", [0, 0, 1, 1]), rect("away", [3, 3, 4, 4])]
    bands = [band("lit", "dot", "e"), band("dark", "dot", "w"), band("far", "away", "e")]
    document = validate_document(tree(1, 1, [shade(bands, light("e", 0, 2, 2))], masks, tones=5))
    result = render(document)
    assert result.pixel(0, 0) == TONES["t0"]
    swapped = [bands[1], bands[0], bands[2]]
    again = validate_document(tree(1, 1, [shade(swapped, light("e", 0, 2, 2))], masks, tones=5))
    assert render(again).pixel(0, 0) == TONES["t4"]


def test_ac1_translucent_ramp_steps_never_blend_two_bands() -> None:
    """In ``rgba``, the last band replaces the first one in the overlap instead of
    compositing over it: the overlap shows the translucent step over transparency."""
    colors = {"t0": "#FF000080", "t2": "#00FF00FF", "t4": "#0000FFFF"}
    bands = [band("lit", "left", "nw"), band("dark", "right", "se")]
    source = tree(8, 4, [shade(bands, light("nw", 0, 1, 1), order="stylized")], HALVES)
    source["palette"]["colors"] = [{"id": k, "rgba": v} for k, v in colors.items()]
    source["canvas"]["profile"] = "rgba"
    result = render(validate_document(source))
    assert result.pixel(1, 1) == (0, 0, 255, 255)
    assert result.pixel(3, 1) == (255, 0, 0, 128)  # not red over blue
    assert [w.code for w in result.warnings] == ["RAMP_PARTIAL_ALPHA_STEP"]


# --- T2: hand fixtures ----------------------------------------------------------------------


def test_t2_five_tone_fixture_with_boundary_pixels() -> None:
    """``e`` light, height 1, intensity 3, ambient 2, ramp ``t0..t4``.

    * ``all`` (``[-2, -2, 8, 8]``, clipped to the canvas), facing ``none``: step 2;
    * ``west`` (``[-1, 0, 3, 6]``), facing ``w``: 2 + round(3 * -4 / 6) = 0;
    * ``slope`` (line (0, 5)-(5, 0)), facing ``n`` (perpendicular), offset 1: 3;
    * ``spark`` (pixel (5, 0)), facing ``e``, offset 3: 2 + 2 + 3 = 7, clamped to 4.
    """
    masks = [
        rect("all", [-2, -2, 8, 8]),
        rect("west", [-1, 0, 3, 6]),
        {"id": "slope", "type": "line", "start": [0, 5], "end": [5, 0]},
        {"id": "spark", "type": "pixel", "at": [5, 0]},
    ]
    bands = [
        band("base", "all", "none"),
        band("shadow", "west", "w"),
        band("ridge", "slope", "n", 1),
        band("glint", "spark", "e", 3),
    ]
    document = validate_document(tree(6, 6, [shade(bands, light("e", 1, 3, 2))], masks, tones=5))
    assert grid(document) == [
        "000224",
        "000232",
        "000322",
        "003222",
        "030222",
        "300222",
    ]


def test_t2_three_tone_fixture_under_a_front_light() -> None:
    """``front`` light, intensity 1, ambient 0, ramp ``t0, t2, t4``.

    ``body`` faces front: 0 + 1 = 1 (t2). ``rim`` (top row of the body) faces ``n``:
    a front light gives it 0, plus offset 2 (t4). ``foot`` (bottom row, partly off the
    canvas) faces ``s``: 0 (t0). Pixels outside every band stay transparent.
    """
    masks = [
        rect("body", [1, 1, 5, 6]),
        rect("rim", [1, 1, 5, 2]),
        rect("foot", [0, 5, 9, 9]),
    ]
    bands = [band("face", "body", "front"), band("top", "rim", "n", 2), band("low", "foot", "s")]
    document = validate_document(tree(6, 6, [shade(bands, light("front", 2, 1, 0))], masks))
    assert grid(document) == [
        "......",
        ".4444.",
        ".2222.",
        ".2222.",
        ".2222.",
        "000000",
    ]


# --- luminance warning (configurable) -------------------------------------------------------


def test_monotonic_order_warns_about_a_stylised_ramp_and_stylized_documents_it() -> None:
    bands = [band("lit", "left", "nw")]
    source = tree(8, 4, [shade(bands, light("nw", 0, 1, 1))], HALVES)
    source["palette"]["ramps"][0]["colors"] = ["t0", "t4", "t2"]  # brighter, then darker
    result = render(validate_document(source))
    assert [(w.code, w.json_pointer) for w in result.warnings] == [
        (RAMP_LUMINANCE_NOT_INCREASING, "/layers/0/operations/0/ramp")
    ]
    source["layers"][0]["operations"][0]["ramp_order"] = "stylized"
    assert render(validate_document(source)).warnings == ()


def test_stylized_order_still_reports_transparent_steps() -> None:
    source = tree(8, 4, [shade([band("lit", "left", "nw")], light("nw", 0, 1, 1))], HALVES)
    source["palette"]["colors"].append({"id": "hole", "rgba": "#00000000"})
    source["palette"]["ramps"][0]["colors"] = ["t0", "hole", "t4"]
    source["layers"][0]["operations"][0]["ramp_order"] = "stylized"
    assert [w.code for w in render(validate_document(source)).warnings] == [RAMP_TRANSPARENT_STEP]


# --- budget-v7 ----------------------------------------------------------------------------


def test_budget_v7_hand_oracle() -> None:
    """8 x 4 canvas (A = 32); ``left`` and ``right`` are 20-pixel rects that overlap.

    Each leaf: 1 + 20 = 21 visits, 20 bytes. Band 0 folds band 1 (boxes meet):
    21 + 4 x 20 + (21 + 20) = 142 visits, 20 + max(20, 20) + 8192 + 24576 = 32808
    bytes. Band 1: 21 + 80 = 101 visits, 40 + 8192 bytes.
    """
    bands = [band("lit", "left", "nw"), band("dark", "right", "se")]
    document = validate_document(tree(8, 4, [shade(bands, light("nw", 0, 1, 1))], HALVES))
    estimate = plan_budget(document)
    assert SHADE_PASSES == 4
    assert estimate.operation_costs[0].pixel_visits == 142 + 101 == 243
    assert (SHADE_FIXED_BYTES, SHADE_FOLD_BYTES) == (8192, 3 * 8192)
    assert estimate.operation_costs[0].mask_bytes == 32808
    assert estimate.pixel_visits == 3 * 32 + 2 * 32 + 243
    # compositor working set, unchanged since budget-v2 (ADR-018): 4A canvas + 4A layer
    # + 32A accumulator = 40A = 1280, never below the compositor's own 14A + 80 x tile
    # with tile = min(4096, max(1, A // 4)) = 8, i.e. 448 + 640 = 1088; then the largest
    # mask (the band peak) and one retained 4A = 128 result
    assert estimate.buffer_bytes == 1280 + 32808 + 128
    assert estimate.estimator_version == ESTIMATOR_VERSION == "budget-v8"
    assert estimate.fills == fill_count(document) == 2


def test_only_later_bands_that_meet_a_band_are_folded() -> None:
    boxes: list[Box | None] = [Box(0, 0, 4, 4), None, Box(4, 0, 8, 4), Box(3, 3, 5, 5)]
    assert shade_later(boxes, 0) == (3,)
    assert shade_later(boxes, 1) == ()
    assert shade_later(boxes, 2) == (3,)
    assert shade_later(boxes, 3) == ()
    estimates = [
        MaskEstimate(Box(0, 0, 4, 4), 17, 16),
        MaskEstimate(None, 1, 0),
        MaskEstimate(Box(4, 0, 8, 4), 17, 16),
        MaskEstimate(Box(3, 3, 5, 5), 5, 4),
    ]
    # band 0: 17 + 64 + (5 + 16) visits, 16 + 16 + 8192 + 24576 bytes; band 2: same;
    # band 3: 5 + 16 visits, 4 + 4 + 8192 bytes; band 1 is never built
    assert shade_cost(estimates) == (102 + 102 + 21, 32 + 8192 + 24576)


def test_cost_plan_of_an_unvalidated_shade_fails_fast() -> None:
    source = tree(4, 4, [shade([band("b", "ghost", "n")], light("n", 0, 1, 0))], [])
    document = Document.model_validate(source)
    for plan in (estimate_cost, plan_budget):
        with pytest.raises(errors.ReferenceError) as raised:
            plan(document)
        assert raised.value.context["reason"] == "unknown_mask"


def test_inspect_summarises_the_shade_without_a_colour() -> None:
    bands = [band("lit", "left", "nw"), band("dark", "right", "se")]
    report = inspect_document(
        validate_document(tree(8, 4, [shade(bands, light("nw", 0, 1, 1))], HALVES))
    )
    summary = report.layers[0].operations[0]
    assert (summary.id, summary.type, summary.color) == ("shading", "shade", None)
    assert report.budget.fills == 2


def _ring_masks(size: int) -> list[dict[str, Any]]:
    return [
        {"id": "big", "type": "ellipse", "box": [10, 10, size - 10, size - 10]},
        {"id": "hole", "type": "ellipse", "box": [60, 60, size - 60, size - 60]},
        {"id": "ring", "type": "subtract", "masks": ["big", "hole"]},
        {"id": "east", "type": "rect", "box": [size // 2, 0, size, size]},
        {"id": "east_ring", "type": "intersect", "masks": ["ring", "east"]},
        {"id": "spot", "type": "ellipse", "box": [20, 20, 80, 80]},
    ]


def test_peak_memory_with_shading_stays_within_the_estimate() -> None:
    size = 200
    bands = [
        band("base", "big", "front"),
        band("rim", "ring", "s"),
        band("side", "east_ring", "e"),
        band("glow", "spot", "nw", 1),
    ]
    document = validate_document(
        tree(size, size, [shade(bands, light("nw", 1, 2, 2))], _ring_masks(size), tones=5)
    )
    estimate = plan_budget(document)
    tracemalloc.start()
    try:
        render(document)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= estimate.buffer_bytes


@pytest.mark.parametrize("first", ["big", "ring", "east_ring", "spot"])
def test_band_fill_peak_stays_within_its_cost(first: str) -> None:
    """One band fill (its mask and every later mask, one at a time) on a 200² canvas."""
    size = 200
    order = ["big", "ring", "east_ring", "spot"]
    later = order[order.index(first) + 1 :]
    document = validate_document(
        tree(
            size,
            size,
            [shade([band(f"b_{m}", m, "n") for m in [first, *later]], light("n", 0, 1, 1))],
            _ring_masks(size),
        )
    )
    dims = Dimensions(size, size)
    nodes = _plan_masks(document, dims)
    estimates = mask_estimates(document)
    _, bound = shade_cost([estimates[first], *(estimates[m] for m in later)])
    boxes = [estimates[m].box for m in [first, *later]]
    folded = tuple(nodes[[first, *later][j]] for j in (0, *shade_later(boxes, 0)))
    _shade_band(folded, dims, None)  # warm-up: the coverage tracer allocates on first run
    tracemalloc.start()
    try:
        result = _shade_band(folded, dims, None)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= bound
    assert not result.is_empty


@pytest.mark.parametrize("size", [16, 128, 512, 2048])
@pytest.mark.parametrize("kind", ["rect", "ellipse", "triangle"])
@pytest.mark.parametrize("later", [0, 1, 4])
def test_band_fill_peak_bound_holds_across_sizes(size: int, kind: str, later: int) -> None:
    """Peak of the first band fill with ``later`` overlapping later bands (tracemalloc).

    Measured overhead over ``area + evaluation``: about 1.5 KB without later masks
    and at most about 18.8 KB with them (NumPy iteration buffers); 8 KB and 8 KB + 24 KB
    are budgeted. The warm-up run keeps the coverage tracer's first-run allocations
    (10-35 KB) out of the measurement. Triangles are ``polygon``
    leaves inside an ``intersect`` with the canvas, so band masks are combinations too.
    """
    masks: list[dict[str, Any]] = []
    for i in range(later + 1):
        x0, y0, x1, y1 = i, i, size - i, size // 2 + i + 1
        if kind == "triangle":
            points = [[x0, y0], [x1, y0], [x0, y1]]
            masks.append({"id": f"p{i}", "type": "polygon", "points": points})
            masks.append({"id": f"c{i}", "type": "rect", "box": [0, 0, size, size]})
            masks.append({"id": f"m{i}", "type": "intersect", "masks": [f"p{i}", f"c{i}"]})
        else:
            masks.append({"id": f"m{i}", "type": kind, "box": [x0, y0, x1, y1]})
    ids = [f"m{i}" for i in range(later + 1)]
    bands = [band(f"b{i}", mask_id, "none") for i, mask_id in enumerate(ids)]
    document = validate_document(tree(size, size, [shade(bands, light("n", 0, 0, 0))], masks))
    dims = Dimensions(size, size)
    nodes = _plan_masks(document, dims)
    estimates = mask_estimates(document)
    _, bound = shade_cost([estimates[mask_id] for mask_id in ids])
    folded = shade_later([estimates[mask_id].box for mask_id in ids], 0)
    assert folded == tuple(range(1, later + 1))
    fill = tuple(nodes[ids[j]] for j in (0, *folded))
    _shade_band(fill, dims, None)  # warm-up: the coverage tracer allocates on first run
    tracemalloc.start()
    try:
        _shade_band(fill, dims, None)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= bound


def _layout_box(layout: str, i: int, width: int, height: int) -> list[int]:
    """Band boxes moved along one edge at a time, or along all four."""
    box = {
        "x0": [i, 0, width, height],
        "y0": [0, i, width, height],
        "x1": [0, 0, width - i, height],
        "y1": [0, 0, width, height - i],
        "shift": [i % 9, (3 * i) % 7, width - i % 5, height - i % 11],
        "diag": [i, i % 7, width - i % 5, height - i],
    }[layout]
    x0, y0 = min(box[0], width - 1), min(box[1], height - 1)
    return [x0, y0, max(box[2], x0 + 1), max(box[3], y0 + 1)]


@pytest.mark.parametrize(
    ("width", "height", "count", "layout"),
    [
        (64, 64, 8, "x0"),
        (64, 64, 8, "y0"),
        (64, 64, 8, "x1"),
        (64, 64, 8, "y1"),
        (256, 256, 8, "shift"),  # the largest overhead measured: 18 793 bytes
        (256, 256, 64, "diag"),  # band 47 folds 16 later bands
        (2048, 1, 8, "shift"),
        (1, 2048, 8, "shift"),
        (2048, 2048, 4, "shift"),
    ],
)
def test_every_band_fill_peak_stays_within_its_cost(
    width: int, height: int, count: int, layout: str
) -> None:
    """Every band of a ``shade`` (rects and ellipses alternating), measured alone."""
    ids = [f"m{i}" for i in range(count)]
    masks: list[dict[str, Any]] = [
        {
            "id": mask_id,
            "type": "ellipse" if i % 2 else "rect",
            "box": _layout_box(layout, i, width, height),
        }
        for i, mask_id in enumerate(ids)
    ]
    bands = [band(f"b{i}", mask_id, "none") for i, mask_id in enumerate(ids)]
    source = tree(width, height, [shade(bands, light("n", 0, 0, 0))], masks, profile="rgba")
    document = validate_document(source)
    dims = Dimensions(width, height)
    nodes = _plan_masks(document, dims)
    estimates = mask_estimates(document)
    boxes = [estimates[mask_id].box for mask_id in ids]
    for index in range(count):
        _, bound = shade_cost([estimates[mask_id] for mask_id in ids[index:]])
        fill = tuple(nodes[ids[j]] for j in (index, *shade_later(boxes, index)))
        _shade_band(fill, dims, None)  # warm-up: the coverage tracer allocates on first run
        tracemalloc.start()
        try:
            _shade_band(fill, dims, None)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert peak <= bound, (index, peak, bound)


box_strategy = st.tuples(
    st.integers(-3, 6), st.integers(-3, 6), st.integers(1, 6), st.integers(1, 6)
)


@settings(max_examples=40, deadline=None)
@given(
    width=st.integers(1, 8),
    height=st.integers(1, 8),
    boxes=st.lists(box_strategy, min_size=1, max_size=4),
    facings=st.lists(st.sampled_from(["n", "se", "front", "none"]), min_size=4, max_size=4),
    layer_mask=st.booleans(),
)
def test_plan_budget_admission_means_render_succeeds_with_shade(
    width: int,
    height: int,
    boxes: list[tuple[int, int, int, int]],
    facings: list[str],
    layer_mask: bool,
) -> None:
    """With limits exactly at the plan, the compositor's own check never rejects."""
    masks: list[dict[str, Any]] = [
        {"id": f"s{i}", "type": "ellipse" if i % 2 else "rect", "box": [x, y, x + w, y + h]}
        for i, (x, y, w, h) in enumerate(boxes)
    ]
    if len(masks) > 1:
        masks.append({"id": "top", "type": "xor", "masks": [m["id"] for m in masks]})
    bands = [band(f"b{i}", m["id"], facings[i % 4]) for i, m in enumerate(masks)]
    source = tree(width, height, [shade(bands, light("n", 1, 1, 1))], masks)
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


# --- example --------------------------------------------------------------------------------


def test_shaded_orb_example_uses_only_ramp_ink_and_transparency() -> None:
    path = ROOT / "examples" / "specs" / "shaded-orb.moanart.json"
    document = validate_document(json.loads(path.read_text(encoding="utf-8")))
    result = render(document)
    assert result.warnings == ()
    palette = {
        color.id: tuple(int(color.rgba[i : i + 2], 16) for i in (1, 3, 5, 7))
        for color in document.palette.colors
    }
    seen = {result.pixel(x, y) for x in range(24) for y in range(24)}
    allowed = set(palette.values()) | {CLEAR}
    assert seen <= allowed
    # light nw, height 1, intensity 3, ambient 1: body (front) 2, lit (nw) 3, shadow (se)
    # clamped to 0, terminators (ne / sw, +1) 2, bounce (se, +2) 1, highlight (nw, +1)
    # 4 -- all five tones appear
    assert {palette[f"orb_{i}"] for i in range(5)} <= seen
    assert result.pixel(8, 8) == palette["orb_4"]  # inside the highlight
    assert result.pixel(11, 11) == palette["orb_2"]  # the body, front facing
    # the bounce is clipped to the lower right and the terminators soften the 2 -> 0
    # jump on the ring: no stray one-pixel cluster is left (MOANART.md section 19)
    clusters = analyze_clusters(result.rgba, Dimensions(24, 24))
    assert clusters.singletons == 0
    assert clusters.warnings == ()
