"""Explicit registry of the schema 1.0 vocabulary (MOANA.md section 12, ADR-011).

``SUPPORTED`` names are part of the 1.0 grammar and validate fully. ``PLANNED`` names
are recognised from the specification but have no grammar yet: a document that uses
one is rejected with ``UNSUPPORTED_OPERATION`` instead of a generic validation error,
and is never silently ignored. Adding a capability means adding its model, its
resolution, cost and raster, tests and documentation in its own issue, then moving the
name from ``PLANNED`` to ``SUPPORTED``; nothing is imported dynamically from JSON.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "PLANNED_BLEND_MODES",
    "PLANNED_COLLECTIONS",
    "PLANNED_LAYER_FIELDS",
    "PLANNED_MASK_TYPES",
    "PLANNED_OPERATION_TYPES",
    "SCHEMA_VERSION",
    "SUPPORTED_BLEND_MODES",
    "SUPPORTED_COLLECTIONS",
    "SUPPORTED_MASK_OPERATORS",
    "SUPPORTED_MASK_SHAPES",
    "SUPPORTED_MASK_TYPES",
    "SUPPORTED_OPERATION_TYPES",
    "SUPPORTED_OVERRIDE_TYPES",
    "SUPPORTED_PATH_BACKENDS",
    "SUPPORTED_PROFILES",
    "SUPPORTED_SCHEMA_VERSIONS",
]

SCHEMA_VERSION: Final = "1.0"
SUPPORTED_SCHEMA_VERSIONS: Final = frozenset({SCHEMA_VERSION})

# ``dither`` (ordered Bayer dithering clipped by a mask) arrived with MOANA-016, ADR-025;
# ``outline`` (outer/inner outline of a mask) with MOANA-014, ADR-027; ``shade`` (band
# shading by ramp index with a discrete light) with MOANA-015, ADR-028; ``material``
# (band shading plus a versioned preset texture) and ``selective_outline`` (outline
# whose authored segments take ramp steps from the light) with MOANA-017, ADR-030.
SUPPORTED_OPERATION_TYPES: Final = frozenset(
    {
        "dither",
        "ellipse",
        "line",
        "material",
        "outline",
        "path",
        "pixel",
        "polygon",
        "rect",
        "selective_outline",
        "shade",
    }
)
PLANNED_OPERATION_TYPES: Final = frozenset({"flood_fill"})
# Raster backends a ``path`` may name (ADR-023). The schema accepts the label; whether
# this environment can render it is a runtime capability (``moana.geometry.paths``).
SUPPORTED_PATH_BACKENDS: Final = frozenset({"aggdraw-v1"})

SUPPORTED_BLEND_MODES: Final = frozenset({"normal"})
PLANNED_BLEND_MODES: Final = frozenset({"multiply", "screen"})

SUPPORTED_PROFILES: Final = frozenset({"rgba", "strict"})

# Semantic masks and regions (ADR-022): leaves reuse the primitive geometry in canvas
# coordinates; combinations fold mask IDs. Path leaves arrived with paths (MOANA-007,
# ADR-023): no mask type is planned any more.
SUPPORTED_MASK_SHAPES: Final = frozenset({"ellipse", "line", "path", "pixel", "polygon", "rect"})
SUPPORTED_MASK_OPERATORS: Final = frozenset({"intersect", "subtract", "union", "xor"})
SUPPORTED_MASK_TYPES: Final = SUPPORTED_MASK_SHAPES | SUPPORTED_MASK_OPERATORS
PLANNED_MASK_TYPES: Final[frozenset[str]] = frozenset()

# Optional root collections with a 1.0 grammar; ``animations`` arrived with timelines
# (MOANA-022, ADR-032).
SUPPORTED_COLLECTIONS: Final = frozenset({"animations", "masks", "regions"})
# Root collections reserved for future capabilities: accepted only when empty.
PLANNED_COLLECTIONS: Final = frozenset({"materials"})
# Frame overrides of an animation (ADR-032): visibility, geometry and colour, with the
# shape of the edit commands of the same name.
SUPPORTED_OVERRIDE_TYPES: Final = frozenset({"set_color", "set_visibility", "translate"})
# Layer members of planned features: groups (children, transform).
PLANNED_LAYER_FIELDS: Final = frozenset({"children", "transform"})
