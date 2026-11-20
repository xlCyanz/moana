"""Integer rasterisers of the first primitive family (MOANA.md section 6, ADR-015).

Every rule is evaluated with Python integers, never with Pillow ``ImageDraw`` or
AggDraw defaults, and every mask is clipped to the canvas without wraparound:

* ``pixel``: exactly one pixel.
* ``line``: endpoints sorted lexicographically, then the symmetric Bresenham of
  section 6 (``e2 = 2 * err``; step x if ``e2 >= dy``, step y if ``e2 <= dx``), both
  endpoints included.
* ``rect``: the half-open box, filled.
* ``ellipse``: pixel ``(x, y)`` of box ``[x0, y0, x1, y1)`` is included when
  ``A^2 h^2 + B^2 w^2 <= w^2 h^2`` with ``A = 2x + 1 - x0 - x1`` and
  ``B = 2y + 1 - y0 - y1``. Solved exactly per row with ``math.isqrt``.
* ``polygon``: even-odd over pixel centres ``(x + 1/2, y + 1/2)``; horizontal edges
  are ignored and an edge is active on row ``y`` when ``min(ya, yb) <= y + 1/2 <
  max(ya, yb)``. Crossing abscissas are rationals compared through integer
  thresholds, so a self-intersecting polygon is never discarded by signed area.

Memory: each mask holds one byte per pixel of the clipped operation bounds (the
budget mask term); temporaries are per row (``O(width + vertices)``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from moana.core.coordinates import Box, Dimensions, Point
from moana.core.errors import ValidationError
from moana.core.limits import MAX_VERTICES
from moana.geometry.mask import Mask

__all__ = [
    "MIN_POLYGON_VERTICES",
    "rasterize_ellipse",
    "rasterize_line",
    "rasterize_pixel",
    "rasterize_polygon",
    "rasterize_rect",
]

MIN_POLYGON_VERTICES = 3

# An edge reduced to integers: (y_top, y_bottom, x_at_top, x_at_bottom), y_top < y_bottom.
_Edge = tuple[int, int, int, int]


def _require(value: object, kind: type, field: str) -> None:
    if not isinstance(value, kind):
        raise TypeError(f"{field} must be a {kind.__name__} value")


def _blank(box: Box) -> np.ndarray[tuple[int, int], np.dtype[np.bool_]]:
    return np.zeros((box.height, box.width), dtype=np.bool_)


def rasterize_pixel(point: Point, dimensions: Dimensions) -> Mask:
    """Mask of ``point`` if it lies on the canvas, else an empty mask."""
    _require(point, Point, "point")
    _require(dimensions, Dimensions, "dimensions")
    box = Box.from_point(point).clip_to(dimensions)
    if box is None:
        return Mask.empty()
    return Mask._adopt(box, np.ones((1, 1), dtype=np.bool_))


def rasterize_rect(box: Box, dimensions: Dimensions) -> Mask:
    """Filled half-open ``box`` clipped to the canvas."""
    _require(box, Box, "box")
    _require(dimensions, Dimensions, "dimensions")
    clipped = box.clip_to(dimensions)
    if clipped is None:
        return Mask.empty()
    return Mask._adopt(clipped, np.ones((clipped.height, clipped.width), dtype=np.bool_))


def rasterize_line(start: Point, end: Point, dimensions: Dimensions) -> Mask:
    """One-pixel Bresenham line including both endpoints; symmetric under reversal.

    Storage is the endpoints' bounding box clipped to the canvas. Steps run before
    clipping (``max(|dx|, |dy|) + 1``, as budgeted) and stop once the monotone path
    leaves the canvas.
    """
    _require(start, Point, "start")
    _require(end, Point, "end")
    _require(dimensions, Dimensions, "dimensions")
    if (end.x, end.y) < (start.x, start.y):
        start, end = end, start
    x, y, x1, y1 = start.x, start.y, end.x, end.y
    bounds = Box(x, min(y, y1), x1 + 1, max(y, y1) + 1)
    clipped = bounds.clip_to(dimensions)
    if clipped is None:
        return Mask.empty()
    bits = _blank(clipped)
    dx, dy = x1 - x, -abs(y1 - y)
    sy = 1 if y < y1 else -1
    err = dx + dy
    entered = False
    while True:
        if clipped.x0 <= x < clipped.x1 and clipped.y0 <= y < clipped.y1:
            bits[y - clipped.y0, x - clipped.x0] = True
            entered = True
        elif entered:
            break  # x and y are monotone: the path never re-enters the canvas
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += 1
        if e2 <= dx:
            err += dx
            y += sy
    return Mask._adopt(clipped, bits)


def rasterize_ellipse(box: Box, dimensions: Dimensions) -> Mask:
    """Pixels of ``box`` whose centre lies inside or on the inscribed ellipse.

    For row ``y`` the inclusion test reduces to ``|A| <= isqrt(w^2 (h^2 - B^2) // h^2)``,
    an exact integer interval of columns, so no per-pixel product is materialised.
    """
    _require(box, Box, "box")
    _require(dimensions, Dimensions, "dimensions")
    clipped = box.clip_to(dimensions)
    if clipped is None:
        return Mask.empty()
    bits = _blank(clipped)
    w, h = box.width, box.height
    centre_x = box.x0 + box.x1 - 1  # A = 2x - centre_x
    for y in range(clipped.y0, clipped.y1):
        b = 2 * y + 1 - box.y0 - box.y1  # |B| <= h - 1 inside the box
        reach = math.isqrt(w * w * (h * h - b * b) // (h * h))
        first = -((reach - centre_x) // 2)  # ceil((centre_x - reach) / 2)
        last = (centre_x + reach) // 2
        _fill_span(bits, clipped, y, first, last + 1)
    return Mask._adopt(clipped, bits)


def _fill_span(
    bits: np.ndarray[tuple[int, int], np.dtype[np.bool_]], clipped: Box, y: int, a: int, b: int
) -> None:
    """Set columns ``[a, b)`` of row ``y`` after clipping them to ``clipped``."""
    a, b = max(a, clipped.x0), min(b, clipped.x1)
    if a < b:
        bits[y - clipped.y0, a - clipped.x0 : b - clipped.x0] = True


def _polygon_points(points: object) -> tuple[Point, ...]:
    if isinstance(points, str | bytes) or not isinstance(points, Sequence):
        raise TypeError("points must be a sequence of Point values")
    if not MIN_POLYGON_VERTICES <= len(points) <= MAX_VERTICES:  # before iterating
        raise ValidationError(
            f"polygon requires {MIN_POLYGON_VERTICES} to {MAX_VERTICES} vertices",
            context={
                "field": "points",
                "reason": "out_of_range",
                "minimum": MIN_POLYGON_VERTICES,
                "maximum": MAX_VERTICES,
            },
        )
    vertices = tuple(points)
    for vertex in vertices:
        _require(vertex, Point, "polygon vertex")
    return vertices


def _edges(vertices: tuple[Point, ...]) -> list[_Edge]:
    """Non-horizontal edges oriented top to bottom; repeated vertices vanish here."""
    edges: list[_Edge] = []
    for a, b in zip(vertices, vertices[1:] + vertices[:1], strict=True):
        if a.y == b.y:
            continue
        top, bottom = (a, b) if a.y < b.y else (b, a)
        edges.append((top.y, bottom.y, top.x, bottom.x))
    return edges


def _row_thresholds(edges: list[_Edge], y: int) -> list[int]:
    """Sorted ``ceil(c - 1/2)`` of each crossing abscissa ``c`` on ``y + 1/2``.

    A centre ``x + 1/2`` has an odd number of crossings strictly to its right exactly
    when an odd number of crossings satisfy ``c <= x + 1/2``, i.e. ``threshold <= x``
    (the active crossing count is always even).
    """
    thresholds: list[int] = []
    for top, bottom, x_top, x_bottom in edges:
        if top <= y < bottom:
            # c = x_top + (x_bottom - x_top) * (2y + 1 - 2 top) / d with d = 2 (bottom - top)
            d = 2 * (bottom - top)
            numerator = x_top * d + (x_bottom - x_top) * (2 * y + 1 - 2 * top)
            thresholds.append(-((d - 2 * numerator) // (2 * d)))
    thresholds.sort()
    return thresholds


def rasterize_polygon(points: Sequence[Point], dimensions: Dimensions) -> Mask:
    """Even-odd fill of the closed polygon by pixel centres, without antialiasing.

    Storage is the box of every pixel whose centre can be inside (``[min x, max x)``
    by ``[min y, max y)``) clipped to the canvas; a collinear polygon is empty.
    """
    vertices = _polygon_points(points)
    _require(dimensions, Dimensions, "dimensions")
    xs = [vertex.x for vertex in vertices]
    ys = [vertex.y for vertex in vertices]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x0 == x1 or y0 == y1:
        return Mask.empty()
    clipped = Box(x0, y0, x1, y1).clip_to(dimensions)
    if clipped is None:
        return Mask.empty()
    bits = _blank(clipped)
    edges = _edges(vertices)
    for y in range(clipped.y0, clipped.y1):
        thresholds = _row_thresholds(edges, y)
        for a, b in zip(thresholds[0::2], thresholds[1::2], strict=True):
            _fill_span(bits, clipped, y, a, b)
    return Mask._adopt(clipped, bits)
