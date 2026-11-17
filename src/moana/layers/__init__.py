"""Ordered layer tree and integer source-over composition (MOANA.md section 11, ADR-017).

``layers`` depends on ``core``, ``palette`` and ``geometry`` (MOANA.md section 3).
Layers hold fills (a geometry mask painted with a palette colour); groups composite
their children in an isolated buffer and apply their opacity once. Only the
``normal`` blend mode exists; semantic masks, regions and group transforms come with
later issues. A :class:`DeferredMask` lets ``render`` rasterise one operation at a
time during composition (ADR-018).
"""

from moana.layers.composite import (
    COMPOSITE_TEMP_BYTES_PER_PIXEL,
    MAX_TILE_PIXELS,
    TILE_ROWS,
    CompositionCost,
    compose,
    composition_cost,
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
    Node,
)

__all__ = [
    "BLEND_MODES",
    "COMPOSITE_TEMP_BYTES_PER_PIXEL",
    "MAX_NAME_BYTES",
    "MAX_TILE_PIXELS",
    "TILE_ROWS",
    "CompositionCost",
    "DeferredMask",
    "Fill",
    "Group",
    "Layer",
    "LayerTree",
    "Node",
    "compose",
    "composition_cost",
    "tile_pixels",
]
