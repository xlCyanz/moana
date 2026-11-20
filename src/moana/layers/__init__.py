"""Ordered layer tree and integer source-over composition (MOANA.md section 11, ADR-017).

``layers`` depends on ``core``, ``palette`` and ``geometry`` (MOANA.md section 3).
Layers hold fills (a geometry mask painted with a palette colour); groups composite
their children in an isolated buffer and apply their opacity once. Only the
``normal`` blend mode exists; group transforms come with a later issue. A
:class:`DeferredMask` lets ``render`` rasterise one operation at a time during
composition (ADR-018). A layer may carry a semantic mask, a DAG of
:class:`MaskShape` leaves and :class:`MaskCombination` nodes in canvas coordinates
that clips the layer before it is composited (ADR-022). :func:`compose` can reuse
finished layer buffers through a :class:`LayerBuffers` store (ADR-038).
"""

from moana.layers.composite import (
    COMPOSITE_TEMP_BYTES_PER_PIXEL,
    MASK_NODE_VISITS,
    MAX_TILE_PIXELS,
    TILE_ROWS,
    CompositionCost,
    LayerBuffers,
    MaskCost,
    compose,
    composition_cost,
    evaluate_mask,
    mask_cost,
    tile_pixels,
)
from moana.layers.nodes import (
    BLEND_MODES,
    MAX_NAME_BYTES,
    DeferredMask,
    Fill,
    Group,
    Layer,
    LayerTree,
    MaskCombination,
    MaskNode,
    MaskShape,
    Node,
    mask_leaves,
)

__all__ = [
    "BLEND_MODES",
    "COMPOSITE_TEMP_BYTES_PER_PIXEL",
    "MASK_NODE_VISITS",
    "MAX_NAME_BYTES",
    "MAX_TILE_PIXELS",
    "TILE_ROWS",
    "CompositionCost",
    "DeferredMask",
    "Fill",
    "Group",
    "Layer",
    "LayerBuffers",
    "LayerTree",
    "MaskCombination",
    "MaskCost",
    "MaskNode",
    "MaskShape",
    "Node",
    "compose",
    "composition_cost",
    "evaluate_mask",
    "mask_cost",
    "mask_leaves",
    "tile_pixels",
]
