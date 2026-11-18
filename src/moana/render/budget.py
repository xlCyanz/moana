"""Cost plan of a validated document, checked before any buffer exists (MOANA-003).

The estimator (``budget-v3``, ADR-018 and ADR-022) is pure integer arithmetic over
the document: it never allocates pixels, imports NumPy or Pillow, or iterates over
pixels. It is an upper bound that the rasterisers and compositor respect; a change in
their memory or work pattern updates these formulas and :data:`ESTIMATOR_VERSION`.

For a canvas of ``A = width * height`` pixels and ``frames`` frames, every operation
has a *mask box*, :func:`mask_box`: the storage box of its rasterised mask, clipped
to the canvas.

* **Operation visits** (MOANA.md section 20: clipped bbox x passes, lines before
  clipping) are raster work plus one paint pass over the mask box. Raster work:
  ``pixel`` 1 if on the canvas else 0; ``rect`` and ``ellipse`` the mask box area;
  ``polygon`` the mask box area plus ``clipped rows x vertices`` for scanline
  crossings; ``line`` ``max(|dx|, |dy|) + 1`` Bresenham steps, *not* clipped.
  (``budget-v1`` omitted the paint pass, which for a long diagonal line is far more
  than its steps.)
* **Frame visits**: ``A`` (clear) + per visible layer ``A`` (clear) + its operation
  visits + ``A`` (composite) + ``A`` (alpha normalisation) + ``A`` (result copy).
  Hidden layers cost nothing. Total visits = ``frames x`` frame visits.
* **Buffer bytes**: working set ``4A`` canvas + ``4A`` layer + ``32A`` composite
  accumulator (four 64-bit channels) + the largest operation mask (1 byte per
  clipped bbox pixel), plus ``frames x 4A`` retained results. The ``40A`` term is
  never below the compositor's own bound ``14A + 80 x tile`` (tile =
  ``min(4096, max(1, A // 4))`` pixels), which only exceeds it on canvases of one or
  two pixels.
* **Semantic masks** (``budget-v3``, ADR-022; a document without masks costs exactly
  as in ``budget-v2``): for a visible layer with ``mask_id`` the mask expression is
  expanded without a memo, so a shared mask counts once per reference. Every
  evaluated node costs at least :data:`MASK_NODE_VISITS` (the floor that keeps an
  expanded DAG of empty masks from being free). A node whose result box is empty
  costs that floor alone: neither its operands nor a leaf's raster are evaluated. A
  non-empty leaf adds its raster work (as above, without the paint pass); a
  non-empty combination adds ``2 x`` its result box (zeroing and final scan) plus,
  per operand, the operand's cost and one fold over the operand's box. Copying the
  result's bits adds its box and clearing the layer outside the mask adds ``A``.
  Bytes: the evaluation peak (a leaf's box, or a combination's box plus its most
  expensive operand; ``0`` when empty) plus one copy of the result, which takes the
  place of the largest operation mask when larger. The result box
  (:func:`moana.core.coordinates.combined_box`) is the hull of the operand boxes for
  ``union``/``xor``, their intersection for ``intersect`` and the first operand's
  box for ``subtract``. These are the formulas of
  :func:`moana.layers.mask_cost` plus each evaluated leaf's raster work.
* **Frame pixels**: ``frames x A``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, assert_never

from moana.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moana.core.coordinates import Box, Dimensions, combined_box, require_int
from moana.core.errors import BudgetExceeded, ErrorDetail, ReferenceError
from moana.schema import (
    CombinationMask,
    Document,
    EllipseMask,
    EllipseOperation,
    LineMask,
    LineOperation,
    MaskNode,
    Operation,
    PixelMask,
    PixelOperation,
    PolygonMask,
    PolygonOperation,
    RectMask,
    RectOperation,
    ShapeMask,
)

__all__ = [
    "ESTIMATOR_VERSION",
    "MASK_NODE_VISITS",
    "MAX_FRAMES",
    "CostEstimate",
    "MaskEstimate",
    "OperationCost",
    "estimate_cost",
    "mask_box",
    "mask_estimates",
    "plan_budget",
]

ESTIMATOR_VERSION: Final = "budget-v3"
RGBA_BYTES: Final = 4
COMPOSITE_BYTES_PER_PIXEL: Final = 32
MASK_BYTES_PER_PIXEL: Final = 1
# MOANA.md section 17: at most 256 frames per export.
MAX_FRAMES: Final = 256
# Compositor working set without groups (ADR-017, ADR-018): root, layer and result
# copies, a deferred mask and its copy (14A) and 80 bytes per kernel tile pixel.
COMPOSITOR_BYTES_PER_PIXEL: Final = 14
COMPOSITOR_TILE_BYTES: Final = 80
COMPOSITOR_MAX_TILE: Final = 4096
# Cost floor of one evaluated mask node reference (ADR-022); equals
# moana.layers.MASK_NODE_VISITS, which this module cannot import (no NumPy here).
MASK_NODE_VISITS: Final = 1
# Operations between two cooperative deadline checks.
CHECKPOINT_EVERY: Final = 256

Geometry = Operation | ShapeMask
"""Anything rasterised from primitive geometry: an operation or a mask leaf."""


@dataclass(frozen=True, slots=True)
class OperationCost:
    """Estimated work and temporary mask of one operation, located by pointer.

    A layer clipped by a semantic mask also gets one entry, at ``.../mask_id``, with
    the work and bytes of evaluating its mask and clearing the layer outside it.
    """

    json_pointer: str
    pixel_visits: int
    mask_bytes: int


@dataclass(frozen=True, slots=True)
class MaskEstimate:
    """Result box, expanded work and evaluation peak bytes of one mask (ADR-022)."""

    box: Box | None
    pixel_visits: int
    buffer_bytes: int


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


def _polygon_bounds(operation: PolygonOperation | PolygonMask) -> Box | None:
    """Box of every pixel whose centre can lie inside the polygon, if any."""
    xs = [x for x, _ in operation.points]
    ys = [y for _, y in operation.points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x0 == x1 or y0 == y1:
        return None
    return Box(x0, y0, x1, y1)


def _line_bounds(operation: LineOperation | LineMask) -> Box:
    (x0, y0), (x1, y1) = operation.start, operation.end
    return Box(min(x0, x1), min(y0, y1), max(x0, x1) + 1, max(y0, y1) + 1)


def mask_box(operation: Geometry, dimensions: Dimensions) -> Box | None:
    """Storage box of an operation's (or mask leaf's) mask clipped to the canvas.

    ``None`` if empty. It equals the box of the mask that :mod:`moana.geometry`
    returns (a polygon with collinear bounds has none), so ``render`` can declare it
    before rasterising.
    """
    match operation:
        case PixelOperation() | PixelMask():
            box: Box | None = Box.from_point(operation.point)
        case LineOperation() | LineMask():
            box = _line_bounds(operation)
        case RectOperation() | EllipseOperation() | RectMask() | EllipseMask():
            box = operation.bbox
        case PolygonOperation() | PolygonMask():
            box = _polygon_bounds(operation)
        case _:  # pragma: no cover - a new operation type must add its box
            assert_never(operation)
    return None if box is None else box.clip_to(dimensions)


def _area(box: Box | None) -> int:
    return 0 if box is None else box.area


def _raster_work(operation: Geometry, box: Box | None) -> int:
    """Visits of rasterising ``operation`` into its clipped mask ``box`` (no paint)."""
    match operation:
        case PixelOperation() | RectOperation() | EllipseOperation():
            return _area(box)
        case PixelMask() | RectMask() | EllipseMask():
            return _area(box)
        case LineOperation() | LineMask():
            (x0, y0), (x1, y1) = operation.start, operation.end
            return max(abs(x1 - x0), abs(y1 - y0)) + 1
        case PolygonOperation() | PolygonMask():
            rows = 0 if box is None else box.height
            return _area(box) + rows * len(operation.points)
        case _:  # pragma: no cover - a new operation type must add its formula
            assert_never(operation)


def _operation_cost(operation: Operation, dimensions: Dimensions, pointer: str) -> OperationCost:
    box = mask_box(operation, dimensions)
    area = _area(box)
    return OperationCost(pointer, _raster_work(operation, box) + area, area * MASK_BYTES_PER_PIXEL)


def _leaf_estimate(mask: ShapeMask, dimensions: Dimensions) -> MaskEstimate:
    box = mask_box(mask, dimensions)
    work = 0 if box is None else _raster_work(mask, box)  # an empty leaf is not built
    return MaskEstimate(box, MASK_NODE_VISITS + work, _area(box))


def _combination_estimate(
    operator: str, operands: list[MaskEstimate], dimensions: Dimensions
) -> MaskEstimate:
    box = combined_box(operator, [operand.box for operand in operands], dimensions)
    if box is None:
        return MaskEstimate(None, MASK_NODE_VISITS, 0)  # empty: no operand is evaluated
    area = box.area
    visits = 2 * area + sum(operand.pixel_visits + _area(operand.box) for operand in operands)
    peak = area + max(operand.buffer_bytes for operand in operands)
    return MaskEstimate(box, MASK_NODE_VISITS + visits, peak)


def _unknown_mask() -> ReferenceError:
    return ReferenceError(
        "mask does not exist", context={"field": "mask_id", "reason": "unknown_mask"}
    )


def mask_estimates(document: Document) -> dict[str, MaskEstimate]:
    """Estimate of every mask of ``document``, keyed by mask ID.

    Operands are estimated before the masks that use them. A shared mask is
    estimated once here, while its users count its cost once per reference. A
    document that skipped validation is still safe: a reference to a missing mask
    raises ``ReferenceError`` (``unknown_mask``) and a cycle ``ReferenceError``
    (``mask_cycle``), in time linear in the references.
    """
    dimensions = document.canvas.dimensions
    masks: dict[str, MaskNode] = {mask.id: mask for mask in document.masks}
    estimates: dict[str, MaskEstimate] = {}
    expanding: set[str] = set()  # the current path; membership only, never order
    for mask in document.masks:
        work: list[tuple[MaskNode, bool]] = [(mask, False)]
        while work:
            node, ready = work.pop()
            if node.id in estimates:
                continue
            if not isinstance(node, CombinationMask):
                estimates[node.id] = _leaf_estimate(node, dimensions)
            elif ready:
                expanding.discard(node.id)
                operands = [estimates[name] for name in node.masks]
                estimates[node.id] = _combination_estimate(node.type, operands, dimensions)
            elif node.id in expanding:
                raise ReferenceError(
                    "mask references form a cycle",
                    context={"field": "masks", "reason": "mask_cycle"},
                )
            else:
                expanding.add(node.id)
                work.append((node, True))
                for name in reversed(node.masks):
                    if name not in masks:
                        raise _unknown_mask()
                    work.append((masks[name], False))
    return estimates


def estimate_cost(
    document: Document, *, frames: int = 1, deadline: Deadline | None = None
) -> CostEstimate:
    """Estimate work and memory of rendering ``frames`` frames of ``document``.

    Pure arithmetic in time linear in the number of operations, vertices and mask
    references. ``frames`` counts identical renders of this document; an animation
    whose frames differ must sum one estimate per evaluated frame. ``deadline`` is
    checked per layer and every :data:`CHECKPOINT_EVERY` operations.
    """
    require_int(frames, "frames", minimum=1, maximum=MAX_FRAMES)
    dimensions: Dimensions = document.canvas.dimensions
    area = dimensions.area
    costs: list[OperationCost] = []
    frame_visits = 3 * area  # clear the canvas, normalise alpha, copy the result
    largest_mask = 0
    operations = 0
    masks = mask_estimates(document)
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
            cost = _operation_cost(operation, dimensions, pointer)
            costs.append(cost)
            frame_visits += cost.pixel_visits
            largest_mask = max(largest_mask, cost.mask_bytes)
        if layer.mask_id is not None:
            if layer.mask_id not in masks:
                raise _unknown_mask()
            mask = masks[layer.mask_id]
            copy = _area(mask.box)
            cost = OperationCost(
                f"/layers/{layer_index}/mask_id",
                mask.pixel_visits + copy + area,  # evaluate, copy its bits, clear outside
                mask.buffer_bytes + copy,  # evaluation peak + result copy
            )
            costs.append(cost)
            frame_visits += cost.pixel_visits
            largest_mask = max(largest_mask, cost.mask_bytes)
    tile = min(COMPOSITOR_MAX_TILE, max(1, area // 4))
    compositor = COMPOSITOR_BYTES_PER_PIXEL * area + COMPOSITOR_TILE_BYTES * tile
    working = max((2 * RGBA_BYTES + COMPOSITE_BYTES_PER_PIXEL) * area, compositor)
    working += largest_mask
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


def _located_geometry(document: Document) -> list[tuple[str, Geometry]]:
    """Every operation and mask leaf with its pointer, in document order."""
    located: list[tuple[str, Geometry]] = [
        (f"/layers/{layer_index}/operations/{index}", operation)
        for layer_index, layer in enumerate(document.layers)
        for index, operation in enumerate(layer.operations)
    ]
    located += [
        (f"/masks/{index}", mask)
        for index, mask in enumerate(document.masks)
        if not isinstance(mask, CombinationMask)
    ]
    return located


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
    for position, (pointer, operation) in enumerate(_located_geometry(document)):
        if deadline is not None and position % CHECKPOINT_EVERY == CHECKPOINT_EVERY - 1:
            deadline.checkpoint("check_geometry")
        reach = _coordinate_reach(operation)
        if reach > geometry.max_coordinate:
            details.append(_exceeded("coordinate", geometry.max_coordinate, reach, pointer))
    return details


def _coordinate_reach(operation: Geometry) -> int:
    """Largest absolute pixel coordinate a geometry names (excluded edges - 1)."""
    match operation:
        case PixelOperation() | PixelMask():
            values: tuple[int, ...] = operation.at
        case LineOperation() | LineMask():
            values = (*operation.start, *operation.end)
        case RectOperation() | EllipseOperation() | RectMask() | EllipseMask():
            x0, y0, x1, y1 = operation.box
            values = (x0, y0, x1 - 1, y1 - 1)
        case PolygonOperation() | PolygonMask():
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
    the canvas, the offending operation or mask, or the most expensive operation or
    layer mask). A request exactly at a limit is admitted. ``document`` should be
    valid (:func:`moana.schema.validate_document`); a missing or cyclic mask
    reference still raises ``ReferenceError`` instead of looping (see
    :func:`mask_estimates`).
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
