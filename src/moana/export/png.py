"""PNG export of one rendered frame: master RGBA or indexed (MOANA.md section 18, ADR-019).

Encoding happens in memory and is verified before anything touches the filesystem:
the PNG bytes are decoded again and compared with the expected pixels, so an export
that would not round-trip exactly is an :class:`ExportError`, never a file.

* **RGBA** is the master format: straight RGBA, zero alpha already normalised.
* **Indexed** writes palette mode ``P`` with every colour of a :class:`Palette` in
  declared order (index = declaration position) and an explicit ``tRNS`` alpha per
  entry. Each pixel must equal a palette value exactly (the first declared entry
  wins); there is no quantisation. At most 256 entries.
* **Scale** is an integer ``1..64`` applied by nearest neighbour (``k x k`` blocks).
  A scaled export is a preview and the manifest says so.

Pillow settings are fixed (``compress_level=9``, no ``optimize``, no text, time or
ICC chunks), so the same pixels and Pillow version give the same bytes.

The frame is any value with ``width``, ``height`` and row-major RGBA ``bytes``
``rgba``, such as :class:`moana.render.RenderResult`: ``export`` may not import
``render`` (MOANA.md section 3).
"""

from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Final, Literal, Protocol

import numpy as np
import numpy.typing as npt
from PIL import Image

from moana.core.budget import DEFAULT_RENDER_LIMITS, RenderLimits
from moana.core.coordinates import MAX_DIMENSION, MIN_DIMENSION, require_int
from moana.core.digest import visual_digest
from moana.core.errors import BudgetExceeded, ErrorDetail, ExportError, ValidationError
from moana.export.atomic import commit_bytes
from moana.palette import Palette

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

MEDIA_TYPE: Final = "image/png"
MAX_SCALE: Final = 64
MAX_INDEXED_COLORS: Final = 256
EXPORT_BYTES_PER_PIXEL: Final = 24
"""Upper bound of encoder memory per output pixel, on top of the ``4`` bytes per source
pixel of the frame: scaled RGBA, Pillow image, decoded check image and its byte copy
(``4 + 4 + 4 + 4``) plus PNG bytes (at most the raw size and a small overhead). Indexed
export instead holds, per source pixel, an ``intp`` search position (8), a ``uint32``
lookup (4), a match flag (1) and the ``uint8`` index (1), at most 14 bytes, released
before scaling. Measured peaks stay below 24 (ADR-019)."""
COMPRESS_LEVEL: Final = 9
PREVIEW_WARNING: Final = "scaled_preview"
_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"

ExportMode = Literal["rgba", "indexed"]
_Pixels = npt.NDArray[np.uint8]


class RasterFrame(Protocol):
    """A rendered frame: size and row-major straight RGBA bytes."""

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def rgba(self) -> bytes: ...


@dataclass(frozen=True, slots=True)
class EncodedPng:
    """Verified PNG bytes, not yet written anywhere."""

    data: bytes
    mode: ExportMode
    width: int
    height: int
    scale: int
    source_width: int
    source_height: int
    source_digest: str
    pixel_digest: str


@dataclass(frozen=True, slots=True)
class ExportManifest:
    """What one export wrote: path, media type, sizes, frames, hashes and warnings.

    ``source_digest`` identifies the frame's pixels (MOANA.md section 14);
    ``pixel_digest`` the decoded pixels of the file (equal to ``source_digest`` for
    a master export); ``file_sha256`` the exact bytes written.
    """

    path: str
    media_type: str
    mode: ExportMode
    width: int
    height: int
    frames: int
    scale: int
    master: bool
    source_width: int
    source_height: int
    source_digest: str
    pixel_digest: str
    file_sha256: str
    byte_size: int
    warnings: tuple[str, ...]

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready manifest with sorted keys."""
        mapping = {field.name: getattr(self, field.name) for field in fields(self)}
        mapping["warnings"] = list(self.warnings)
        return dict(sorted(mapping.items()))


def _frame_pixels(frame: RasterFrame, scale: int, limits: RenderLimits) -> _Pixels:
    width, height, rgba = frame.width, frame.height, frame.rgba
    require_int(width, "width", minimum=MIN_DIMENSION, maximum=MAX_DIMENSION)
    require_int(height, "height", minimum=MIN_DIMENSION, maximum=MAX_DIMENSION)
    if type(rgba) is not bytes:
        raise TypeError("frame.rgba must be bytes")
    if len(rgba) != width * height * 4:
        raise ValidationError(
            "frame RGBA size does not match its dimensions",
            context={"field": "rgba", "reason": "wrong_size"},
        )
    _check_budget(width, height, scale, limits)  # before any temporary is allocated
    pixels = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4)
    if not is_normalized(pixels):
        raise ValidationError(
            "frame pixels with zero alpha must be (0, 0, 0, 0)",
            context={"field": "rgba", "reason": "not_normalized"},
        )
    return pixels


def is_normalized(pixels: _Pixels) -> bool:
    """Whether every pixel of an ``(h, w, 4)`` RGBA array with zero alpha is ``(0, 0, 0, 0)``.

    Temporaries: three boolean planes of ``h * w`` bytes.
    """
    return not bool(np.any((pixels[:, :, 3] == 0) & pixels[:, :, :3].any(axis=2)))


def _check_budget(width: int, height: int, scale: int, limits: RenderLimits) -> None:
    out_width, out_height = width * scale, height * scale
    geometry = limits.geometry
    checks = (
        ("export_dimension", geometry.max_dimension, max(out_width, out_height)),
        ("export_area", geometry.max_area, out_width * out_height),
        (
            "buffer_bytes",
            limits.max_buffer_bytes,
            EXPORT_BYTES_PER_PIXEL * out_width * out_height + 4 * width * height,
        ),
    )
    details = [
        ErrorDetail(
            BudgetExceeded.code,
            f"export {resource} exceed the request budget",
            context={"resource": resource, "limit": limit, "estimated": estimated},
        )
        for resource, limit, estimated in checks
        if estimated > limit
    ]
    if details:
        raise BudgetExceeded(
            "export exceeds the request budget", context=dict(details[0].context), details=details
        )


def _palette_planes(palette: Palette) -> tuple[_Pixels, bytes, bytes]:
    """Normalised palette values (N, 4), ``PLTE`` RGB bytes and ``tRNS`` alpha bytes."""
    if not isinstance(palette, Palette):
        raise TypeError("palette must be a moana.palette.Palette")
    count = len(palette.colors)
    if count > MAX_INDEXED_COLORS:
        raise ValidationError(
            "indexed PNG supports at most 256 palette entries",
            context={
                "field": "palette",
                "reason": "too_many_colors",
                "maximum": MAX_INDEXED_COLORS,
                "count": count,
            },
        )
    values = np.array(
        [color.rgba.normalized().as_tuple() for color in palette.colors], dtype=np.uint8
    ).reshape(count, 4)
    return values, values[:, :3].tobytes(), values[:, 3].tobytes()


def palette_indices(pixels: _Pixels, values: _Pixels) -> _Pixels:
    """Index of each pixel's first equal palette value; no quantisation.

    ``pixels`` is a C-contiguous ``(h, w, 4)`` array and ``values`` an ``(N, 4)`` array
    of normalised palette values, ``1 <= N <= 256``. Shared by indexed PNG and GIF
    (ADR-034); a missing colour is ``ValidationError`` ``color_not_in_palette`` with
    the first ``x``, ``y`` and the number of unmatched ``pixels``.
    """
    keys = pixels.view(np.uint32).reshape(pixels.shape[:2])
    palette_keys = values.view(np.uint32).reshape(-1)
    order = np.argsort(palette_keys, kind="stable")  # stable: first declared entry wins
    sorted_keys = palette_keys[order]
    _, first = np.unique(sorted_keys, return_index=True)
    unique_keys = sorted_keys[first]
    position = np.searchsorted(unique_keys, keys)
    np.minimum(position, unique_keys.size - 1, out=position)
    found = unique_keys[position] == keys
    if not bool(found.all()):
        ys, xs = np.nonzero(~found)
        raise ValidationError(
            "pixel colour is not in the palette (indexed export never quantises)",
            context={
                "field": "palette",
                "reason": "color_not_in_palette",
                "x": int(xs[0]),
                "y": int(ys[0]),
                "pixels": int(ys.size),
            },
        )
    del found
    return order[first].astype(np.uint8)[position]


def _scaled(array: _Pixels, scale: int) -> _Pixels:
    if scale == 1:
        return array
    return np.ascontiguousarray(np.repeat(np.repeat(array, scale, axis=0), scale, axis=1))


def _encode_image(image: Image.Image, **options: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=COMPRESS_LEVEL, optimize=False, **options)
    return buffer.getvalue()


def _chunk(data: bytes, kind: bytes) -> bytes | None:
    """Payload of the first ``kind`` chunk of a PNG produced by ``_encode_image``."""
    offset = len(_PNG_SIGNATURE)
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        if data[offset + 4 : offset + 8] == kind:
            return data[offset + 8 : offset + 8 + length]
        offset += 12 + length
    return None


def _check_palette_chunks(data: bytes, rgb: bytes, alpha: bytes) -> None:
    """The file keeps every declared entry, in order, with its explicit alpha."""
    if _chunk(data, b"PLTE") != rgb or _chunk(data, b"tRNS") != alpha:
        raise ExportError(
            "encoded PNG palette does not match the declared palette",
            context={"reason": "palette_mismatch"},
        )


def _decode_rgba(data: bytes) -> _Pixels:
    with Image.open(io.BytesIO(data)) as decoded:
        decoded.load()
        rgba = decoded.convert("RGBA") if decoded.mode != "RGBA" else decoded
        height, width = decoded.height, decoded.width
        return np.frombuffer(rgba.tobytes("raw", "RGBA"), dtype=np.uint8).reshape(height, width, 4)


def encode_png(
    frame: RasterFrame,
    *,
    scale: int = 1,
    mode: ExportMode = "rgba",
    palette: Palette | None = None,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> EncodedPng:
    """Encode ``frame`` as PNG in memory and verify it decodes to the expected pixels.

    Raises ``ValidationError`` (invalid frame, options, palette size, colour outside
    the palette), ``BudgetExceeded`` (scaled size or memory, before any buffer) or
    ``ExportError`` (the encoder did not round-trip).
    """
    require_int(scale, "scale", minimum=1, maximum=MAX_SCALE)
    if mode not in ("rgba", "indexed"):
        raise ValidationError(
            "mode must be rgba or indexed", context={"field": "mode", "reason": "unknown_mode"}
        )
    if mode == "indexed" and palette is None:
        raise ValidationError(
            "indexed export needs a palette",
            context={"field": "palette", "reason": "missing_palette"},
        )
    if mode == "rgba" and palette is not None:
        raise ValidationError(
            "a palette only applies to indexed export",
            context={"field": "palette", "reason": "unexpected_palette"},
        )
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    pixels = _frame_pixels(frame, scale, limits)
    height, width = pixels.shape[:2]
    expected = _scaled(pixels, scale)
    out_height, out_width = expected.shape[:2]
    if mode == "rgba":
        image = Image.frombytes("RGBA", (out_width, out_height), expected.tobytes())
        data = _encode_image(image)
    else:
        assert palette is not None  # checked above
        values, rgb, alpha = _palette_planes(palette)
        indices = _scaled(palette_indices(pixels, values), scale)
        image = Image.frombytes("P", (out_width, out_height), indices.tobytes())
        image.putpalette(rgb, "RGB")
        data = _encode_image(image, transparency=alpha)
        _check_palette_chunks(data, rgb, alpha)
    del image
    decoded = _decode_rgba(data)
    if decoded.shape != expected.shape or not np.array_equal(decoded, expected):
        raise ExportError(
            "encoded PNG does not decode to the frame pixels",
            context={"reason": "roundtrip_mismatch"},
        )
    return EncodedPng(
        data=data,
        mode=mode,
        width=out_width,
        height=out_height,
        scale=scale,
        source_width=width,
        source_height=height,
        source_digest=visual_digest(width, height, pixels.tobytes()),
        pixel_digest=visual_digest(out_width, out_height, decoded.tobytes()),
    )


def _representable(raw: str) -> bool:
    """Whether the OS can name ``raw``: no NUL and encodable with the filesystem codec."""
    if "\x00" in raw:
        return False
    try:
        os.fsencode(raw)
    except UnicodeEncodeError:
        return False
    return True


def destination_path(path: object, *, field: str = "path", suffix: str = ".png") -> Path:
    """A caller-chosen export path: text, representable and ending in ``suffix``.

    ``TypeError`` for a non-path or a bytes path; ``ValidationError`` ``invalid_name``
    or ``wrong_extension`` (a bare ``.png`` has no suffix) with ``field``.
    """
    if not isinstance(path, str | os.PathLike):
        raise TypeError(f"{field} must be a str or os.PathLike")
    raw = os.fspath(path)
    if not isinstance(raw, str):
        raise TypeError(f"{field} must be text, not bytes")
    if not _representable(raw):
        raise ValidationError(
            "the export path is not representable on this system",
            context={"field": field, "reason": "invalid_name"},
        )
    destination = Path(raw)
    if destination.suffix.lower() != suffix:
        raise ValidationError(
            f"this export must use the {suffix} extension",
            context={"field": field, "reason": "wrong_extension"},
        )
    return destination


def export_png(
    frame: RasterFrame,
    path: str | os.PathLike[str],
    *,
    scale: int = 1,
    overwrite: bool = False,
    mode: ExportMode = "rgba",
    palette: Palette | None = None,
    limits: RenderLimits = DEFAULT_RENDER_LIMITS,
) -> ExportManifest:
    """Encode, verify and atomically write ``frame`` to ``path`` (host-authorised).

    With ``overwrite=False`` (default) an existing file is never replaced, even by a
    concurrent writer; see :mod:`moana.export.atomic`. Returns the manifest only
    after the file is committed.
    """
    destination = destination_path(path)
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be a bool")
    encoded = encode_png(frame, scale=scale, mode=mode, palette=palette, limits=limits)
    commit_bytes(encoded.data, destination, overwrite=overwrite)
    return ExportManifest(
        path=os.fspath(destination),
        media_type=MEDIA_TYPE,
        mode=encoded.mode,
        width=encoded.width,
        height=encoded.height,
        frames=1,
        scale=encoded.scale,
        master=encoded.scale == 1,
        source_width=encoded.source_width,
        source_height=encoded.source_height,
        source_digest=encoded.source_digest,
        pixel_digest=encoded.pixel_digest,
        file_sha256="sha256:" + hashlib.sha256(encoded.data).hexdigest(),
        byte_size=len(encoded.data),
        warnings=(PREVIEW_WARNING,) if encoded.scale > 1 else (),
    )
