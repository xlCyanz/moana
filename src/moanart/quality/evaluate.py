"""Deterministic evaluation of rendered pixels against section 19 (ADR-036).

:func:`evaluate_quality` receives pixels, never a renderer: a still image (anything
with ``width``, ``height`` and RGBA ``bytes``, such as
:class:`~moanart.render.RenderResult`), the canvas and palette of its document, the
region masks the configuration names and, optionally, the frames of a timeline
(anything with ``frame_id`` and such a ``result``, such as
:class:`~moanart.animation.FrameRender`). It reads them and builds a new report;
inputs are never modified and nothing is cleaned or repaired.

Rules of ``quality-v1`` (definitions in ADR-036):

* hard (``error``, never suppressible): ``canvas_dimensions`` (an image whose size
  is not the canvas; it is not analysed further: no other rule, metric or digest),
  ``alpha_normalized`` (pixels with alpha 0 and RGB other than 0),
  ``palette_strict`` (with a ``strict`` palette, one finding per RGBA value with
  alpha > 0 that is no palette value) and ``outside_mask`` (opaque pixels outside
  the union of the ``containment`` regions; still image only);
* soft (``warning``): ``singleton`` and ``irregular_steps`` (the findings of
  :func:`moanart.techniques.analyze_clusters` with ``cluster_connectivity``,
  suppressed by its region exceptions; singletons are grouped per colour above
  ``max_listed_singletons``), ``color_excess`` and ``noise`` (whole image and each
  configured region), ``temporal_change`` (off by default) and
  ``temporal_flicker`` (consecutive frames and, with ``loop``, the seam from the
  last frame back to the first).

A suppression silences a warning only when every pixel behind it lies in the
suppression's region; the first matching suppression in canonical order (region,
then rule) is recorded in ``suppressed_by``. Each region mask is read once and
turned into one canvas plane reused by every rule. Work is admitted against
:class:`~moanart.core.budget.RenderLimits` with :func:`quality_cost` before any array
exists, and ``deadline`` is checked between stages (``quality_region`` per region,
``quality_frame`` per frame).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol

import numpy as np
import numpy.typing as npt

from moanart.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moanart.core.coordinates import Box, Dimensions, require_int
from moanart.core.digest import visual_digest
from moanart.core.errors import BudgetExceeded, ErrorDetail, ReferenceError, ValidationError
from moanart.core.ids import check_id
from moanart.core.limits import MAX_ANIMATION_FRAMES
from moanart.geometry import Mask, cover_bytes
from moanart.palette import Palette
from moanart.quality._collect import (
    HELD_PER_LIST,
    MAX_HELD_FINDINGS,
    MAX_QUALITY_FINDINGS,
    MIN_LISTED_PER_RULE,
    FindingList,
)
from moanart.quality.config import (
    HARD_RULES,
    RULE_SET_VERSION,
    RULE_SEVERITY,
    SOFT_RULES,
    QualityConfig,
    QualityRule,
    RegionSettings,
)
from moanart.quality.report import (
    Evidence,
    FrameMetrics,
    Metrics,
    QualityFinding,
    QualityReport,
    RegionMetrics,
)
from moanart.techniques import (
    ClusterException,
    ClusterFinding,
    ClusterRule,
    analyze_clusters,
    cluster_bytes,
)

__all__ = [
    "EXPLANATIONS",
    "MAX_QUALITY_FINDINGS",
    "MIN_LISTED_PER_RULE",
    "RasterImage",
    "TimelineFrame",
    "evaluate_quality",
    "quality_cost",
]

_IMAGE_VISITS_PER_PIXEL: Final = 16
"""Visits per pixel of the still image and of each configured region: two cluster
analyses (silhouette and colour, two passes each) and at most twelve array passes."""
_FRAME_VISITS_PER_PIXEL: Final = 16
"""Visits per pixel of each frame: hard checks, metrics, differences and flicker."""
_IMAGE_BYTES_PER_PIXEL: Final = 64
"""Bytes per pixel held while one image or region is analysed besides its input and
the region planes (measured, with margin, in the memory tests): the masked copy and
its bytes, the silhouette, opaque colours and their unique values, palette indexes
and boolean planes."""
_FRAME_BYTES_PER_PIXEL: Final = 80
"""Bytes per pixel of the temporal pass: five normalised frames (the window and the
two first frames kept for the loop seam), palette indexes, opaque colours and their
unique values and boolean planes."""
_REGION_BYTES_PER_PIXEL: Final = 2
"""Each named region: its mask (at most one byte per canvas pixel) and its plane."""
_FINDING_BYTES: Final = 1024
"""Upper bound of one held finding: the object, its evidence tuple and pairs, a box
(measured below 600 bytes in the memory tests)."""
_SMALL_RULES: Final = 8
_ALPHA_SHIFT: Final = 24
_PERMILLE: Final = 1000
_SILHOUETTE: Final = 0xFFFFFFFF
_CLUSTER_RULES: Final[tuple[ClusterRule, ...]] = ("irregular_steps", "singleton")

EXPLANATIONS: Final[Mapping[QualityRule, str]] = MappingProxyType(
    {
        "canvas_dimensions": "The image size differs from the document canvas.",
        "alpha_normalized": "Pixels with alpha 0 keep a colour; alpha 0 must be (0, 0, 0, 0).",
        "palette_strict": "Pixels use a colour that is not a value of the strict palette.",
        "outside_mask": "Opaque pixels lie outside the regions that must contain the sprite.",
        "singleton": (
            "Isolated pixel: a cluster of exactly one pixel. Keep if intentional (eye, "
            "glint, particle); otherwise merge it into a neighbouring cluster or "
            "suppress it by region."
        ),
        "irregular_steps": "Abrupt step change in a one-pixel stair (jagged edge).",
        "color_excess": "More distinct colours than the configured maximum.",
        "noise": (
            "Many one-pixel clusters for the opaque area; expected for deliberate "
            "dithering or texture; suppress by region."
        ),
        "temporal_change": (
            "Many of the opaque pixels change between consecutive frames; this may be "
            "an intended pose change."
        ),
        "temporal_flicker": "Isolated pixels change for exactly one frame and change back.",
    }
)
"""Fixed explanation of each rule (read-only); findings never echo document strings."""

U32 = npt.NDArray[np.uint32]
Plane = npt.NDArray[np.bool_]


class RasterImage(Protocol):
    """Straight row-major RGBA pixels (``RenderResult`` satisfies it)."""

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def rgba(self) -> bytes: ...


class TimelineFrame(Protocol):
    """One timeline frame (``moanart.animation.FrameRender`` satisfies it)."""

    @property
    def frame_id(self) -> str: ...

    @property
    def result(self) -> RasterImage: ...


@dataclass(frozen=True, slots=True)
class _Image:
    width: int
    height: int
    rgba: bytes

    @property
    def dimensions(self) -> Dimensions:
        return Dimensions(self.width, self.height)

    def values(self) -> U32:
        """Read-only ``(height, width)`` view: ``r | g << 8 | b << 16 | a << 24``."""
        flat = np.frombuffer(self.rgba, dtype="<u4").astype(np.uint32, copy=False)
        shaped: U32 = flat.reshape(self.height, self.width)
        return shaped


def _image(value: object, field: str) -> _Image:
    try:
        width = getattr(value, "width")  # noqa: B009  # structural protocol, checked here
        height = getattr(value, "height")  # noqa: B009
        rgba = getattr(value, "rgba")  # noqa: B009
    except AttributeError:
        raise TypeError(f"{field} must have width, height and rgba") from None
    dimensions = Dimensions(width, height)
    if type(rgba) is not bytes:
        raise TypeError(f"{field}.rgba must be bytes")
    if len(rgba) != 4 * dimensions.area:
        raise ValidationError(
            "rgba must hold 4 bytes per pixel",
            context={"field": field, "reason": "size_mismatch"},
        )
    return _Image(dimensions.width, dimensions.height, rgba)


def _frames(frames: object) -> tuple[tuple[str, _Image], ...]:
    if isinstance(frames, str | bytes) or not isinstance(frames, Sequence):
        raise TypeError("frames must be a sequence of timeline frames")
    if len(frames) > MAX_ANIMATION_FRAMES:
        raise BudgetExceeded(
            "too many frames for one quality report",
            context={
                "resource": "frames",
                "limit": MAX_ANIMATION_FRAMES,
                "estimated": len(frames),
            },
        )
    checked: dict[str, _Image] = {}
    for frame in frames:
        try:
            frame_id = getattr(frame, "frame_id")  # noqa: B009  # structural protocol
            result = getattr(frame, "result")  # noqa: B009
        except AttributeError:
            raise TypeError("frames must have frame_id and result") from None
        check_id(frame_id, "frame_id")
        if frame_id in checked:
            raise ValidationError(
                "repeated frame", context={"field": "frame_id", "reason": "duplicate_frame"}
            )
        checked[frame_id] = _image(result, "frame")
    return tuple(checked.items())


def _held_findings(area: int, frames: int, regions: int) -> int:
    """Upper bound of the findings held at once (see :mod:`moanart.quality._collect`).

    A rule's findings are split between the active and suppressed lists, each holding
    at most ``MAX_QUALITY_FINDINGS + slack`` of them: ``palette_strict`` builds at
    most :data:`MAX_QUALITY_FINDINGS` groups per image, ``singleton`` and
    ``irregular_steps`` at most one per pixel of the still image and every other
    rule at most a few per image, region and seam.
    """
    held = min((1 + frames) * min(area, MAX_QUALITY_FINDINGS), 2 * HELD_PER_LIST)
    held += 2 * min(area, 2 * HELD_PER_LIST)
    held += _SMALL_RULES * 2 * (2 + frames + regions)
    return min(held, MAX_HELD_FINDINGS)


def quality_cost(dimensions: Dimensions, config: QualityConfig, frames: int = 0) -> tuple[int, int]:
    """Estimated ``(pixel visits, bytes)`` of an evaluation over a canvas ``dimensions``.

    Visits: 16 per pixel for the still image and for each configured region, one
    mask pass per named region and 16 per pixel and frame. Bytes: one cluster
    analysis at a time (:func:`~moanart.techniques.cluster_bytes`), the cover of the
    cluster suppressions, two bytes per pixel per named region (its mask and its
    plane), the larger of the image and temporal working sets and the findings held
    at once (bounded per rule, ADR-036 §8). Only canvas-sized images are analysed,
    so the canvas bounds the work whatever the size of the inputs, which belong to
    the caller.
    """
    if not isinstance(dimensions, Dimensions):
        raise TypeError("dimensions must be a Dimensions value")
    if not isinstance(config, QualityConfig):
        raise TypeError("config must be a QualityConfig")
    require_int(frames, "frames", minimum=0, maximum=MAX_ANIMATION_FRAMES)
    area = dimensions.area
    named = len(config.region_ids)
    visits = area * (
        _IMAGE_VISITS_PER_PIXEL * (1 + len(config.regions))
        + named
        + _FRAME_VISITS_PER_PIXEL * frames
    )
    working = _FRAME_BYTES_PER_PIXEL if frames else _IMAGE_BYTES_PER_PIXEL
    held = (
        cluster_bytes(dimensions)
        + (cover_bytes(dimensions) if config.suppressions else 0)
        + _REGION_BYTES_PER_PIXEL * named * area
        + working * area
        + _FINDING_BYTES * _held_findings(area, frames, len(config.regions))
    )
    return visits, held


def _admit(cost: tuple[int, int], limits: RenderLimits) -> None:
    checks = (
        ("pixel_visits", limits.max_pixel_visits, cost[0]),
        ("buffer_bytes", limits.max_buffer_bytes, cost[1]),
    )
    details = [
        ErrorDetail(
            BudgetExceeded.code,
            f"estimated {name} of the quality report exceed the request budget",
            context={"resource": name, "limit": limit, "estimated": value},
        )
        for name, limit, value in checks
        if value > limit
    ]
    if details:
        raise BudgetExceeded(
            "quality report exceeds the request budget",
            context=dict(details[0].context),
            details=details,
        )


def _masks(config: QualityConfig, regions: object) -> dict[str, Mask]:
    """The mask of every region the configuration names, each read once."""
    if regions is None:
        regions = {}
    if not isinstance(regions, Mapping):
        raise TypeError("regions must be a mapping of region IDs to Mask values")
    masks: dict[str, Mask] = {}
    for region_id in config.region_ids:
        if region_id not in regions:
            raise ReferenceError(
                "configured region has no mask",
                context={"field": "region_id", "reason": "unknown_region"},
            )
        mask = regions[region_id]
        if not isinstance(mask, Mask):
            raise TypeError("regions must map region IDs to Mask values")
        masks[region_id] = mask
    return masks


# --- pixel helpers ------------------------------------------------------------------


def _plane(mask: Mask, dimensions: Dimensions) -> Plane:
    """Canvas-sized boolean plane of ``mask`` (clipped to the canvas)."""
    plane: Plane = np.zeros((dimensions.height, dimensions.width), dtype=np.bool_)
    box = mask.box
    clipped = None if box is None else box.clip_to(dimensions)
    if box is None or clipped is None:
        return plane
    bits = mask.to_array()[
        clipped.y0 - box.y0 : clipped.y1 - box.y0, clipped.x0 - box.x0 : clipped.x1 - box.x0
    ]
    plane[clipped.y0 : clipped.y1, clipped.x0 : clipped.x1] = bits
    return plane


def _bounds(plane: Plane) -> Box | None:
    rows = np.flatnonzero(plane.any(axis=1))
    if rows.size == 0:
        return None
    columns = np.flatnonzero(plane.any(axis=0))
    return Box(int(columns[0]), int(rows[0]), int(columns[-1]) + 1, int(rows[-1]) + 1)


def _located(plane: Plane) -> tuple[Box, Evidence] | None:
    """Bounds, count and first pixel (row-major) of ``plane``; ``None`` when empty."""
    box = _bounds(plane)
    if box is None:
        return None
    first = int(np.argmax(plane))
    width = plane.shape[1]
    evidence: Evidence = (
        ("first_x", first % width),
        ("first_y", first // width),
        ("pixels", int(np.count_nonzero(plane))),
    )
    return box, evidence


def _hex(value: int) -> str:
    r, g, b, a = value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF, value >> 24
    return f"#{r:02X}{g:02X}{b:02X}{a:02X}"


def _packed(palette: Palette) -> U32:
    """Palette values with alpha > 0 as packed ``uint32``, sorted."""
    values = sorted(
        {
            color.rgba.r | color.rgba.g << 8 | color.rgba.b << 16 | color.rgba.a << 24: None
            for color in palette.colors
            if color.rgba.a
        }
    )
    packed: U32 = np.array(values, dtype=np.uint32)
    return packed


def _in_palette(values: U32, packed: U32) -> Plane:
    """Whether each value is a packed palette value (binary search, one index each)."""
    if packed.size == 0:
        return np.zeros(values.shape, dtype=np.bool_)
    index = np.minimum(np.searchsorted(packed, values), packed.size - 1)
    found: Plane = packed[index] == values
    return found


def _normalized(values: U32) -> U32:
    normal: U32 = np.where((values >> _ALPHA_SHIFT) == 0, np.uint32(0), values).astype(np.uint32)
    return normal


def _permille(part: int, whole: int) -> int:
    return part * _PERMILLE // whole if whole else 0


# --- findings -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Where:
    """Where findings of one image belong: region and frame."""

    region_id: str | None = None
    frame_id: str | None = None
    frame_index: int | None = None


_STILL: Final = _Where()


def _finding(rule: QualityRule, box: Box, evidence: Evidence, where: _Where) -> QualityFinding:
    return QualityFinding(
        rule,
        RULE_SEVERITY[rule],
        box,
        where.region_id,
        where.frame_id,
        where.frame_index,
        EXPLANATIONS[rule],
        tuple(sorted(evidence)),
    )


def _suppressed(finding: QualityFinding, region_id: str) -> QualityFinding:
    return QualityFinding(
        finding.rule_id,
        finding.severity,
        finding.bbox,
        finding.region_id,
        finding.frame_id,
        finding.frame_index,
        finding.explanation,
        finding.evidence,
        region_id,
    )


class _Collector:
    """Active and suppressed findings, and one canvas plane per named region.

    Every plane is built once from its mask and reused for containment, region
    metrics and suppressions.
    """

    def __init__(self, config: QualityConfig, masks: dict[str, Mask], canvas: Dimensions) -> None:
        self.config = config
        self.masks = masks
        self.planes = {region_id: _plane(mask, canvas) for region_id, mask in masks.items()}
        self.active = FindingList()
        self.suppressed = FindingList()

    def add(self, finding: QualityFinding) -> None:
        self.active.add(finding)

    def add_soft(self, finding: QualityFinding, pixels: Plane) -> None:
        """Add a warning, suppressed when ``pixels`` lie entirely in a suppression region."""
        for suppression in self.config.suppressions:
            if suppression.rule_id != finding.rule_id:
                continue
            if not np.any(pixels & ~self.planes[suppression.region_id]):
                self.suppressed.add(_suppressed(finding, suppression.region_id))
                return
        self.active.add(finding)


# --- hard rules -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Context:
    canvas: Dimensions
    palette: Palette
    config: QualityConfig
    out: _Collector
    deadline: Deadline | None


def _hard_checks(image: _Image, context: _Context, where: _Where) -> U32 | None:
    """Size, alpha and palette rules; the pixel values, ``None`` when not canvas-sized.

    An image whose size is not the canvas is never read: only its size is reported.
    """
    config, out, canvas = context.config, context.out, context.canvas
    if image.dimensions != canvas:
        if config.enabled("canvas_dimensions"):
            evidence: Evidence = (
                ("expected_height", canvas.height),
                ("expected_width", canvas.width),
                ("height", image.height),
                ("width", image.width),
            )
            box = Box(0, 0, image.width, image.height)
            out.add(_finding("canvas_dimensions", box, evidence, where))
        return None
    values = image.values()
    alpha_zero = (values >> _ALPHA_SHIFT) == 0
    if config.enabled("alpha_normalized"):
        located = _located(alpha_zero & (values != 0))
        if located is not None:
            out.add(_finding("alpha_normalized", *located, where))
    if config.enabled("palette_strict") and context.palette.profile == "strict":
        off = ~alpha_zero & ~_in_palette(values, _packed(context.palette))
        groups = 0
        for box, evidence in _off_palette(values, off):
            out.add(_finding("palette_strict", box, evidence, where))
            groups += 1
        out.active.count_omitted("palette_strict", _off_palette_count(values, off) - groups)
    return values


def _off_palette_count(values: U32, off: Plane) -> int:
    return int(np.unique(values[off]).size)


def _off_palette(values: U32, off: Plane) -> Iterator[tuple[Box, Evidence]]:
    """``(bounds, evidence)`` per off-palette colour in report order, at most
    :data:`MAX_QUALITY_FINDINGS` (no image can list more of one rule).

    Groups are sorted as :func:`~moanart.quality.report.finding_sort_key` sorts them
    (``y0``, ``x0``, ``y1``, ``x1``, then the colour text).
    """
    width = values.shape[1]
    indices = np.flatnonzero(off)
    if indices.size == 0:
        return
    colours = values.reshape(-1)[indices]
    order = np.lexsort((indices, colours))
    indices, colours = indices[order], colours[order]
    starts = np.flatnonzero(np.r_[True, colours[1:] != colours[:-1]])
    xs, ys = indices % width, indices // width
    min_x, max_x = np.minimum.reduceat(xs, starts), np.maximum.reduceat(xs, starts) + 1
    min_y, max_y = np.minimum.reduceat(ys, starts), np.maximum.reduceat(ys, starts) + 1
    counts = np.diff(np.r_[starts, indices.size])
    text_order = colours[starts].byteswap()  # #RRGGBBAA order is big-endian order
    groups = np.lexsort((text_order, max_x, max_y, min_x, min_y))
    for group in groups[:MAX_QUALITY_FINDINGS].tolist():
        start = int(starts[group])
        box = Box(int(min_x[group]), int(min_y[group]), int(max_x[group]), int(max_y[group]))
        evidence: Evidence = (
            ("color", _hex(int(colours[start]))),
            ("first_x", int(xs[start])),
            ("first_y", int(ys[start])),
            ("pixels", int(counts[group])),
        )
        yield box, evidence


def _containment(opaque: Plane, config: QualityConfig, out: _Collector) -> None:
    """``outside_mask``: opaque pixels outside the union of the containment regions."""
    if not config.containment or not config.enabled("outside_mask"):
        return
    inside: Plane = np.zeros(opaque.shape, dtype=np.bool_)
    for region_id in config.containment:
        inside |= out.planes[region_id]
    located = _located(opaque & ~inside)
    if located is not None:
        box, evidence = located
        regions = ("regions", ",".join(config.containment))
        out.add(_finding("outside_mask", box, (*evidence, regions), _STILL))


# --- metrics and soft rules of one image ----------------------------------------------


@dataclass(frozen=True, slots=True)
class _Analysis:
    metrics: Metrics
    singletons: Plane
    opaque: Plane
    warnings: tuple[ClusterFinding, ...]
    suppressed: tuple[ClusterFinding, ...]


def _components(opaque: Plane, config: QualityConfig, deadline: Deadline | None) -> int:
    """Connected components of the silhouette with ``connectivity``."""
    height, width = opaque.shape
    silhouette = np.where(opaque, np.uint32(_SILHOUETTE), np.uint32(0)).astype("<u4").tobytes()
    report = analyze_clusters(
        silhouette, Dimensions(width, height), connectivity=config.connectivity, deadline=deadline
    )
    return len(report.clusters)


def _analyse(
    values: U32,
    config: QualityConfig,
    deadline: Deadline | None,
    *,
    exceptions: Sequence[ClusterException] = (),
    masks: Mapping[str, Mask] | None = None,
) -> _Analysis:
    height, width = values.shape
    opaque: Plane = (values >> _ALPHA_SHIFT) != 0
    colours = int(np.unique(values[opaque]).size)
    components = _components(opaque, config, deadline)
    clusters = analyze_clusters(
        values.astype("<u4").tobytes(),
        Dimensions(width, height),
        connectivity=config.cluster_connectivity,
        exceptions=exceptions,
        regions=masks,
        deadline=deadline,
    )
    singletons: Plane = np.zeros((height, width), dtype=np.bool_)
    for cluster in clusters.clusters:
        if cluster.area == 1:
            singletons[cluster.seed.y, cluster.seed.x] = True
    opaque_area = int(np.count_nonzero(opaque))
    metrics = Metrics(
        distinct_colors=colours,
        opaque_area=opaque_area,
        components=components,
        clusters=len(clusters.clusters),
        singletons=clusters.singletons,
        singleton_permille=_permille(clusters.singletons, opaque_area),
        bbox=_bounds(opaque),
    )
    return _Analysis(metrics, singletons, opaque, clusters.warnings, clusters.suppressed)


def _excess_and_noise(
    analysis: _Analysis,
    config: QualityConfig,
    thresholds: tuple[int, int],
    where: _Where,
    out: _Collector,
) -> None:
    metrics = analysis.metrics
    max_colors, max_permille = thresholds
    if config.enabled("color_excess") and metrics.distinct_colors > max_colors:
        assert metrics.bbox is not None  # at least one colour means opaque pixels
        evidence: Evidence = (
            ("distinct_colors", metrics.distinct_colors),
            ("max_colors", max_colors),
        )
        out.add_soft(_finding("color_excess", metrics.bbox, evidence, where), analysis.opaque)
    noisy = (
        metrics.singletons >= config.min_noise_singletons
        and metrics.singleton_permille > max_permille
    )
    if config.enabled("noise") and noisy:
        box = _bounds(analysis.singletons)
        assert box is not None  # min_noise_singletons >= 1
        evidence = (
            ("max_singleton_permille", max_permille),
            ("opaque_area", metrics.opaque_area),
            ("singleton_permille", metrics.singleton_permille),
            ("singletons", metrics.singletons),
        )
        out.add_soft(_finding("noise", box, evidence, where), analysis.singletons)


def _cluster_exceptions(config: QualityConfig) -> tuple[ClusterException, ...]:
    """Enabled cluster suppressions as one exception per region, in region order."""
    rules: dict[str, list[ClusterRule]] = {}
    for suppression in config.suppressions:
        for rule in _CLUSTER_RULES:
            if suppression.rule_id == rule and config.enabled(rule):
                rules.setdefault(suppression.region_id, []).append(rule)
    return tuple(ClusterException(region, tuple(chosen)) for region, chosen in rules.items())


def _from_cluster(finding: ClusterFinding) -> QualityFinding:
    evidence: Evidence = (*finding.evidence, ("color", finding.color))
    quality = _finding(finding.rule_id, finding.box, evidence, _STILL)
    if finding.region_id is None:
        return quality
    return _suppressed(quality, finding.region_id)


def _grouped_singletons(singletons: list[ClusterFinding]) -> Iterator[QualityFinding]:
    """One ``singleton`` finding per ``(colour, suppression region)``.

    Singletons arrive in row-major order, so the first of each group is its first
    pixel; the box bounds every singleton of the group.
    """
    groups: dict[tuple[str, str | None], list[ClusterFinding]] = {}
    for finding in singletons:
        groups.setdefault((finding.color, finding.region_id), []).append(finding)
    for (color, region_id), members in groups.items():
        first = members[0].box
        box = Box(
            min(item.box.x0 for item in members),
            min(item.box.y0 for item in members),
            max(item.box.x1 for item in members),
            max(item.box.y1 for item in members),
        )
        evidence: Evidence = (
            ("color", color),
            ("first_x", first.x0),
            ("first_y", first.y0),
            ("pixels", len(members)),
        )
        quality = _finding("singleton", box, evidence, _STILL)
        yield quality if region_id is None else _suppressed(quality, region_id)


def _cluster_findings(
    findings: tuple[ClusterFinding, ...], config: QualityConfig, add: FindingList
) -> None:
    """Add the enabled cluster findings of one list; singletons per pixel up to
    ``max_listed_singletons``, one per colour above it."""
    singletons: list[ClusterFinding] = []
    for finding in findings:
        if not config.enabled(finding.rule_id):
            continue
        if finding.rule_id == "singleton":
            singletons.append(finding)
        else:
            add.add(_from_cluster(finding))
    if len(singletons) > config.max_listed_singletons:
        for grouped in _grouped_singletons(singletons):
            add.add(grouped)
    else:
        for finding in singletons:
            add.add(_from_cluster(finding))


def _still(image: _Image, context: _Context) -> tuple[Metrics | None, tuple[RegionMetrics, ...]]:
    """Every rule and metric of the still image, then of each configured region."""
    config, out = context.config, context.out
    values = _hard_checks(image, context, _STILL)
    if values is None:
        return None, ()
    analysis = _analyse(
        values,
        config,
        context.deadline,
        exceptions=_cluster_exceptions(config),
        masks=out.masks,
    )
    _cluster_findings(analysis.warnings, config, out.active)
    _cluster_findings(analysis.suppressed, config, out.suppressed)
    _containment(analysis.opaque, config, out)
    thresholds = (config.max_colors, config.max_singleton_permille)
    _excess_and_noise(analysis, config, thresholds, _STILL, out)
    metrics = analysis.metrics
    del analysis
    regions = tuple(_region(values, settings, context) for settings in config.regions)
    return metrics, regions


def _region(values: U32, settings: RegionSettings, context: _Context) -> RegionMetrics:
    """Analyse the pixels of one configured region; the rest is seen as transparent."""
    if context.deadline is not None:
        context.deadline.checkpoint("quality_region")
    config = context.config
    plane = context.out.planes[settings.region_id]
    masked: U32 = np.where(plane, values, np.uint32(0)).astype(np.uint32)
    region = _analyse(masked, config, context.deadline)
    max_colors = settings.max_colors
    max_permille = settings.max_singleton_permille
    thresholds = (
        config.max_colors if max_colors is None else max_colors,
        config.max_singleton_permille if max_permille is None else max_permille,
    )
    _excess_and_noise(region, config, thresholds, _Where(settings.region_id), context.out)
    return RegionMetrics(settings.region_id, region.metrics)


# --- timeline -----------------------------------------------------------------------


def _isolated(changed: Plane) -> Plane:
    """Pixels of ``changed`` none of whose eight neighbours is in ``changed``."""
    padded = np.pad(changed, 1)
    height, width = changed.shape
    neighbours: Plane = np.zeros(changed.shape, dtype=np.bool_)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            if dy != 1 or dx != 1:
                neighbours |= padded[dy : dy + height, dx : dx + width]
    isolated: Plane = changed & ~neighbours
    return isolated


@dataclass(frozen=True, slots=True)
class _Normal:
    """Normalised pixels of one canvas-sized frame and where its findings belong."""

    values: U32
    where: _Where


def _frame_metrics(
    frame_id: str, index: int, image: _Image, values: U32 | None, changed: int | None, area: int
) -> FrameMetrics:
    if values is None:
        return FrameMetrics(frame_id, index, None, None, None, None, None, None)
    opaque = (values >> _ALPHA_SHIFT) != 0
    return FrameMetrics(
        frame_id=frame_id,
        index=index,
        digest=visual_digest(image.width, image.height, image.rgba),
        distinct_colors=int(np.unique(values[opaque]).size),
        opaque_area=int(np.count_nonzero(opaque)),
        bbox=_bounds(opaque),
        changed_pixels=changed,
        changed_permille=None if changed is None else _permille(changed, area),
    )


def _timeline(
    frames: tuple[tuple[str, _Image], ...], loop: bool, context: _Context
) -> tuple[FrameMetrics, ...]:
    """Hard checks and metrics of every frame, then the temporal rules.

    Only the normalised pixels of the last three frames and, for the loop seam, of
    the first two are kept; a frame that is not canvas-sized breaks the window.
    """
    window: list[_Normal | None] = [None, None]
    head: list[_Normal | None] = []
    rows: list[FrameMetrics] = []
    for index, (frame_id, image) in enumerate(frames):
        if context.deadline is not None:
            context.deadline.checkpoint("quality_frame")
        where = _Where(None, frame_id, index)
        values = _hard_checks(image, context, where)
        current = None if values is None else _Normal(_normalized(values), where)
        changed = _compare((window[0], window[1], current), context)
        rows.append(_frame_metrics(frame_id, index, image, values, changed, context.canvas.area))
        window = [window[1], current]
        if index < 2:
            head.append(current)
    if loop and len(frames) >= 3:
        last, first, second = window[1], head[0], head[1]
        _compare((window[0], last, first), context)  # last -> first, flicker of last
        if last is not None and first is not None and second is not None:
            _flicker(last.values, first, second.values, context)  # flicker of first
    return tuple(rows)


def _compare(
    triple: tuple[_Normal | None, _Normal | None, _Normal | None], context: _Context
) -> int | None:
    """Temporal rules for ``previous → current`` and flicker of ``previous``.

    Returns the changed pixels of ``previous → current`` (``None`` when either is
    missing).
    """
    before, previous, current = triple
    if previous is None or current is None:
        return None
    plane: Plane = previous.values != current.values
    changed = int(np.count_nonzero(plane))
    _temporal_change(plane, changed, previous, current, context)
    if before is not None:
        _flicker(before.values, previous, current.values, context)
    return changed


def _temporal_change(
    plane: Plane, changed: int, previous: _Normal, current: _Normal, context: _Context
) -> None:
    """``temporal_change`` of ``current``: changed pixels over the pixels opaque in
    either frame (a pixel transparent in both never changes)."""
    config = context.config
    if not config.enabled("temporal_change"):
        return
    union = int(np.count_nonzero((previous.values != 0) | (current.values != 0)))
    permille = _permille(changed, union)
    if permille <= config.max_changed_permille:
        return
    box = _bounds(plane)
    assert box is not None  # a positive permille means changed pixels
    assert previous.where.frame_id is not None
    evidence: Evidence = (
        ("changed_permille", permille),
        ("changed_pixels", changed),
        ("max_changed_permille", config.max_changed_permille),
        ("opaque_union", union),
        ("previous_frame_id", previous.where.frame_id),
    )
    context.out.add_soft(_finding("temporal_change", box, evidence, current.where), plane)


def _flicker(before: U32, middle: _Normal, after: U32, context: _Context) -> None:
    """``temporal_flicker`` of the middle frame: a one-frame blip with no changed neighbour."""
    if not context.config.enabled("temporal_flicker"):
        return
    blips: Plane = _isolated(middle.values != before) & (after == before)
    located = _located(blips)
    if located is not None:
        context.out.add_soft(_finding("temporal_flicker", *located, middle.where), blips)


# --- entry point --------------------------------------------------------------------


def _checked_options(
    canvas: object,
    palette: object,
    config: object,
    loop: object,
    limits: object,
    deadline: object,
) -> tuple[QualityConfig, RenderLimits]:
    if not isinstance(canvas, Dimensions):
        raise TypeError("canvas must be a Dimensions value")
    if not isinstance(palette, Palette):
        raise TypeError("palette must be a moanart.palette.Palette")
    config = QualityConfig() if config is None else config
    if not isinstance(config, QualityConfig):
        raise TypeError("config must be a QualityConfig")
    if type(loop) is not bool:
        raise TypeError("loop must be a bool")
    limits = DEFAULT_RENDER_LIMITS if limits is None else limits
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    if deadline is not None and not isinstance(deadline, Deadline):
        raise TypeError("deadline must be a Deadline or None")
    return config, limits


def evaluate_quality(
    image: RasterImage,
    *,
    canvas: Dimensions,
    palette: Palette,
    config: QualityConfig | None = None,
    regions: Mapping[str, Mask] | None = None,
    frames: Sequence[TimelineFrame] = (),
    loop: bool = False,
    limits: RenderLimits | None = None,
    deadline: Deadline | None = None,
) -> QualityReport:
    """Quality report of ``image`` (and of the timeline ``frames``) for a document.

    ``canvas`` and ``palette`` are the document's; ``regions`` maps at least every
    region the configuration names to its mask (``ReferenceError``,
    ``unknown_region``), each read once. With ``loop`` (a timeline that plays more
    than once) the seam from the last frame back to the first is compared too
    (``temporal_change`` and ``temporal_flicker``; at least three frames). Raises
    ``TypeError`` for inputs of the wrong type, ``ValidationError``
    (``size_mismatch``, ``duplicate_frame``) and ``BudgetExceeded`` (``frames`` over
    256 or the estimate of :func:`quality_cost` for the canvas over ``limits``)
    before any pixel is analysed, then ``BudgetExceeded`` (``cluster_runs``,
    ``time``) from the analyses.
    """
    config, limits = _checked_options(canvas, palette, config, loop, limits, deadline)
    still = _image(image, "image")
    timeline = _frames(frames)
    _admit(quality_cost(canvas, config, len(timeline)), limits)
    out = _Collector(config, _masks(config, regions), canvas)
    context = _Context(canvas, palette, config, out, deadline)
    metrics, region_metrics = _still(still, context)
    frame_metrics = _timeline(timeline, loop, context)
    findings, omitted = out.active.capped()
    suppressed, omitted_suppressed = out.suppressed.capped()
    errors = out.active.total(HARD_RULES)
    analysed = metrics is not None
    return QualityReport(
        rule_set=RULE_SET_VERSION,
        width=still.width,
        height=still.height,
        image_digest=visual_digest(still.width, still.height, still.rgba) if analysed else None,
        config=config,
        passed_hard_checks=errors == 0,
        error_count=errors,
        warning_count=out.active.total(SOFT_RULES),
        findings=findings,
        suppressed=suppressed,
        omitted_findings_by_rule=omitted,
        omitted_suppressed_by_rule=omitted_suppressed,
        metrics=metrics,
        region_metrics=region_metrics,
        frame_metrics=frame_metrics,
    )
