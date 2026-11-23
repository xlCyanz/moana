"""Runtime codec capabilities of the export formats (MOANART.md section 18, ADR-035).

A format is available only when this Pillow build has its codec *and* a tiny
in-memory roundtrip of that format succeeds here: a feature flag alone is not proof
of support. Nothing is cached and nothing is substituted: :func:`export_capabilities`
probes on every call (a few 1 x 1 or 2 x 1 images, well under a millisecond each),
and an exporter whose codec is missing raises :class:`UnsupportedOperation` before it
reads a pixel or touches the destination, never falling back to another format.

* ``png`` and ``apng``: Pillow's PNG plugin over ``zlib`` (``features`` codec
  ``zlib``); the APNG probe writes and reads a two-frame animation with partial alpha.
* ``gif``: Pillow's built-in LZW encoder and GIF decoder (no separate library; the
  reported version is Pillow's).
* ``webp``: the ``libwebp`` module (``features.check_module("webp")``) and a two-frame
  lossless animated roundtrip with partial alpha and a loop count. Pillow 13 removed
  the ``webp_anim`` flag, so animation support is proved by the probe itself.

Bytes produced through a codec depend on its version: the same frames and options
give the same file only with the same Pillow and codec versions, which is why every
report records them.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Final, Literal

import PIL
from PIL import Image, features

from moanart.core.errors import UnsupportedOperation, ValidationError

__all__ = [
    "EXPORT_FORMATS",
    "WEBP_ENCODER_OPTIONS",
    "CodecStatus",
    "ExportCapabilities",
    "ExportFormat",
    "codec_status",
    "export_capabilities",
    "require_codec",
]

ExportFormat = Literal["png", "gif", "apng", "webp"]
CodecReason = Literal["missing", "roundtrip_failed"]

EXPORT_FORMATS: Final[tuple[ExportFormat, ...]] = ("png", "gif", "apng", "webp")
WEBP_ENCODER_OPTIONS: Final[dict[str, object]] = {
    "lossless": True,
    "quality": 75,
    "method": 4,
    "alpha_quality": 100,
    "minimize_size": False,
    "allow_mixed": False,
    "kmin": 9,
    "kmax": 17,
    "exact": True,
    "background": (0, 0, 0, 0),
}
"""The fixed ``libwebp`` options of ``moanart.export.animated`` (lossless only); the WebP
probe uses exactly these, so a build that cannot honour them is reported unavailable."""


@dataclass(frozen=True, slots=True)
class _Format:
    media_type: str
    extension: str
    codec: str
    lossless: bool


_FORMATS: Final[dict[str, _Format]] = {
    "png": _Format("image/png", ".png", "zlib", lossless=True),
    "gif": _Format("image/gif", ".gif", "pillow-lzw", lossless=False),
    "apng": _Format("image/apng", ".png", "zlib", lossless=True),
    "webp": _Format("image/webp", ".webp", "libwebp", lossless=True),
}
_PARTIAL: Final = (255, 0, 0, 128)
_OPAQUE: Final = (1, 2, 3, 255)


@dataclass(frozen=True, slots=True)
class CodecStatus:
    """One export format in this build.

    ``reason`` is ``None`` when available, ``"missing"`` when Pillow lacks the codec
    and ``"roundtrip_failed"`` when the codec exists but the probe did not round-trip.
    ``lossless`` says whether the format can keep any RGBA frame exactly (GIF cannot:
    its losses are explicit, ADR-034). ``codec_version`` is ``None`` when unknown.
    """

    format: ExportFormat
    media_type: str
    extension: str
    codec: str
    codec_version: str | None
    pillow_version: str
    lossless: bool
    available: bool
    reason: CodecReason | None

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready entry with sorted keys."""
        return dict(sorted((field.name, getattr(self, field.name)) for field in fields(self)))


@dataclass(frozen=True, slots=True)
class ExportCapabilities:
    """The capability matrix of this build, one :class:`CodecStatus` per format."""

    pillow_version: str
    formats: tuple[CodecStatus, ...]

    def status(self, name: ExportFormat) -> CodecStatus:
        """The entry of ``name`` (``KeyError`` for an unknown format)."""
        for entry in self.formats:
            if entry.format == name:
                return entry
        raise KeyError(name)

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready matrix: ``formats`` in :data:`EXPORT_FORMATS` order."""
        return {
            "formats": [entry.to_mapping() for entry in self.formats],
            "pillow_version": self.pillow_version,
        }


# --- probes ----------------------------------------------------------------------------


def _image(*pixels: tuple[int, int, int, int]) -> Image.Image:
    return Image.frombytes("RGBA", (len(pixels), 1), bytes(c for pixel in pixels for c in pixel))


def _frames_of(data: bytes, kind: str) -> tuple[list[bytes], object]:
    """Composited RGBA bytes of every decoded frame and the decoded loop value."""
    decoded: list[bytes] = []
    with Image.open(io.BytesIO(data), formats=(kind,)) as image:
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            decoded.append(image.convert("RGBA").tobytes())
        return decoded, image.info.get("loop")


def _probe_png() -> bool:
    buffer = io.BytesIO()
    _image(_PARTIAL, _OPAQUE).save(buffer, format="PNG")
    frames, _ = _frames_of(buffer.getvalue(), "PNG")
    return frames == [_image(_PARTIAL, _OPAQUE).tobytes()]


def _probe_gif() -> bool:
    image = Image.frombytes("P", (2, 1), b"\x00\x01")
    image.putpalette(bytes((*_OPAQUE[:3], *_PARTIAL[:3])), "RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="GIF")
    frames, _ = _frames_of(buffer.getvalue(), "GIF")
    return frames == [bytes((*_OPAQUE, 255, 0, 0, 255))]


def _probe_animation(kind: str, **options: object) -> bool:
    first, second = _image(_PARTIAL, _OPAQUE), _image(_OPAQUE, _PARTIAL)
    buffer = io.BytesIO()
    first.save(
        buffer, format=kind, save_all=True, append_images=[second], duration=[10, 20], loop=3,
        **options,
    )  # fmt: skip
    frames, loop = _frames_of(buffer.getvalue(), kind)
    return frames == [first.tobytes(), second.tobytes()] and loop == 3


def _probe_apng() -> bool:
    return _probe_animation("PNG")


def _probe_webp() -> bool:
    return _probe_animation("WEBP", **WEBP_ENCODER_OPTIONS)


_PROBES: Final[dict[str, tuple[Callable[[], bool], Callable[[], bool]]]] = {
    "png": (lambda: bool(features.check_codec("zlib")), _probe_png),
    "gif": (lambda: True, _probe_gif),
    "apng": (lambda: bool(features.check_codec("zlib")), _probe_apng),
    "webp": (lambda: bool(features.check_module("webp")), _probe_webp),
}


def _codec_version(name: str) -> str | None:
    """The codec's version as Pillow reports it; ``None`` if the query itself fails."""
    try:
        if name == "zlib":
            return features.version_codec("zlib")
        if name == "libwebp":
            return features.version_module("webp")
        return PIL.__version__
    except Exception:  # a broken build reports no version, never crashes
        return None


def _present(check: Callable[[], bool]) -> bool:
    """Whether Pillow has the codec; a feature query that raises counts as missing."""
    try:
        return bool(check())
    except Exception:  # e.g. ImportError of a broken plugin module
        return False


def _roundtrips(probe: Callable[[], bool]) -> bool:
    """Run one isolated probe: any exception from Pillow or the codec is a failed probe.

    Catching everything is deliberate: the probe only touches 2-pixel images built
    here, and a capability report must describe a broken codec, not crash with it.
    """
    try:
        return bool(probe())
    except Exception:  # isolated probe: any failure is roundtrip_failed
        return False


def codec_status(name: ExportFormat) -> CodecStatus:
    """Probe one format now (``ValidationError`` ``unknown_format`` for another name).

    Never raises for a broken codec: a feature query that fails is ``missing``, a probe
    that fails or raises is ``roundtrip_failed`` and an unreadable version is ``None``.
    """
    if type(name) is not str or name not in _FORMATS:
        raise ValidationError(
            "unknown export format", context={"field": "name", "reason": "unknown_format"}
        )
    spec = _FORMATS[name]
    present, probe = _PROBES[name]
    reason: CodecReason | None = None
    if not _present(present):
        reason = "missing"
    elif not _roundtrips(probe):
        reason = "roundtrip_failed"
    return CodecStatus(
        format=name,
        media_type=spec.media_type,
        extension=spec.extension,
        codec=spec.codec,
        codec_version=_codec_version(spec.codec) if reason != "missing" else None,
        pillow_version=PIL.__version__,
        lossless=spec.lossless,
        available=reason is None,
        reason=reason,
    )


def export_capabilities() -> ExportCapabilities:
    """Probe every export format of this build (nothing is cached)."""
    return ExportCapabilities(
        pillow_version=PIL.__version__,
        formats=tuple(codec_status(name) for name in EXPORT_FORMATS),
    )


def require_codec(name: ExportFormat) -> CodecStatus:
    """The status of an available format, else ``UnsupportedOperation`` ``codec_unavailable``.

    The error carries ``format``, ``codec``, ``cause`` (``missing`` or
    ``roundtrip_failed``) and ``pillow_version``; never a path or an input value.
    """
    status = codec_status(name)
    if not status.available:
        raise UnsupportedOperation(
            f"{name} export is not available in this build (no fallback format is used)",
            context={
                "reason": "codec_unavailable",
                "format": name,
                "codec": status.codec,
                "cause": status.reason,
                "pillow_version": status.pillow_version,
            },
        )
    return status
