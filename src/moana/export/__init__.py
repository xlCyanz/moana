"""Exports at the edge of the engine (MOANA.md sections 3 and 18, ADR-019).

``export`` depends on ``core`` and ``palette`` only: it receives rendered frames
(any value with ``width``, ``height`` and RGBA ``bytes``, such as
``moana.render.RenderResult``) and never calls the renderer or the editor. Implemented:
master RGBA and indexed PNG with integer nearest-neighbour scale, in-memory
round-trip verification and atomic writes that do not overwrite by default. GIF,
WebP, APNG and atlases come with later issues.
"""

from moana.export.png import (
    EXPORT_BYTES_PER_PIXEL,
    MAX_INDEXED_COLORS,
    MAX_SCALE,
    MEDIA_TYPE,
    EncodedPng,
    ExportManifest,
    ExportMode,
    RasterFrame,
    encode_png,
    export_png,
)

__all__ = [
    "EXPORT_BYTES_PER_PIXEL",
    "MAX_INDEXED_COLORS",
    "MAX_SCALE",
    "MEDIA_TYPE",
    "EncodedPng",
    "ExportManifest",
    "ExportMode",
    "RasterFrame",
    "encode_png",
    "export_png",
]
