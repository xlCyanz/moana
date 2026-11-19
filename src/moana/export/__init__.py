"""Exports at the edge of the engine (MOANA.md sections 3 and 18, ADR-019).

``export`` depends on ``core`` and ``palette`` only: it receives rendered frames
(any value with ``width``, ``height`` and RGBA ``bytes``, such as
``moana.render.RenderResult``) and never calls the renderer or the editor. Implemented:
master RGBA and indexed PNG with integer nearest-neighbour scale, in-memory
round-trip verification and atomic writes that do not overwrite by default; grid
spritesheets (uniform grid, margin and padding, no trim or rotation) with a versioned
JSON manifest whose rects ``[x, y, w, h]``, durations, pivots and digests rebuild every
frame exactly (MOANA-023, ADR-033). Spritesheet frames are any ``SpriteFrame``
(``frame_id``, ``duration_ms``, ``pivot``, ``result``) such as
``moana.animation.FrameRender``, which ``export`` never imports. Animated GIF
(MOANA-024, ADR-034): one shared palette of at most 256 entries (exact colours, never
quantised; a reserved transparent index), binary alpha with an explicit flatten
``background``, durations in multiples of 10 ms or an explicit rounding policy, full
frames with a configured disposal, and a decoded-timeline verification; every accepted
loss is reported. WebP, APNG and compact packing come with later issues.
"""

from moana.export.gif import (
    GIF_MEDIA_TYPE,
    EncodedGif,
    GifDisposal,
    GifDurationPolicy,
    GifExport,
    GifLoss,
    GifLossKind,
    GifWarning,
    GifWarningKind,
    encode_gif,
    export_gif,
)
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
from moana.export.spritesheet import (
    MANIFEST_MEDIA_TYPE,
    MAX_SPRITESHEET_IMAGE_BYTES,
    MAX_SPRITESHEET_MANIFEST_BYTES,
    SPRITESHEET_FORMAT,
    SPRITESHEET_VERSION,
    EncodedSpritesheet,
    FramePixels,
    ManifestFrame,
    SheetAnimation,
    SheetFrame,
    SheetLayout,
    SpriteFrame,
    SpritesheetExport,
    SpritesheetManifest,
    encode_spritesheet,
    export_spritesheet,
    load_spritesheet,
    parse_spritesheet_manifest,
    slice_spritesheet,
    spritesheet_layout,
)

__all__ = [
    "EXPORT_BYTES_PER_PIXEL",
    "GIF_MEDIA_TYPE",
    "MANIFEST_MEDIA_TYPE",
    "MAX_INDEXED_COLORS",
    "MAX_SCALE",
    "MAX_SPRITESHEET_IMAGE_BYTES",
    "MAX_SPRITESHEET_MANIFEST_BYTES",
    "MEDIA_TYPE",
    "SPRITESHEET_FORMAT",
    "SPRITESHEET_VERSION",
    "EncodedGif",
    "EncodedPng",
    "EncodedSpritesheet",
    "ExportManifest",
    "ExportMode",
    "FramePixels",
    "GifDisposal",
    "GifDurationPolicy",
    "GifExport",
    "GifLoss",
    "GifLossKind",
    "GifWarning",
    "GifWarningKind",
    "ManifestFrame",
    "RasterFrame",
    "SheetAnimation",
    "SheetFrame",
    "SheetLayout",
    "SpriteFrame",
    "SpritesheetExport",
    "SpritesheetManifest",
    "encode_gif",
    "encode_png",
    "encode_spritesheet",
    "export_gif",
    "export_png",
    "export_spritesheet",
    "load_spritesheet",
    "parse_spritesheet_manifest",
    "slice_spritesheet",
    "spritesheet_layout",
]
