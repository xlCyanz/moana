"""Exact visual regression harness for tests (MOANA.md section 21, MOANA-028).

Goldens are compared on decoded pixels, never on compressed PNG bytes: dimensions and
straight RGBA must match exactly, after normalising every zero-alpha pixel to
``(0, 0, 0, 0)`` (section 5). There is no perceptual tolerance.

On a mismatch :func:`assert_matches_golden` writes ``expected.png``, ``actual.png``,
``diff.png`` and ``manifest.json`` into ``<artifacts>/<name>/`` and raises
:class:`VisualMismatch`. The baseline is only rewritten when an update is requested
explicitly (``MOANA_UPDATE_GOLDENS=1`` or ``update=True``), and never while ``CI`` is
set: the CI guard runs immediately before every baseline write. See
``tests/visual/README.md`` for the review procedure.

This is test tooling, not part of the ``moana`` package.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt
import PIL
from PIL import Image

from moana.core import Dimensions, RenderLimits
from moana.core.canvas import Canvas, check_canvas_budget
from moana.core.pillow_adapter import canvas_from_pillow

__all__ = [
    "ARTIFACTS_ENV",
    "DIFF_ADDED",
    "DIFF_CHANGED",
    "GOLDENS_DIR",
    "MANIFEST_FORMAT",
    "ROOT",
    "UPDATE_ENV",
    "BBox",
    "Comparison",
    "VisualMismatch",
    "assert_matches_golden",
    "ci_active",
    "clear_diagnostics",
    "compare_rgba",
    "default_artifacts_dir",
    "default_name",
    "diff_rgba",
    "load_png",
    "normalize_rgba",
    "update_requested",
    "visual_digest",
    "write_diagnostics",
    "write_png",
]

ROOT: Final = Path(__file__).resolve().parents[2]
GOLDENS_DIR: Final = Path(__file__).resolve().parent / "goldens"
UPDATE_ENV: Final = "MOANA_UPDATE_GOLDENS"
ARTIFACTS_ENV: Final = "MOANA_VISUAL_ARTIFACTS"
MANIFEST_FORMAT: Final = "moana-visual-diff/1"

DIFF_CHANGED: Final = (255, 0, 255, 255)
"""Opaque magenta: pixel present in both images with different RGBA."""
DIFF_ADDED: Final = (0, 255, 255, 255)
"""Opaque cyan: pixel present in only one image (dimension mismatch)."""
_UNCHANGED_MIN: Final = 16
_UNCHANGED_MAX: Final = 96
"""Unchanged pixels are opaque grey in ``[16, 96]`` from the expected luma: never black
(reserved for the corner outside both images) and never as bright as the markers."""

_SAFE_NAME: Final = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_. -]{0,99}")
_UNSAFE_CHARS: Final = re.compile(r"[^A-Za-z0-9_. -]")
_DIAGNOSTIC_FILES: Final = ("expected.png", "actual.png", "diff.png", "manifest.json")
_CI_FALSE: Final = frozenset({"", "0", "false"})

RGBAArray = npt.NDArray[np.uint8]


class VisualMismatch(AssertionError):
    """A golden comparison failed; ``manifest`` is the diagnostics manifest path."""

    def __init__(self, message: str, manifest: Path) -> None:
        super().__init__(f"{message}; diagnostics: {manifest}")
        self.manifest = manifest


@dataclass(frozen=True, slots=True)
class BBox:
    """Half-open pixel box ``[x0, x1) x [y0, y1)``."""

    x0: int
    y0: int
    x1: int
    y1: int

    def as_dict(self) -> dict[str, int]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass(frozen=True, slots=True)
class Comparison:
    """Result of an exact comparison; sizes are ``(width, height)``.

    With different dimensions both images are anchored at the top-left corner and
    compared over the union of their areas. ``changed_pixels`` are covered by both
    images with different RGBA; ``only_in_one_pixels`` are covered by exactly one.
    """

    expected_size: tuple[int, int]
    actual_size: tuple[int, int]
    expected_digest: str
    actual_digest: str
    changed_pixels: int
    only_in_one_pixels: int
    bbox: BBox | None

    @property
    def differing_pixels(self) -> int:
        return self.changed_pixels + self.only_in_one_pixels

    @property
    def dimensions_match(self) -> bool:
        return self.expected_size == self.actual_size

    @property
    def matches(self) -> bool:
        return self.dimensions_match and self.differing_pixels == 0


def _check_budget(width: int, height: int) -> None:
    """Canvas budget (ADR-012) before any buffer derived from these sizes is reserved."""
    check_canvas_budget(Dimensions(width, height), RenderLimits())


def _require_rgba(array: object, name: str) -> RGBAArray:
    if type(array) is not np.ndarray or array.dtype != np.uint8:
        raise TypeError(f"{name} must be a uint8 NumPy array")
    if array.ndim != 3 or array.shape[2] != 4 or array.shape[0] < 1 or array.shape[1] < 1:
        raise ValueError(f"{name} must have shape (height, width, 4) with positive sizes")
    _check_budget(int(array.shape[1]), int(array.shape[0]))
    return array


def _as_rgba(image: Canvas | RGBAArray, name: str) -> RGBAArray:
    return image.to_array() if isinstance(image, Canvas) else _require_rgba(image, name)


def _size(array: RGBAArray) -> tuple[int, int]:
    return int(array.shape[1]), int(array.shape[0])


def normalize_rgba(array: RGBAArray) -> RGBAArray:
    """A C-contiguous copy where every zero-alpha pixel is ``(0, 0, 0, 0)``."""
    pixels = np.array(_require_rgba(array, "array"), dtype=np.uint8, order="C", copy=True)
    pixels[pixels[:, :, 3] == 0] = 0
    return pixels


def visual_digest(array: RGBAArray) -> str:
    """``sha256:<hex>`` of width, height (uint32 big-endian) and normalised RGBA rows."""
    pixels = normalize_rgba(array)
    width, height = _size(pixels)
    digest = hashlib.sha256(width.to_bytes(4, "big") + height.to_bytes(4, "big"))
    digest.update(pixels.tobytes(order="C"))
    return "sha256:" + digest.hexdigest()


def _masks(
    expected: RGBAArray, actual: RGBAArray
) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_]]:
    """``(changed, only_one)`` masks over the union canvas; inputs already normalised.

    ``changed``: covered by both images with different RGBA. ``only_one``: covered by
    exactly one image. The corner covered by neither image is in no mask.
    """
    (ew, eh), (aw, ah) = _size(expected), _size(actual)
    width, height = max(ew, aw), max(eh, ah)
    _check_budget(width, height)
    cw, ch = min(ew, aw), min(eh, ah)
    covered_expected = np.zeros((height, width), dtype=np.bool_)
    covered_expected[:eh, :ew] = True
    covered_actual = np.zeros((height, width), dtype=np.bool_)
    covered_actual[:ah, :aw] = True
    changed = np.zeros((height, width), dtype=np.bool_)
    changed[:ch, :cw] = np.any(expected[:ch, :cw] != actual[:ch, :cw], axis=2)
    return changed, covered_expected ^ covered_actual


def compare_rgba(expected: Canvas | RGBAArray, actual: Canvas | RGBAArray) -> Comparison:
    """Exact comparison of dimensions and normalised RGBA."""
    left = normalize_rgba(_as_rgba(expected, "expected"))
    right = normalize_rgba(_as_rgba(actual, "actual"))
    changed, only_one = _masks(left, right)
    ys, xs = np.nonzero(changed | only_one)
    changed_count = int(np.count_nonzero(changed))
    bbox = (
        BBox(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        if xs.size
        else None
    )
    return Comparison(
        expected_size=_size(left),
        actual_size=_size(right),
        expected_digest=visual_digest(left),
        actual_digest=visual_digest(right),
        changed_pixels=changed_count,
        only_in_one_pixels=int(xs.size) - changed_count,
        bbox=bbox,
    )


def diff_rgba(expected: Canvas | RGBAArray, actual: Canvas | RGBAArray) -> RGBAArray:
    """Opaque diagnostic image over the union canvas.

    Unchanged pixels: grey ``16..96`` from the expected luma. Changed pixels:
    :data:`DIFF_CHANGED`. Pixels present in only one image: :data:`DIFF_ADDED`.
    Pixels covered by neither image (dimension mismatch corner): opaque black.
    """
    left = normalize_rgba(_as_rgba(expected, "expected"))
    right = normalize_rgba(_as_rgba(actual, "actual"))
    changed, only_one = _masks(left, right)
    (ew, eh), (aw, ah) = _size(left), _size(right)
    cw, ch = min(ew, aw), min(eh, ah)
    out = np.zeros((*changed.shape, 4), dtype=np.uint8)
    out[:, :, 3] = 255
    rgb = left[:ch, :cw, :3].astype(np.uint32)
    alpha = left[:ch, :cw, 3].astype(np.uint32)
    luma = (rgb[:, :, 0] * 299 + rgb[:, :, 1] * 587 + rgb[:, :, 2] * 114) // 1000
    span = _UNCHANGED_MAX - _UNCHANGED_MIN
    grey = (_UNCHANGED_MIN + luma * alpha // 255 * span // 255).astype(np.uint8)
    out[:ch, :cw, 0] = grey
    out[:ch, :cw, 1] = grey
    out[:ch, :cw, 2] = grey
    out[only_one] = DIFF_ADDED
    out[changed] = DIFF_CHANGED
    return out


def load_png(path: Path) -> RGBAArray:
    """Decode an RGBA single-frame PNG through the canvas budget checks."""
    with Image.open(path, formats=["PNG"]) as image:
        canvas = canvas_from_pillow(image, limits=RenderLimits())
    return canvas.to_array()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".tmp-", suffix=path.suffix, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temporary, 0o644)  # mkstemp creates 0600; goldens are shared files
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _png_bytes(array: RGBAArray) -> bytes:
    pixels = np.ascontiguousarray(_require_rgba(array, "array"))
    image = Image.frombytes("RGBA", _size(pixels), pixels.tobytes(order="C"))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def write_png(array: RGBAArray, path: Path) -> None:
    """Encode ``array`` as RGBA PNG (no metadata) and replace ``path`` atomically."""
    _atomic_write(path, _png_bytes(array))


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pillow": PIL.__version__,
    }


def _check_name(name: str) -> str:
    if not _SAFE_NAME.fullmatch(name) or ".." in name:
        raise ValueError(f"unsafe diagnostics name: {name!r}")
    return name


def clear_diagnostics(directory: Path) -> None:
    """Remove the harness files of a previous run from ``directory`` (nothing else)."""
    for name in _DIAGNOSTIC_FILES:
        (directory / name).unlink(missing_ok=True)


def write_diagnostics(
    comparison: Comparison,
    expected: RGBAArray | None,
    actual: RGBAArray,
    directory: Path,
    *,
    golden: Path,
    source: str | None = None,
) -> Path:
    """Write expected/actual/diff PNG and ``manifest.json``; return the manifest path.

    Files of a previous run are removed first. ``expected`` is ``None`` when the
    baseline does not exist; then only ``actual.png`` is written. Paths inside the
    manifest are relative to it. ``source`` records the provenance of ``actual``.
    """
    directory.mkdir(parents=True, exist_ok=True)
    clear_diagnostics(directory)
    files: dict[str, str | None] = {"expected": None, "actual": "actual.png", "diff": None}
    write_png(normalize_rgba(actual), directory / "actual.png")
    if expected is not None:
        write_png(normalize_rgba(expected), directory / "expected.png")
        write_png(diff_rgba(expected, actual), directory / "diff.png")
        files["expected"] = "expected.png"
        files["diff"] = "diff.png"
    expected_info = (
        None
        if expected is None
        else {
            "width": comparison.expected_size[0],
            "height": comparison.expected_size[1],
            "digest": comparison.expected_digest,
        }
    )
    manifest = {
        "format": MANIFEST_FORMAT,
        "golden": _display_path(golden),
        "source": source,
        "baseline_found": expected is not None,
        "dimensions_match": comparison.dimensions_match,
        "expected": expected_info,
        "actual": {
            "width": comparison.actual_size[0],
            "height": comparison.actual_size[1],
            "digest": comparison.actual_digest,
        },
        "differing_pixels": comparison.differing_pixels,
        "changed_pixels": comparison.changed_pixels,
        "only_in_one_pixels": comparison.only_in_one_pixels,
        "bbox": None if comparison.bbox is None else comparison.bbox.as_dict(),
        "files": files,
        "diff_legend": {
            "changed": list(DIFF_CHANGED),
            "only_in_one_image": list(DIFF_ADDED),
            "unchanged": f"opaque grey {_UNCHANGED_MIN}..{_UNCHANGED_MAX} from expected luma",
            "outside_both_images": [0, 0, 0, 255],
        },
        "environment": _environment(),
    }
    text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path = directory / "manifest.json"
    _atomic_write(path, text.encode("utf-8"))
    return path


def ci_active() -> bool:
    """``CI`` set to anything but empty, ``0`` or ``false`` (case-insensitive)."""
    return os.environ.get("CI", "").strip().lower() not in _CI_FALSE


def _refuse_in_ci() -> None:
    if ci_active():
        raise RuntimeError("golden updates are refused in CI: baselines are reviewed locally")


def update_requested() -> bool:
    """``True`` only for exactly ``MOANA_UPDATE_GOLDENS=1``; refused when ``CI`` is set."""
    requested = os.environ.get(UPDATE_ENV, "") == "1"
    if requested:
        _refuse_in_ci()
    return requested


def default_name(golden: Path) -> str:
    """Diagnostics folder name for ``golden``.

    The path below :data:`GOLDENS_DIR` without suffix, ``/`` written as ``__`` (so
    equal stems in different subfolders do not collide); the file stem for goldens
    elsewhere. Unsafe characters become ``_``.
    """
    resolved = golden.resolve()
    try:
        relative = resolved.relative_to(GOLDENS_DIR).with_suffix("").as_posix()
    except ValueError:
        relative = resolved.stem
    return _UNSAFE_CHARS.sub("_", relative.replace("/", "__")).lstrip(".")[:100] or "_"


def default_artifacts_dir() -> Path:
    """``$MOANA_VISUAL_ARTIFACTS`` or ``<repo>/artifacts/visual`` (ignored by Git)."""
    configured = os.environ.get(ARTIFACTS_ENV, "")
    return Path(configured) if configured else ROOT / "artifacts" / "visual"


def assert_matches_golden(
    actual: Canvas | RGBAArray,
    golden: Path,
    *,
    artifacts: Path | None = None,
    name: str | None = None,
    update: bool | None = None,
    source: str | None = None,
) -> None:
    """Fail with diagnostics unless ``actual`` equals the golden PNG pixel for pixel.

    ``update=None`` reads :func:`update_requested`. In update mode a missing or
    different baseline is rewritten (diagnostics are still written) and the call
    fails so the change is reviewed and the test rerun without the update flag.
    An equal baseline is never rewritten, and no baseline is ever written while
    ``CI`` is set, however the update was requested. Diagnostics of a previous run
    for the same name are removed, also when the comparison passes. ``source``
    (e.g. the fixture or document that produced ``actual``) goes to the manifest.
    """
    pixels = normalize_rgba(_as_rgba(actual, "actual"))
    directory = (artifacts or default_artifacts_dir()) / _check_name(
        default_name(golden) if name is None else name
    )
    do_update = update_requested() if update is None else update
    expected = load_png(golden) if golden.is_file() else None
    if expected is not None:
        comparison = compare_rgba(expected, pixels)
        if comparison.matches:
            clear_diagnostics(directory)
            return
    else:
        width, height = _size(pixels)
        comparison = Comparison(
            expected_size=(0, 0),
            actual_size=(width, height),
            expected_digest="",
            actual_digest=visual_digest(pixels),
            changed_pixels=0,
            only_in_one_pixels=width * height,
            bbox=BBox(0, 0, width, height),
        )
    manifest = write_diagnostics(
        comparison, expected, pixels, directory, golden=golden, source=source
    )
    if do_update:
        _refuse_in_ci()
        write_png(pixels, golden)
        raise VisualMismatch(
            f"golden {_display_path(golden)} rewritten; review the diff and rerun "
            f"without {UPDATE_ENV}",
            manifest,
        )
    if expected is None:
        raise VisualMismatch(f"golden {_display_path(golden)} does not exist", manifest)
    raise VisualMismatch(
        f"{comparison.differing_pixels} pixel(s) differ from {_display_path(golden)} "
        f"(expected {comparison.expected_size}, actual {comparison.actual_size}, "
        f"bbox {comparison.bbox})",
        manifest,
    )
