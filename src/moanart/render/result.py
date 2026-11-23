"""Immutable render result and its reproduction manifest (MOANART.md sections 13-14).

:class:`RenderResult` holds the straight RGBA bytes of one frame (row-major,
``height * width * 4``) and their visual digest: SHA-256 of width and height as
``uint32`` big-endian followed by the RGBA bytes. :class:`Provenance` records what
identifies the render (document snapshot, seed, frame, versions of renderer,
estimator and procedural randomness) and never paths or timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from moanart import __version__
from moanart.core.coordinates import MAX_DIMENSION, MIN_DIMENSION, Dimensions, Point, require_int
from moanart.core.digest import visual_digest

__all__ = [
    "RENDERER_BACKEND",
    "RENDERER_VERSION",
    "Provenance",
    "RenderResult",
    "RenderWarning",
]

RENDERER_VERSION: Final = "render-v1"
"""Version of the render pipeline; changes when the same input could change pixels."""
RENDERER_BACKEND: Final = "integer"
"""The integer raster profile of MOANART.md section 14; paths add ``vector_backend``."""

_CHANNELS: Final = 4


@dataclass(frozen=True, slots=True)
class RenderWarning:
    """A located observation that did not stop the render (``code`` is stable)."""

    code: str
    message: str
    json_pointer: str


@dataclass(frozen=True, slots=True)
class Provenance:
    """Everything needed to reproduce a render, without paths or timestamps.

    ``moanart_version`` is the package version that rendered it; the lock file and
    platform are environment facts recorded by the caller, not by the engine. A
    document with paths (ADR-023) also records ``vector_backend`` (``"aggdraw-v1"``)
    and ``vector_backend_versions`` (``"aggdraw==1.4.1"``, ``"pillow==..."``): its
    pixels are reproducible only with those versions. Without paths both are empty.
    """

    document_id: str
    revision: int
    snapshot_digest: str
    schema_version: str
    seed: int
    profile: str
    frame_id: str | None
    renderer_version: str
    renderer_backend: str
    estimator_version: str
    rng_version: str
    moanart_version: str = __version__
    vector_backend: str | None = None
    vector_backend_versions: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready manifest with sorted, stable keys (tuples become lists)."""
        fields = {name: getattr(self, name) for name in self.__dataclass_fields__}
        return {
            name: list(value) if isinstance(value, tuple) else value
            for name, value in sorted(fields.items())
        }


@dataclass(frozen=True, slots=True)
class RenderResult:
    """One rendered frame: immutable RGBA bytes, digest, warnings and provenance.

    The constructor checks that ``rgba`` has ``width * height * 4`` bytes and that
    ``digest`` matches them, so a result never describes pixels other than its own.
    :func:`~moanart.render.render` builds it from a normalised canvas (zero alpha is
    ``(0, 0, 0, 0)``). ``render`` loads no NumPy type into the result: callers that
    want an array use ``numpy.frombuffer(result.rgba, numpy.uint8)``.
    """

    width: int
    height: int
    rgba: bytes
    digest: str
    warnings: tuple[RenderWarning, ...]
    renderer_version: str
    provenance: Provenance

    def __post_init__(self) -> None:
        for name in ("width", "height"):
            require_int(getattr(self, name), name, minimum=MIN_DIMENSION, maximum=MAX_DIMENSION)
        if type(self.rgba) is not bytes:
            raise TypeError("rgba must be bytes")
        if len(self.rgba) != self.width * self.height * _CHANNELS:
            raise ValueError("rgba must hold width * height * 4 bytes")
        if self.digest != visual_digest(self.width, self.height, self.rgba):
            raise ValueError("digest does not match the pixels")
        if type(self.warnings) is not tuple or not all(
            isinstance(warning, RenderWarning) for warning in self.warnings
        ):
            raise TypeError("warnings must be a tuple of RenderWarning values")
        if not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance value")
        if self.renderer_version != self.provenance.renderer_version:
            raise ValueError("renderer_version must match the provenance")

    def pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        """RGBA at ``(x, y)``; :class:`OutOfBoundsError` outside, never wrapping."""
        Dimensions(self.width, self.height).check_pixel(Point(x, y))
        start = (y * self.width + x) * _CHANNELS
        r, g, b, a = self.rgba[start : start + _CHANNELS]
        return (r, g, b, a)
