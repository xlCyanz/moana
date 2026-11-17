"""Integer source-over composition of a layer tree (MOANA.md section 11, ADR-017).

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
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from moana.core.budget import Deadline, RenderLimits
from moana.core.canvas import Canvas
from moana.core.coordinates import Box, Dimensions
from moana.core.errors import BudgetExceeded, ErrorDetail
from moana.geometry import Mask
from moana.layers.nodes import DeferredMask, Fill, Group, Layer, LayerTree, Node

__all__ = [
    "COMPOSITE_TEMP_BYTES_PER_PIXEL",
    "MAX_TILE_PIXELS",
    "TILE_ROWS",
    "CompositionCost",
    "compose",
    "composition_cost",
    "tile_pixels",
]

RGBA_BYTES: Final = 4
TILE_ROWS: Final = 64
"""Maximum rows of one kernel tile."""
MAX_TILE_PIXELS: Final = 4096
"""Maximum pixels of one kernel tile."""
COMPOSITE_TEMP_BYTES_PER_PIXEL: Final = 80
"""Upper bound of kernel temporaries per tile pixel (``uint32`` planes, measured ~66)."""

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


def _visible_cost(nodes: tuple[Node, ...], area: int) -> tuple[int, int, bool]:
    """Visits, deepest visible group nesting (<= 16) and whether a deferred mask is built."""
    visits = depth = 0
    deferred = False
    for node in nodes:
        if not node.visible:
            continue
        visits += 2 * area  # clear the node buffer, composite it onto its parent
        if isinstance(node, Group):
            inner_visits, inner_depth, inner_deferred = _visible_cost(node.children, area)
            visits += inner_visits
            depth = max(depth, inner_depth + 1)
            deferred = deferred or inner_deferred
            continue
        for fill in node.fills:
            box = fill.box
            visits += 0 if box is None else box.area
            deferred = deferred or (box is not None and isinstance(fill.mask, DeferredMask))
    return visits, depth, deferred


def composition_cost(tree: LayerTree) -> CompositionCost:
    """Upper bound of visits and bytes of composing ``tree`` (pure arithmetic).

    Visits: ``3A`` for the root (clear, alpha normalisation and copy into the
    result), ``2A`` per visible layer or group, plus each fill's mask box. Bytes: the
    root, one isolated buffer per open group, one layer buffer and the result copy
    (``(3 + depth) * 4A``), the largest mask copy (``A``), the built mask itself
    (``A``) when a visible fill has a :class:`DeferredMask`, and one kernel tile of
    temporaries. The work of ``DeferredMask.build`` is budgeted by its caller.
    """
    if not isinstance(tree, LayerTree):
        raise TypeError("tree must be a LayerTree value")
    area = tree.dimensions.area
    visits, depth, deferred = _visible_cost(tree.children, area)
    masks = (2 if deferred else 1) * area
    layers = operations = 0
    for node, _ in tree.walk():
        layers += 1
        if isinstance(node, Layer):
            operations += len(node.fills)
    temporaries = COMPOSITE_TEMP_BYTES_PER_PIXEL * tile_pixels(tree.dimensions)
    return CompositionCost(
        pixel_visits=3 * area + visits,
        buffer_bytes=(3 + depth) * RGBA_BYTES * area + masks + temporaries,
        layers=layers,
        operations=operations,
        group_depth=depth,
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


def _resolve(fill: Fill) -> Mask:
    """The fill's mask; a deferred one is built now and checked against its box."""
    if not isinstance(fill.mask, DeferredMask):
        return fill.mask
    declared = fill.mask.box
    mask = fill.mask.build()
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
    mask = _resolve(fill)
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


def _compose_into(
    target: Pixels, nodes: tuple[Node, ...], pixels: int, deadline: Deadline | None
) -> None:
    """Composite ``nodes`` bottom to top onto ``target`` (group depth <= 16)."""
    for node in nodes:
        if not node.visible:
            continue
        if deadline is not None:
            deadline.checkpoint("compose_node")
        buffer = np.zeros(target.shape, dtype=np.uint8)
        if isinstance(node, Group):
            _compose_into(buffer, node.children, pixels, deadline)
        else:
            for fill in node.fills:
                if deadline is not None:
                    deadline.checkpoint("compose_fill")
                _paint(buffer, fill, pixels)
        _composite(target, buffer, node.opacity, pixels)
        del buffer


def compose(tree: LayerTree, *, limits: RenderLimits, deadline: Deadline | None = None) -> Canvas:
    """Composite ``tree`` onto a transparent canvas; budget checked before allocating.

    Raises :class:`BudgetExceeded` (resources ``canvas_dimension``, ``canvas_area``,
    ``frame_pixels``, ``layers``, ``operations``, ``pixel_visits``, ``buffer_bytes``)
    from :func:`composition_cost` before any buffer exists. ``deadline`` is checked
    before each visible node and each fill; deferred masks are built one at a time,
    after that check.
    """
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    cost = composition_cost(tree)
    _check_budget(tree, cost, limits)
    dimensions = tree.dimensions
    root = np.zeros((dimensions.height, dimensions.width, RGBA_BYTES), dtype=np.uint8)
    _compose_into(root, tree.children, tile_pixels(dimensions), deadline)
    return Canvas.from_array(root, limits=limits)
