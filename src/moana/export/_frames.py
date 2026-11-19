"""Shared helpers of the animated exports (spritesheet, GIF, APNG and WebP).

Private to ``moana.export`` (ADR-033, ADR-034, ADR-035): every exporter receives
structural ``SpriteFrame`` values (``frame_id``, ``duration_ms``, ``pivot`` and a
``result`` raster) and validates their metadata the same way, with the same reasons
and ``index``, before any buffer exists. The animated containers also share the
budget check (one detail per resource, before reading a pixel), the normalised pixel
view of a frame and the timeline verification: decode with Pillow, normalise alpha 0
and compare digests and durations after merging equal consecutive frames.
"""

from __future__ import annotations

import io
import zlib
from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

import numpy as np
import numpy.typing as npt
from PIL import Image

from moana.core.budget import RenderLimits
from moana.core.coordinates import MAX_DIMENSION, Point, require_int
from moana.core.digest import visual_digest
from moana.core.errors import BudgetExceeded, ErrorDetail, ExportError, ValidationError
from moana.core.ids import is_id
from moana.core.limits import MAX_ANIMATION_FRAMES, MAX_FRAME_DURATION_MS, MIN_FRAME_DURATION_MS
from moana.export.png import RasterFrame, is_normalized

if TYPE_CHECKING:
    from moana.export.spritesheet import SpriteFrame

__all__ = [
    "Timeline",
    "check_animation_budget",
    "checked_sprite_frames",
    "decoded_timeline",
    "equivalent_timeline",
    "frame_error",
    "normalized_pixels",
    "too_many_frames",
]

Timeline = list[tuple[str, int | None]]
"""``(visual digest, duration in ms)`` per frame; ``None`` when a still file has no time."""

_MISSING: Final = object()
_FRAME_MEMBERS: Final = ("frame_id", "duration_ms", "pivot", "result")
_RASTER_MEMBERS: Final = ("width", "height", "rgba")
_DECODE_ERRORS: Final = (OSError, ValueError, KeyError, SyntaxError, EOFError, zlib.error)
_DURATION_TOLERANCE: Final = 1e-6
_Pixels = npt.NDArray[np.uint8]


def frame_error(message: str, reason: str, index: int, **extra: int) -> ValidationError:
    """``ValidationError`` located at ``frames`` and the frame ``index``."""
    return ValidationError(
        message, context={"field": "frames", "reason": reason, "index": index, **extra}
    )


def too_many_frames(count: int, subject: str) -> BudgetExceeded:
    """The ``frames`` budget error, raised from ``len`` before any frame is read."""
    context = {"resource": "frames", "limit": MAX_ANIMATION_FRAMES, "estimated": count}
    return BudgetExceeded(
        f"{subject} exceeds the request budget",
        context=context,
        details=[
            ErrorDetail(
                BudgetExceeded.code, f"{subject} frames exceed the request budget", context=context
            )
        ],
    )


def _require_members(value: object, members: tuple[str, ...], what: str, index: int) -> None:
    for name in members:
        if getattr(value, name, _MISSING) is _MISSING:  # only a missing attribute
            raise TypeError(f"frames[{index}] must be a sprite frame with a {what}.{name}")


def checked_sprite_frames(
    frames: object, *, subject: str, check_pivot: bool, check_pixels: bool
) -> tuple[tuple[SpriteFrame, RasterFrame], ...]:
    """Metadata, sizes and (optionally) pivots and normalised pixels of every frame.

    ``TypeError`` for a non-sequence, an item without the ``SpriteFrame`` members or a
    non-``bytes`` raster; ``BudgetExceeded`` ``frames`` (over 256, from ``len`` before
    any frame is read); ``ValidationError`` ``empty_frames`` and, with ``index``,
    ``size_mismatch``, ``invalid_id``, ``duplicate_frame``, ``invalid_duration``,
    ``pivot_out_of_frame`` (``check_pivot``), ``wrong_size`` and ``not_normalized``
    (``check_pixels``; reads a view of the pixels and three boolean planes).
    """
    if isinstance(frames, str | bytes) or not isinstance(frames, Sequence):
        raise TypeError("frames must be a sequence of sprite frames")
    if len(frames) > MAX_ANIMATION_FRAMES:  # before touching any frame
        raise too_many_frames(len(frames), subject)
    if not frames:
        raise ValidationError(
            f"a {subject} needs at least one frame",
            context={"field": "frames", "reason": "empty_frames"},
        )
    checked: list[tuple[SpriteFrame, RasterFrame]] = []
    seen: set[str] = set()
    size: tuple[int, int] | None = None
    for index, frame in enumerate(frames):
        _require_members(frame, _FRAME_MEMBERS, "frame", index)
        raster = frame.result
        _require_members(raster, _RASTER_MEMBERS, "result", index)
        width, height = raster.width, raster.height
        require_int(width, "width", minimum=1, maximum=MAX_DIMENSION)
        require_int(height, "height", minimum=1, maximum=MAX_DIMENSION)
        if size is None:
            size = (width, height)
        elif (width, height) != size:
            raise frame_error(
                f"every frame of a {subject} must have the same size", "size_mismatch", index
            )
        if not is_id(frame.frame_id):
            raise frame_error("frame_id must be a Moana ID", "invalid_id", index)
        if frame.frame_id in seen:
            raise frame_error("frame IDs must be unique", "duplicate_frame", index)
        seen.add(frame.frame_id)
        duration = frame.duration_ms
        if type(duration) is not int or not (
            MIN_FRAME_DURATION_MS <= duration <= MAX_FRAME_DURATION_MS
        ):
            raise frame_error(
                "duration_ms must be an integer in 1..60000", "invalid_duration", index
            )
        pivot = frame.pivot
        if check_pivot and (
            not isinstance(pivot, Point) or not (0 <= pivot.x <= width and 0 <= pivot.y <= height)
        ):
            raise frame_error(
                "pivot must be a Point inside the frame (edges included)",
                "pivot_out_of_frame",
                index,
            )
        if type(raster.rgba) is not bytes:
            raise TypeError("frame.result.rgba must be bytes")
        if len(raster.rgba) != width * height * 4:
            raise frame_error("frame RGBA size does not match its dimensions", "wrong_size", index)
        if check_pixels:
            pixels = np.frombuffer(raster.rgba, dtype=np.uint8).reshape(height, width, 4)
            if not is_normalized(pixels):
                raise frame_error(
                    "frame pixels with zero alpha must be (0, 0, 0, 0)", "not_normalized", index
                )
        checked.append((frame, raster))
    return tuple(checked)


def check_animation_budget(
    subject: str,
    count: int,
    width: int,
    height: int,
    limits: RenderLimits,
    *,
    frame_bytes_per_pixel: int,
    output_bytes_per_pixel: int,
    fixed_bytes: int = 0,
) -> None:
    """One ``BudgetExceeded`` detail per exceeded resource, with integer arithmetic only.

    ``frame_pixels`` (``n·A``), ``export_dimension``, ``export_area`` and
    ``buffer_bytes = fixed_bytes + frame_bytes_per_pixel·A + output_bytes_per_pixel·n·A``.
    """
    area = width * height
    geometry = limits.geometry
    checks = (
        ("frame_pixels", limits.max_frame_pixels, count * area),
        ("export_dimension", geometry.max_dimension, max(width, height)),
        ("export_area", geometry.max_area, area),
        (
            "buffer_bytes",
            limits.max_buffer_bytes,
            fixed_bytes + frame_bytes_per_pixel * area + output_bytes_per_pixel * count * area,
        ),
    )
    details = [
        ErrorDetail(
            BudgetExceeded.code,
            f"{subject} {resource} exceed the request budget",
            context={"resource": resource, "limit": limit, "estimated": estimated},
        )
        for resource, limit, estimated in checks
        if estimated > limit
    ]
    if details:
        raise BudgetExceeded(
            f"{subject} export exceeds the request budget",
            context=dict(details[0].context),
            details=details,
        )


def normalized_pixels(raster: RasterFrame, index: int) -> _Pixels:
    """A read-only ``(h, w, 4)`` view of the frame; ``not_normalized`` if alpha 0 has colour."""
    pixels = np.frombuffer(raster.rgba, dtype=np.uint8).reshape(raster.height, raster.width, 4)
    pixels.flags.writeable = False  # also over a writable buffer: never write the caller's
    if not is_normalized(pixels):
        raise frame_error(
            "frame pixels with zero alpha must be (0, 0, 0, 0)", "not_normalized", index
        )
    return pixels


def equivalent_timeline(timeline: Sequence[tuple[str, int | None]]) -> Timeline:
    """Equal consecutive frames merged, their durations summed (``None`` stays ``None``)."""
    merged: Timeline = []
    for digest, duration in timeline:
        if merged and merged[-1][0] == digest:
            previous = merged[-1][1]
            total = None if previous is None or duration is None else previous + duration
            merged[-1] = (digest, total)
        else:
            merged.append((digest, duration))
    return merged


def _milliseconds(value: object) -> int | None:
    """A decoded duration as whole milliseconds, or ``None`` if it is not one.

    Ints are kept; floats only when integral: APNG stores ``num / den`` seconds and
    Pillow reports ``num / den * 1000`` as a float (``1001 / 1000 * 1000`` is
    ``1000.9999999999999``), so a value within ``1e-6`` of an integer is that integer
    and anything else (another float, another type) cannot be a Moana duration.
    """
    if type(value) is int:
        return value
    if isinstance(value, float):
        nearest = round(value)
        if abs(value - nearest) <= _DURATION_TOLERANCE:
            return nearest
    return None


def decoded_timeline(
    data: bytes, kind: str, width: int, height: int, *, unreadable: str
) -> tuple[Timeline, object]:
    """Composited, normalised frames and durations as Pillow decodes them, and the loop.

    Only the ``kind`` plugin may open the bytes. A wrong size or a duration that is not
    whole milliseconds is ``ExportError`` ``timeline_mismatch``; a Pillow failure or a
    frame without a duration, ``ExportError`` with reason ``unreadable``.
    """
    timeline: Timeline = []
    try:
        with Image.open(io.BytesIO(data), formats=(kind,)) as image:
            if image.size != (width, height):
                raise ExportError(
                    "encoded animation has the wrong size",
                    context={"reason": "timeline_mismatch"},
                )
            loop = image.info.get("loop")
            for index in range(getattr(image, "n_frames", 1)):
                image.seek(index)
                rgba = np.frombuffer(image.convert("RGBA").tobytes(), dtype=np.uint8)
                pixels = rgba.reshape(height, width, 4).copy()
                del rgba
                pixels[pixels[:, :, 3] == 0] = 0
                digest = visual_digest(width, height, memoryview(pixels))
                del pixels
                duration = _milliseconds(image.info["duration"])
                if duration is None:
                    raise ExportError(
                        "decoded duration is not whole milliseconds",
                        context={"reason": "timeline_mismatch"},
                    )
                timeline.append((digest, duration))
    except ExportError:
        raise
    except _DECODE_ERRORS:
        raise ExportError(
            "encoded animation cannot be decoded", context={"reason": unreadable}
        ) from None
    return timeline, loop
