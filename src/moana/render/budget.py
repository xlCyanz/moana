"""Cost plan of a validated document, checked before any buffer exists (MOANA-003).

The estimator (``budget-v1``) is pure integer arithmetic over the document: it never
allocates pixels, imports NumPy or Pillow, or iterates over pixels. It is an upper
bound that the rasterisers and compositor of later issues must respect; a change in
their memory or work pattern updates these formulas and :data:`ESTIMATOR_VERSION`.

For a canvas of ``A = width * height`` pixels and ``frames`` frames:

* **Operation visits** (MOANA.md section 20: clipped bbox x passes, lines before
  clipping): ``pixel`` 1 if on the canvas else 0; ``rect`` and ``ellipse`` the area
  of the box clipped to the canvas; ``polygon`` the clipped area of its pixel-centre
  bounds plus ``clipped rows x vertices`` for scanline crossings; ``line``
  ``max(|dx|, |dy|) + 1`` Bresenham steps, *not* clipped.
* **Frame visits**: ``A`` (clear) + per visible layer ``A`` (clear) + its operation
  visits + ``A`` (composite) + ``A`` (alpha normalisation) + ``A`` (result copy).
  Hidden layers cost nothing. Total visits = ``frames x`` frame visits.
* **Buffer bytes**: working set ``4A`` canvas + ``4A`` layer + ``32A`` composite
  accumulator (four 64-bit channels) + the largest operation mask (1 byte per
  clipped bbox pixel), plus ``frames x 4A`` retained results.
* **Frame pixels**: ``frames x A``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, assert_never

from moana.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moana.core.coordinates import Box, Dimensions, require_int
from moana.core.errors import BudgetExceeded, ErrorDetail
from moana.schema import (
    Document,
    EllipseOperation,
    LineOperation,
    Operation,
    PixelOperation,
    PolygonOperation,
    RectOperation,
)

__all__ = [
    "ESTIMATOR_VERSION",
    "MAX_FRAMES",
    "CostEstimate",
    "OperationCost",
    "estimate_cost",
    "plan_budget",
]

ESTIMATOR_VERSION: Final = "budget-v1"
RGBA_BYTES: Final = 4
COMPOSITE_BYTES_PER_PIXEL: Final = 32
MASK_BYTES_PER_PIXEL: Final = 1
# MOANA.md section 17: at most 256 frames per export.
MAX_FRAMES: Final = 256
# Operations between two cooperative deadline checks.
CHECKPOINT_EVERY: Final = 256


@dataclass(frozen=True, slots=True)
class OperationCost:
    """Estimated work and temporary mask of one operation, located by pointer."""

    json_pointer: str
    pixel_visits: int
    mask_bytes: int


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """Whole-request estimate; compare it with :class:`RenderLimits` before raster."""

    estimator_version: str
    frames: int
    pixel_visits: int
    buffer_bytes: int
    frame_pixels: int
    operations: int
    layers: int
    operation_costs: tuple[OperationCost, ...]


def _clipped_area(box: Box | None, canvas: Box) -> tuple[int, int]:
    """Area and row count of ``box`` clipped to ``canvas`` (zero when disjoint)."""
    clipped = box.intersection(canvas) if box is not None else None
    if clipped is None:
        return 0, 0
    return clipped.area, clipped.height


def _polygon_bounds(operation: PolygonOperation) -> Box | None:
    """Box of every pixel whose centre can lie inside the polygon, if any."""
    xs = [x for x, _ in operation.points]
    ys = [y for _, y in operation.points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x0 == x1 or y0 == y1:
        return None
    return Box(x0, y0, x1, y1)


def _line_bounds(operation: LineOperation) -> Box:
    (x0, y0), (x1, y1) = operation.start, operation.end
    return Box(min(x0, x1), min(y0, y1), max(x0, x1) + 1, max(y0, y1) + 1)


def _operation_cost(operation: Operation, canvas: Box, pointer: str) -> OperationCost:
    match operation:
        case PixelOperation():
            visits = 1 if canvas.contains(operation.point) else 0
            return OperationCost(pointer, visits, visits * MASK_BYTES_PER_PIXEL)
        case LineOperation():
            (x0, y0), (x1, y1) = operation.start, operation.end
            steps = max(abs(x1 - x0), abs(y1 - y0)) + 1
            area, _ = _clipped_area(_line_bounds(operation), canvas)
            return OperationCost(pointer, steps, area * MASK_BYTES_PER_PIXEL)
        case RectOperation() | EllipseOperation():
            area, _ = _clipped_area(operation.bbox, canvas)
            return OperationCost(pointer, area, area * MASK_BYTES_PER_PIXEL)
        case PolygonOperation():
            area, rows = _clipped_area(_polygon_bounds(operation), canvas)
            visits = area + rows * len(operation.points)
            return OperationCost(pointer, visits, area * MASK_BYTES_PER_PIXEL)
        case _:  # pragma: no cover - a new operation type must add its formula
            assert_never(operation)


def estimate_cost(
    document: Document, *, frames: int = 1, deadline: Deadline | None = None
) -> CostEstimate:
    """Estimate work and memory of rendering ``frames`` frames of ``document``.

    Pure arithmetic in time linear in the number of operations and vertices.
    ``frames`` counts identical renders of this document; an animation whose frames
    differ must sum one estimate per evaluated frame. ``deadline`` is checked per
    layer and every :data:`CHECKPOINT_EVERY` operations.
    """
    require_int(frames, "frames", minimum=1, maximum=MAX_FRAMES)
    dimensions: Dimensions = document.canvas.dimensions
    area = dimensions.area
    canvas = Box.from_dimensions(dimensions)
    costs: list[OperationCost] = []
    frame_visits = 3 * area  # clear the canvas, normalise alpha, copy the result
    largest_mask = 0
    operations = 0
    for layer_index, layer in enumerate(document.layers):
        if deadline is not None:
            deadline.checkpoint("estimate_layer")
        operations += len(layer.operations)
        if not layer.visible:
            continue
        frame_visits += 2 * area  # clear the layer buffer, composite it
        for index, operation in enumerate(layer.operations):
            if deadline is not None and index % CHECKPOINT_EVERY == CHECKPOINT_EVERY - 1:
                deadline.checkpoint("estimate_operation")
            pointer = f"/layers/{layer_index}/operations/{index}"
            cost = _operation_cost(operation, canvas, pointer)
            costs.append(cost)
            frame_visits += cost.pixel_visits
            largest_mask = max(largest_mask, cost.mask_bytes)
    working = (2 * RGBA_BYTES + COMPOSITE_BYTES_PER_PIXEL) * area + largest_mask
    return CostEstimate(
        estimator_version=ESTIMATOR_VERSION,
        frames=frames,
        pixel_visits=frames * frame_visits,
        buffer_bytes=working + frames * RGBA_BYTES * area,
        frame_pixels=frames * area,
        operations=operations,
        layers=len(document.layers),
        operation_costs=tuple(costs),
    )


def _exceeded(resource: str, limit: int, estimated: int, pointer: str | None) -> ErrorDetail:
    return ErrorDetail(
        BudgetExceeded.code,
        f"estimated {resource} exceed the request budget",
        json_pointer=pointer,
        context={"resource": resource, "limit": limit, "estimated": estimated},
    )


def _most_expensive(estimate: CostEstimate) -> str | None:
    if not estimate.operation_costs:
        return None
    return max(estimate.operation_costs, key=lambda cost: cost.pixel_visits).json_pointer


def _geometry_details(
    document: Document, limits: RenderLimits, deadline: Deadline | None
) -> list[ErrorDetail]:
    geometry = limits.geometry
    canvas = document.canvas
    details: list[ErrorDetail] = []
    for axis in ("width", "height"):
        value = getattr(canvas, axis)
        if value > geometry.max_dimension:
            details.append(
                _exceeded("canvas_dimension", geometry.max_dimension, value, f"/canvas/{axis}")
            )
    if canvas.dimensions.area > geometry.max_area:
        details.append(
            _exceeded("canvas_area", geometry.max_area, canvas.dimensions.area, "/canvas")
        )
    for layer_index, layer in enumerate(document.layers):
        for index, operation in enumerate(layer.operations):
            if deadline is not None and index % CHECKPOINT_EVERY == CHECKPOINT_EVERY - 1:
                deadline.checkpoint("check_geometry")
            reach = _coordinate_reach(operation)
            if reach > geometry.max_coordinate:
                pointer = f"/layers/{layer_index}/operations/{index}"
                details.append(_exceeded("coordinate", geometry.max_coordinate, reach, pointer))
    return details


def _coordinate_reach(operation: Operation) -> int:
    """Largest absolute pixel coordinate an operation names (excluded edges - 1)."""
    match operation:
        case PixelOperation():
            values: tuple[int, ...] = operation.at
        case LineOperation():
            values = (*operation.start, *operation.end)
        case RectOperation() | EllipseOperation():
            x0, y0, x1, y1 = operation.box
            values = (x0, y0, x1 - 1, y1 - 1)
        case PolygonOperation():
            values = tuple(c for point in operation.points for c in point)
        case _:  # pragma: no cover - a new operation type must add its reach
            assert_never(operation)
    return max(abs(value) for value in values)


def plan_budget(
    document: Document,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
    *,
    frames: int = 1,
    deadline: Deadline | None = None,
) -> CostEstimate:
    """Estimate ``document`` and reject it before any allocation if over ``limits``.

    Raises :class:`BudgetExceeded` listing every exceeded resource in ``details``
    (``resource``, ``limit`` and ``estimated`` in each context; the pointer locates
    the canvas, the offending operation or the most expensive operation). A request
    exactly at a limit is admitted.
    """
    require_int(frames, "frames", minimum=1, maximum=MAX_FRAMES)
    layers = len(document.layers)
    operations = sum(len(layer.operations) for layer in document.layers)
    counts = (
        ("layers", limits.max_layers, layers, "/layers"),
        ("operations", limits.max_operations, operations, "/layers"),
    )
    _raise_if_any(  # cheap counts first: reject before costing every operation
        [
            _exceeded(name, limit, value, pointer)
            for name, limit, value, pointer in counts
            if value > limit
        ]
    )
    estimate = estimate_cost(document, frames=frames, deadline=deadline)
    details = _geometry_details(document, limits, deadline)
    checks = (
        ("pixel_visits", limits.max_pixel_visits, estimate.pixel_visits, _most_expensive(estimate)),
        ("buffer_bytes", limits.max_buffer_bytes, estimate.buffer_bytes, None),
        ("frame_pixels", limits.max_frame_pixels, estimate.frame_pixels, None),
    )
    details.extend(
        _exceeded(resource, limit, estimated, pointer)
        for resource, limit, estimated, pointer in checks
        if estimated > limit
    )
    _raise_if_any(details)
    return estimate


def _raise_if_any(details: list[ErrorDetail]) -> None:
    if not details:
        return
    first = details[0]
    raise BudgetExceeded(
        f"request exceeds {len(details)} budget{'s' if len(details) != 1 else ''}",
        json_pointer=first.json_pointer,
        context=dict(first.context),
        details=details,
    )
