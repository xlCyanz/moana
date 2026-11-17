"""Pillow boundary of :class:`~moana.core.canvas.Canvas` (MOANA.md sections 5 and 20).

Only already-open ``PIL.Image.Image`` objects cross this boundary; decoding files
belongs to ``project``/``export``. Mode, frame count and size are checked before the
pixel data is read, and data is always copied in both directions.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from moana.core.budget import RenderLimits
from moana.core.canvas import CHANNELS, Canvas, check_canvas_budget
from moana.core.coordinates import MAX_DIMENSION, MIN_DIMENSION, Dimensions, require_int
from moana.core.errors import ValidationError

__all__ = ["canvas_from_pillow", "canvas_to_pillow"]


def canvas_to_pillow(canvas: Canvas) -> Image.Image:
    """A new ``RGBA`` image with a copy of the canvas pixels."""
    return Image.frombytes("RGBA", (canvas.width, canvas.height), canvas.to_bytes())


def canvas_from_pillow(image: object, *, limits: RenderLimits) -> Canvas:
    """Copy an ``RGBA`` single-frame image into a new canvas.

    Other modes are rejected rather than converted implicitly (no silent change of
    colours or alpha). Size and budget are checked before reading pixel data.
    """
    if not isinstance(image, Image.Image):
        raise ValidationError(
            "canvas source must be a Pillow image",
            context={"field": "image", "reason": "not_image"},
        )
    if image.mode != "RGBA":
        raise ValidationError(
            "image mode must be RGBA",
            context={"field": "image", "reason": "wrong_mode", "mode": image.mode},
        )
    if getattr(image, "n_frames", 1) != 1:
        raise ValidationError(
            "image must have exactly one frame",
            context={"field": "image", "reason": "multiple_frames"},
        )
    width, height = image.size
    for name, value in (("width", width), ("height", height)):
        require_int(value, name, minimum=MIN_DIMENSION, maximum=MAX_DIMENSION)
    dimensions = Dimensions(width, height)
    check_canvas_budget(dimensions, limits)
    try:
        data = image.tobytes("raw", "RGBA")
    except (OSError, ValueError) as exc:  # closed or truncated lazy image
        raise ValidationError(
            "image pixel data cannot be read",
            context={"field": "image", "reason": "unreadable_image"},
        ) from exc
    pixels = np.frombuffer(data, dtype=np.uint8).reshape(height, width, CHANNELS)
    return Canvas.from_array(pixels, limits=limits)
