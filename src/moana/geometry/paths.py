"""AggDraw adapter of fixed-point paths, backend ``aggdraw-v1`` (MOANA.md section 6, ADR-023).

A :class:`~moana.core.vector_path.FixedPath` (validated and flattened with integers
in ``core``) becomes a binary :class:`Mask`:

1. The storage box is the path's pixel box clipped to the canvas; an empty box
   returns an empty mask without touching the backend.
2. AggDraw fills the flattened outline with antialiasing into a private 8-bit
   coverage buffer of that box plus a 1-pixel margin, at native scale (one
   coverage sample per pixel). Coordinates are passed as exact ``v / 256`` floats,
   which AGG stores on its own 1/256 subpixel grid without rounding. AGG clips every
   segment to the buffer, so the work depends on the buffer, not on how far the
   path extends outside the canvas.
3. **Fill rule: nonzero winding** (AGG's default, the one AggDraw uses). Subpaths
   are closed implicitly; overlapping subpaths with the same orientation stay
   filled and an inner subpath with the opposite orientation makes a hole.
4. Coverage ``>= 128`` becomes a pixel of the mask, cut to the path's storage box;
   anything else is outside. The cut, not the backend, keeps pixels outside the box
   out of the mask; since the box belongs to the whole path, the cut is not local
   (see :attr:`~moana.core.vector_path.FixedPath.bounds`). No colour or alpha of
   the coverage survives: the operation paints its palette colour through the mask
   like every other primitive.

AggDraw 1.4.1 grows every subpath by about 1/4 pixel along its orientation, with
spikes of up to about 1 pixel at sharp angles, and the coverage of overlapping
subpaths accumulates with their winding (ADR-023). The only pixel-level promise is
therefore narrow: for a single simple subpath (no self-intersection, no holes), a
pixel whose square lies fully inside the outline is in the mask. Holes, walls one
pixel thick between holes, regions of winding -1 reached through a shared vertex,
thin slivers and stacked copies are the backend's: reproducible only on the tested
versions and platforms, and never the integer raster of ``polygon``.

Nothing of AggDraw or Pillow crosses this module: ``aggdraw`` is imported lazily
when a path is rasterised or the backend is probed, and its objects never escape.
:func:`path_backend` reports whether the backend is importable and tested; when it
is not, rasterising raises :class:`UnsupportedOperation`.
"""

from __future__ import annotations

import importlib
import importlib.metadata
from dataclasses import dataclass
from typing import Final, Protocol, cast

import numpy as np

from moana.core.coordinates import Box, Dimensions
from moana.core.errors import BudgetExceeded, MoanaError, UnsupportedOperation
from moana.core.limits import MAX_PATH_CELLS
from moana.core.vector_path import (
    PATH_BUFFER_MARGIN,
    PATH_UNITS,
    FixedPath,
    path_buffer_box,
)
from moana.geometry.mask import Mask

__all__ = [
    "AGGDRAW_BACKEND",
    "COVERAGE_THRESHOLD",
    "PATH_BUFFER_MARGIN",
    "TESTED_AGGDRAW_VERSIONS",
    "PathBackend",
    "backend_unavailable_error",
    "path_backend",
    "path_buffer_box",
    "path_mask_box",
    "rasterize_path",
]

AGGDRAW_BACKEND: Final = "aggdraw-v1"
"""Contract label of the path backend recorded in capabilities and provenance."""
TESTED_AGGDRAW_VERSIONS: Final = ("1.4.1",)
"""AggDraw versions whose output the tests of ADR-023 have exercised."""
COVERAGE_THRESHOLD: Final = 128
"""Coverage (0..255) from which a pixel belongs to the mask."""

_MODULE: Final = "aggdraw"
_PILLOW_DISTRIBUTION: Final = "pillow"
_REQUIRED: Final = ("Draw", "Path", "Brush")
_FULL: Final = 255


class _AggPath(Protocol):
    def moveto(self, x: float, y: float, /) -> None: ...
    def lineto(self, x: float, y: float, /) -> None: ...
    def close(self) -> None: ...


class _AggDraw(Protocol):
    def path(self, path: _AggPath, brush: object, /) -> None: ...
    def flush(self) -> None: ...
    def tobytes(self) -> bytes: ...


class _AggModule(Protocol):
    """The part of ``aggdraw`` this adapter uses (the package ships no stubs)."""

    def Draw(self, mode: str, size: tuple[int, int], color: int, /) -> _AggDraw: ...
    def Path(self) -> _AggPath: ...
    def Brush(self, color: int, /) -> object: ...


@dataclass(frozen=True, slots=True)
class PathBackend:
    """Availability of the path backend in this environment.

    ``reason`` is ``None`` when available, ``"missing"`` when ``aggdraw`` is not
    installed, ``"import_failed"`` when importing it raises anything else,
    ``"incompatible"`` when it lacks ``Draw``, ``Path`` or ``Brush`` and
    ``"untested_version"`` when its version is not in :data:`TESTED_AGGDRAW_VERSIONS`.
    ``version`` is the imported AggDraw version and ``pillow_version`` the installed
    Pillow distribution (AggDraw loads Pillow on import), when known.
    """

    name: str
    available: bool
    version: str | None
    reason: str | None
    pillow_version: str | None = None


def _version(module: object) -> str | None:
    for name in ("VERSION", "__version__"):
        value = getattr(module, name, None)
        if isinstance(value, str):
            return value
    return None


def _pillow_version() -> str | None:
    try:
        return importlib.metadata.version(_PILLOW_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError:
        return None


def _load() -> tuple[_AggModule | None, PathBackend]:
    try:
        module = cast("_AggModule", importlib.import_module(_MODULE))
    except ImportError:
        return None, PathBackend(AGGDRAW_BACKEND, False, None, "missing")
    except Exception:  # a broken native build may raise anything on import
        return None, PathBackend(AGGDRAW_BACKEND, False, None, "import_failed")
    version = _version(module)
    pillow = _pillow_version()
    if not all(callable(getattr(module, name, None)) for name in _REQUIRED):
        return None, PathBackend(AGGDRAW_BACKEND, False, version, "incompatible", pillow)
    if version not in TESTED_AGGDRAW_VERSIONS:
        status = PathBackend(AGGDRAW_BACKEND, False, version, "untested_version", pillow)
        return None, status
    return module, PathBackend(AGGDRAW_BACKEND, True, version, None, pillow)


def path_backend() -> PathBackend:
    """Probe the backend: importable and of a tested version (nothing is cached)."""
    return _load()[1]


def backend_unavailable_error(
    status: PathBackend, *, json_pointer: str | None = None
) -> UnsupportedOperation:
    """The one error of an unusable backend, shared by the adapter and the renderer."""
    context: dict[str, object] = {
        "reason": "backend_unavailable",
        "backend": status.name,
        "cause": status.reason,
        "tested_versions": TESTED_AGGDRAW_VERSIONS,
    }
    if status.version is not None:
        context["version"] = status.version
    return UnsupportedOperation(
        "path backend is not available in this build", json_pointer=json_pointer, context=context
    )


def path_mask_box(path: FixedPath, dimensions: Dimensions) -> Box | None:
    """Storage box of the path's mask: its pixel box clipped to the canvas."""
    bounds = path.bounds
    return None if bounds is None else bounds.clip_to(dimensions)


def _check_cells(path: FixedPath, box: Box) -> None:
    cells = path.cell_bound(path_buffer_box(box))
    if cells > MAX_PATH_CELLS:
        raise BudgetExceeded(
            "path needs more coverage cells than the backend holds",
            context={"resource": "path_cells", "limit": MAX_PATH_CELLS, "estimated": cells},
        )


def _coverage(module: _AggModule, path: FixedPath, box: Box) -> bytes:
    """8-bit coverage of the buffer of ``box``, row-major; backend failures wrapped."""
    try:
        return _draw(module, path, box)
    except (ValueError, MemoryError, OSError) as error:
        context = {"reason": "backend_failure", "backend": AGGDRAW_BACKEND}
        context["cause"] = type(error).__name__
        raise MoanaError("path backend failed to draw the path", context=context) from None


def _draw(module: _AggModule, path: FixedPath, box: Box) -> bytes:
    """The backend call: fill the outline into the buffer of ``box``."""
    buffer = path_buffer_box(box)
    width, height = buffer.width, buffer.height
    origin_x = (box.x0 - PATH_BUFFER_MARGIN) * PATH_UNITS
    origin_y = (box.y0 - PATH_BUFFER_MARGIN) * PATH_UNITS
    outline = module.Path()
    first = True
    for starts, (x, y) in path.outline():
        u, v = (x - origin_x) / PATH_UNITS, (y - origin_y) / PATH_UNITS  # exact dyadics
        if starts:
            if not first:
                outline.close()
            outline.moveto(u, v)
            first = False
        else:
            outline.lineto(u, v)
    outline.close()
    draw = module.Draw("L", (width, height), 0)
    draw.path(outline, module.Brush(_FULL))
    draw.flush()
    return bytes(draw.tobytes())


def rasterize_path(path: FixedPath, dimensions: Dimensions) -> Mask:
    """Binary mask of the nonzero fill of ``path`` (coverage ``>= 128``), clipped.

    Raises :class:`UnsupportedOperation` (``backend_unavailable``) when the backend
    is missing or untested and :class:`BudgetExceeded` (``path_cells``) when the
    path could overflow the backend's cell storage; both before drawing.
    """
    if not isinstance(path, FixedPath):
        raise TypeError("path must be a FixedPath value")
    if not isinstance(dimensions, Dimensions):
        raise TypeError("dimensions must be a Dimensions value")
    module, status = _load()
    if module is None:
        raise backend_unavailable_error(status)
    box = path_mask_box(path, dimensions)
    if box is None:
        return Mask.empty()
    _check_cells(path, box)
    buffer = path_buffer_box(box)
    width, height = buffer.width, buffer.height
    coverage = np.frombuffer(_coverage(module, path, box), dtype=np.uint8)
    inner = coverage.reshape(height, width)[
        PATH_BUFFER_MARGIN : height - PATH_BUFFER_MARGIN,
        PATH_BUFFER_MARGIN : width - PATH_BUFFER_MARGIN,
    ]
    return Mask._adopt(box, np.ascontiguousarray(inner >= COVERAGE_THRESHOLD))
