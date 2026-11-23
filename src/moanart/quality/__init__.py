"""Graphic quality reports: hard checks, artistic heuristics and metrics (MOANART.md §19).

``quality`` reads rendered pixels and the document facts they must honour (canvas,
palette, region masks) and returns an immutable :class:`QualityReport`; it never
renders, edits, cleans or writes anything (ADR-036). It depends on ``core``,
``palette``, ``geometry`` (region masks) and ``techniques`` (the cluster analysis of
ADR-027 is reused, not reimplemented); no domain module imports it, and
:func:`moanart.api.evaluate_quality` composes it with the renderer.

Hard rules are mathematical conformance (``error``); soft rules are heuristics with
configurable thresholds (``warning``) that never reject anything. A report has no
aggregate score and is never a professional guarantee or a human review.

:func:`parse_rubric` validates the human rubric record of an example of the art
corpus (ADR-037): pending or person-reviewed categories, an optional labelled agent
assessment that never counts, and ``professional`` only with a human review scoring
every applicable category at least 4 and passed hard checks.
"""

from moanart.quality.config import (
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
from moanart.quality.evaluate import (
    EXPLANATIONS,
    MAX_QUALITY_FINDINGS,
    MIN_LISTED_PER_RULE,
    RasterImage,
    TimelineFrame,
    evaluate_quality,
    quality_cost,
)
from moanart.quality.report import (
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
from moanart.quality.rubric import (
    AGENT_NOTICE,
    ANIMATION_CATEGORIES,
    LEGACY_RUBRIC_FORMAT,
    MAX_RUBRIC_TEXT,
    MIN_PROFESSIONAL_SCORE,
    RUBRIC_CATEGORIES,
    RUBRIC_FORMAT,
    STATIC_CATEGORIES,
    AgentAssessment,
    CategoryResult,
    HumanReview,
    Rubric,
    RubricCategory,
    applicable_categories,
    migrate_rubric,
    parse_rubric,
)

__all__ = [
    "AGENT_NOTICE",
    "ANIMATION_CATEGORIES",
    "DEFAULT_MAX_CHANGED_PERMILLE",
    "DEFAULT_MAX_COLORS",
    "DEFAULT_MAX_LISTED_SINGLETONS",
    "DEFAULT_MAX_SINGLETON_PERMILLE",
    "DEFAULT_MIN_NOISE_SINGLETONS",
    "DEFAULT_RULES",
    "EXPLANATIONS",
    "HARD_RULES",
    "LEGACY_RUBRIC_FORMAT",
    "MAX_QUALITY_FINDINGS",
    "MAX_QUALITY_REGIONS",
    "MAX_RUBRIC_TEXT",
    "MIN_LISTED_PER_RULE",
    "MIN_PROFESSIONAL_SCORE",
    "QUALITY_RULES",
    "REPORT_NOTICE",
    "RUBRIC_CATEGORIES",
    "RUBRIC_FORMAT",
    "RULE_SET_VERSION",
    "RULE_SEVERITY",
    "SOFT_RULES",
    "STATIC_CATEGORIES",
    "AgentAssessment",
    "CategoryResult",
    "Evidence",
    "FrameMetrics",
    "HumanReview",
    "Metrics",
    "OmittedByRule",
    "QualityConfig",
    "QualityFinding",
    "QualityReport",
    "QualityRule",
    "RasterImage",
    "RegionMetrics",
    "RegionSettings",
    "Rubric",
    "RubricCategory",
    "Severity",
    "Suppression",
    "TimelineFrame",
    "applicable_categories",
    "evaluate_quality",
    "finding_sort_key",
    "migrate_rubric",
    "parse_rubric",
    "quality_cost",
]
