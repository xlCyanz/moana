"""Cost plan of a validated document, checked before any buffer exists (MOANA-003).

The estimator (``budget-v8``, ADR-018, ADR-022, ADR-023, ADR-025, ADR-027, ADR-028 and
ADR-030)
is pure integer arithmetic over
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
  crossings; ``line`` ``max(|dx|, |dy|) + 1`` Bresenham steps, *not* clipped;
  ``path`` (``budget-v4``, ADR-023) its ``S`` flattened segments, *not* clipped,
  plus, when its box is not empty, the coverage cells bound
  (:meth:`~moana.core.vector_path.FixedPath.cell_bound` over the coverage buffer:
  the box with a 1-pixel margin) and ``3 x`` the buffer area (clear, coverage
  sweep, threshold). (``budget-v1`` omitted the paint pass, which for a long
  diagonal line is far more than its steps.)
* **Frame visits**: ``A`` (clear) + per visible layer ``A`` (clear) + its operation
  visits + ``A`` (composite) + ``A`` (alpha normalisation) + ``A`` (result copy).
  Hidden layers cost nothing. Total visits = ``frames x`` frame visits.
* **Buffer bytes**: working set ``4A`` canvas + ``4A`` layer + ``32A`` composite
  accumulator (four 64-bit channels) + the largest operation mask (1 byte per
  clipped bbox pixel; a path adds ``2 x`` its buffer area, :data:`PATH_CELL_BYTES`
  per bounded cell, :data:`PATH_COMMAND_BYTES` per command and the backend's fixed
  native heap :data:`PATH_BACKEND_FIXED_BYTES`, which ``tracemalloc`` cannot see;
  :func:`moana.core.vector_path.path_raster_bytes`), plus
  ``frames x 4A`` retained results. The ``40A`` term is never below the
  compositor's own bound ``14A + 80 x tile`` (tile = ``min(4096, max(1, A // 4))``
  pixels), which only exceeds it on canvases of one or two pixels.
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
* **Paths** (``budget-v4``, ADR-023; a document without paths costs exactly as in
  ``budget-v3``): besides visits and bytes, a path whose cell bound exceeds
  :data:`~moana.core.limits.MAX_PATH_CELLS` is rejected (``path_cells``): the
  backend would drop cells silently. This is an engine limit that no
  ``RenderLimits`` raises.
* **Dithering** (``budget-v5``, ADR-025; a document without ``dither`` costs exactly
  as in ``budget-v4``): a ``dither`` operation paints two deferred fills, colour A and
  colour B, and each one evaluates the clipping mask ``mask_id`` again. With ``M``
  the :func:`mask_estimates` entry of that mask (result box ``Bm``), the operation
  costs ``2 x (M.pixel_visits + 4 x area(Bm))`` visits (evaluation, the periodic
  selection's gather, AND and emptiness scan, and the paint pass) and
  ``M.buffer_bytes + area(Bm) + 8 x (width(Bm) + height(Bm)) + N x width(Bm) +``
  :data:`DITHER_FIXED_BYTES` bytes (evaluation peak, the selected copy, the
  ``int64`` row and column indexes, one box-wide row per pattern row and the cell
  table), ``N`` being the matrix side. Since both fills reach the
  compositor, the ``operations`` budget counts raster fills: a ``dither`` counts 2.
* **Outlines** (``budget-v6``, ADR-027; a document without ``outline`` costs exactly
  as in ``budget-v5``): an ``outline`` paints one deferred fill that evaluates its
  mask ``mask_id`` (estimate ``M``, result box ``Bm``) and runs one dilation
  (``outer``) or erosion (``inner``) of radius ``w`` = ``width`` over the work box
  ``X``: ``Bm`` grown by ``w`` and clipped for ``outer``
  (:func:`moana.core.coordinates.grown_box`), ``Bm`` for ``inner``. With
  ``P = (width(X) + 2w + 1) x (height(X) + 2w + 1)`` (the padded box of the prefix
  sums), it costs ``M.pixel_visits +`` :data:`OUTLINE_PASSES` ``x P`` visits (source
  copy, two prefix-sum passes, compare, the subtraction fold and scan and the paint
  pass, all bounded by ``P``) and ``M.buffer_bytes + area(Bm) +
  morphology_bytes(X, w) + 2 x area(X)`` bytes (evaluation peak, the mask kept
  during the morphology, :func:`moana.core.morphology.morphology_bytes`, and the
  operand and result of the subtraction). An empty ``M`` costs ``M`` alone.
* **Band shading** (``budget-v7``, ADR-028; a document without ``shade`` costs exactly
  as in ``budget-v6``): a ``shade`` paints one deferred fill per band. Band ``i``
  (mask estimate ``Mi``, result box ``Bi``) folds into one buffer over ``Bi`` its
  own mask and every *later* band mask ``Mj`` whose box meets ``Bi``
  (:func:`shade_later`), so the last listed band wins. It costs
  ``Mi.pixel_visits +`` :data:`SHADE_PASSES` ``x area(Bi) + sum(Mj.pixel_visits +
  area(Bi))`` visits (zeroing, first fold, emptiness scan and paint pass, plus one
  fold per later mask) and ``area(Bi) + max(Mi.buffer_bytes, Mj.buffer_bytes...) +``
  :data:`SHADE_FIXED_BYTES` (``+`` :data:`SHADE_FOLD_BYTES` when some later mask is
  folded) bytes: the buffer, one mask evaluation at a time and the measured fixed
  overhead of the fill and of NumPy's iteration buffers. A band whose ``Bi`` is empty
  is never built and costs nothing. The operation's visits are the sum over its
  bands and its bytes the largest band (fills run one at a time); the ``operations``
  budget counts one fill per band. A ``shade`` has no coordinates of its own.
* **Materials** (``budget-v8``, ADR-030; a document without ``material`` or
  ``selective_outline`` costs exactly as in ``budget-v7``): a ``material`` paints one
  deferred fill per band and per part of its preset (``len(parts)`` offsets). The
  fill of band ``i`` and part ``p`` builds the band's visible part exactly as a
  ``shade`` band (its share of :func:`shade_cost`) and then the texture over the
  band box ``Bi``: with ``C`` the cells of :func:`moana.core.materials.cell_span` of
  ``Bi`` (``Cw x Ch``) and ``k`` the preset's hash channels, it adds
  ``C x (k x`` :data:`MATERIAL_HASH_VISITS` ``+ 2) +`` :data:`MATERIAL_PASSES`
  ``x area(Bi)`` visits (hashes, cell loop and comparison; gather, AND and emptiness
  scan) and its peak is ``max(band peak, 2 x area(Bi) +`` :data:`MATERIAL_CELL_BYTES`
  ``x C + Ch x width(Bi) + 8 x (width(Bi) + height(Bi)) +``
  :data:`MATERIAL_FIXED_BYTES` ``)`` bytes (visible part, selection, cell bytes and
  comparison, one box-wide row per cell row, ``int64`` indexes, hashing objects). A
  ``selective_outline`` paints a base fill over the outline box ``X`` (the ring of
  :func:`outline_cost` minus every segment mask whose box meets ``X``) and one fill
  per segment over the intersection of its box with ``X`` (the segment's visible
  part as a ``shade`` band, intersected with the ring); see
  :func:`selective_outline_cost`. ``operations`` counts ``len(bands) x len(parts)``
  fills per ``material`` and ``1 + len(segments)`` per ``selective_outline``.
* **Frame pixels**: ``frames x A``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, assert_never

from moana.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moana.core.coordinates import Box, Dimensions, combined_box, grown_box, require_int
from moana.core.dither import PATTERN_INDEX_BYTES
from moana.core.errors import BudgetExceeded, ErrorDetail, ReferenceError
from moana.core.limits import MAX_ANIMATION_FRAMES, MAX_PATH_CELLS
from moana.core.materials import MaterialPreset, cell_span, preset
from moana.core.morphology import morphology_bytes
from moana.core.vector_path import (
    PATH_BACKEND_FIXED_BYTES,
    PATH_BUFFER_MARGIN,
    PATH_CELL_BYTES,
    PATH_COMMAND_BYTES,
    FixedPath,
    path_buffer_box,
    path_raster_bytes,
    path_raster_visits,
)
from moana.schema import (
    CombinationMask,
    DitherOperation,
    Document,
    EllipseMask,
    EllipseOperation,
    LineMask,
    LineOperation,
    MaskNode,
    MaterialOperation,
    Operation,
    OutlineOperation,
    PathMask,
    PathOperation,
    PixelMask,
    PixelOperation,
    PolygonMask,
    PolygonOperation,
    RectMask,
    RectOperation,
    SelectiveOutlineOperation,
    ShadeOperation,
    ShapeMask,
    ShapeOperation,
)

__all__ = [
    "DITHER_FILLS",
    "DITHER_FIXED_BYTES",
    "DITHER_PASSES",
    "ESTIMATOR_VERSION",
    "MASK_NODE_VISITS",
    "MATERIAL_CELL_BYTES",
    "MATERIAL_FIXED_BYTES",
    "MATERIAL_HASH_VISITS",
    "MATERIAL_PASSES",
    "MAX_FRAMES",
    "OUTLINE_PASSES",
    "PATH_BACKEND_FIXED_BYTES",
    "PATH_BUFFER_MARGIN",
    "PATH_CELL_BYTES",
    "PATH_COMMAND_BYTES",
    "SHADE_FIXED_BYTES",
    "SHADE_FOLD_BYTES",
    "SHADE_PASSES",
    "CostEstimate",
    "MaskEstimate",
    "OperationCost",
    "dither_cost",
    "estimate_cost",
    "fill_count",
    "mask_box",
    "mask_estimates",
    "material_cost",
    "outline_box",
    "outline_cost",
    "plan_budget",
    "selective_outline_cost",
    "shade_cost",
    "shade_later",
]

ESTIMATOR_VERSION: Final = "budget-v8"
RGBA_BYTES: Final = 4
COMPOSITE_BYTES_PER_PIXEL: Final = 32
MASK_BYTES_PER_PIXEL: Final = 1
# MOANA.md section 17: at most 256 frames per export.
MAX_FRAMES: Final = MAX_ANIMATION_FRAMES
# Compositor working set without groups (ADR-017, ADR-018): root, layer and result
# copies, a deferred mask and its copy (14A) and 80 bytes per kernel tile pixel.
COMPOSITOR_BYTES_PER_PIXEL: Final = 14
COMPOSITOR_TILE_BYTES: Final = 80
COMPOSITOR_MAX_TILE: Final = 4096
# Cost floor of one evaluated mask node reference (ADR-022); equals
# moana.layers.MASK_NODE_VISITS, which this module cannot import (no NumPy here).
MASK_NODE_VISITS: Final = 1
# Path backend (ADR-023): PATH_BUFFER_MARGIN, PATH_CELL_BYTES, PATH_COMMAND_BYTES and
# PATH_BACKEND_FIXED_BYTES come from moana.core.vector_path, shared with the adapter.
# Dithering (ADR-025): fills per dither operation, passes of the periodic selection
# plus the paint pass per fill and the cell table's fixed overhead; the int64 index
# bytes are moana.core.dither.PATTERN_INDEX_BYTES, shared with geometry.
DITHER_FILLS: Final = 2
DITHER_PASSES: Final = 4
DITHER_FIXED_BYTES: Final = 4096
# Outlines (ADR-027): passes over the padded work box of one outline fill.
OUTLINE_PASSES: Final = 16
# Band shading (ADR-028): zeroing, first fold, emptiness scan and paint of one band;
# fixed bytes of one band fill (mask, builder and generator objects) and of folding
# later masks. The fold term is NumPy's iteration buffers of the strided subtraction:
# at most NPY_BUFSIZE = 8192 one-byte elements for each of its three operands (two
# inputs and the output), whatever the box or the number of later masks, since the
# masks are folded one at a time. Measured with tracemalloc: at most 18 793 bytes
# (256 x 256, eight shifted rects), against 3 x 8192 = 24 576.
SHADE_PASSES: Final = 4
SHADE_FIXED_BYTES: Final = 8192
SHADE_FOLD_BYTES: Final = 3 * 8192
# Materials (ADR-030): one hashed cell is weighted as 64 pixel visits (a SHA-256 of a
# short key in Python against a NumPy byte pass); gather, AND and emptiness scan of
# the texture selection; bytes per cell (gate and sign bytes, the bytearray, its bytes
# copy and the comparison) and the measured fixed overhead of hashing and the fill.
MATERIAL_HASH_VISITS: Final = 64
MATERIAL_PASSES: Final = 3
MATERIAL_CELL_BYTES: Final = 5
MATERIAL_FIXED_BYTES: Final = 16384
# Operations between two cooperative deadline checks.
CHECKPOINT_EVERY: Final = 256

Geometry = ShapeOperation | ShapeMask
"""Anything rasterised from primitive geometry: a shape operation or a mask leaf."""
Located = Operation | ShapeMask
"""Anything whose coordinates the plan checks: an operation or a mask leaf."""


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
    """Whole-request estimate; compare it with :class:`RenderLimits` before raster.

    ``operations`` counts the operations of the document; ``fills`` the raster fills
    the compositor receives (:func:`fill_count`: one per operation, two per
    ``dither``; ``budget-v5``, ADR-025). The ``operations`` budget of
    :func:`plan_budget` compares ``fills`` with ``RenderLimits.max_operations``, so
    its ``estimated`` value is ``fills``.
    """

    estimator_version: str
    frames: int
    pixel_visits: int
    buffer_bytes: int
    frame_pixels: int
    operations: int
    fills: int
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
        case PathOperation() | PathMask():
            box = operation.path.bounds
        case _:  # pragma: no cover - a new operation type must add its box
            assert_never(operation)
    return None if box is None else box.clip_to(dimensions)


def _area(box: Box | None) -> int:
    return 0 if box is None else box.area


def _path_cells(path: FixedPath, box: Box | None) -> int:
    return 0 if box is None else path.cell_bound(path_buffer_box(box))


def _mask_bytes(operation: Geometry, box: Box | None) -> int:
    """Peak bytes of rasterising ``operation`` into its clipped mask ``box``."""
    if isinstance(operation, PathOperation | PathMask):
        return path_raster_bytes(operation.path, box)
    return _area(box) * MASK_BYTES_PER_PIXEL


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
        case PathOperation() | PathMask():
            return path_raster_visits(operation.path, box)
        case _:  # pragma: no cover - a new operation type must add its formula
            assert_never(operation)


def dither_cost(mask: MaskEstimate, size: int) -> tuple[int, int]:
    """``(visits, bytes)`` of a ``dither`` of side ``size`` clipped by ``mask``."""
    box = mask.box
    if box is None:
        return DITHER_FILLS * mask.pixel_visits, mask.buffer_bytes
    visits = DITHER_FILLS * (mask.pixel_visits + DITHER_PASSES * box.area)
    indexes = PATTERN_INDEX_BYTES * (box.width + box.height) + size * box.width
    return visits, mask.buffer_bytes + box.area + indexes + DITHER_FIXED_BYTES


def outline_box(mask: Box | None, width: int, side: str, dimensions: Dimensions) -> Box | None:
    """Storage (and work) box of an outline of ``width`` of a mask stored in ``mask``."""
    return grown_box(mask, width if side == "outer" else 0, dimensions)


def outline_cost(
    mask: MaskEstimate, width: int, side: str, dimensions: Dimensions
) -> tuple[int, int]:
    """``(visits, bytes)`` of an ``outline`` of ``width`` on ``side`` of ``mask``."""
    work = outline_box(mask.box, width, side, dimensions)
    if work is None:
        return mask.pixel_visits, mask.buffer_bytes
    side_pixels = 2 * width + 1
    padded = (work.width + side_pixels) * (work.height + side_pixels)
    peak = mask.buffer_bytes + _area(mask.box) + morphology_bytes(work, width) + 2 * work.area
    return mask.pixel_visits + OUTLINE_PASSES * padded, peak


def shade_later(boxes: list[Box | None], index: int) -> tuple[int, ...]:
    """Indexes of the bands after ``index`` whose box meets band ``index``'s box.

    Only those later masks can remove pixels from band ``index``; ``render`` folds
    exactly these, in order, so plan and raster agree. An empty band needs none.
    """
    box = boxes[index]
    if box is None:
        return ()
    return tuple(
        later
        for later in range(index + 1, len(boxes))
        if (other := boxes[later]) is not None and box.intersection(other) is not None
    )


def shade_cost(bands: list[MaskEstimate]) -> tuple[int, int]:
    """``(visits, bytes)`` of a ``shade`` whose band masks have estimates ``bands``."""
    costs = [_band_cost(bands, index) for index in range(len(bands))]
    return sum(visits for visits, _ in costs), max([0, *(peak for _, peak in costs)])


def _band_cost(bands: list[MaskEstimate], index: int) -> tuple[int, int]:
    """``(visits, bytes)`` of the visible part of band ``index`` (``shade`` rule)."""
    box = bands[index].box
    if box is None:
        return 0, 0
    boxes = [band.box for band in bands]
    later = [bands[position] for position in shade_later(boxes, index)]
    area = box.area
    visits = bands[index].pixel_visits + SHADE_PASSES * area
    visits += sum(mask.pixel_visits + area for mask in later)
    evaluation = max([bands[index].buffer_bytes, *(mask.buffer_bytes for mask in later)])
    fold = SHADE_FOLD_BYTES if later else 0
    return visits, area + evaluation + SHADE_FIXED_BYTES + fold


def _recipe(operation: MaterialOperation) -> MaterialPreset:
    row = preset(operation.preset, operation.version)
    if row is None:
        raise ReferenceError(
            "material preset does not exist",
            context={"field": "version", "reason": "unknown_preset_version"},
        )
    return row


def material_cost(
    bands: list[MaskEstimate], recipe: MaterialPreset, scale: int, origin: tuple[int, int]
) -> tuple[int, int]:
    """``(visits, bytes)`` of a ``material`` of ``recipe`` with band estimates ``bands``."""
    visits = peak = 0
    for index, band in enumerate(bands):
        box = band.box
        if box is None:
            continue  # no fill of this band is built
        band_visits, band_peak = _band_cost(bands, index)
        span = cell_span(box, scale, origin)
        cells = span.area
        texture_visits = cells * (recipe.channels * MATERIAL_HASH_VISITS + 2)
        texture_visits += MATERIAL_PASSES * box.area
        texture_bytes = (
            2 * box.area
            + MATERIAL_CELL_BYTES * cells
            + span.height * box.width
            + PATTERN_INDEX_BYTES * (box.width + box.height)
            + MATERIAL_FIXED_BYTES
        )
        visits += len(recipe.parts) * (band_visits + texture_visits)
        peak = max(peak, band_peak, texture_bytes)
    return visits, peak


def selective_outline_cost(
    mask: MaskEstimate,
    width: int,
    side: str,
    segments: list[MaskEstimate],
    dimensions: Dimensions,
) -> tuple[int, int]:
    """``(visits, bytes)`` of a ``selective_outline`` of ``mask`` with ``segments``.

    Base fill over the outline box ``X``: the ring (:func:`outline_cost`), then every
    segment mask whose box meets ``X`` folded out of it. Fill of segment ``i`` over
    the intersection ``D`` of its box ``Bi`` with ``X``: its visible part (a ``shade``
    band), then the ring while that part is held, then their intersection. A fill
    with an empty box is never built.
    """
    work = outline_box(mask.box, width, side, dimensions)
    ring_visits, ring_peak = outline_cost(mask, width, side, dimensions)
    if work is None:
        return ring_visits, ring_peak
    area = work.area
    meeting = [s for s in segments if s.box is not None and s.box.intersection(work)]
    visits = ring_visits + SHADE_PASSES * area
    visits += sum(segment.pixel_visits + area for segment in meeting)
    evaluation = max([0, *(segment.buffer_bytes for segment in meeting)])
    fold = SHADE_FOLD_BYTES if meeting else 0
    peak = max(ring_peak, 2 * area, area + evaluation + fold) + SHADE_FIXED_BYTES
    for index, segment in enumerate(segments):
        box = segment.box
        part = None if box is None else box.intersection(work)
        if box is None or part is None:
            continue
        band_visits, band_peak = _band_cost(segments, index)
        visits += band_visits + ring_visits + 3 * part.area + box.area + area
        held = box.area + area + part.area + SHADE_FOLD_BYTES
        peak = max(peak, band_peak, box.area + ring_peak, held + SHADE_FIXED_BYTES)
    return visits, peak


def _fills(operation: Operation) -> int:
    if isinstance(operation, DitherOperation):
        return DITHER_FILLS
    if isinstance(operation, ShadeOperation):
        return len(operation.bands)
    if isinstance(operation, MaterialOperation):
        return len(operation.bands) * len(_recipe(operation).parts)
    if isinstance(operation, SelectiveOutlineOperation):
        return 1 + len(operation.segments)
    return 1


def fill_count(document: Document) -> int:
    """Raster fills the compositor receives: one per operation, two per ``dither``,
    one per band of a ``shade``, one per band and part of a ``material`` and one plus
    one per segment of a ``selective_outline``."""
    return sum(_fills(operation) for layer in document.layers for operation in layer.operations)


def _operation_cost(
    operation: Operation, dimensions: Dimensions, pointer: str, masks: dict[str, MaskEstimate]
) -> OperationCost:
    if isinstance(operation, DitherOperation):
        if operation.mask_id not in masks:
            raise _unknown_mask()
        visits, peak = dither_cost(masks[operation.mask_id], operation.size)
        return OperationCost(pointer, visits, peak)
    if isinstance(operation, ShadeOperation):
        if any(band.mask_id not in masks for band in operation.bands):
            raise _unknown_mask()
        visits, peak = shade_cost([masks[band.mask_id] for band in operation.bands])
        return OperationCost(pointer, visits, peak)
    if isinstance(operation, OutlineOperation):
        if operation.mask_id not in masks:
            raise _unknown_mask()
        mask = masks[operation.mask_id]
        visits, peak = outline_cost(mask, operation.width, operation.side, dimensions)
        return OperationCost(pointer, visits, peak)
    if isinstance(operation, MaterialOperation):
        if any(band.mask_id not in masks for band in operation.bands):
            raise _unknown_mask()
        bands = [masks[band.mask_id] for band in operation.bands]
        recipe = _recipe(operation)
        visits, peak = material_cost(bands, recipe, operation.scale, operation.origin)
        return OperationCost(pointer, visits, peak)
    if isinstance(operation, SelectiveOutlineOperation):
        names = [operation.mask_id, *(segment.mask_id for segment in operation.segments)]
        if any(name not in masks for name in names):
            raise _unknown_mask()
        segments = [masks[segment.mask_id] for segment in operation.segments]
        visits, peak = selective_outline_cost(
            masks[operation.mask_id], operation.width, operation.side, segments, dimensions
        )
        return OperationCost(pointer, visits, peak)
    box = mask_box(operation, dimensions)
    area = _area(box)
    return OperationCost(pointer, _raster_work(operation, box) + area, _mask_bytes(operation, box))


def _leaf_estimate(mask: ShapeMask, dimensions: Dimensions) -> MaskEstimate:
    box = mask_box(mask, dimensions)
    work = 0 if box is None else _raster_work(mask, box)  # an empty leaf is not built
    return MaskEstimate(box, MASK_NODE_VISITS + work, _mask_bytes(mask, box))


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
            cost = _operation_cost(operation, dimensions, pointer, masks)
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
        fills=fill_count(document),
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


def _located_geometry(document: Document) -> list[tuple[str, Located]]:
    """Every operation and mask leaf with its pointer, in document order."""
    located: list[tuple[str, Located]] = [
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
        if isinstance(operation, PathOperation | PathMask):
            path = operation.path
            cells = _path_cells(path, mask_box(operation, canvas.dimensions))
            if cells > MAX_PATH_CELLS:
                details.append(_exceeded("path_cells", MAX_PATH_CELLS, cells, pointer))
    return details


def _coordinate_reach(operation: Located) -> int:
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
        case PathOperation() | PathMask():
            return operation.path.reach
        case DitherOperation() | MaterialOperation():
            values = operation.origin
        case OutlineOperation() | ShadeOperation() | SelectiveOutlineOperation():
            return 0  # no coordinates: its pixels derive from checked masks
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
    fills = fill_count(document)  # what the compositor counts (ADR-025)
    counts = (
        ("layers", limits.max_layers, layers, "/layers"),
        ("operations", limits.max_operations, fills, "/layers"),
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
