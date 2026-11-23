"""Verified PNG assets of a project (MOANART.md sections 16 and 20, ADR-029).

The only asset type is an 8-bit RGBA PNG. :meth:`Asset.from_png` checks, before any
pixel is decoded: the PNG signature, a leading ``IHDR`` (dimensions, bit depth 8,
colour type 6), a final ``IEND`` chunk, the canvas contract (2048 per axis, hence
at most 4 194 304 pixels) and the pixel budget of the caller. Pillow then opens the
header only and must agree; animated PNG and embedded ICC profiles are rejected;
decoding failures (truncated data, bad CRC, corrupt zlib, a Pillow decompression
bomb) are ``ValidationError`` (``unreadable_image``). Pillow's own
decompression-bomb protection stays active and is never changed globally; the canvas
contract keeps every accepted asset far below its threshold.

An :class:`Asset` keeps the source bytes unchanged (they are what is saved and
hashed) and the decoded straight RGBA pixels. Pillow objects never leave this module.
"""

from __future__ import annotations

import hashlib
import io
import struct
import zlib
from dataclasses import dataclass, field
from typing import Final

from PIL import Image

from moanart.core.coordinates import MAX_DIMENSION
from moanart.core.errors import BudgetExceeded, ValidationError
from moanart.core.ids import is_id
from moanart.core.limits import MAX_ASSET_BYTES, MAX_ASSET_PIXELS

__all__ = ["PNG_MIME", "Asset", "asset_path"]

PNG_MIME: Final = "image/png"
_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_IHDR: Final = struct.Struct(">I4sIIBBBBB")
_RGBA_COLOR_TYPE: Final = 6
_IEND: Final = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def asset_path(sha256: str) -> str:
    """Immutable relative POSIX path of an asset: ``assets/<sha256>.png``."""
    return f"assets/{sha256}.png"


def _invalid(message: str, reason: str, **extra: int) -> ValidationError:
    return ValidationError(message, context={"field": "asset", "reason": reason, **extra})


def _header(data: bytes) -> tuple[int, int]:
    """Width and height from the leading ``IHDR``; only 8-bit RGBA is accepted."""
    if not data.startswith(_SIGNATURE) or len(data) < len(_SIGNATURE) + _IHDR.size:
        raise _invalid("the asset is not a PNG image", "not_png")
    length, kind, width, height, depth, color, *_ = _IHDR.unpack_from(data, len(_SIGNATURE))
    if length != 13 or kind != b"IHDR":
        raise _invalid("the asset is not a PNG image", "not_png")
    if depth != 8 or color != _RGBA_COLOR_TYPE:
        raise _invalid("the asset must be an 8-bit RGBA PNG", "wrong_mode")
    if not data.endswith(_IEND):
        # Truncated data: rejected before Pillow, whatever LOAD_TRUNCATED_IMAGES says.
        raise _invalid("the PNG asset is truncated", "unreadable_image")
    return width, height


def _check_size(width: int, height: int, max_pixels: int) -> None:
    """Both axes within the canvas contract (whose area is exactly 2048 x 2048)."""
    for value in (width, height):
        if not 1 <= value <= MAX_DIMENSION:
            raise _invalid(
                "the asset dimensions exceed the canvas contract",
                "image_too_large",
                maximum=MAX_DIMENSION,
            )
    if width * height > max_pixels:
        raise BudgetExceeded(
            "the decoded assets would exceed the pixel budget",
            context={"resource": "asset_pixels", "limit": max_pixels, "estimated": width * height},
        )


def _decode(data: bytes, width: int, height: int) -> bytes:
    """Straight RGBA bytes; every Pillow failure becomes ``unreadable_image``."""
    try:
        with Image.open(io.BytesIO(data), formats=("PNG",)) as image:
            if image.size != (width, height) or image.mode != "RGBA":  # pragma: no cover
                # The IHDR checks above already fix both; kept against a Pillow change.
                raise _invalid("the PNG header is inconsistent", "unreadable_image")
            if getattr(image, "is_animated", False):
                raise _invalid("animated PNG assets are not supported", "multiple_frames")
            if "icc_profile" in image.info:
                raise _invalid("assets with an ICC profile are not supported", "color_profile")
            image.load()
            rgba = image.tobytes("raw", "RGBA")
    except ValidationError:
        raise
    except (
        OSError,
        ValueError,
        SyntaxError,
        EOFError,
        zlib.error,
        Image.DecompressionBombError,
    ) as exc:
        raise _invalid("the PNG asset cannot be decoded", "unreadable_image") from exc
    if len(rgba) != width * height * 4:  # pragma: no cover - Pillow guarantees the size
        raise _invalid("the PNG asset cannot be decoded", "unreadable_image")
    return rgba


@dataclass(frozen=True, slots=True)
class Asset:
    """A declared PNG asset: its ID, source bytes and decoded straight RGBA pixels.

    Build one with :meth:`from_png`. The public constructor decodes ``data`` again and
    requires ``width``, ``height`` and ``rgba`` to match it, so an ``Asset`` value is
    always consistent with the bytes that are saved.
    """

    id: str
    data: bytes
    width: int
    height: int
    rgba: bytes
    sha256: str = field(init=False, repr=False, compare=False)
    """Lower-case hexadecimal SHA-256 of the source bytes, computed once."""

    def __post_init__(self) -> None:
        decoded = Asset.from_png(self.id, self.data)
        if (decoded.width, decoded.height, decoded.rgba) != (self.width, self.height, self.rgba):
            raise _invalid("the asset pixels do not match its PNG bytes", "pixel_mismatch")
        object.__setattr__(self, "sha256", decoded.sha256)

    @classmethod
    def from_png(
        cls,
        asset_id: str,
        data: bytes,
        *,
        max_bytes: int = MAX_ASSET_BYTES,
        max_pixels: int = MAX_ASSET_PIXELS,
    ) -> Asset:
        """Verify and decode ``data``; ``ValidationError`` or ``BudgetExceeded`` otherwise.

        ``asset_id`` follows the ID grammar of documents. Encoded size and decoded
        pixels are checked against ``max_bytes`` and ``max_pixels`` before decoding.
        """
        if not is_id(asset_id):
            raise ValidationError(
                "the asset ID is not a valid identifier",
                context={"field": "id", "reason": "invalid_id"},
            )
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        if len(data) > max_bytes:
            raise BudgetExceeded(
                "the asset exceeds the byte limit",
                context={"resource": "asset_bytes", "limit": max_bytes, "estimated": len(data)},
            )
        width, height = _header(data)
        _check_size(width, height, max_pixels)
        asset = object.__new__(cls)
        rgba = _decode(data, width, height)
        for name, value in zip(
            ("id", "data", "width", "height", "rgba", "sha256"),
            (asset_id, data, width, height, rgba, hashlib.sha256(data).hexdigest()),
            strict=True,
        ):
            object.__setattr__(asset, name, value)
        return asset

    @property
    def mime(self) -> str:
        """Media type of the source bytes; always ``image/png``."""
        return PNG_MIME

    @property
    def path(self) -> str:
        """Immutable relative path under the project root, derived from the hash."""
        return asset_path(self.sha256)

    @property
    def pixels(self) -> int:
        """Decoded pixel count, charged against ``max_asset_pixels``."""
        return self.width * self.height
