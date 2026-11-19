"""Grid spritesheets with a reversible JSON manifest (MOANA.md section 17, ADR-033).

A sheet places ``n`` frames of one size ``w x h`` on a uniform grid, in frame order,
row by row, with ``columns`` cells per row (``1 <= columns <= n``; more columns than
frames is rejected, never clamped), ``padding`` transparent pixels between cells
and ``margin`` transparent pixels around the grid. No trim, no rotation, no packing.
Frame ``i`` occupies::

    x = margin + (i % columns) * (w + padding)
    y = margin + (i // columns) * (h + padding)
    rows = ceil(n / columns)
    sheet_width  = 2 * margin + columns * w + (columns - 1) * padding
    sheet_height = 2 * margin + rows * h + (rows - 1) * padding

**Rects are ``[x, y, w, h]``** (origin and size), not the half-open boxes
``[x0, y0, x1, y1]`` of documents: the frame covers columns ``x .. x + w - 1`` and
rows ``y .. y + h - 1``, i.e. the half-open box ``[x, y, x + w, y + h]``.

Every size, area, accumulated frame pixel count and byte estimate is checked with
integer arithmetic before the atlas is allocated. The atlas is encoded as a master
RGBA PNG by :func:`moana.export.encode_png` (verified round-trip) and the manifest is
canonical JSON (sorted keys, two-space indent, UTF-8, final newline), so the same
frames and options give the same bytes for both files. :func:`slice_spritesheet`
parses the manifest strictly, decodes the atlas within the budget, rejects
unnormalised pixels and non-transparent gaps, and rebuilds every frame, checking the
atlas digest and each frame digest.

The pivot is in integer pixels of the source frame (origin at its top-left corner,
``y = h`` is the edge below the last row), never relative to the rect or the atlas.
``trim_offset`` is the position of the trimmed rect inside ``source_size``; with no
trim it is always ``(0, 0)``.

Frames are any :class:`SpriteFrame` (``frame_id``, ``duration_ms``, ``pivot`` and a
``result`` raster), such as ``moana.animation.FrameRender``; ``export`` may not import
``animation`` or ``render`` (MOANA.md section 3).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, fields
from pathlib import Path, PurePosixPath
from typing import Final, NoReturn, Protocol

import numpy as np
import numpy.typing as npt
from PIL import Image

from moana.core.budget import DEFAULT_RENDER_LIMITS, RenderLimits
from moana.core.coordinates import MAX_DIMENSION, Point, require_int
from moana.core.digest import visual_digest
from moana.core.errors import (
    BudgetExceeded,
    ErrorDetail,
    ExportError,
    ReadError,
    UnsupportedVersion,
    ValidationError,
)
from moana.core.ids import is_id
from moana.core.limits import (
    MAX_ANIMATION_FRAMES,
    MAX_FRAME_DURATION_MS,
    MAX_LOOP_COUNT,
    MIN_FRAME_DURATION_MS,
)
from moana.export._frames import checked_sprite_frames
from moana.export.atomic import commit_bytes
from moana.export.png import (
    EXPORT_BYTES_PER_PIXEL,
    MEDIA_TYPE,
    RasterFrame,
    destination_path,
    encode_png,
    is_normalized,
)

__all__ = [
    "MANIFEST_MEDIA_TYPE",
    "MAX_SPRITESHEET_IMAGE_BYTES",
    "MAX_SPRITESHEET_MANIFEST_BYTES",
    "SHEET_BYTES_PER_PIXEL",
    "SLICE_BYTES_PER_PIXEL",
    "SPRITESHEET_FORMAT",
    "SPRITESHEET_VERSION",
    "EncodedSpritesheet",
    "FramePixels",
    "ManifestFrame",
    "SheetAnimation",
    "SheetFrame",
    "SheetLayout",
    "SpriteFrame",
    "SpritesheetExport",
    "SpritesheetManifest",
    "encode_spritesheet",
    "export_spritesheet",
    "load_spritesheet",
    "parse_spritesheet_manifest",
    "slice_spritesheet",
    "spritesheet_layout",
]

SPRITESHEET_FORMAT: Final = "moana-spritesheet"
SPRITESHEET_VERSION: Final = 1
MANIFEST_MEDIA_TYPE: Final = "application/json"
MAX_SPRITESHEET_MANIFEST_BYTES: Final = 1024 * 1024
"""256 frames with 64-character IDs need about 110 KiB; anything larger is rejected
(``BudgetExceeded``, ``manifest_bytes``) before it is decoded or parsed."""
MAX_SPRITESHEET_IMAGE_BYTES: Final = 32 * 1024 * 1024
"""Encoded atlas bytes accepted by :func:`slice_spritesheet` (the asset bound of
section 16: a 2048 x 2048 RGBA PNG is at most about 16 MiB)."""
SHEET_BYTES_PER_PIXEL: Final = 4 + 4 + EXPORT_BYTES_PER_PIXEL
"""Bytes per atlas pixel while encoding: the atlas array, its RGBA bytes and the PNG
encoder bound of :func:`moana.export.encode_png` (which counts those bytes again
inside its own estimate). The input frames are owned by the caller."""
SLICE_BYTES_PER_PIXEL: Final = 12
"""Bytes per atlas pixel while slicing, on top of the encoded PNG bytes. The real peak
is ``len(png) + 8·A``: the decoded Pillow image and its RGBA bytes (``4A + 4A``), then
the RGBA bytes with at most ``3A`` of boolean planes for the normalisation and gap
checks, then the RGBA bytes and the rebuilt frames (at most ``4A``); 12 keeps a
margin for Pillow's decoder state."""

_DIGEST: Final = re.compile("sha256:[0-9a-f]{64}")
_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_IHDR: Final = struct.Struct(">I4sIIBBBBB")
_IEND: Final = b"\x00\x00\x00\x00IEND\xaeB`\x82"
_RGBA_COLOR_TYPE: Final = 6
_MAX_NAME_CHARS: Final = 255
_ROOT_KEYS: Final = frozenset({"format", "version", "image", "layout", "frames"})
_OPTIONAL_ROOT_KEYS: Final = frozenset({"animation"})
_ANIMATION_KEYS: Final = frozenset({"id", "loop_count"})
_IMAGE_KEYS: Final = frozenset({"name", "media_type", "width", "height", "sha256", "digest"})
_LAYOUT_KEYS: Final = frozenset(
    {"frame_count", "columns", "rows", "margin", "padding", "frame_width", "frame_height"}
)
_FRAME_KEYS: Final = frozenset(
    {"frame_id", "rect", "duration_ms", "pivot", "source_size", "trim_offset", "digest"}
)

Rect = tuple[int, int, int, int]
Pair = tuple[int, int]


class SpriteFrame(Protocol):
    """One frame to place on a sheet; ``moana.animation.FrameRender`` satisfies it."""

    @property
    def frame_id(self) -> str: ...

    @property
    def duration_ms(self) -> int: ...

    @property
    def pivot(self) -> Point: ...

    @property
    def result(self) -> RasterFrame: ...


@dataclass(frozen=True, slots=True)
class FramePixels:
    """Straight row-major RGBA pixels of one frame (a :class:`RasterFrame`)."""

    width: int
    height: int
    rgba: bytes

    @property
    def digest(self) -> str:
        """Visual digest of the pixels (MOANA.md section 14)."""
        return visual_digest(self.width, self.height, self.rgba)


@dataclass(frozen=True, slots=True)
class SheetFrame:
    """A frame with its timeline values; a :class:`SpriteFrame` built without ``animation``.

    :func:`slice_spritesheet` returns these, so a sliced sheet can be exported again.
    """

    frame_id: str
    duration_ms: int
    pivot: Point
    result: FramePixels


@dataclass(frozen=True, slots=True)
class SheetAnimation:
    """Optional playback data of the manifest: animation ID and ``loop_count`` (0: infinite).

    Built by the caller (for example from ``AnimationRender.animation_id`` and
    ``loop_count``); ``export`` never imports ``animation``.
    """

    animation_id: str
    loop_count: int

    def to_mapping(self) -> dict[str, object]:
        """The ``animation`` member of the manifest."""
        return {"id": self.animation_id, "loop_count": self.loop_count}


@dataclass(frozen=True, slots=True)
class SheetLayout:
    """The grid of a sheet: admitted sizes and the ``[x, y, w, h]`` rect of each frame."""

    frame_count: int
    columns: int
    rows: int
    margin: int
    padding: int
    frame_width: int
    frame_height: int
    width: int
    height: int

    def rect(self, index: int) -> Rect:
        """``[x, y, w, h]`` of frame ``index`` (half-open box ``[x, y, x + w, y + h]``)."""
        require_int(index, "index", minimum=0, maximum=self.frame_count - 1)
        column, row = index % self.columns, index // self.columns
        x = self.margin + column * (self.frame_width + self.padding)
        y = self.margin + row * (self.frame_height + self.padding)
        return (x, y, self.frame_width, self.frame_height)

    @property
    def rects(self) -> tuple[Rect, ...]:
        """Rect of every frame, in frame order."""
        return tuple(self.rect(index) for index in range(self.frame_count))

    def to_mapping(self) -> dict[str, int]:
        """The ``layout`` member of the manifest (without the derived sheet size)."""
        return {
            "columns": self.columns,
            "frame_count": self.frame_count,
            "frame_height": self.frame_height,
            "frame_width": self.frame_width,
            "margin": self.margin,
            "padding": self.padding,
            "rows": self.rows,
        }


@dataclass(frozen=True, slots=True)
class ManifestFrame:
    """One frame entry of the manifest; ``trim_offset`` is always ``(0, 0)`` (no trim)."""

    frame_id: str
    rect: Rect
    duration_ms: int
    pivot: Pair
    source_size: Pair
    trim_offset: Pair
    digest: str

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready entry with sorted keys."""
        return {
            "digest": self.digest,
            "duration_ms": self.duration_ms,
            "frame_id": self.frame_id,
            "pivot": list(self.pivot),
            "rect": list(self.rect),
            "source_size": list(self.source_size),
            "trim_offset": list(self.trim_offset),
        }


@dataclass(frozen=True, slots=True)
class SpritesheetManifest:
    """Manifest version 1: atlas reference, grid layout and frames in order.

    ``image_sha256`` is the hash of the PNG bytes as written (provenance, not checked
    when slicing: a lossless re-encoding keeps the sheet valid); ``image_digest`` is
    the visual digest of the atlas pixels, which slicing verifies.
    """

    image_name: str
    image_sha256: str
    image_digest: str
    layout: SheetLayout
    frames: tuple[ManifestFrame, ...]
    animation: SheetAnimation | None = None

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready manifest with sorted keys; ``animation`` only when present."""
        mapping: dict[str, object] = {
            "format": SPRITESHEET_FORMAT,
            "frames": [frame.to_mapping() for frame in self.frames],
            "image": {
                "digest": self.image_digest,
                "height": self.layout.height,
                "media_type": MEDIA_TYPE,
                "name": self.image_name,
                "sha256": self.image_sha256,
                "width": self.layout.width,
            },
            "layout": self.layout.to_mapping(),
            "version": SPRITESHEET_VERSION,
        }
        if self.animation is not None:
            mapping["animation"] = self.animation.to_mapping()
        return dict(sorted(mapping.items()))

    def to_json(self) -> bytes:
        """Canonical bytes: sorted keys, two-space indent, UTF-8 and a final newline."""
        text = json.dumps(
            self.to_mapping(), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        )
        return text.encode("utf-8") + b"\n"


@dataclass(frozen=True, slots=True)
class EncodedSpritesheet:
    """Verified atlas PNG and manifest bytes, not yet written anywhere."""

    image: bytes
    manifest_json: bytes
    manifest: SpritesheetManifest


@dataclass(frozen=True, slots=True)
class SpritesheetExport:
    """What :func:`export_spritesheet` wrote: both files, sizes, frames and hashes."""

    image_path: str
    manifest_path: str
    image_media_type: str
    manifest_media_type: str
    width: int
    height: int
    frames: int
    columns: int
    rows: int
    margin: int
    padding: int
    frame_width: int
    frame_height: int
    image_digest: str
    image_sha256: str
    image_byte_size: int
    manifest_sha256: str
    manifest_byte_size: int
    warnings: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready report with sorted keys (``warnings`` as a list)."""
        mapping = {field.name: getattr(self, field.name) for field in fields(self)}
        mapping["warnings"] = list(self.warnings)
        return dict(sorted(mapping.items()))


# --- layout and budget -------------------------------------------------------------


def spritesheet_layout(
    frame_count: int,
    frame_width: int,
    frame_height: int,
    *,
    columns: int,
    margin: int = 0,
    padding: int = 0,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> SheetLayout:
    """Admit a grid of ``frame_count`` frames; pure integer arithmetic, no buffer.

    ``ValidationError`` for a non-integer (``bool`` included) or out-of-range value,
    ``frame_count < 1`` (``empty_frames``) or ``columns > frame_count``
    (``too_many_columns``); ``BudgetExceeded`` with one detail per exceeded resource
    (``frames`` over 256, ``frame_pixels``, ``export_dimension``, ``export_area``,
    ``buffer_bytes``) before anything is allocated.
    """
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    require_int(frame_count, "frame_count", minimum=0, maximum=2**31)
    if frame_count == 0:
        raise ValidationError(
            "a spritesheet needs at least one frame",
            context={"field": "frames", "reason": "empty_frames"},
        )
    require_int(frame_width, "frame_width", minimum=1, maximum=MAX_DIMENSION)
    require_int(frame_height, "frame_height", minimum=1, maximum=MAX_DIMENSION)
    require_int(columns, "columns", minimum=1, maximum=MAX_ANIMATION_FRAMES)
    require_int(margin, "margin", minimum=0, maximum=MAX_DIMENSION)
    require_int(padding, "padding", minimum=0, maximum=MAX_DIMENSION)
    if columns > frame_count:
        raise ValidationError(
            "columns must not exceed the number of frames",
            context={
                "field": "columns",
                "reason": "too_many_columns",
                "maximum": frame_count,
            },
        )
    rows = -(-frame_count // columns)
    width = 2 * margin + columns * frame_width + (columns - 1) * padding
    height = 2 * margin + rows * frame_height + (rows - 1) * padding
    _check_sheet_budget(
        frame_count, frame_count * frame_width * frame_height, width, height, limits
    )
    return SheetLayout(
        frame_count, columns, rows, margin, padding, frame_width, frame_height, width, height
    )


def _check_sheet_budget(
    frame_count: int,
    frame_pixels: int,
    width: int,
    height: int,
    limits: RenderLimits,
    *,
    encoded_bytes: int | None = None,
) -> None:
    """``encoded_bytes`` is ``None`` when encoding, the PNG size when slicing."""
    geometry = limits.geometry
    if encoded_bytes is None:
        buffer_bytes = SHEET_BYTES_PER_PIXEL * width * height
    else:
        buffer_bytes = encoded_bytes + SLICE_BYTES_PER_PIXEL * width * height
    checks = (
        ("frames", MAX_ANIMATION_FRAMES, frame_count),
        ("frame_pixels", limits.max_frame_pixels, frame_pixels),
        ("export_dimension", geometry.max_dimension, max(width, height)),
        ("export_area", geometry.max_area, width * height),
        ("buffer_bytes", limits.max_buffer_bytes, buffer_bytes),
    )
    details = [
        ErrorDetail(
            BudgetExceeded.code,
            f"spritesheet {resource} exceed the request budget",
            context={"resource": resource, "limit": limit, "estimated": estimated},
        )
        for resource, limit, estimated in checks
        if estimated > limit
    ]
    if details:
        raise BudgetExceeded(
            "spritesheet exceeds the request budget",
            context=dict(details[0].context),
            details=details,
        )


# --- encoding ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Atlas:
    width: int
    height: int
    rgba: bytes


def _plain_name(name: str) -> bool:
    """A plain ``<stem>.png`` file name: strict UTF-8, no directory part or control.

    Rejects surrogates, C0 and C1 controls and DEL, and a bare ``.png`` (no suffix,
    as :func:`moana.export.png.destination_path` decides).
    """
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return (
        0 < len(name) <= _MAX_NAME_CHARS
        and "/" not in name
        and "\\" not in name
        and not any(ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F for char in name)
        and PurePosixPath(name).suffix.lower() == ".png"
    )


def _check_name(name: object) -> str:
    if type(name) is not str:
        raise TypeError("image_name must be a str")
    if not _plain_name(name):
        raise ValidationError(
            "the image name must be a plain .png file name",
            context={"field": "image_name", "reason": "invalid_name"},
        )
    return name


def _check_animation(animation: object) -> SheetAnimation | None:
    if animation is None:
        return None
    if not isinstance(animation, SheetAnimation):
        raise TypeError("animation must be a SheetAnimation or None")
    if not is_id(animation.animation_id):
        raise ValidationError(
            "the animation ID must be a Moana ID",
            context={"field": "animation", "reason": "invalid_id"},
        )
    require_int(animation.loop_count, "loop_count", minimum=0, maximum=MAX_LOOP_COUNT)
    return animation


def encode_spritesheet(
    frames: Sequence[SpriteFrame],
    *,
    columns: int,
    margin: int = 0,
    padding: int = 0,
    image_name: str = "spritesheet.png",
    animation: SheetAnimation | None = None,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> EncodedSpritesheet:
    """Lay out, budget, compose and encode a sheet in memory (no disk).

    ``image_name`` is the atlas file name the manifest refers to; ``animation`` adds
    the optional ``animation`` block (ID and ``loop_count``). Raises ``TypeError``
    (not a sequence), ``ValidationError`` (layout values, frame metadata:
    ``size_mismatch``, ``invalid_id``, ``duplicate_frame``, ``invalid_duration``,
    ``pivot_out_of_frame``, ``wrong_size``, ``not_normalized``; ``invalid_name``),
    ``BudgetExceeded`` (before the atlas exists) or ``ExportError`` (PNG round-trip).
    """
    name = _check_name(image_name)
    playback = _check_animation(animation)
    checked = checked_sprite_frames(
        frames, subject="spritesheet", check_pivot=True, check_pixels=True
    )
    width, height = checked[0][1].width, checked[0][1].height
    layout = spritesheet_layout(
        len(checked), width, height, columns=columns, margin=margin, padding=padding, limits=limits
    )
    atlas = np.zeros((layout.height, layout.width, 4), dtype=np.uint8)
    entries: list[ManifestFrame] = []
    for index, (frame, raster) in enumerate(checked):
        x, y, _, _ = layout.rect(index)
        pixels = np.frombuffer(raster.rgba, dtype=np.uint8).reshape(height, width, 4)
        atlas[y : y + height, x : x + width] = pixels
        entries.append(
            ManifestFrame(
                frame_id=frame.frame_id,
                rect=layout.rect(index),
                duration_ms=frame.duration_ms,
                pivot=(frame.pivot.x, frame.pivot.y),
                source_size=(width, height),
                trim_offset=(0, 0),
                digest=visual_digest(width, height, raster.rgba),
            )
        )
    rgba = atlas.tobytes()
    del atlas
    encoded = encode_png(_Atlas(layout.width, layout.height, rgba), limits=limits)
    del rgba
    manifest = SpritesheetManifest(
        image_name=name,
        image_sha256="sha256:" + hashlib.sha256(encoded.data).hexdigest(),
        image_digest=encoded.source_digest,
        layout=layout,
        frames=tuple(entries),
        animation=playback,
    )
    return EncodedSpritesheet(
        image=encoded.data, manifest_json=manifest.to_json(), manifest=manifest
    )


# --- writing -----------------------------------------------------------------------


def export_spritesheet(
    frames: Sequence[SpriteFrame],
    image_path: str | os.PathLike[str],
    manifest_path: str | os.PathLike[str],
    *,
    columns: int,
    margin: int = 0,
    padding: int = 0,
    animation: SheetAnimation | None = None,
    overwrite: bool = False,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> SpritesheetExport:
    """Encode a sheet and write the atlas, then the manifest (host-authorised paths).

    Both files live in the same directory (``separate_directories`` otherwise): the
    manifest names the atlas by its file name. Everything is encoded and verified
    before the first write. With ``overwrite=False`` an existing destination is
    ``ExportError`` ``exists`` before anything is written (and the atomic link still
    refuses a file created concurrently). The atlas is committed first and the
    manifest last, so the manifest marks a complete sheet: if the manifest commit
    fails, the error carries ``committed`` = the atlas file name, which stays on
    disk (``overwrite=True`` may already have replaced an older atlas).
    """
    image = destination_path(image_path, field="image_path", suffix=".png")
    manifest_file = destination_path(manifest_path, field="manifest_path", suffix=".json")
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be a bool")
    if Path(os.path.abspath(image)).parent != Path(os.path.abspath(manifest_file)).parent:
        raise ValidationError(
            "the atlas and its manifest must be in the same directory",
            context={"field": "manifest_path", "reason": "separate_directories"},
        )
    encoded = encode_spritesheet(
        frames,
        columns=columns,
        margin=margin,
        padding=padding,
        image_name=image.name,
        animation=animation,
        limits=limits,
    )
    if not overwrite:
        for destination in (image, manifest_file):
            if os.path.lexists(destination):
                raise ExportError(
                    "destination already exists",
                    context={"reason": "exists", "file_name": destination.name},
                )
    commit_bytes(encoded.image, image, overwrite=overwrite)
    try:
        commit_bytes(encoded.manifest_json, manifest_file, overwrite=overwrite)
    except ExportError as exc:
        raise ExportError(
            exc.message,
            json_pointer=exc.json_pointer,
            context={**exc.context, "committed": image.name},
            details=exc.details,
        ) from None
    manifest, layout = encoded.manifest, encoded.manifest.layout
    return SpritesheetExport(
        image_path=os.fspath(image),
        manifest_path=os.fspath(manifest_file),
        image_media_type=MEDIA_TYPE,
        manifest_media_type=MANIFEST_MEDIA_TYPE,
        width=layout.width,
        height=layout.height,
        frames=layout.frame_count,
        columns=layout.columns,
        rows=layout.rows,
        margin=layout.margin,
        padding=layout.padding,
        frame_width=layout.frame_width,
        frame_height=layout.frame_height,
        image_digest=manifest.image_digest,
        image_sha256=manifest.image_sha256,
        image_byte_size=len(encoded.image),
        manifest_sha256="sha256:" + hashlib.sha256(encoded.manifest_json).hexdigest(),
        manifest_byte_size=len(encoded.manifest_json),
    )


# --- strict manifest parsing --------------------------------------------------------


def _corrupt(pointer: str, reason: str, message: str, **extra: int | str) -> NoReturn:
    raise ValidationError(
        f"invalid spritesheet manifest: {message}",
        json_pointer=pointer,
        context={"field": "manifest", "reason": reason, **extra},
    )


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey
        result[key] = value
    return result


class _DuplicateKey(Exception):
    """A JSON object repeats a member name."""


def _reject_constant(_: str) -> NoReturn:
    raise ValueError("NaN and Infinity are not JSON")


def _object(
    value: object, pointer: str, keys: frozenset[str], optional: frozenset[str] = frozenset()
) -> dict[str, object]:
    if type(value) is not dict:
        _corrupt(pointer, "wrong_type", "expected an object")
    for key in sorted(keys - value.keys()):
        _corrupt(f"{pointer}/{key}", "missing_member", "a required member is missing")
    if value.keys() - keys - optional:
        # Points at the object, never echoing a manifest key (as editing's not_parameter).
        _corrupt(pointer, "unknown_member", "the object has an unknown member")
    return value


def _int(value: object, pointer: str, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        _corrupt(pointer, "wrong_type", "expected an integer")
    if not minimum <= value <= maximum:
        _corrupt(pointer, "out_of_range", "integer out of range", minimum=minimum, maximum=maximum)
    return value


def _ints(value: object, pointer: str, count: int) -> tuple[int, ...]:
    if type(value) is not list or len(value) != count:
        _corrupt(pointer, "wrong_type", f"expected an array of {count} integers")
    return tuple(
        _int(item, f"{pointer}/{index}", -(2**31), 2**31) for index, item in enumerate(value)
    )


def _digest(value: object, pointer: str) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        _corrupt(pointer, "invalid_digest", "expected sha256: and 64 lower-case hex digits")
    return value


def _loaded(data: object) -> object:
    if not isinstance(data, bytes):
        raise TypeError("manifest must be bytes")
    if len(data) > MAX_SPRITESHEET_MANIFEST_BYTES:
        raise BudgetExceeded(
            "the spritesheet manifest exceeds the byte limit",
            context={
                "resource": "manifest_bytes",
                "limit": MAX_SPRITESHEET_MANIFEST_BYTES,
                "estimated": len(data),
            },
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _corrupt("", "not_utf8", "the manifest is not UTF-8")
    try:
        return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)
    except _DuplicateKey:
        _corrupt("", "duplicate_member", "an object repeats a member")
    except (ValueError, RecursionError):
        _corrupt("", "invalid_json", "the manifest is not valid JSON")


def _parsed_layout(value: object) -> SheetLayout:
    layout = _object(value, "/layout", _LAYOUT_KEYS)
    count = _int(layout["frame_count"], "/layout/frame_count", 1, MAX_ANIMATION_FRAMES)
    columns = _int(layout["columns"], "/layout/columns", 1, count)
    rows = _int(layout["rows"], "/layout/rows", 1, MAX_ANIMATION_FRAMES)
    margin = _int(layout["margin"], "/layout/margin", 0, MAX_DIMENSION)
    padding = _int(layout["padding"], "/layout/padding", 0, MAX_DIMENSION)
    frame_width = _int(layout["frame_width"], "/layout/frame_width", 1, MAX_DIMENSION)
    frame_height = _int(layout["frame_height"], "/layout/frame_height", 1, MAX_DIMENSION)
    if rows != -(-count // columns):
        _corrupt("/layout/rows", "layout_mismatch", "rows do not match frames and columns")
    width = 2 * margin + columns * frame_width + (columns - 1) * padding
    height = 2 * margin + rows * frame_height + (rows - 1) * padding
    return SheetLayout(
        count, columns, rows, margin, padding, frame_width, frame_height, width, height
    )


def _parsed_image(value: object, layout: SheetLayout) -> tuple[str, str, str]:
    image = _object(value, "/image", _IMAGE_KEYS)
    name = image["name"]
    if type(name) is not str:
        _corrupt("/image/name", "wrong_type", "expected a string")
    if not _plain_name(name):
        _corrupt("/image/name", "invalid_name", "the image name must be a plain .png file name")
    if image["media_type"] != MEDIA_TYPE:
        _corrupt("/image/media_type", "wrong_media_type", "the atlas must be image/png")
    for key, expected in (("width", layout.width), ("height", layout.height)):
        if _int(image[key], f"/image/{key}", 1, 2**31) != expected:
            _corrupt(f"/image/{key}", "layout_mismatch", "the sheet size does not match the grid")
    return (
        name,
        _digest(image["sha256"], "/image/sha256"),
        _digest(image["digest"], "/image/digest"),
    )


def _parsed_frame(value: object, index: int, layout: SheetLayout) -> ManifestFrame:
    pointer = f"/frames/{index}"
    frame = _object(value, pointer, _FRAME_KEYS)
    frame_id = frame["frame_id"]
    if not is_id(frame_id):
        _corrupt(f"{pointer}/frame_id", "invalid_id", "frame_id must be a Moana ID")
    assert isinstance(frame_id, str)  # narrowed by is_id
    x, y, w, h = _ints(frame["rect"], f"{pointer}/rect", 4)
    if w < 1 or h < 1 or x < 0 or y < 0 or x + w > layout.width or y + h > layout.height:
        _corrupt(f"{pointer}/rect", "rect_out_of_sheet", "the rect leaves the sheet")
    if (x, y, w, h) != layout.rect(index):
        _corrupt(f"{pointer}/rect", "rect_mismatch", "the rect is not the grid cell of the frame")
    duration = _int(
        frame["duration_ms"], f"{pointer}/duration_ms", MIN_FRAME_DURATION_MS, MAX_FRAME_DURATION_MS
    )
    pivot_x, pivot_y = _ints(frame["pivot"], f"{pointer}/pivot", 2)
    if not (0 <= pivot_x <= w and 0 <= pivot_y <= h):
        _corrupt(f"{pointer}/pivot", "pivot_out_of_frame", "the pivot leaves the frame")
    if _ints(frame["source_size"], f"{pointer}/source_size", 2) != (w, h):
        _corrupt(f"{pointer}/source_size", "source_size_mismatch", "trimmed frames are unsupported")
    if _ints(frame["trim_offset"], f"{pointer}/trim_offset", 2) != (0, 0):
        _corrupt(f"{pointer}/trim_offset", "unsupported_trim", "trim_offset must be [0, 0]")
    return ManifestFrame(
        frame_id=frame_id,
        rect=(x, y, w, h),
        duration_ms=duration,
        pivot=(pivot_x, pivot_y),
        source_size=(w, h),
        trim_offset=(0, 0),
        digest=_digest(frame["digest"], f"{pointer}/digest"),
    )


def _parsed_animation(value: object) -> SheetAnimation:
    animation = _object(value, "/animation", _ANIMATION_KEYS)
    animation_id = animation["id"]
    if not is_id(animation_id):
        _corrupt("/animation/id", "invalid_id", "the animation ID must be a Moana ID")
    assert isinstance(animation_id, str)  # narrowed by is_id
    loop_count = _int(animation["loop_count"], "/animation/loop_count", 0, MAX_LOOP_COUNT)
    return SheetAnimation(animation_id, loop_count)


def _versioned_root(data: bytes) -> dict[str, object]:
    """The root object after ``format`` and ``version``, before the v1 member set."""
    root = _loaded(data)
    if type(root) is not dict:
        _corrupt("", "wrong_type", "expected an object")
    for key in ("format", "version"):
        if key not in root:
            _corrupt(f"/{key}", "missing_member", "a required member is missing")
    if root["format"] != SPRITESHEET_FORMAT:
        _corrupt("/format", "wrong_format", "not a Moana spritesheet manifest")
    version = root["version"]
    if type(version) is not int:
        _corrupt("/version", "wrong_type", "expected an integer")
    if version != SPRITESHEET_VERSION:
        raise UnsupportedVersion(
            "unsupported spritesheet manifest version",
            json_pointer="/version",
            context={"field": "version", "reason": "unknown_version", "supported": 1},
        )
    return _object(root, "", _ROOT_KEYS, _OPTIONAL_ROOT_KEYS)


def parse_spritesheet_manifest(data: bytes) -> SpritesheetManifest:
    """Parse and strictly validate manifest bytes (no image needed).

    The size is checked before decoding (``BudgetExceeded`` ``manifest_bytes``). Every
    other problem is ``ValidationError`` with ``reason`` and ``json_pointer``:
    ``not_utf8``, ``invalid_json``, ``duplicate_member``, ``wrong_type``,
    ``missing_member``, ``unknown_member``, ``wrong_format``, ``out_of_range``
    (integers are never ``bool`` or float), ``layout_mismatch``, ``wrong_media_type``,
    ``invalid_name``, ``invalid_digest``, ``invalid_id``, ``duplicate_frame``,
    ``rect_out_of_sheet``, ``rect_mismatch`` (overlap, padding or margin),
    ``pivot_out_of_frame``, ``source_size_mismatch``, ``unsupported_trim`` and
    ``frame_count_mismatch``. The root object, ``format`` and ``version`` are checked
    first: a well-formed integer ``version`` other than 1 is ``UnsupportedVersion``
    whatever the other members are; only then is the exact v1 member set applied
    (``animation`` is optional).
    """
    root = _versioned_root(data)
    layout = _parsed_layout(root["layout"])
    name, sha256, digest = _parsed_image(root["image"], layout)
    frames = root["frames"]
    if type(frames) is not list:
        _corrupt("/frames", "wrong_type", "expected an array")
    if len(frames) != layout.frame_count:
        _corrupt("/frames", "frame_count_mismatch", "frames do not match layout/frame_count")
    entries: list[ManifestFrame] = []
    seen: set[str] = set()
    for index, value in enumerate(frames):
        entry = _parsed_frame(value, index, layout)
        if entry.frame_id in seen:
            _corrupt(f"/frames/{index}/frame_id", "duplicate_frame", "frame IDs must be unique")
        seen.add(entry.frame_id)
        entries.append(entry)
    animation = _parsed_animation(root["animation"]) if "animation" in root else None
    return SpritesheetManifest(name, sha256, digest, layout, tuple(entries), animation)


# --- slicing -----------------------------------------------------------------------


def _image_error(reason: str, message: str) -> ValidationError:
    return ValidationError(message, context={"field": "image", "reason": reason})


def _image_limit(limits: RenderLimits) -> int:
    return min(MAX_SPRITESHEET_IMAGE_BYTES, limits.max_buffer_bytes)


def _decoded_atlas(data: bytes, layout: SheetLayout, limits: RenderLimits) -> bytes:
    """Header, size and budget before Pillow decodes anything (as project assets)."""
    if len(data) > _image_limit(limits):
        raise BudgetExceeded(
            "the spritesheet image exceeds the byte limit",
            context={
                "resource": "image_bytes",
                "limit": _image_limit(limits),
                "estimated": len(data),
            },
        )
    if not data.startswith(_SIGNATURE) or len(data) < len(_SIGNATURE) + _IHDR.size:
        raise _image_error("not_png", "the spritesheet image is not a PNG")
    length, kind, width, height, depth, color, *_ = _IHDR.unpack_from(data, len(_SIGNATURE))
    if length != 13 or kind != b"IHDR":
        raise _image_error("not_png", "the spritesheet image is not a PNG")
    if depth != 8 or color != _RGBA_COLOR_TYPE:
        raise _image_error("wrong_mode", "the spritesheet image must be an 8-bit RGBA PNG")
    if (width, height) != (layout.width, layout.height):
        raise _image_error("image_size_mismatch", "the image size does not match the manifest")
    if not data.endswith(_IEND):
        raise _image_error("unreadable_image", "the spritesheet image is truncated")
    _check_sheet_budget(
        layout.frame_count,
        layout.frame_count * layout.frame_width * layout.frame_height,
        width,
        height,
        limits,
        encoded_bytes=len(data),
    )
    try:
        with Image.open(io.BytesIO(data), formats=("PNG",)) as image:
            if getattr(image, "is_animated", False):
                raise _image_error("multiple_frames", "animated PNG atlases are not supported")
            image.load()
            if image.size != (width, height) or image.mode != "RGBA":  # pragma: no cover
                raise _image_error("unreadable_image", "the PNG header is inconsistent")
            return image.tobytes("raw", "RGBA")
    except ValidationError:
        raise
    except (OSError, ValueError, SyntaxError, EOFError, zlib.error, Image.DecompressionBombError):
        raise _image_error("unreadable_image", "the spritesheet image cannot be decoded") from None


def _check_atlas_pixels(atlas: npt.NDArray[np.uint8], frames: Sequence[ManifestFrame]) -> None:
    """Every pixel normalised and every gap (margin, padding, empty cells) ``(0, 0, 0, 0)``.

    Checked independently of the digests, with at most ``3A`` bytes of boolean planes.
    """
    if not is_normalized(atlas):
        raise _image_error("not_normalized", "atlas pixels with zero alpha must be (0, 0, 0, 0)")
    occupied = atlas.any(axis=2)
    for frame in frames:
        x, y, w, h = frame.rect
        occupied[y : y + h, x : x + w] = False
    if bool(occupied.any()):
        raise _image_error("dirty_gap", "margin and padding pixels must be (0, 0, 0, 0)")


def slice_spritesheet(
    image: bytes,
    manifest: bytes,
    *,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> tuple[SheetFrame, ...]:
    """Rebuild every frame from atlas PNG bytes and manifest bytes, in manifest order.

    The manifest is parsed first (:func:`parse_spritesheet_manifest`); the PNG header
    must be 8-bit RGBA of the manifest's size, its bytes within
    ``min(MAX_SPRITESHEET_IMAGE_BYTES, limits.max_buffer_bytes)`` and the request budget
    (``len(png) + SLICE_BYTES_PER_PIXEL·A``) is checked before decoding. Then the atlas
    digest (``/image/digest``) must match, every pixel must be normalised
    (``not_normalized``) and every gap transparent (``dirty_gap``), and every frame
    digest (``/frames/i/digest``) must match (``ValidationError`` ``digest_mismatch``).
    """
    if not isinstance(image, bytes):
        raise TypeError("image must be bytes")
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    parsed = parse_spritesheet_manifest(manifest)
    layout = parsed.layout
    rgba = _decoded_atlas(image, layout, limits)
    if visual_digest(layout.width, layout.height, rgba) != parsed.image_digest:
        _corrupt("/image/digest", "digest_mismatch", "the atlas pixels do not match")
    atlas = np.frombuffer(rgba, dtype=np.uint8).reshape(layout.height, layout.width, 4)
    _check_atlas_pixels(atlas, parsed.frames)
    frames: list[SheetFrame] = []
    for index, entry in enumerate(parsed.frames):
        x, y, w, h = entry.rect
        pixels = FramePixels(w, h, atlas[y : y + h, x : x + w].tobytes())
        if pixels.digest != entry.digest:
            _corrupt(f"/frames/{index}/digest", "digest_mismatch", "the frame pixels do not match")
        frames.append(SheetFrame(entry.frame_id, entry.duration_ms, Point(*entry.pivot), pixels))
    return tuple(frames)


_READ_FLAGS: Final = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
_READ_CHUNK: Final = 1024 * 1024


def _read_failure(reason: str, field: str, name: str) -> ReadError:
    return ReadError(
        "the file cannot be read", context={"field": field, "reason": reason, "file_name": name}
    )


def _read_bounded(path: object, field: str, maximum: int) -> bytes:
    """At most ``maximum + 1`` bytes of a regular file, opened without blocking.

    Same reasons as ``moana.project``'s caller reads (``not_found``, ``is_directory``,
    ``permission_denied``, ``not_a_file``, ``io_error``); a FIFO or device never blocks.
    """
    if not isinstance(path, str | os.PathLike):
        raise TypeError(f"{field} must be a str or os.PathLike")
    raw = os.fspath(path)
    if not isinstance(raw, str):
        raise TypeError(f"{field} must be text, not bytes")
    name = Path(raw).name
    try:
        descriptor = os.open(raw, _READ_FLAGS)
    except FileNotFoundError:
        raise _read_failure("not_found", field, name) from None
    except PermissionError:
        reason = "is_directory" if os.path.isdir(raw) else "permission_denied"
        raise _read_failure(reason, field, name) from None
    except (OSError, ValueError):
        reason = "is_directory" if os.path.isdir(raw) else "io_error"
        raise _read_failure(reason, field, name) from None
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            reason = "is_directory" if stat.S_ISDIR(mode) else "not_a_file"
            raise _read_failure(reason, field, name)
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, _READ_CHUNK))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError:  # pragma: no cover - a regular file that fails mid-read
        raise _read_failure("io_error", field, name) from None
    finally:
        os.close(descriptor)
    data = b"".join(chunks)
    if len(data) > maximum:
        raise BudgetExceeded(
            "the file exceeds the byte limit",
            context={"resource": f"{field}_bytes", "limit": maximum, "estimated": len(data)},
        )
    return data


def load_spritesheet(
    image_path: str | os.PathLike[str],
    manifest_path: str | os.PathLike[str],
    *,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> tuple[SheetFrame, ...]:
    """Read both files (each bounded before reading the rest) and slice the sheet.

    A missing or unreadable file is ``ReadError`` (``not_found``, ``is_directory``,
    ``permission_denied``, ``not_a_file``, ``io_error``) with its file name only; a
    file over its byte limit is ``BudgetExceeded``. The manifest's ``/image/name`` need
    not equal the atlas file name: integrity comes from the digests. Then as
    :func:`slice_spritesheet`.
    """
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    manifest = _read_bounded(manifest_path, "manifest", MAX_SPRITESHEET_MANIFEST_BYTES)
    image = _read_bounded(image_path, "image", _image_limit(limits))
    return slice_spritesheet(image, manifest, limits=limits)
