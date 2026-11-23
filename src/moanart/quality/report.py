"""Findings, metrics and the quality report (MOANART.md section 19, ADR-036).

A report holds facts, not a verdict: findings of hard rules (``error``) and soft
heuristics (``warning``), numeric metrics without judgement and the identity of the
configuration and rule set that produced them. There is deliberately **no aggregate
score**: :data:`REPORT_NOTICE` says so in every serialised report. Nothing in a
report is, or stands for, a professional guarantee or a human review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from moanart.core.coordinates import Box
from moanart.quality.config import QUALITY_RULES, QualityConfig, QualityRule, Severity

__all__ = [
    "REPORT_NOTICE",
    "Evidence",
    "FrameMetrics",
    "Metrics",
    "OmittedByRule",
    "QualityFinding",
    "QualityReport",
    "RegionMetrics",
    "finding_sort_key",
]

REPORT_NOTICE: Final = (
    "Automated conformance checks and artistic heuristics. Not a quality score, "
    "a professional guarantee or a human review."
)

Evidence = tuple[tuple[str, int | str], ...]
"""Sorted ``(name, value)`` pairs: integers, colours as ``#RRGGBBAA`` and IDs only."""


def _box(box: Box | None) -> list[int] | None:
    return None if box is None else [box.x0, box.y0, box.x1, box.y1]


@dataclass(frozen=True, slots=True)
class QualityFinding:
    """One incident of section 19.

    ``bbox`` is half-open in canvas coordinates. ``region_id`` is the region the
    finding was evaluated in (``None``: the whole image); ``frame_id`` the timeline
    frame it concerns (``None``: the still image); ``suppressed_by`` the region of the
    suppression that silenced it (only in :attr:`QualityReport.suppressed`).
    ``explanation`` is a fixed text of the rule; it never echoes document strings.
    """

    rule_id: QualityRule
    severity: Severity
    bbox: Box
    region_id: str | None
    frame_id: str | None
    frame_index: int | None
    explanation: str
    evidence: Evidence
    suppressed_by: str | None = None

    def to_mapping(self) -> dict[str, object]:
        """JSON-compatible form; ``evidence`` becomes an object with sorted keys."""
        return {
            "bbox": _box(self.bbox),
            "evidence": dict(self.evidence),
            "explanation": self.explanation,
            "frame_id": self.frame_id,
            "frame_index": self.frame_index,
            "region_id": self.region_id,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "suppressed_by": self.suppressed_by,
        }


def finding_sort_key(
    finding: QualityFinding,
) -> tuple[int, int, str, int, int, int, int, int, Evidence]:
    """Rule (order of :data:`QUALITY_RULES`), region (``None`` first), frame (the still
    image first), ``y``, ``x``, then the far corner and evidence as tie-breakers."""
    box = finding.bbox
    frame = -1 if finding.frame_index is None else finding.frame_index
    return (
        QUALITY_RULES.index(finding.rule_id),
        0 if finding.region_id is None else 1,
        finding.region_id or "",
        frame,
        box.y0,
        box.x0,
        box.y1,
        box.x1,
        finding.evidence,
    )


@dataclass(frozen=True, slots=True)
class Metrics:
    """Numbers without judgement for an image or one region of it.

    * ``distinct_colors``: distinct RGBA values among pixels with alpha > 0;
    * ``opaque_area``: pixels with alpha > 0 (the silhouette of section 8);
    * ``components``: connected components of the silhouette, whatever the colour,
      with ``connectivity`` (4 by default, section 8);
    * ``clusters`` / ``singletons``: same-colour clusters of
      :func:`moanart.techniques.analyze_clusters` with ``cluster_connectivity`` (8 by
      default) and those of exactly one pixel;
    * ``singleton_permille``: ``floor(1000 · singletons / opaque_area)`` (0 without
      opaque pixels), the measure of ``noise``;
    * ``bbox``: bounds of the silhouette, ``None`` when it is empty.
    """

    distinct_colors: int
    opaque_area: int
    components: int
    clusters: int
    singletons: int
    singleton_permille: int
    bbox: Box | None

    def to_mapping(self) -> dict[str, object]:
        """JSON-compatible form."""
        return {
            "bbox": _box(self.bbox),
            "clusters": self.clusters,
            "components": self.components,
            "distinct_colors": self.distinct_colors,
            "opaque_area": self.opaque_area,
            "singleton_permille": self.singleton_permille,
            "singletons": self.singletons,
        }


@dataclass(frozen=True, slots=True)
class RegionMetrics:
    """:class:`Metrics` of the pixels of one region (the rest seen as transparent)."""

    region_id: str
    metrics: Metrics

    def to_mapping(self) -> dict[str, object]:
        """JSON-compatible form."""
        return {"metrics": self.metrics.to_mapping(), "region_id": self.region_id}


@dataclass(frozen=True, slots=True)
class FrameMetrics:
    """Per-frame numbers of a timeline.

    A frame whose size is not the canvas is not analysed (only ``canvas_dimensions``
    is reported): ``digest``, ``distinct_colors``, ``opaque_area`` and ``bbox`` are
    ``None``. ``changed_pixels`` counts pixels whose RGBA (alpha 0 normalised)
    differs from the previous frame and ``changed_permille`` is
    ``floor(1000 · changed / canvas area)``; both are ``None`` for the first frame
    and next to a frame that is not analysed.
    """

    frame_id: str
    index: int
    digest: str | None
    distinct_colors: int | None
    opaque_area: int | None
    bbox: Box | None
    changed_pixels: int | None
    changed_permille: int | None

    def to_mapping(self) -> dict[str, object]:
        """JSON-compatible form."""
        return {
            "bbox": _box(self.bbox),
            "changed_permille": self.changed_permille,
            "changed_pixels": self.changed_pixels,
            "digest": self.digest,
            "distinct_colors": self.distinct_colors,
            "frame_id": self.frame_id,
            "index": self.index,
            "opaque_area": self.opaque_area,
        }


OmittedByRule = tuple[tuple[QualityRule, int], ...]
"""``(rule, omitted findings)`` in rule order, only for rules with omissions."""


@dataclass(frozen=True, slots=True)
class QualityReport:
    """Findings and metrics of one evaluation; immutable and deterministic.

    ``findings`` are the active findings and ``suppressed`` the silenced warnings,
    both in :func:`finding_sort_key` order and each capped at
    :data:`~moanart.quality.MAX_QUALITY_FINDINGS`: every rule with findings keeps at
    least :data:`~moanart.quality.MIN_LISTED_PER_RULE` of them (its first ones in report
    order) and the rest of the cap goes to the first remaining findings in report
    order. ``omitted_*`` count the rest, also per rule; ``truncated`` says whether
    any was cut. ``error_count`` and ``warning_count`` count every active finding,
    omitted ones included, and ``passed_hard_checks`` is ``error_count == 0``.
    ``image_digest`` and ``metrics`` are ``None`` when the image is not the size of
    the canvas (it is then not analysed).
    """

    rule_set: str
    width: int
    height: int
    image_digest: str | None
    config: QualityConfig
    passed_hard_checks: bool
    error_count: int
    warning_count: int
    findings: tuple[QualityFinding, ...]
    suppressed: tuple[QualityFinding, ...]
    omitted_findings_by_rule: OmittedByRule
    omitted_suppressed_by_rule: OmittedByRule
    metrics: Metrics | None
    region_metrics: tuple[RegionMetrics, ...]
    frame_metrics: tuple[FrameMetrics, ...]

    @property
    def omitted_findings(self) -> int:
        """Active findings left out by the cap."""
        return sum(count for _, count in self.omitted_findings_by_rule)

    @property
    def omitted_suppressed(self) -> int:
        """Suppressed findings left out by the cap."""
        return sum(count for _, count in self.omitted_suppressed_by_rule)

    @property
    def truncated(self) -> bool:
        """Whether some finding was left out by the cap."""
        return bool(self.omitted_findings or self.omitted_suppressed)

    @property
    def errors(self) -> tuple[QualityFinding, ...]:
        """Listed active findings of hard rules."""
        return tuple(item for item in self.findings if item.severity == "error")

    @property
    def warnings(self) -> tuple[QualityFinding, ...]:
        """Listed active findings of soft rules."""
        return tuple(item for item in self.findings if item.severity == "warning")

    def to_mapping(self) -> dict[str, object]:
        """Canonical JSON-compatible form; equal reports give equal mappings."""
        return {
            "config": self.config.to_mapping(),
            "config_digest": self.config.digest,
            "error_count": self.error_count,
            "findings": [item.to_mapping() for item in self.findings],
            "frame_metrics": [item.to_mapping() for item in self.frame_metrics],
            "height": self.height,
            "image_digest": self.image_digest,
            "metrics": None if self.metrics is None else self.metrics.to_mapping(),
            "notice": REPORT_NOTICE,
            "omitted_findings": self.omitted_findings,
            "omitted_findings_by_rule": dict(self.omitted_findings_by_rule),
            "omitted_suppressed": self.omitted_suppressed,
            "omitted_suppressed_by_rule": dict(self.omitted_suppressed_by_rule),
            "passed_hard_checks": self.passed_hard_checks,
            "region_metrics": [item.to_mapping() for item in self.region_metrics],
            "rule_set": self.rule_set,
            "suppressed": [item.to_mapping() for item in self.suppressed],
            "truncated": self.truncated,
            "warning_count": self.warning_count,
            "width": self.width,
        }
