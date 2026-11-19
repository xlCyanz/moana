"""Graphic quality reports: hard checks, artistic heuristics and metrics (MOANA.md §19).

``quality`` reads rendered pixels and the document facts they must honour (canvas,
palette, region masks) and returns an immutable :class:`QualityReport`; it never
renders, edits, cleans or writes anything (ADR-036). It depends on ``core``,
``palette``, ``geometry`` (region masks) and ``techniques`` (the cluster analysis of
ADR-027 is reused, not reimplemented); no domain module imports it, and
:func:`moana.api.evaluate_quality` composes it with the renderer.

Hard rules are mathematical conformance (``error``); soft rules are heuristics with
configurable thresholds (``warning``) that never reject anything. A report has no
aggregate score and is never a professional guarantee or a human review.
"""

from moana.quality.config import (
    DEFAULT_MAX_CHANGED_PERMILLE,
    DEFAULT_MAX_COLORS,
    DEFAULT_MAX_LISTED_SINGLETONS,
    DEFAULT_MAX_SINGLETON_PERMILLE,
    DEFAULT_MIN_NOISE_SINGLETONS,
    DEFAULT_RULES,
    HARD_RULES,
    MAX_QUALITY_REGIONS,
    QUALITY_RULES,
    RULE_SET_VERSION,
    RULE_SEVERITY,
    SOFT_RULES,
    QualityConfig,
    QualityRule,
    RegionSettings,
    Severity,
    Suppression,
)
from moana.quality.evaluate import (
    EXPLANATIONS,
    MAX_QUALITY_FINDINGS,
    MIN_LISTED_PER_RULE,
    RasterImage,
    TimelineFrame,
    evaluate_quality,
    quality_cost,
)
from moana.quality.report import (
    REPORT_NOTICE,
    Evidence,
    FrameMetrics,
    Metrics,
    OmittedByRule,
    QualityFinding,
    QualityReport,
    RegionMetrics,
    finding_sort_key,
)

__all__ = [
    "DEFAULT_MAX_CHANGED_PERMILLE",
    "DEFAULT_MAX_COLORS",
    "DEFAULT_MAX_LISTED_SINGLETONS",
    "DEFAULT_MAX_SINGLETON_PERMILLE",
    "DEFAULT_MIN_NOISE_SINGLETONS",
    "DEFAULT_RULES",
    "EXPLANATIONS",
    "HARD_RULES",
    "MAX_QUALITY_FINDINGS",
    "MAX_QUALITY_REGIONS",
    "MIN_LISTED_PER_RULE",
    "QUALITY_RULES",
    "REPORT_NOTICE",
    "RULE_SET_VERSION",
    "RULE_SEVERITY",
    "SOFT_RULES",
    "Evidence",
    "FrameMetrics",
    "Metrics",
    "OmittedByRule",
    "QualityConfig",
    "QualityFinding",
    "QualityReport",
    "QualityRule",
    "RasterImage",
    "RegionMetrics",
    "RegionSettings",
    "Severity",
    "Suppression",
    "TimelineFrame",
    "evaluate_quality",
    "finding_sort_key",
    "quality_cost",
]
