"""Rasteriser memory stays within the budget-v1 estimate (ADR-012, ADR-015).

Each mask stores exactly the estimator's mask term (1 byte per pixel of the clipped
operation bounds) and the traced peak adds only per-row temporaries.
"""

from __future__ import annotations

import tracemalloc
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

from moanart.core.budget import RenderLimits
from moanart.core.canvas import Canvas
from moanart.core.coordinates import Box, Dimensions, Point
from moanart.geometry import (
    FLOOD_FILL_BYTES_PER_PIXEL,
    Mask,
    flood_fill,
    rasterize_ellipse,
    rasterize_line,
    rasterize_pixel,
    rasterize_polygon,
    rasterize_rect,
)
from moanart.render import estimate_cost
from moanart.schema import validate_document

SIDE = 512
DIMS = Dimensions(SIDE, SIDE)
ROW_OVERHEAD = 64 * 1024
# 258 vertices alternating between rows 0 and 500: up to 256 crossings per row.
ZIGZAG = [[x * 2, 0 if x % 2 else 500] for x in range(256)] + [[510, 511], [0, 511]]

OPERATIONS: dict[str, dict[str, Any]] = {
    "pixel": {"type": "pixel", "at": [7, 9]},
    "line": {"type": "line", "start": [-300, 20], "end": [700, 490]},
    "rect": {"type": "rect", "box": [-10, 3, 400, 600]},
    "ellipse": {"type": "ellipse", "box": [-100, -50, 480, 530]},
    "polygon": {"type": "polygon", "points": ZIGZAG},
}


def _point(pair: list[int]) -> Point:
    return Point(pair[0], pair[1])


def _rasterize(spec: dict[str, Any]) -> Callable[[], Mask]:
    match spec["type"]:
        case "pixel":
            return lambda: rasterize_pixel(_point(spec["at"]), DIMS)
        case "line":
            return lambda: rasterize_line(_point(spec["start"]), _point(spec["end"]), DIMS)
        case "rect":
            return lambda: rasterize_rect(Box(*spec["box"]), DIMS)
        case "ellipse":
            return lambda: rasterize_ellipse(Box(*spec["box"]), DIMS)
        case _:
            return lambda: rasterize_polygon([_point(p) for p in spec["points"]], DIMS)


@pytest.mark.parametrize("name", sorted(OPERATIONS))
def test_rasteriser_peak_memory_within_estimate(name: str) -> None:
    spec = OPERATIONS[name]
    document = validate_document(
        {
            "schema_version": "1.0",
            "id": "doc",
            "canvas": {"width": SIDE, "height": SIDE},
            "palette": {"id": "pal", "colors": [{"id": "ink", "rgba": "#000000FF"}]},
            "layers": [
                {"id": "layer", "name": "L", "operations": [{"id": "op", "color": "ink", **spec}]}
            ],
        }
    )
    estimate = estimate_cost(document)
    (cost,) = estimate.operation_costs
    run = _rasterize(spec)
    tracemalloc.start()
    try:
        mask = run()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    stored = 0 if mask.box is None else mask.box.area
    assert stored == cost.mask_bytes  # storage is exactly the estimator's mask term
    assert peak <= cost.mask_bytes + ROW_OVERHEAD
    assert peak <= estimate.buffer_bytes
    assert not mask.is_empty


def test_flood_fill_peak_memory_within_its_estimate() -> None:
    # Vertical comb: every row has SIDE / 2 runs, the worst case for the run stack.
    pixels = np.zeros((SIDE, SIDE, 4), dtype=np.uint8)
    pixels[:, :, 3] = 255
    pixels[: SIDE - 1, 1::2, 0] = 200  # teeth of another colour; the last row joins them
    snapshot = Canvas.from_array(pixels, limits=RenderLimits())
    del pixels
    tracemalloc.start()
    try:
        mask = flood_fill(snapshot, Point(0, 0), limits=RenderLimits())
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert mask.count == SIDE * SIDE // 2 + SIDE // 2
    assert peak <= FLOOD_FILL_BYTES_PER_PIXEL * SIDE * SIDE + ROW_OVERHEAD
