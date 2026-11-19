"""Shared frame checks of the animated exports (spritesheet and GIF; ADR-033, ADR-034).

Private to ``moana.export``: both exporters receive structural ``SpriteFrame`` values
(``frame_id``, ``duration_ms``, ``pivot`` and a ``result`` raster) and validate their
metadata the same way, with the same reasons and ``index``, before any buffer exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

import numpy as np

from moana.core.coordinates import MAX_DIMENSION, Point, require_int
from moana.core.errors import BudgetExceeded, ErrorDetail, ValidationError
from moana.core.ids import is_id
from moana.core.limits import MAX_ANIMATION_FRAMES, MAX_FRAME_DURATION_MS, MIN_FRAME_DURATION_MS
from moana.export.png import RasterFrame, is_normalized

if TYPE_CHECKING:
    from moana.export.spritesheet import SpriteFrame

__all__ = ["checked_sprite_frames", "frame_error", "too_many_frames"]

_MISSING: Final = object()
_FRAME_MEMBERS: Final = ("frame_id", "duration_ms", "pivot", "result")
_RASTER_MEMBERS: Final = ("width", "height", "rgba")


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
