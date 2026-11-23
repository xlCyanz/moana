"""Exports at the edge of the engine (MOANART.md sections 3 and 18, ADR-019).

``export`` depends on ``core`` and ``palette`` only: it receives rendered frames
(any value with ``width``, ``height`` and RGBA ``bytes``, such as
``moanart.render.RenderResult``) and never calls the renderer or the editor. Implemented:
master RGBA and indexed PNG with integer nearest-neighbour scale, in-memory
round-trip verification and atomic writes that do not overwrite by default; grid
spritesheets (uniform grid, margin and padding, no trim or rotation) with a versioned
JSON manifest whose rects ``[x, y, w, h]``, durations, pivots and digests rebuild every
frame exactly (MOANA-023, ADR-033). Spritesheet frames are any ``SpriteFrame``
(``frame_id``, ``duration_ms``, ``pivot``, ``result``) such as
``moanart.animation.FrameRender``, which ``export`` never imports. Animated GIF
(MOANA-024, ADR-034): one shared palette of at most 256 entries (exact colours, never
quantised; a reserved transparent index), binary alpha with an explicit flatten
``background``, durations in multiples of 10 ms or an explicit rounding policy, full
frames with a configured disposal, and a decoded-timeline verification; every accepted
loss is reported. Lossless APNG and WebP (MOANA-025, ADR-035): every RGBA value and
duration kept exactly, ``loop_count`` as total plays, full-frame APNG container written
by MoanArt and ``libwebp`` lossless only, both verified by decoding; each is available
only when :func:`export_capabilities` proves its codec in this build (a probe per call,
no cache), otherwise ``UnsupportedOperation`` before any file and never another format.
Reports carry codec and Pillow versions. Compact packing comes with a later issue.
"""

from moanart.export.animated import (
    APNG_MEDIA_TYPE,
    STILL_IMAGE_WARNING,
    WEBP_MEDIA_TYPE,
    AnimatedFormat,
    AnimationExport,
    AnimationWarning,
    AnimationWarningKind,
    EncodedAnimation,
    encode_apng,
    encode_webp,
    export_apng,
    export_webp,
)
from moanart.export.codecs import (
    EXPORT_FORMATS,
    CodecStatus,
    ExportCapabilities,
    ExportFormat,
    codec_status,
    export_capabilities,
)
from moanart.export.gif import (
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
from moanart.export.png import (
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
from moanart.export.spritesheet import (
    LEGACY_SPRITESHEET_FORMAT,
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
    migrate_spritesheet_manifest,
    parse_spritesheet_manifest,
    slice_spritesheet,
    spritesheet_layout,
)

__all__ = [
    "APNG_MEDIA_TYPE",
    "EXPORT_BYTES_PER_PIXEL",
    "EXPORT_FORMATS",
    "GIF_MEDIA_TYPE",
    "LEGACY_SPRITESHEET_FORMAT",
    "MANIFEST_MEDIA_TYPE",
    "MAX_INDEXED_COLORS",
    "MAX_SCALE",
    "MAX_SPRITESHEET_IMAGE_BYTES",
    "MAX_SPRITESHEET_MANIFEST_BYTES",
    "MEDIA_TYPE",
    "SPRITESHEET_FORMAT",
    "SPRITESHEET_VERSION",
    "STILL_IMAGE_WARNING",
    "WEBP_MEDIA_TYPE",
    "AnimatedFormat",
    "AnimationExport",
    "AnimationWarning",
    "AnimationWarningKind",
    "CodecStatus",
    "EncodedAnimation",
    "EncodedGif",
    "EncodedPng",
    "EncodedSpritesheet",
    "ExportCapabilities",
    "ExportFormat",
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
    "codec_status",
    "encode_apng",
    "encode_gif",
    "encode_png",
    "encode_spritesheet",
    "encode_webp",
    "export_apng",
    "export_capabilities",
    "export_gif",
    "export_png",
    "export_spritesheet",
    "export_webp",
    "load_spritesheet",
    "migrate_spritesheet_manifest",
    "parse_spritesheet_manifest",
    "slice_spritesheet",
    "spritesheet_layout",
]
