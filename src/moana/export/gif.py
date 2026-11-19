"""Animated GIF export with an explicit loss policy (MOANA.md section 18, ADR-034).

GIF cannot store partial alpha, more than 256 colours or arbitrary times, so every
loss is either refused or explicitly accepted by the caller and reported:

* **Palette.** One global colour table shared by every frame, at most 256 entries.
  Without ``palette`` the exporter derives the exact set of colours present (never
  quantises): the transparent entry first (index 0, only when some pixel is
  transparent), then every opaque colour sorted ascending by ``(r, g, b)``. With a
  :class:`~moana.palette.Palette`, declared order is index order (as indexed PNG); its
  first ``alpha == 0`` entry is the transparent index, or one transparent entry is
  appended when a pixel needs it. Reserving the transparent index leaves 255 opaque
  colours; more colours than entries is ``ValidationError`` ``too_many_colors``.
* **Alpha.** Alpha 0 is the transparent index and alpha 255 opaque. A pixel with
  ``0 < a < 255`` is ``partial_alpha`` unless the caller passes an opaque
  ``background``; then each channel becomes ``(c·a + b·(255 - a) + 127) // 255``
  (nearest integer; no ties exist because 255 is odd), alpha 255, and an
  ``alpha_flattened`` loss is reported per frame. Alpha 0 stays transparent.
  Pick the real destination page colour as ``background`` (any other colour leaves a
  halo), or remove partial alpha at the source (outline, dither). With a declared
  ``palette`` the flattened colours must already be in it (``color_not_in_palette``).
* **Durations.** GIF stores centiseconds. ``duration_policy="exact"`` (default)
  rejects a duration that is not a multiple of 10 ms (``duration_not_representable``);
  ``"round"`` uses ``max(10, 10·⌊(d + 5) / 10⌋)`` (half up, at least 10 ms) and
  reports a ``duration_rounded`` loss for every changed frame. Browsers stretch delays
  under 20 ms: one :class:`GifWarning` ``short_delay`` per such frame (the file keeps
  the effective value).
* **Frames.** Every frame is a full ``w x h`` image at ``(0, 0)`` with its own
  graphic control extension. ``disposal="background"`` (2, default) restores the
  frame area to transparent before the next one, so a transparent pixel never shows
  an older frame; ``disposal="none"`` (1) keeps the previous frame, and a frame that
  would reveal it (transparent where the previous one is opaque) is rejected
  (``disposal_reveals_previous``), also across the loop seam (frame 0 after the last
  frame) unless ``loop_count == 1``. GIF has no pivot (ignored) and the exporter never
  scales: upscale frames by an integer, nearest neighbour, before exporting.
* **Loop.** Moana's ``loop_count`` is the number of plays (0: infinite). It maps to
  the ``NETSCAPE2.0`` repeat count as ``0 -> 0``, ``N >= 2 -> N - 1``, and ``1`` omits
  the block (a single play).

The container is assembled here byte by byte; Pillow only LZW-compresses the index
plane of each frame (a single-frame save with fixed options, parsed strictly). Its
multi-frame writer is not used: it crops, merges identical frames and, in Pillow 13,
writes a second GIF header after a fully transparent frame with disposal 2. The
result is decoded again with Pillow and the composited, normalised timeline (digest
and duration per frame, equal consecutive frames merged) must equal the target, as
must the loop count; otherwise :class:`ExportError`, never a file.
"""

from __future__ import annotations

import hashlib
import io
import os
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import Final, Literal

import numpy as np
import numpy.typing as npt
from PIL import Image

from moana.core.budget import DEFAULT_RENDER_LIMITS, RenderLimits
from moana.core.coordinates import require_int
from moana.core.digest import visual_digest
from moana.core.errors import BudgetExceeded, ErrorDetail, ExportError, ValidationError
from moana.core.limits import MAX_LOOP_COUNT
from moana.export._frames import checked_sprite_frames, frame_error
from moana.export.atomic import commit_bytes
from moana.export.png import RasterFrame, destination_path, is_normalized, palette_indices
from moana.export.spritesheet import SpriteFrame
from moana.palette import Palette, Rgba

__all__ = [
    "GIF_DELAY_UNIT_MS",
    "GIF_FRAME_BYTES_PER_PIXEL",
    "GIF_MEDIA_TYPE",
    "GIF_OUTPUT_BYTES_PER_PIXEL",
    "MAX_GIF_COLORS",
    "SHORT_DELAY_MS",
    "SHORT_DELAY_WARNING",
    "EncodedGif",
    "GifDisposal",
    "GifDurationPolicy",
    "GifExport",
    "GifLoss",
    "GifLossKind",
    "GifWarning",
    "GifWarningKind",
    "encode_gif",
    "export_gif",
]

GIF_MEDIA_TYPE: Final = "image/gif"
MAX_GIF_COLORS: Final = 256
GIF_DELAY_UNIT_MS: Final = 10
SHORT_DELAY_MS: Final = 20
GIF_FRAME_BYTES_PER_PIXEL: Final = 48
"""Working bytes per pixel of the one frame being processed: flattening (a copy and a
``uint32`` plane of the partial pixels, at most ``4 + 16``), palette lookup (``intp``
position, flag and index, ``8 + 1 + 1``), the Pillow index image and its LZW output
(``1 + 2``) and the verification decode (Pillow's frame state, the RGBA conversion,
its bytes and a normalised copy, about ``12 + 4 + 4 + 4``). Measured below (ADR-034)."""
GIF_OUTPUT_BYTES_PER_PIXEL: Final = 4
"""Bytes per pixel of every frame for the encoded stream: LZW with 12-bit codes is at
most 1.5 bytes per pixel plus one length byte per 255, held as parts and once joined."""

GifDisposal = Literal["background", "none"]
GifDurationPolicy = Literal["exact", "round"]
GifLossKind = Literal["duration_rounded", "alpha_flattened"]
GifWarningKind = Literal["short_delay"]

SHORT_DELAY_WARNING: Final[GifWarningKind] = "short_delay"

_DISPOSAL_CODES: Final[dict[str, int]] = {"background": 2, "none": 1}
_TRANSPARENT: Final = (0, 0, 0, 0)
_Pixels = npt.NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class GifLoss:
    """One accepted loss. ``duration_rounded``: requested and effective milliseconds;
    ``alpha_flattened``: ``requested`` = pixels with partial alpha, ``effective`` = 0."""

    kind: GifLossKind
    frame_id: str
    requested: int
    effective: int

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready entry with sorted keys."""
        return dict(sorted((field.name, getattr(self, field.name)) for field in fields(self)))


@dataclass(frozen=True, slots=True)
class GifWarning:
    """A frame the file keeps as asked but players may not: ``short_delay`` (< 20 ms)."""

    kind: GifWarningKind
    frame_id: str

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready entry with sorted keys."""
        return {"frame_id": self.frame_id, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class EncodedGif:
    """Verified GIF bytes, not yet written anywhere.

    ``frame_digests`` are the visual digests of the target frames after flattening
    (the effective pixels), verified equivalent to the decoded timeline;
    ``durations_ms`` their effective durations; ``transparent_index`` is ``None`` when
    the file has no transparency; ``background`` is the flatten colour ``(r, g, b, a)``
    or ``None``, so an ``alpha_flattened`` loss can be reproduced.
    """

    data: bytes
    width: int
    height: int
    frames: int
    encoded_frames: int
    durations_ms: tuple[int, ...]
    frame_digests: tuple[str, ...]
    loop_count: int
    disposal: GifDisposal
    palette_size: int
    transparent_index: int | None
    background: tuple[int, int, int, int] | None
    losses: tuple[GifLoss, ...]
    warnings: tuple[GifWarning, ...]


@dataclass(frozen=True, slots=True)
class GifExport:
    """What :func:`export_gif` wrote: path, media type, size, timeline, hashes, losses."""

    path: str
    media_type: str
    width: int
    height: int
    frames: int
    encoded_frames: int
    durations_ms: tuple[int, ...]
    duration_ms: int
    frame_digests: tuple[str, ...]
    loop_count: int
    disposal: GifDisposal
    palette_size: int
    transparent_index: int | None
    background: tuple[int, int, int, int] | None
    file_sha256: str
    byte_size: int
    losses: tuple[GifLoss, ...]
    warnings: tuple[GifWarning, ...]

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready report with sorted keys.

        Tuples become lists, losses and warnings sorted mappings and ``background``
        ``[r, g, b, a]`` or ``None``.
        """
        mapping = {field.name: getattr(self, field.name) for field in fields(self)}
        mapping["durations_ms"] = list(self.durations_ms)
        mapping["frame_digests"] = list(self.frame_digests)
        mapping["background"] = None if self.background is None else list(self.background)
        mapping["losses"] = [loss.to_mapping() for loss in self.losses]
        mapping["warnings"] = [warning.to_mapping() for warning in self.warnings]
        return dict(sorted(mapping.items()))


# --- options, frames and budget ------------------------------------------------------


def _option_error(field: str, reason: str, message: str) -> ValidationError:
    return ValidationError(message, context={"field": field, "reason": reason})


def _check_options(
    loop_count: object,
    duration_policy: object,
    disposal: object,
    background: object,
    palette: object,
    limits: object,
) -> None:
    require_int(loop_count, "loop_count", minimum=0, maximum=MAX_LOOP_COUNT)
    if type(duration_policy) is not str or duration_policy not in ("exact", "round"):
        raise _option_error(
            "duration_policy", "unknown_duration_policy", "duration_policy must be exact or round"
        )
    if type(disposal) is not str or disposal not in _DISPOSAL_CODES:
        raise _option_error("disposal", "unknown_disposal", "disposal must be background or none")
    if background is not None:
        if not isinstance(background, Rgba):
            raise TypeError("background must be an Rgba value or None")
        if not background.is_opaque:
            raise _option_error("background", "not_opaque", "the flatten background must be opaque")
    if palette is not None and not isinstance(palette, Palette):
        raise TypeError("palette must be a moana.palette.Palette or None")
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")


def _check_budget(count: int, width: int, height: int, limits: RenderLimits) -> None:
    """One detail per exceeded resource, with integer arithmetic only."""
    area = width * height
    geometry = limits.geometry
    checks = (
        ("frame_pixels", limits.max_frame_pixels, count * area),
        ("export_dimension", geometry.max_dimension, max(width, height)),
        ("export_area", geometry.max_area, area),
        (
            "buffer_bytes",
            limits.max_buffer_bytes,
            GIF_FRAME_BYTES_PER_PIXEL * area + GIF_OUTPUT_BYTES_PER_PIXEL * count * area,
        ),
    )
    details = [
        ErrorDetail(
            BudgetExceeded.code,
            f"GIF {resource} exceed the request budget",
            context={"resource": resource, "limit": limit, "estimated": estimated},
        )
        for resource, limit, estimated in checks
        if estimated > limit
    ]
    if details:
        raise BudgetExceeded(
            "GIF export exceeds the request budget",
            context=dict(details[0].context),
            details=details,
        )


def _effective_durations(
    checked: Sequence[tuple[SpriteFrame, RasterFrame]], policy: GifDurationPolicy
) -> tuple[tuple[int, ...], tuple[GifLoss, ...]]:
    effective: list[int] = []
    losses: list[GifLoss] = []
    for index, (frame, _) in enumerate(checked):
        requested = frame.duration_ms
        if requested % GIF_DELAY_UNIT_MS == 0:
            effective.append(requested)
            continue
        if policy == "exact":
            raise frame_error(
                "GIF durations are multiples of 10 ms (use duration_policy='round')",
                "duration_not_representable",
                index,
                duration_ms=requested,
            )
        rounded = max(GIF_DELAY_UNIT_MS, (requested + 5) // 10 * 10)
        effective.append(rounded)
        losses.append(GifLoss("duration_rounded", frame.frame_id, requested, rounded))
    return tuple(effective), tuple(losses)


# --- pixels ----------------------------------------------------------------------------


def _pixels(raster: RasterFrame, index: int) -> _Pixels:
    pixels = np.frombuffer(raster.rgba, dtype=np.uint8).reshape(raster.height, raster.width, 4)
    if not is_normalized(pixels):
        raise frame_error(
            "frame pixels with zero alpha must be (0, 0, 0, 0)", "not_normalized", index
        )
    return pixels


def _flatten_values(values: _Pixels, background: Rgba) -> _Pixels:
    """``(k, 4)`` partial-alpha values composited over ``background``, alpha 255."""
    wide = values.astype(np.uint32)
    alpha = wide[:, 3:4]
    ground = np.array([background.r, background.g, background.b], dtype=np.uint32)
    wide[:, :3] = (wide[:, :3] * alpha + ground * (255 - alpha) + 127) // 255
    wide[:, 3] = 255
    return wide.astype(np.uint8)


def _flattened(pixels: _Pixels, background: Rgba | None, index: int) -> tuple[_Pixels, int]:
    """The frame with binary alpha, and how many partial-alpha pixels were flattened."""
    alpha = pixels[:, :, 3]
    partial = (alpha != 0) & (alpha != 255)
    count = int(np.count_nonzero(partial))
    if count == 0:
        return pixels, 0
    if background is None:
        ys, xs = np.nonzero(partial)
        raise frame_error(
            "GIF has binary alpha: pass an opaque background to flatten partial alpha",
            "partial_alpha",
            index,
            x=int(xs[0]),
            y=int(ys[0]),
            pixels=count,
        )
    flat = pixels.copy()
    flat[partial] = _flatten_values(flat[partial], background)
    return flat, count


@dataclass(frozen=True, slots=True)
class _Scan:
    """First pass over the frames: colours, transparency and flattened pixel counts."""

    opaque: npt.NDArray[np.uint32]
    transparent: bool
    flattened: tuple[int, ...]


def _too_many_colors(count: int, maximum: int) -> ValidationError:
    return ValidationError(
        "GIF supports at most 256 palette entries (255 opaque colours with transparency)",
        context={
            "field": "palette",
            "reason": "too_many_colors",
            "maximum": maximum,
            "count": count,
        },
    )


def _scan(
    checked: Sequence[tuple[SpriteFrame, RasterFrame]],
    background: Rgba | None,
    disposal: GifDisposal,
    *,
    collect: bool,
    wraps: bool,
) -> _Scan:
    """``wraps``: playback returns from the last frame to frame 0 (``loop_count != 1``)."""
    opaque = np.zeros(0, dtype=np.uint32)
    transparent = False
    flattened: list[int] = []
    previous_opaque: npt.NDArray[np.bool_] | None = None
    first_clear: npt.NDArray[np.bool_] | None = None
    for index, (_, raster) in enumerate(checked):
        flat, count = _flattened(_pixels(raster, index), background, index)
        flattened.append(count)
        clear = flat[:, :, 3] == 0
        transparent = transparent or bool(clear.any())
        if disposal == "none":
            if previous_opaque is not None and bool((previous_opaque & clear).any()):
                raise _reveals_previous(index)
            previous_opaque = ~clear
            first_clear = clear if first_clear is None else first_clear
        if collect:
            keys = np.ascontiguousarray(flat).view(np.uint32).reshape(-1)
            opaque = np.union1d(opaque, np.unique(keys[~clear.reshape(-1)]))
            if opaque.size > MAX_GIF_COLORS:
                raise _too_many_colors(int(opaque.size), MAX_GIF_COLORS)
    if (  # the last frame, then frame 0 again
        wraps
        and first_clear is not None
        and previous_opaque is not None
        and bool((previous_opaque & first_clear).any())
    ):
        raise _reveals_previous(0)
    return _Scan(opaque, transparent, tuple(flattened))


def _reveals_previous(index: int) -> ValidationError:
    return ValidationError(
        "with disposal none a transparent pixel would show the previous frame",
        context={"field": "disposal", "reason": "disposal_reveals_previous", "index": index},
    )


def _derived_values(scan: _Scan) -> tuple[_Pixels, int | None]:
    """Transparent entry first (when needed), then opaque colours by ``(r, g, b)``."""
    colors = scan.opaque.view(np.uint8).reshape(-1, 4)
    colors = colors[np.lexsort((colors[:, 2], colors[:, 1], colors[:, 0]))]
    if not scan.transparent:
        return np.ascontiguousarray(colors), None
    if colors.shape[0] + 1 > MAX_GIF_COLORS:
        raise _too_many_colors(colors.shape[0] + 1, MAX_GIF_COLORS)
    clear = np.zeros((1, 4), dtype=np.uint8)
    return np.ascontiguousarray(np.concatenate((clear, colors))), 0


def _declared_values(
    palette: Palette, background: Rgba | None, transparent: bool
) -> tuple[_Pixels, int | None]:
    """Declared entries in order, flattened like pixels; a transparent one appended if needed."""
    entries: list[tuple[int, int, int, int]] = []
    for position, color in enumerate(palette.colors):
        value = color.rgba.normalized()
        if 0 < value.a < 255:
            if background is None:
                raise ValidationError(
                    "a palette entry has partial alpha and no flatten background was given",
                    context={"field": "palette", "reason": "partial_alpha", "index": position},
                )
            flat = _flatten_values(np.array([value.as_tuple()], dtype=np.uint8), background)
            entries.append((int(flat[0, 0]), int(flat[0, 1]), int(flat[0, 2]), 255))
        else:
            entries.append(value.as_tuple())
    transparent_index = entries.index(_TRANSPARENT) if _TRANSPARENT in entries else None
    if transparent and transparent_index is None:
        transparent_index = len(entries)
        entries.append(_TRANSPARENT)
    if len(entries) > MAX_GIF_COLORS:
        raise _too_many_colors(len(entries), MAX_GIF_COLORS)
    return np.array(entries, dtype=np.uint8).reshape(len(entries), 4), transparent_index


def _frame_indices(flat: _Pixels, values: _Pixels, index: int) -> _Pixels:
    try:
        return palette_indices(np.ascontiguousarray(flat), values)
    except ValidationError as exc:
        raise ValidationError(exc.message, context={**exc.context, "index": index}) from None


# --- GIF container ---------------------------------------------------------------------


def _encoder_error() -> ExportError:
    return ExportError(
        "the LZW encoder produced an unexpected layout", context={"reason": "encoder_layout"}
    )


def _image_data(single: bytes, width: int, height: int) -> bytes:
    """LZW code size, sub-blocks and terminator of Pillow's single-frame GIF, strictly."""
    if len(single) < 13 or single[:6] not in (b"GIF87a", b"GIF89a"):
        raise _encoder_error()
    flags = single[10]
    offset = 13 + (3 << ((flags & 7) + 1) if flags & 0x80 else 0)
    while single[offset : offset + 1] == b"!":
        offset = _after_sub_blocks(single, offset + 2)  # skip a well-formed extension
    descriptor = b"," + struct.pack("<HHHHB", 0, 0, width, height, 0)
    if single[offset : offset + 10] != descriptor:
        raise _encoder_error()
    start = offset + 10
    position = _after_sub_blocks(single, start + 1)
    if single[position:] != b";" or not 2 <= single[start] <= 8:
        raise _encoder_error()
    return single[start:position]


def _after_sub_blocks(data: bytes, position: int) -> int:
    """Offset after the data sub-blocks starting at ``position`` and their terminator."""
    while position < len(data):
        length = data[position]
        position += 1 + length
        if length == 0:
            return position
    raise _encoder_error()


def _lzw(indices: _Pixels) -> bytes:
    height, width = indices.shape
    image = Image.frombytes("P", (width, height), indices.tobytes())
    image.putpalette(bytes(768), "RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="GIF", optimize=False, interlace=False)
    return _image_data(buffer.getvalue(), width, height)


def _netscape_repeats(loop_count: int) -> int | None:
    """``NETSCAPE2.0`` repeat count for Moana's plays: 0 -> 0, 1 -> no block, N -> N - 1."""
    if loop_count == 1:
        return None
    return 0 if loop_count == 0 else loop_count - 1


def _header(
    width: int, height: int, values: _Pixels, loop_count: int, transparent: int | None
) -> bytes:
    """Signature, screen (background index = transparent index or 0), table and loop."""
    bits = max(1, (values.shape[0] - 1).bit_length())
    table = np.zeros((1 << bits, 3), dtype=np.uint8)
    table[: values.shape[0]] = values[:, :3]
    flags = 0x80 | 0x70 | (bits - 1)
    screen = struct.pack("<HHBBB", width, height, flags, transparent or 0, 0)
    repeats = _netscape_repeats(loop_count)
    netscape = (
        b""
        if repeats is None
        else b"!\xff\x0bNETSCAPE2.0\x03\x01" + struct.pack("<H", repeats) + b"\x00"
    )
    return b"GIF89a" + screen + table.tobytes() + netscape


def _frame_block(
    data: bytes, width: int, height: int, duration_ms: int, disposal: int, transparent: int | None
) -> bytes:
    packed = disposal << 2 | (1 if transparent is not None else 0)
    control = b"!\xf9\x04" + struct.pack(
        "<BHBB", packed, duration_ms // GIF_DELAY_UNIT_MS, transparent or 0, 0
    )
    descriptor = b"," + struct.pack("<HHHHB", 0, 0, width, height, 0)
    return control + descriptor + data


# --- verification ----------------------------------------------------------------------

_Timeline = list[tuple[str, int]]


def _equivalent(timeline: _Timeline) -> _Timeline:
    """Equal consecutive frames merged, their durations summed."""
    merged: _Timeline = []
    for digest, duration in timeline:
        if merged and merged[-1][0] == digest:
            merged[-1] = (digest, merged[-1][1] + duration)
        else:
            merged.append((digest, duration))
    return merged


def _decoded(data: bytes, width: int, height: int) -> tuple[_Timeline, object]:
    """Composited, normalised frames and durations as Pillow decodes them, and the loop."""
    timeline: _Timeline = []
    try:
        with Image.open(io.BytesIO(data), formats=("GIF",)) as image:
            if image.size != (width, height):
                raise ExportError(
                    "encoded GIF has the wrong size", context={"reason": "timeline_mismatch"}
                )
            loop = image.info.get("loop")
            for index in range(getattr(image, "n_frames", 1)):
                image.seek(index)
                rgba = np.frombuffer(image.convert("RGBA").tobytes(), dtype=np.uint8)
                pixels = rgba.reshape(height, width, 4).copy()
                del rgba
                pixels[pixels[:, :, 3] == 0] = 0
                timeline.append(
                    (visual_digest(width, height, memoryview(pixels)), image.info["duration"])
                )
                del pixels
    except ExportError:
        raise
    except (OSError, ValueError, KeyError, SyntaxError, EOFError, zlib.error):
        raise ExportError(
            "encoded GIF cannot be decoded", context={"reason": "unreadable_gif"}
        ) from None
    return timeline, loop


def _verify(data: bytes, width: int, height: int, target: _Timeline, loop_count: int) -> int:
    decoded, loop = _decoded(data, width, height)
    if _equivalent(decoded) != _equivalent(target):
        raise ExportError(
            "decoded GIF frames or times differ from the target timeline",
            context={"reason": "timeline_mismatch"},
        )
    if loop != _netscape_repeats(loop_count):
        raise ExportError(
            "decoded GIF loop count differs from the requested one",
            context={"reason": "loop_mismatch"},
        )
    return len(decoded)


# --- public API ------------------------------------------------------------------------


def encode_gif(
    frames: Sequence[SpriteFrame],
    *,
    loop_count: int = 0,
    duration_policy: GifDurationPolicy = "exact",
    disposal: GifDisposal = "background",
    background: Rgba | None = None,
    palette: Palette | None = None,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> EncodedGif:
    """Encode ``frames`` as an animated GIF in memory and verify its decoded timeline.

    ``frames`` are any :class:`SpriteFrame` of one size (``pivot`` is ignored: GIF has
    none), such as ``moana.animation.FrameRender``. Raises ``TypeError`` (wrong
    types), ``ValidationError`` (options; frames: ``empty_frames``, ``size_mismatch``,
    ``invalid_id``, ``duplicate_frame``, ``invalid_duration``, ``wrong_size``,
    ``not_normalized``, ``duration_not_representable``, ``partial_alpha``,
    ``color_not_in_palette``, all with ``index``; ``too_many_colors``;
    ``disposal_reveals_previous``), ``BudgetExceeded`` (``frames``, ``frame_pixels``,
    ``export_dimension``, ``export_area``, ``buffer_bytes``, before any pixel buffer)
    or ``ExportError`` (``timeline_mismatch``, ``loop_mismatch``, ``unreadable_gif``,
    ``encoder_layout``).
    """
    _check_options(loop_count, duration_policy, disposal, background, palette, limits)
    checked = checked_sprite_frames(frames, subject="GIF", check_pivot=False, check_pixels=False)
    width, height = checked[0][1].width, checked[0][1].height
    _check_budget(len(checked), width, height, limits)
    durations, duration_losses = _effective_durations(checked, duration_policy)
    scan = _scan(checked, background, disposal, collect=palette is None, wraps=loop_count != 1)
    if palette is None:
        values, transparent_index = _derived_values(scan)
    else:
        values, transparent_index = _declared_values(palette, background, scan.transparent)
    disposal_code = _DISPOSAL_CODES[disposal]
    parts = [_header(width, height, values, loop_count, transparent_index)]
    target: _Timeline = []
    for index, (_, raster) in enumerate(checked):
        flat, _ = _flattened(_pixels(raster, index), background, index)
        target.append((visual_digest(width, height, memoryview(np.ascontiguousarray(flat))), 0))
        lzw = _lzw(_frame_indices(flat, values, index))
        del flat
        parts.append(
            _frame_block(lzw, width, height, durations[index], disposal_code, transparent_index)
        )
    parts.append(b";")
    data = b"".join(parts)
    del parts
    target = [(digest, duration) for (digest, _), duration in zip(target, durations, strict=True)]
    encoded_frames = _verify(data, width, height, target, loop_count)
    alpha_losses = tuple(
        GifLoss("alpha_flattened", frame.frame_id, count, 0)
        for (frame, _), count in zip(checked, scan.flattened, strict=True)
        if count
    )
    return EncodedGif(
        data=data,
        width=width,
        height=height,
        frames=len(checked),
        encoded_frames=encoded_frames,
        durations_ms=durations,
        frame_digests=tuple(digest for digest, _ in target),
        loop_count=loop_count,
        disposal=disposal,
        palette_size=int(values.shape[0]),
        transparent_index=transparent_index,
        background=None if background is None else background.as_tuple(),
        losses=duration_losses + alpha_losses,
        warnings=tuple(
            GifWarning(SHORT_DELAY_WARNING, frame.frame_id)
            for (frame, _), duration in zip(checked, durations, strict=True)
            if duration < SHORT_DELAY_MS
        ),
    )


def export_gif(
    frames: Sequence[SpriteFrame],
    path: str | os.PathLike[str],
    *,
    loop_count: int = 0,
    duration_policy: GifDurationPolicy = "exact",
    disposal: GifDisposal = "background",
    background: Rgba | None = None,
    palette: Palette | None = None,
    overwrite: bool = False,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> GifExport:
    """Encode, verify and atomically write an animated GIF to ``path`` (host-authorised).

    ``path`` must end in ``.gif`` (``wrong_extension``; unrepresentable: ``invalid_name``).
    Everything is encoded and verified before the write; with ``overwrite=False``
    (default) an existing file is never replaced (``ExportError`` ``exists``). Returns
    the report only after the file is committed.
    """
    destination = destination_path(path, field="path", suffix=".gif")
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be a bool")
    encoded = encode_gif(
        frames,
        loop_count=loop_count,
        duration_policy=duration_policy,
        disposal=disposal,
        background=background,
        palette=palette,
        limits=limits,
    )
    commit_bytes(encoded.data, destination, overwrite=overwrite)
    return GifExport(
        path=os.fspath(destination),
        media_type=GIF_MEDIA_TYPE,
        width=encoded.width,
        height=encoded.height,
        frames=encoded.frames,
        encoded_frames=encoded.encoded_frames,
        durations_ms=encoded.durations_ms,
        duration_ms=sum(encoded.durations_ms),
        frame_digests=encoded.frame_digests,
        loop_count=encoded.loop_count,
        disposal=encoded.disposal,
        palette_size=encoded.palette_size,
        transparent_index=encoded.transparent_index,
        background=encoded.background,
        file_sha256="sha256:" + hashlib.sha256(encoded.data).hexdigest(),
        byte_size=len(encoded.data),
        losses=encoded.losses,
        warnings=encoded.warnings,
    )
