"""Integer source-over composition of a layer tree (MOANART.md section 11, ADR-017).

One kernel implements the normative formula on straight RGBA ``uint8``::

    sa = round_half_up(alpha * opacity / 255)
    D  = sa * 255 + da * (255 - sa)
    a  = round_half_up(D / 255)
    c  = round_half_up((sc * sa * 255 + dc * da * (255 - sa)) / D)   if D > 0, else 0

with ``round_half_up(n / d) = (2n + d) // (2d)``; a result with alpha 0 (exactly
when ``D == 0``) is normalised to ``(0, 0, 0, 0)``. Every intermediate fits ``uint32``
(``2n + D < 2^27``). The kernel runs over tiles of at most :func:`tile_pixels`
pixels, so its temporaries stay within a quarter of the canvas and 4096 pixels.

A layer paints its fills in order onto a transparent layer buffer (source-over at
opacity 255, only over each mask's box), then the layer buffer is composited onto its
parent with the layer opacity. A group composites its children into an isolated
transparent buffer and applies its opacity once, to that buffer. Hidden nodes and
their subtrees cost no work; ``locked`` never changes the result.

A layer with a semantic ``mask`` (ADR-022) evaluates it after painting its fills and
clears the layer buffer outside it before compositing. Clearing a pixel makes its
source alpha 0, so ``sa = 0`` and the parent pixel outside the mask stays exactly as
it was; the layer opacity is still applied once. Mask nodes are evaluated depth
first, operand by operand, into one :class:`~moanart.geometry.MaskBuilder` per node.
There is no memo: a shared node is evaluated again wherever it is referenced, and
the cost counts it so, at least :data:`MASK_NODE_VISITS` per evaluated node. A node
whose result box is empty is the empty mask without evaluating its operands, so its
cost is that floor alone.

``compose`` may reuse finished layer buffers through a :class:`LayerBuffers` store
(MOANA-032, ADR-038): a layer whose ID the store knows is composited from those
immutable bytes instead of painting its fills and clearing outside its mask; any
other visible layer is painted as usual and offered to the store before it is
composited. A layer buffer starts transparent and never reads its parent, so reusing
the same bytes gives the same pixels. The budget is checked for the whole tree
before anything, with or without a store.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final, Protocol

import numpy as np
import numpy.typing as npt

from moanart.core.budget import Deadline, RenderLimits
from moanart.core.canvas import Canvas
from moanart.core.coordinates import Box, Dimensions
from moanart.core.errors import BudgetExceeded, ErrorDetail
from moanart.geometry import Mask, MaskBuilder, combined_box
from moanart.layers.nodes import (
    DeferredMask,
    Fill,
    Group,
    Layer,
    LayerTree,
    MaskCombination,
    MaskNode,
    MaskShape,
    Node,
)

__all__ = [
    "COMPOSITE_TEMP_BYTES_PER_PIXEL",
    "MASK_NODE_VISITS",
    "MAX_TILE_PIXELS",
    "TILE_ROWS",
    "CompositionCost",
    "LayerBuffers",
    "MaskCost",
    "compose",
    "composition_cost",
    "evaluate_mask",
    "mask_cost",
    "tile_pixels",
]

RGBA_BYTES: Final = 4
TILE_ROWS: Final = 64
"""Maximum rows of one kernel tile."""
MAX_TILE_PIXELS: Final = 4096
"""Maximum pixels of one kernel tile."""
COMPOSITE_TEMP_BYTES_PER_PIXEL: Final = 80
"""Upper bound of kernel temporaries per tile pixel (``uint32`` planes, measured ~66)."""
MASK_NODE_VISITS: Final = 1
"""Cost floor of evaluating one mask node reference, even an empty one (ADR-022)."""

Pixels = npt.NDArray[np.uint8]
_Plane = npt.NDArray[np.uint32]


def tile_pixels(dimensions: Dimensions) -> int:
    """Pixels per kernel tile: ``min(4096, A // 4)``, at least one."""
    return max(1, min(MAX_TILE_PIXELS, dimensions.area // 4))


@dataclass(frozen=True, slots=True)
class CompositionCost:
    """Work and memory of :func:`compose`, computed before any buffer exists.

    ``layers`` counts every layer and group and ``operations`` every fill, visible or
    not, as the document budget counts document layers and operations; ``pixel_visits`` and
    ``buffer_bytes`` only count visible nodes.
    """

    pixel_visits: int
    buffer_bytes: int
    layers: int
    operations: int
    group_depth: int


@dataclass(frozen=True, slots=True)
class MaskCost:
    """Result box, work and peak bytes of evaluating one mask node (ADR-022).

    ``box`` is the storage box of the result (:func:`~moanart.geometry.combined_box`
    of the operand boxes). ``pixel_visits`` counts every evaluated node of the
    expanded expression (a shared node once per reference): :data:`MASK_NODE_VISITS`
    for the node itself and, for a combination with a non-empty box, the zeroing and
    final scan of its buffer (``2 x`` its box area) plus each operand's cost and one
    fold over its box. A combination with an empty box evaluates no operand. Leaves
    count only the floor, since their raster work is budgeted by the caller, like
    fills. ``buffer_bytes`` is the peak of mask storage alive while evaluating: a
    leaf's box area, or a combination's own buffer plus its most expensive operand
    (``0`` for an empty combination).
    """

    box: Box | None
    pixel_visits: int
    buffer_bytes: int


def _area(box: Box | None) -> int:
    return 0 if box is None else box.area


def _mask_costs(root: MaskNode, dimensions: Dimensions) -> dict[int, MaskCost]:
    """Cost of every node of a mask DAG, children first, keyed by node identity.

    Identities only memoise arithmetic on shared nodes; no order is taken from them.
    """
    costs: dict[int, MaskCost] = {}
    stack: list[tuple[MaskNode, bool]] = [(root, False)]
    while stack:
        node, ready = stack.pop()
        if id(node) in costs:
            continue
        if isinstance(node, MaskShape):
            costs[id(node)] = MaskCost(node.box, MASK_NODE_VISITS, _area(node.box))
        elif ready:
            operands = [costs[id(operand)] for operand in node.operands]
            box = combined_box(node.operator, [cost.box for cost in operands], dimensions)
            costs[id(node)] = _combination_cost(box, operands)
        else:
            stack.append((node, True))
            stack.extend((operand, False) for operand in reversed(node.operands))
    return costs


def _combination_cost(box: Box | None, operands: list[MaskCost]) -> MaskCost:
    """Cost of a combination from its result box and operand costs (see MaskCost)."""
    if box is None:
        return MaskCost(None, MASK_NODE_VISITS, 0)  # empty: no operand is evaluated
    area = box.area
    visits = 2 * area + sum(cost.pixel_visits + _area(cost.box) for cost in operands)
    peak = area + max(cost.buffer_bytes for cost in operands)
    return MaskCost(box, MASK_NODE_VISITS + visits, peak)


def mask_cost(root: MaskNode, dimensions: Dimensions) -> MaskCost:
    """Cost of evaluating ``root`` on a canvas of ``dimensions`` (pure arithmetic)."""
    if not isinstance(root, MaskShape | MaskCombination):
        raise TypeError("root must be a MaskShape or MaskCombination value")
    if not isinstance(dimensions, Dimensions):
        raise TypeError("dimensions must be a Dimensions value")
    return _mask_costs(root, dimensions)[id(root)]


@dataclass(frozen=True, slots=True)
class _Visible:
    """Cost terms of the visible nodes of one level (and their descendants)."""

    visits: int
    depth: int
    deferred: bool
    mask_bytes: int


def _visible_cost(nodes: tuple[Node, ...], dimensions: Dimensions) -> _Visible:
    """Visits, deepest visible group nesting (<= 16), whether a deferred fill mask is
    built and the largest semantic-mask working set of a visible layer."""
    area = dimensions.area
    visits = depth = mask_bytes = 0
    deferred = False
    for node in nodes:
        if not node.visible:
            continue
        visits += 2 * area  # clear the node buffer, composite it onto its parent
        if isinstance(node, Group):
            inner = _visible_cost(node.children, dimensions)
            visits += inner.visits
            depth = max(depth, inner.depth + 1)
            deferred = deferred or inner.deferred
            mask_bytes = max(mask_bytes, inner.mask_bytes)
            continue
        for fill in node.fills:
            box = fill.box
            visits += 0 if box is None else box.area
            deferred = deferred or (box is not None and isinstance(fill.mask, DeferredMask))
        if node.mask is not None:
            cost = mask_cost(node.mask, dimensions)
            # evaluate, copy the result's bits, then clear the layer outside the mask
            visits += cost.pixel_visits + _area(cost.box) + area
            mask_bytes = max(mask_bytes, cost.buffer_bytes + _area(cost.box))
    return _Visible(visits, depth, deferred, mask_bytes)


def composition_cost(tree: LayerTree) -> CompositionCost:
    """Upper bound of visits and bytes of composing ``tree`` (pure arithmetic).

    Visits: ``3A`` for the root (clear, alpha normalisation and copy into the
    result), ``2A`` per visible layer or group, plus each fill's mask box and, for a
    visible layer with a semantic mask, its :func:`mask_cost` visits, its result box
    (copying the bits) and ``A`` (clearing outside the mask). Bytes: the root, one
    isolated buffer per open group, one layer buffer and the result copy
    (``(3 + depth) * 4A``); the larger of the fill-mask term (the largest mask copy,
    ``A``, plus the built mask itself, ``A``, when a visible fill has a
    :class:`DeferredMask`) and the largest semantic-mask working set (evaluation peak
    plus one copy of the result); and one kernel tile of temporaries. The work of
    ``DeferredMask.build`` is budgeted by its caller.
    """
    if not isinstance(tree, LayerTree):
        raise TypeError("tree must be a LayerTree value")
    dimensions = tree.dimensions
    area = dimensions.area
    visible = _visible_cost(tree.children, dimensions)
    masks = max((2 if visible.deferred else 1) * area, visible.mask_bytes)
    layers = operations = 0
    for node, _ in tree.walk():
        layers += 1
        if isinstance(node, Layer):
            operations += len(node.fills)
    temporaries = COMPOSITE_TEMP_BYTES_PER_PIXEL * tile_pixels(dimensions)
    return CompositionCost(
        pixel_visits=3 * area + visible.visits,
        buffer_bytes=(3 + visible.depth) * RGBA_BYTES * area + masks + temporaries,
        layers=layers,
        operations=operations,
        group_depth=visible.depth,
    )


def _check_budget(tree: LayerTree, cost: CompositionCost, limits: RenderLimits) -> None:
    dimensions, geometry = tree.dimensions, limits.geometry
    checks = [
        ("canvas_dimension", geometry.max_dimension, value)
        for value in (dimensions.width, dimensions.height)
    ]
    checks += [
        ("canvas_area", geometry.max_area, dimensions.area),
        ("frame_pixels", limits.max_frame_pixels, dimensions.area),
        ("layers", limits.max_layers, cost.layers),
        ("operations", limits.max_operations, cost.operations),
        ("pixel_visits", limits.max_pixel_visits, cost.pixel_visits),
        ("buffer_bytes", limits.max_buffer_bytes, cost.buffer_bytes),
    ]
    details = [
        ErrorDetail(
            BudgetExceeded.code,
            f"composition {resource} exceed the request budget",
            context={"resource": resource, "limit": limit, "estimated": estimated},
        )
        for resource, limit, estimated in checks
        if estimated > limit
    ]
    if details:
        raise BudgetExceeded(
            "composition exceeds the request budget",
            context=dict(details[0].context),
            details=details,
        )


def _tiles(box: Box, pixels: int) -> Iterator[tuple[slice, slice]]:
    """Row and column slices (relative to ``box``) of tiles of at most ``pixels``."""
    rows = max(1, min(TILE_ROWS, box.height, pixels))
    columns = max(1, pixels // rows)
    for top in range(0, box.height, rows):
        for left in range(0, box.width, columns):
            yield slice(top, top + rows), slice(left, left + columns)


def _over(dst: Pixels, src_rgb: tuple[_Plane, ...], src_a: _Plane, opacity: int) -> None:
    """Source-over of ``src`` (straight RGBA planes) onto ``dst`` in place."""
    sa = (src_a * np.uint32(2 * opacity) + np.uint32(255)) // np.uint32(510)
    dst_weight = dst[:, :, 3] * (np.uint32(255) - sa)
    src_weight = sa * np.uint32(255)
    total = src_weight + dst_weight
    alpha = (np.uint32(2) * total + np.uint32(255)) // np.uint32(510)
    visible = alpha > 0  # alpha is 0 exactly when D == 0; RGB is then normalised
    denominator = np.uint32(2) * np.maximum(total, np.uint32(1))
    for channel in range(3):
        weighted = src_rgb[channel] * src_weight + dst[:, :, channel] * dst_weight
        weighted = (np.uint32(2) * weighted + total) // denominator
        dst[:, :, channel] = np.where(visible, weighted, np.uint32(0))
    dst[:, :, 3] = alpha


def _resolve(source: Mask | DeferredMask) -> Mask:
    """A mask; a deferred one is built now and checked against its declared box."""
    if not isinstance(source, DeferredMask):
        return source
    declared = source.box
    mask = source.build()
    if not isinstance(mask, Mask):
        raise TypeError("DeferredMask.build must return a Mask value")
    box = mask.box
    if box is not None and (declared is None or box.intersection(declared) != box):
        # A caller bug (its declared box is wrong), not invalid user input.
        raise RuntimeError("deferred mask lies outside its declared box")
    return mask


def _paint(layer_buffer: Pixels, fill: Fill, pixels: int) -> None:
    """Source-over of one fill (opacity 255) restricted to its mask box."""
    if fill.box is None:
        return  # nothing to draw: a deferred mask is not even built
    mask = _resolve(fill.mask)
    box = mask.box
    if box is None:
        return
    bits = mask.to_array()
    del mask  # a deferred mask lives only while its bits are copied
    color = fill.color
    rgb = tuple(np.uint32(value) for value in (color.r, color.g, color.b))
    for rows, columns in _tiles(box, pixels):
        src_a = bits[rows, columns].astype(np.uint32) * np.uint32(color.a)
        target = layer_buffer[box.y0 : box.y1, box.x0 : box.x1][rows, columns]
        planes = tuple(np.full(src_a.shape, value, dtype=np.uint32) for value in rgb)
        _over(target, planes, src_a, 255)


def _composite(parent: Pixels, child: Pixels, opacity: int, pixels: int) -> None:
    """Source-over of a whole child buffer onto ``parent`` with ``opacity``."""
    height, width = parent.shape[:2]
    for rows, columns in _tiles(Box(0, 0, width, height), pixels):
        source = child[rows, columns]
        planes = tuple(source[:, :, channel].astype(np.uint32) for channel in range(3))
        _over(parent[rows, columns], planes, source[:, :, 3].astype(np.uint32), opacity)


def _evaluate(node: MaskNode, costs: dict[int, MaskCost], deadline: Deadline | None) -> Mask:
    """Mask of ``node``: operands folded in order, one alive at a time (depth <= 16)."""
    if deadline is not None:
        deadline.checkpoint("compose_mask")
    box = costs[id(node)].box
    if box is None:
        return Mask.empty()  # nothing to build: operands (or a deferred leaf) skipped
    if isinstance(node, MaskShape):
        return _resolve(node.mask)
    builder = MaskBuilder(node.operator, box)
    for operand in node.operands:
        builder.add(_evaluate(operand, costs, deadline))
    return builder.finish()


def evaluate_mask(
    root: MaskNode, dimensions: Dimensions, *, deadline: Deadline | None = None
) -> Mask:
    """The mask of ``root``, evaluated exactly as for a layer mask (ADR-022).

    Same order, work and peak as :func:`mask_cost` describes; ``deadline`` is checked
    before each node. ``render`` uses it to clip a ``dither`` operation (ADR-025).
    """
    if not isinstance(root, MaskShape | MaskCombination):
        raise TypeError("root must be a MaskShape or MaskCombination value")
    if not isinstance(dimensions, Dimensions):
        raise TypeError("dimensions must be a Dimensions value")
    return _evaluate(root, _mask_costs(root, dimensions), deadline)


def _clear_outside(buffer: Pixels, mask: Mask) -> None:
    """Zero every pixel of ``buffer`` outside ``mask``, whose box is not ``None``.

    Work: the result box (copying the bits) plus at most the whole buffer.
    """
    box = mask.box
    assert box is not None
    bits = mask.to_array()
    buffer[: box.y0] = 0
    buffer[box.y1 :] = 0
    buffer[box.y0 : box.y1, : box.x0] = 0
    buffer[box.y0 : box.y1, box.x1 :] = 0
    window = buffer[box.y0 : box.y1, box.x0 : box.x1]
    np.multiply(window, bits[:, :, np.newaxis], out=window)


def _layer_mask(layer: Layer, dimensions: Dimensions, deadline: Deadline | None) -> Mask | None:
    """The evaluated semantic mask of ``layer``, or ``None`` when it has none."""
    if layer.mask is None:
        return None
    return _evaluate(layer.mask, _mask_costs(layer.mask, dimensions), deadline)


class LayerBuffers(Protocol):
    """Finished layer buffers reused between compositions (MOANA-032, ADR-038).

    ``lookup`` returns the row-major RGBA bytes (``4·width·height``) of a layer
    painted and clipped exactly as :func:`compose` would, or ``None``. ``store``
    receives a read-only view of a freshly painted layer buffer, valid only during
    the call: a store that keeps it must copy it. Neither sees the layer opacity,
    which is applied when the buffer is composited.
    """

    def lookup(self, layer_id: str) -> bytes | None:
        """Bytes of the finished buffer of ``layer_id``, or ``None``."""
        ...  # pragma: no cover - protocol

    def store(self, layer_id: str, pixels: memoryview) -> None:
        """Offer the finished buffer of ``layer_id`` (copy it to keep it)."""
        ...  # pragma: no cover - protocol


def _reused(buffers: LayerBuffers | None, node: Layer, shape: tuple[int, ...]) -> Pixels | None:
    """A read-only view of the stored buffer of ``node``, or ``None``."""
    if buffers is None:
        return None
    stored = buffers.lookup(node.id)
    if stored is None:
        return None
    if type(stored) is not bytes:
        raise RuntimeError("a layer buffer store returned a value that is not bytes")
    if len(stored) != shape[0] * shape[1] * shape[2]:
        raise RuntimeError("a layer buffer store returned bytes of another size")
    return np.frombuffer(stored, dtype=np.uint8).reshape(shape)  # read-only: bytes


def _compose_into(
    target: Pixels,
    nodes: tuple[Node, ...],
    dimensions: Dimensions,
    deadline: Deadline | None,
    buffers: LayerBuffers | None = None,
) -> None:
    """Composite ``nodes`` bottom to top onto ``target`` (group depth <= 16)."""
    pixels = tile_pixels(dimensions)
    for node in nodes:
        if not node.visible:
            continue
        if deadline is not None:
            deadline.checkpoint("compose_node")
        if isinstance(node, Layer):
            reused = _reused(buffers, node, target.shape)
            if reused is not None:
                _composite(target, reused, node.opacity, pixels)
                continue
        buffer = np.zeros(target.shape, dtype=np.uint8)
        if isinstance(node, Group):
            _compose_into(buffer, node.children, dimensions, deadline, buffers)
        else:
            for fill in node.fills:
                if deadline is not None:
                    deadline.checkpoint("compose_fill")
                _paint(buffer, fill, pixels)
            mask = _layer_mask(node, dimensions, deadline)
            if mask is not None:
                if mask.box is None:
                    continue  # an empty mask hides the whole layer: nothing to composite
                _clear_outside(buffer, mask)
                del mask
            if buffers is not None:
                buffers.store(node.id, memoryview(buffer).toreadonly())
        _composite(target, buffer, node.opacity, pixels)
        del buffer


def compose(
    tree: LayerTree,
    *,
    limits: RenderLimits,
    deadline: Deadline | None = None,
    buffers: LayerBuffers | None = None,
) -> Canvas:
    """Composite ``tree`` onto a transparent canvas; budget checked before allocating.

    Raises :class:`BudgetExceeded` (resources ``canvas_dimension``, ``canvas_area``,
    ``frame_pixels``, ``layers``, ``operations``, ``pixel_visits``, ``buffer_bytes``)
    from :func:`composition_cost` before any buffer exists. ``deadline`` is checked
    before each visible node, each fill and each semantic mask node; deferred masks
    are built one at a time, after that check. ``buffers`` (optional) reuses and
    receives finished layer buffers (:class:`LayerBuffers`); a reused layer builds no
    fill and no mask, and gives the same pixels.
    """
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    cost = composition_cost(tree)
    _check_budget(tree, cost, limits)
    dimensions = tree.dimensions
    root = np.zeros((dimensions.height, dimensions.width, RGBA_BYTES), dtype=np.uint8)
    _compose_into(root, tree.children, dimensions, deadline, buffers)
    return Canvas.from_array(root, limits=limits)
