"""Lossless animated APNG and WebP export, only with a proven codec (MOANA.md §18, ADR-035).

Both formats keep every RGBA value exactly, partial alpha included, so unlike GIF
(ADR-034) there is no loss policy: a frame that would not decode to itself is an
:class:`ExportError`, never a file. Each exporter first asks
:func:`moana.export.codecs.require_codec` for its format; a missing or failing codec is
:class:`UnsupportedOperation` ``codec_unavailable`` before any pixel is read and before
the destination is touched, and no other format is ever written instead.

* **APNG** (``image/apng``, ``.png``: an APNG is a valid PNG whose first frame is the
  default image, so the extension does not lie and non-animated readers show frame 0).
  Moana writes the container itself: signature, ``IHDR`` (RGBA 8-bit), ``acTL`` with
  ``num_frames`` = frames requested and ``num_plays`` = ``loop_count`` (both count total
  plays, 0 = infinite), then per frame an ``fcTL`` for a full ``w x h`` frame at
  ``(0, 0)`` with ``dispose_op`` NONE, ``blend_op`` SOURCE (the frame replaces every
  pixel, alpha included) and delay ``duration_ms / 1000`` s exactly
  (``delay_den = 1000``, ``delay_num <= 60000``), and its data in ``IDAT`` (frame 0)
  or ``fdAT``. Pillow only deflates each frame: a single-frame RGBA PNG save with
  ``compress_level=9`` whose ``IHDR``/``IDAT``/``IEND`` layout is checked strictly.
  Pillow's own APNG writer is not used: it crops frames to the changed box, merges
  equal consecutive frames and writes a plain PNG for a single frame.
* **WebP** (``image/webp``, ``.webp``): Pillow's ``libwebp`` animation encoder, always
  ``lossless=True`` (there is no lossy option), ``quality=75`` and ``method=4`` (in
  lossless mode both only set the compression effort: ``cwebp -lossless`` defaults;
  ``method=6`` took about 1.2 s per noisy 128 x 128 frame),
  ``alpha_quality=100``, ``minimize_size=False``, ``allow_mixed=False``, ``kmin=9``,
  ``kmax=17`` and a transparent background. ``loop`` is the ``ANIM`` loop count, which
  also counts total plays (0 = infinite), and durations are whole milliseconds. The
  encoder may crop sub-frames and merges equal consecutive frames; that is verified
  as an equivalent timeline. When only one distinct frame remains (a single frame, or
  every frame equal) ``libwebp`` writes a still lossless WebP (no ``ANIM`` chunk, found
  by walking the RIFF chunks) that stores neither duration nor loop: only its pixels
  are verified, the report says ``stored_loop_count = stored_durations_ms = None`` and
  carries the warning ``still_image``. Every instant of the requested timeline shows
  those same pixels, so the still file is visually equivalent, not a hidden loss.

Every file is decoded again with Pillow (only the expected plugin): each composited
frame, alpha 0 normalised, must have the target's visual digest and duration once
equal consecutive frames are merged on both sides (``timeline_mismatch``), and the
loop must be the requested one (``loop_mismatch``). Same frames, options and codec
versions give the same bytes; the report records the codec and Pillow versions
because another version may legitimately produce other (equally lossless) bytes.
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
from moana.core.errors import ExportError
from moana.core.limits import MAX_LOOP_COUNT
from moana.export._frames import (
    Timeline,
    check_animation_budget,
    checked_sprite_frames,
    decoded_timeline,
    equivalent_timeline,
    normalized_pixels,
)
from moana.export.atomic import commit_bytes
from moana.export.codecs import WEBP_ENCODER_OPTIONS, CodecStatus, require_codec
from moana.export.png import COMPRESS_LEVEL, RasterFrame, destination_path
from moana.export.spritesheet import SpriteFrame

__all__ = [
    "APNG_DELAY_DENOMINATOR",
    "APNG_FRAME_BYTES_PER_PIXEL",
    "APNG_MEDIA_TYPE",
    "APNG_OUTPUT_BYTES_PER_PIXEL",
    "STILL_IMAGE_WARNING",
    "WEBP_FIXED_BYTES",
    "WEBP_FRAME_BYTES_PER_PIXEL",
    "WEBP_MEDIA_TYPE",
    "WEBP_OUTPUT_BYTES_PER_PIXEL",
    "AnimatedFormat",
    "AnimationExport",
    "AnimationWarning",
    "AnimationWarningKind",
    "EncodedAnimation",
    "encode_apng",
    "encode_webp",
    "export_apng",
    "export_webp",
]

AnimatedFormat = Literal["apng", "webp"]
AnimationWarningKind = Literal["still_image"]

APNG_MEDIA_TYPE: Final = "image/apng"
WEBP_MEDIA_TYPE: Final = "image/webp"
APNG_DELAY_DENOMINATOR: Final = 1000
STILL_IMAGE_WARNING: Final[AnimationWarningKind] = "still_image"
APNG_FRAME_BYTES_PER_PIXEL: Final = 48
"""Working bytes per pixel of the one APNG frame being deflated or verified: Pillow's
image and its PNG output in a buffer, the value and the extracted stream (about
``4 + 3·5``), and the verification decode (Pillow's canvas and previous frame, the
RGBA conversion, its bytes and a normalised copy, about ``5·4``). The process RSS
growth measured in fresh processes stays below ``48·A + 12·n·A`` (ADR-035 §8)."""
APNG_OUTPUT_BYTES_PER_PIXEL: Final = 12
"""Bytes per pixel of every frame for the file: a deflated frame is at most its raw
filtered size ``h·(1 + 4w) <= 5·A`` plus stored-block overhead, held once as a chunk
part and once in the joined file."""
WEBP_FIXED_BYTES: Final = 24 * 1024 * 1024
"""Native working memory of ``libwebp``'s lossless encoder that does not scale with the
frame (hash chains and entropy tables): one 256 x 256 frame already grows the process
RSS by about 19 MiB (ADR-035 §8)."""
WEBP_FRAME_BYTES_PER_PIXEL: Final = 64
"""Working bytes per pixel of one lossless encode and of the verification decode,
almost all native: a single 1024 x 1024 frame grows the RSS by about ``66·A``
including the fixed part (ADR-035 §8)."""
WEBP_OUTPUT_BYTES_PER_PIXEL: Final = 32
"""Bytes per pixel of every frame, measured as process RSS growth (``22 to 29·n·A`` with
many frames): the Pillow image handed to the encoder (``4``), the sub-frames and
keyframe candidates ``WebPAnimEncoder`` keeps (about ``8``), the assembled stream, the
output buffer and the returned value (about ``4`` each) and the verification decode
reading the whole file (``4``) (ADR-035 §8)."""

_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_DISPOSE_OP_NONE: Final = 0
_BLEND_OP_SOURCE: Final = 0
_WEBP_ANIMATION_FLAG: Final = 0x02


@dataclass(frozen=True, slots=True)
class _Container:
    media_type: str
    suffix: str
    plugin: str
    frame_bytes_per_pixel: int
    output_bytes_per_pixel: int
    fixed_bytes: int


_CONTAINERS: Final[dict[str, _Container]] = {
    "apng": _Container(
        APNG_MEDIA_TYPE,
        ".png",
        "PNG",
        APNG_FRAME_BYTES_PER_PIXEL,
        APNG_OUTPUT_BYTES_PER_PIXEL,
        fixed_bytes=0,
    ),
    "webp": _Container(
        WEBP_MEDIA_TYPE,
        ".webp",
        "WEBP",
        WEBP_FRAME_BYTES_PER_PIXEL,
        WEBP_OUTPUT_BYTES_PER_PIXEL,
        fixed_bytes=WEBP_FIXED_BYTES,
    ),
}


@dataclass(frozen=True, slots=True)
class AnimationWarning:
    """Something the file keeps differently from the request, without losing pixels.

    ``still_image``: the WebP is a still image (``frame_id`` is ``None``: it concerns the
    whole file). Same schema as ``GifWarning`` (``kind`` and ``frame_id``).
    """

    kind: AnimationWarningKind
    frame_id: str | None = None

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready entry with sorted keys."""
        return {"frame_id": self.frame_id, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class EncodedAnimation:
    """Verified APNG or WebP bytes, not yet written anywhere.

    ``frame_digests`` are the visual digests of the requested frames (verified
    equivalent to the decoded timeline), ``durations_ms`` their requested durations and
    ``encoded_frames`` the frames the decoder sees (fewer when the encoder merged equal
    neighbours). ``stored_durations_ms`` and ``stored_loop_count`` are what the file
    stores, as decoded (merged durations for WebP), or ``None`` for a still WebP that
    stores no time. ``codec``, ``codec_version`` and ``pillow_version`` identify the
    encoder that produced ``data``.
    """

    data: bytes
    format: AnimatedFormat
    width: int
    height: int
    frames: int
    encoded_frames: int
    durations_ms: tuple[int, ...]
    frame_digests: tuple[str, ...]
    loop_count: int
    stored_durations_ms: tuple[int, ...] | None
    stored_loop_count: int | None
    codec: str
    codec_version: str | None
    pillow_version: str
    warnings: tuple[AnimationWarning, ...]


@dataclass(frozen=True, slots=True)
class AnimationExport:
    """What :func:`export_apng` or :func:`export_webp` wrote, with codec versions."""

    path: str
    media_type: str
    format: AnimatedFormat
    width: int
    height: int
    frames: int
    encoded_frames: int
    durations_ms: tuple[int, ...]
    duration_ms: int
    frame_digests: tuple[str, ...]
    loop_count: int
    stored_durations_ms: tuple[int, ...] | None
    stored_loop_count: int | None
    codec: str
    codec_version: str | None
    pillow_version: str
    file_sha256: str
    byte_size: int
    warnings: tuple[AnimationWarning, ...]

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready report with sorted keys: tuples as lists, warnings as mappings."""
        mapping = {field.name: getattr(self, field.name) for field in fields(self)}
        mapping["durations_ms"] = list(self.durations_ms)
        mapping["frame_digests"] = list(self.frame_digests)
        stored = self.stored_durations_ms
        mapping["stored_durations_ms"] = None if stored is None else list(stored)
        mapping["warnings"] = [warning.to_mapping() for warning in self.warnings]
        return dict(sorted(mapping.items()))


# --- APNG container --------------------------------------------------------------------


def _encoder_error() -> ExportError:
    return ExportError(
        "the PNG encoder produced an unexpected layout", context={"reason": "encoder_layout"}
    )


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _ihdr(width: int, height: int) -> bytes:
    """RGBA, 8 bits per channel, deflate, adaptive filtering, no interlace."""
    return struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)


def _zlib_stream(single: bytes, width: int, height: int) -> bytes:
    """The joined ``IDAT`` payloads of Pillow's single-frame PNG, layout checked strictly:
    signature, the expected ``IHDR``, one or more consecutive ``IDAT``, ``IEND``, end."""
    if not single.startswith(_PNG_SIGNATURE):
        raise _encoder_error()
    chunks: list[tuple[bytes, bytes]] = []
    offset = len(_PNG_SIGNATURE)
    while offset < len(single):
        if offset + 12 > len(single):
            raise _encoder_error()
        length = int.from_bytes(single[offset : offset + 4], "big")
        end = offset + 12 + length
        if end > len(single):
            raise _encoder_error()
        chunks.append((single[offset + 4 : offset + 8], single[offset + 8 : end - 4]))
        offset = end
    kinds = [kind for kind, _ in chunks]
    if (
        len(chunks) < 3
        or chunks[0] != (b"IHDR", _ihdr(width, height))
        or chunks[-1] != (b"IEND", b"")
        or any(kind != b"IDAT" for kind in kinds[1:-1])
    ):
        raise _encoder_error()
    return b"".join(payload for _, payload in chunks[1:-1])


def _deflated(pixels: npt.NDArray[np.uint8], width: int, height: int) -> bytes:
    image = Image.frombytes("RGBA", (width, height), pixels.tobytes())
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=COMPRESS_LEVEL, optimize=False)
    del image
    return _zlib_stream(buffer.getvalue(), width, height)


def _frame_control(sequence: int, width: int, height: int, duration_ms: int) -> bytes:
    payload = struct.pack(
        ">IIIIIHHBB",
        sequence,
        width,
        height,
        0,
        0,
        duration_ms,
        APNG_DELAY_DENOMINATOR,
        _DISPOSE_OP_NONE,
        _BLEND_OP_SOURCE,
    )
    return _png_chunk(b"fcTL", payload)


def _apng_bytes(
    checked: Sequence[tuple[SpriteFrame, RasterFrame]], width: int, height: int, loop_count: int
) -> bytes:
    parts = [
        _PNG_SIGNATURE,
        _png_chunk(b"IHDR", _ihdr(width, height)),
        _png_chunk(b"acTL", struct.pack(">II", len(checked), loop_count)),
    ]
    sequence = 0
    for index, (frame, raster) in enumerate(checked):
        stream = _deflated(normalized_pixels(raster, index), width, height)
        parts.append(_frame_control(sequence, width, height, frame.duration_ms))
        sequence += 1
        if index == 0:
            parts.append(_png_chunk(b"IDAT", stream))
        else:
            parts.append(_png_chunk(b"fdAT", struct.pack(">I", sequence) + stream))
            sequence += 1
        del stream
    parts.append(_png_chunk(b"IEND", b""))
    data = b"".join(parts)
    del parts
    return data


# --- WebP ------------------------------------------------------------------------------


def _webp_bytes(
    checked: Sequence[tuple[SpriteFrame, RasterFrame]], width: int, height: int, loop_count: int
) -> bytes:
    images = [
        Image.frombytes("RGBA", (width, height), normalized_pixels(raster, index).tobytes())
        for index, (_, raster) in enumerate(checked)
    ]
    buffer = io.BytesIO()
    try:
        images[0].save(
            buffer,
            format="WEBP",
            save_all=True,
            append_images=images[1:],
            duration=[frame.duration_ms for frame, _ in checked],
            loop=loop_count,
            **WEBP_ENCODER_OPTIONS,
        )
    except (OSError, ValueError):
        raise ExportError("the WebP encoder failed", context={"reason": "encoder_failed"}) from None
    finally:
        del images
    return buffer.getvalue()


def _webp_layout_error() -> ExportError:
    return ExportError(
        "the WebP encoder produced an unexpected layout", context={"reason": "encoder_layout"}
    )


def _webp_is_animated(data: bytes) -> bool:
    """Walk the RIFF chunks: animated iff ``VP8X`` sets the animation flag and an ``ANIM``
    chunk follows; a malformed container is ``ExportError`` ``encoder_layout``."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise _webp_layout_error()
    if int.from_bytes(data[4:8], "little") != len(data) - 8:
        raise _webp_layout_error()
    kinds: list[bytes] = []
    flags = 0
    offset = 12
    while offset < len(data):
        if offset + 8 > len(data):
            raise _webp_layout_error()
        kind = data[offset : offset + 4]
        length = int.from_bytes(data[offset + 4 : offset + 8], "little")
        end = offset + 8 + length + (length & 1)
        if end > len(data):
            raise _webp_layout_error()
        if kind == b"VP8X" and not kinds and length >= 1:
            flags = data[offset + 8]
        kinds.append(kind)
        offset = end
    return bool(flags & _WEBP_ANIMATION_FLAG) and b"ANIM" in kinds


# --- shared pipeline -------------------------------------------------------------------


def _check_options(loop_count: object, limits: object) -> None:
    require_int(loop_count, "loop_count", minimum=0, maximum=MAX_LOOP_COUNT)
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")


def _target(checked: Sequence[tuple[SpriteFrame, RasterFrame]]) -> Timeline:
    target: Timeline = []
    for index, (frame, raster) in enumerate(checked):
        pixels = normalized_pixels(raster, index)
        digest = visual_digest(raster.width, raster.height, memoryview(pixels))
        target.append((digest, frame.duration_ms))
    return target


def _verify(
    data: bytes,
    kind: AnimatedFormat,
    size: tuple[int, int],
    target: Timeline,
    loop_count: int,
    *,
    still: bool,
) -> Timeline:
    """Decoded frames equal the target timeline (equal neighbours merged) and the loop.

    A still WebP stores no time or loop (Pillow reports duration 0 and loop 1): only
    its pixels are compared. Returns the decoded timeline.
    """
    decoded, decoded_loop = decoded_timeline(
        data, _CONTAINERS[kind].plugin, size[0], size[1], unreadable=f"unreadable_{kind}"
    )
    if still:
        decoded = [(digest, None) for digest, _ in decoded]
        target = [(digest, None) for digest, _ in target]
    if equivalent_timeline(decoded) != equivalent_timeline(target):
        raise ExportError(
            f"decoded {kind} frames or times differ from the target timeline",
            context={"reason": "timeline_mismatch"},
        )
    if not still and decoded_loop != loop_count:
        raise ExportError(
            f"decoded {kind} loop count differs from the requested one",
            context={"reason": "loop_mismatch"},
        )
    return decoded


def _encode(
    kind: AnimatedFormat, frames: Sequence[SpriteFrame], loop_count: int, limits: RenderLimits
) -> EncodedAnimation:
    _check_options(loop_count, limits)
    status: CodecStatus = require_codec(kind)
    subject = kind.upper()
    checked = checked_sprite_frames(frames, subject=subject, check_pivot=False, check_pixels=False)
    width, height = checked[0][1].width, checked[0][1].height
    container = _CONTAINERS[kind]
    check_animation_budget(
        subject,
        len(checked),
        width,
        height,
        limits,
        frame_bytes_per_pixel=container.frame_bytes_per_pixel,
        output_bytes_per_pixel=container.output_bytes_per_pixel,
        fixed_bytes=container.fixed_bytes,
    )
    target = _target(checked)
    if kind == "apng":
        data = _apng_bytes(checked, width, height, loop_count)
    else:
        data = _webp_bytes(checked, width, height, loop_count)
    still = kind == "webp" and not _webp_is_animated(data)
    decoded = _verify(data, kind, (width, height), target, loop_count, still=still)
    stored = tuple(duration for _, duration in decoded if duration is not None)
    return EncodedAnimation(
        data=data,
        format=kind,
        width=width,
        height=height,
        frames=len(checked),
        encoded_frames=len(decoded),
        durations_ms=tuple(frame.duration_ms for frame, _ in checked),
        frame_digests=tuple(digest for digest, _ in target),
        loop_count=loop_count,
        stored_durations_ms=None if still else stored,
        stored_loop_count=None if still else loop_count,
        codec=status.codec,
        codec_version=status.codec_version,
        pillow_version=status.pillow_version,
        warnings=(AnimationWarning(STILL_IMAGE_WARNING),) if still else (),
    )


def _export(
    kind: AnimatedFormat,
    frames: Sequence[SpriteFrame],
    path: object,
    *,
    loop_count: int,
    overwrite: object,
    limits: RenderLimits,
) -> AnimationExport:
    container = _CONTAINERS[kind]
    destination = destination_path(path, field="path", suffix=container.suffix)
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be a bool")
    encoded = _encode(kind, frames, loop_count, limits)
    commit_bytes(encoded.data, destination, overwrite=overwrite)
    return AnimationExport(
        path=os.fspath(destination),
        media_type=container.media_type,
        format=kind,
        width=encoded.width,
        height=encoded.height,
        frames=encoded.frames,
        encoded_frames=encoded.encoded_frames,
        durations_ms=encoded.durations_ms,
        duration_ms=sum(encoded.durations_ms),
        frame_digests=encoded.frame_digests,
        loop_count=encoded.loop_count,
        stored_durations_ms=encoded.stored_durations_ms,
        stored_loop_count=encoded.stored_loop_count,
        codec=encoded.codec,
        codec_version=encoded.codec_version,
        pillow_version=encoded.pillow_version,
        file_sha256="sha256:" + hashlib.sha256(encoded.data).hexdigest(),
        byte_size=len(encoded.data),
        warnings=encoded.warnings,
    )


# --- public API ------------------------------------------------------------------------


def encode_apng(
    frames: Sequence[SpriteFrame],
    *,
    loop_count: int = 0,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> EncodedAnimation:
    """Encode ``frames`` as a lossless APNG in memory and verify its decoded timeline.

    ``frames`` are any :class:`SpriteFrame` of one size (``pivot`` is ignored), such as
    ``moana.animation.FrameRender``; ``loop_count`` counts total plays (0: infinite).
    Raises ``UnsupportedOperation`` ``codec_unavailable`` (before reading any frame),
    ``TypeError`` (wrong types), ``ValidationError`` (``loop_count``; frames:
    ``empty_frames``, ``size_mismatch``, ``invalid_id``, ``duplicate_frame``,
    ``invalid_duration``, ``wrong_size``, ``not_normalized``, with ``index``),
    ``BudgetExceeded`` (``frames``, ``frame_pixels``, ``export_dimension``,
    ``export_area``, ``buffer_bytes``, before any pixel is read) or ``ExportError``
    (``timeline_mismatch``, ``loop_mismatch``, ``unreadable_apng``, ``encoder_layout``).
    """
    return _encode("apng", frames, loop_count, limits)


def encode_webp(
    frames: Sequence[SpriteFrame],
    *,
    loop_count: int = 0,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> EncodedAnimation:
    """Encode ``frames`` as a lossless (animated) WebP in memory and verify it.

    ``frames`` are any :class:`SpriteFrame` of one size (``pivot`` is ignored), such as
    ``moana.animation.FrameRender``; ``loop_count`` counts total plays (0: infinite).
    Raises ``UnsupportedOperation`` ``codec_unavailable`` (before reading any frame),
    ``TypeError`` (wrong types), ``ValidationError`` (``loop_count``; frames:
    ``empty_frames``, ``size_mismatch``, ``invalid_id``, ``duplicate_frame``,
    ``invalid_duration``, ``wrong_size``, ``not_normalized``, with ``index``),
    ``BudgetExceeded`` (``frames``, ``frame_pixels``, ``export_dimension``,
    ``export_area``, ``buffer_bytes``, before any pixel is read) or ``ExportError``
    (``timeline_mismatch``, ``loop_mismatch``, ``unreadable_webp``, ``encoder_failed``,
    ``encoder_layout``).
    A single frame (or all frames equal) gives a still WebP and the warning
    ``still_image``: the file keeps the pixels but no duration or loop
    (``stored_durations_ms`` and ``stored_loop_count`` are ``None``).
    """
    return _encode("webp", frames, loop_count, limits)


def export_apng(
    frames: Sequence[SpriteFrame],
    path: str | os.PathLike[str],
    *,
    loop_count: int = 0,
    overwrite: bool = False,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> AnimationExport:
    """Encode, verify and atomically write a lossless APNG to ``path`` (``.png``).

    Everything is encoded and verified before the write; with ``overwrite=False``
    (default) an existing file is never replaced (``ExportError`` ``exists``).
    """
    return _export("apng", frames, path, loop_count=loop_count, overwrite=overwrite, limits=limits)


def export_webp(
    frames: Sequence[SpriteFrame],
    path: str | os.PathLike[str],
    *,
    loop_count: int = 0,
    overwrite: bool = False,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> AnimationExport:
    """Encode, verify and atomically write a lossless WebP to ``path`` (``.webp``).

    Everything is encoded and verified before the write; with ``overwrite=False``
    (default) an existing file is never replaced (``ExportError`` ``exists``).
    """
    return _export("webp", frames, path, loop_count=loop_count, overwrite=overwrite, limits=limits)
