"""Human art rubric records and the professional rule (MOANART.md section 19, ADR-037).

A rubric record states how a **person** judged one example of the art corpus: a score
from 1 to 5 with a justification for every applicable category (legibility at 1x,
silhouette, clusters, palette, light/material and, only for an animation, temporal
continuity). :func:`parse_rubric` turns the JSON object of a record into a frozen
:class:`Rubric` and enforces, without reading files or rendering anything:

* the record has exactly the applicable categories (``missing_category``,
  ``not_applicable``); a category is either ``pending_human_review`` (no score, no
  justification) or ``reviewed`` (integer score 1-5, a justification with a letter or number);
* a reviewed category exists only with a ``human_review`` (reviewer, ``reviewer_kind``
  ``"human"``, an ISO date and the ``render_fingerprint`` of the reviewed render), and
  a human review covers every category
  (``missing_human_review``, ``incomplete_review``);
* an optional ``agent_assessment`` carries the fixed :data:`AGENT_NOTICE` and
  ``assessor_kind`` ``"ai_agent"``; its scores never count for anything;
* ``professional`` may be ``true`` only when the hard checks passed, a human review
  exists and every applicable category scored at least
  :data:`MIN_PROFESSIONAL_SCORE` (``not_professional``).

An agent can therefore record its own opinion, clearly labelled, but can never make
an example professional: that needs a person's review recorded with their name. The
module only checks the structure of what was recorded; whether the reviewer really
is a person is a fact of the review process, not of the data.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal, get_args

from moanart.core.errors import UnsupportedVersion, ValidationError

__all__ = [
    "AGENT_NOTICE",
    "ANIMATION_CATEGORIES",
    "LEGACY_RUBRIC_FORMAT",
    "MAX_RUBRIC_TEXT",
    "MIN_PROFESSIONAL_SCORE",
    "RUBRIC_CATEGORIES",
    "RUBRIC_FORMAT",
    "STATIC_CATEGORIES",
    "AgentAssessment",
    "CategoryResult",
    "HumanReview",
    "Rubric",
    "RubricCategory",
    "applicable_categories",
    "migrate_rubric",
    "parse_rubric",
]

RUBRIC_FORMAT: Final = "moanart-rubric/1"
LEGACY_RUBRIC_FORMAT: Final = "moana-rubric/1"
"""Format of 0.1.0rc1, before the rename of ADR-041; read only by :func:`migrate_rubric`."""
RubricCategory = Literal[
    "legibility",
    "silhouette",
    "clusters",
    "palette",
    "light_material",
    "temporal_continuity",
]
RUBRIC_CATEGORIES: Final[tuple[RubricCategory, ...]] = get_args(RubricCategory)
STATIC_CATEGORIES: Final[tuple[RubricCategory, ...]] = RUBRIC_CATEGORIES[:5]
"""Categories of a still image; ``temporal_continuity`` only applies to animations."""
ANIMATION_CATEGORIES: Final[tuple[RubricCategory, ...]] = RUBRIC_CATEGORIES
MIN_PROFESSIONAL_SCORE: Final = 4
MAX_RUBRIC_TEXT: Final = 2000
AGENT_NOTICE: Final = (
    "AI agent assessment: not a human review and never an approval; "
    "it does not count towards the professional rule."
)
CategoryStatus = Literal["pending_human_review", "reviewed"]
_PENDING: Final[CategoryStatus] = "pending_human_review"
_REVIEWED: Final[CategoryStatus] = "reviewed"
_KEYS: Final = frozenset(
    {"format", "categories", "human_review", "agent_assessment", "professional"}
)
_REVIEW_KEYS: Final = frozenset({"reviewer", "reviewer_kind", "date", "render_fingerprint"})
_AGENT_KEYS: Final = frozenset({"notice", "assessor_kind", "agent", "date", "scores"})
_SCORE_KEYS: Final = frozenset({"score", "justification"})
_CATEGORY_KEYS: Final = frozenset({"status", "score", "justification"})
_DATE: Final = re.compile(r"\d{4}-\d{2}-\d{2}")
_FINGERPRINT: Final = re.compile(r"sha256:[0-9a-f]{64}")


def _invalid(pointer: str, message: str, reason: str, **extra: str | int) -> ValidationError:
    return ValidationError(message, context={"field": pointer, "reason": reason, **extra})


def _object(value: object, pointer: str, keys: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(type(key) is str for key in value):
        raise _invalid(pointer, "expected a JSON object", "invalid_type")
    unknown = sorted(set(value) - keys)
    if unknown:
        raise _invalid(f"{pointer}/{unknown[0]}", "unknown member", "unknown_field")
    missing = sorted(keys - set(value))
    if missing:
        raise _invalid(f"{pointer}/{missing[0]}", "missing member", "missing_field")
    return value


def _text(value: object, pointer: str) -> str:
    if (
        type(value) is not str
        or not any(char.isalnum() for char in value)
        or len(value) > MAX_RUBRIC_TEXT
    ):
        raise _invalid(pointer, "expected a text with a letter or number", "invalid_text")
    return value


def _score(value: object, pointer: str) -> int:
    if type(value) is not int or not 1 <= value <= 5:
        raise _invalid(pointer, "a score is an integer from 1 to 5", "invalid_score")
    return value


def _iso_date(value: object, pointer: str) -> str:
    if type(value) is str and _DATE.fullmatch(value):
        try:
            date.fromisoformat(value)
        except ValueError:
            pass
        else:
            return value
    raise _invalid(pointer, "expected an ISO date YYYY-MM-DD", "invalid_date")


def _fingerprint(value: object) -> str:
    if type(value) is str and _FINGERPRINT.fullmatch(value):
        return value
    raise _invalid(
        "/human_review/render_fingerprint", "expected sha256:<64 hex>", "invalid_fingerprint"
    )


def _constant(value: object, expected: str, pointer: str) -> str:
    if value != expected:
        raise _invalid(pointer, "unexpected value", "invalid_value", expected=expected)
    return expected


@dataclass(frozen=True, slots=True)
class CategoryResult:
    """One category of a record: pending (no score) or reviewed by a person."""

    category: RubricCategory
    status: CategoryStatus
    score: int | None
    justification: str | None


@dataclass(frozen=True, slots=True)
class HumanReview:
    """Who reviewed the example, when, and which render they saw.

    ``reviewer_kind`` is always ``"human"``. ``render_fingerprint`` (``sha256:`` and
    64 lowercase hex digits) identifies the rendered pixels the person judged; the
    caller compares it with the current render to detect art changed afterwards.
    """

    reviewer: str
    date: str
    render_fingerprint: str


@dataclass(frozen=True, slots=True)
class AgentAssessment:
    """An AI agent's labelled opinion; informative only, never an approval."""

    agent: str
    date: str
    scores: tuple[tuple[RubricCategory, int, str], ...]


@dataclass(frozen=True, slots=True)
class Rubric:
    """A validated rubric record of one corpus example."""

    animated: bool
    categories: tuple[CategoryResult, ...]
    human_review: HumanReview | None
    agent_assessment: AgentAssessment | None
    professional: bool

    @property
    def pending(self) -> tuple[RubricCategory, ...]:
        """Categories still waiting for a person's review."""
        return tuple(item.category for item in self.categories if item.status == _PENDING)

    @property
    def meets_professional_bar(self) -> bool:
        """A person reviewed every category and every score is at least 4."""
        return self.human_review is not None and all(
            item.score is not None and item.score >= MIN_PROFESSIONAL_SCORE
            for item in self.categories
        )


def applicable_categories(*, animated: bool) -> tuple[RubricCategory, ...]:
    """The categories a record must hold: temporal continuity only for animations."""
    return ANIMATION_CATEGORIES if animated else STATIC_CATEGORIES


def _category(name: RubricCategory, value: object, pointer: str) -> CategoryResult:
    item = _object(value, pointer, _CATEGORY_KEYS)
    status = item["status"]
    if status == _PENDING:
        if item["score"] is not None or item["justification"] is not None:
            raise _invalid(pointer, "a pending category has no score", "pending_with_score")
        return CategoryResult(name, _PENDING, None, None)
    _constant(status, _REVIEWED, f"{pointer}/status")
    score = _score(item["score"], f"{pointer}/score")
    return CategoryResult(
        name, _REVIEWED, score, _text(item["justification"], f"{pointer}/justification")
    )


def _categories(value: object, animated: bool) -> tuple[CategoryResult, ...]:
    expected = applicable_categories(animated=animated)
    if not isinstance(value, Mapping):
        raise _invalid("/categories", "expected a JSON object", "invalid_type")
    for name in value:
        if name not in expected:
            raise _invalid(f"/categories/{name}", "category does not apply", "not_applicable")
    for name in expected:
        if name not in value:
            raise _invalid(f"/categories/{name}", "category is missing", "missing_category")
    return tuple(_category(name, value[name], f"/categories/{name}") for name in expected)


def _human_review(value: object) -> HumanReview | None:
    if value is None:
        return None
    item = _object(value, "/human_review", _REVIEW_KEYS)
    _constant(item["reviewer_kind"], "human", "/human_review/reviewer_kind")
    return HumanReview(
        reviewer=_text(item["reviewer"], "/human_review/reviewer"),
        date=_iso_date(item["date"], "/human_review/date"),
        render_fingerprint=_fingerprint(item["render_fingerprint"]),
    )


def _agent_assessment(value: object, animated: bool) -> AgentAssessment | None:
    if value is None:
        return None
    item = _object(value, "/agent_assessment", _AGENT_KEYS)
    _constant(item["notice"], AGENT_NOTICE, "/agent_assessment/notice")
    _constant(item["assessor_kind"], "ai_agent", "/agent_assessment/assessor_kind")
    scores = item["scores"]
    if not isinstance(scores, Mapping):
        raise _invalid("/agent_assessment/scores", "expected a JSON object", "invalid_type")
    expected = applicable_categories(animated=animated)
    entries: list[tuple[RubricCategory, int, str]] = []
    for name in expected:
        if name in scores:
            pointer = f"/agent_assessment/scores/{name}"
            entry = _object(scores[name], pointer, _SCORE_KEYS)
            score = _score(entry["score"], f"{pointer}/score")
            entries.append((name, score, _text(entry["justification"], f"{pointer}/justification")))
    if len(entries) != len(scores):
        raise _invalid("/agent_assessment/scores", "category does not apply", "not_applicable")
    return AgentAssessment(
        agent=_text(item["agent"], "/agent_assessment/agent"),
        date=_iso_date(item["date"], "/agent_assessment/date"),
        scores=tuple(entries),
    )


def _check_review(rubric: Rubric) -> None:
    reviewed = len(rubric.categories) - len(rubric.pending)
    if rubric.human_review is None and reviewed:
        raise _invalid(
            "/human_review", "reviewed categories need a human review", "missing_human_review"
        )
    if rubric.human_review is not None and rubric.pending:
        raise _invalid(
            f"/categories/{rubric.pending[0]}",
            "a human review scores every applicable category",
            "incomplete_review",
        )


def _check_professional(rubric: Rubric, passed_hard_checks: bool) -> None:
    if not rubric.professional:
        return
    if not passed_hard_checks:
        raise _invalid(
            "/professional", "a hard check failed", "not_professional", cause="hard_checks"
        )
    if rubric.human_review is None:
        raise _invalid(
            "/professional",
            "no human review is recorded",
            "not_professional",
            cause="no_human_review",
        )
    if not rubric.meets_professional_bar:
        raise _invalid(
            "/professional",
            f"every category needs a score of at least {MIN_PROFESSIONAL_SCORE}",
            "not_professional",
            cause="low_score",
        )


def migrate_rubric(record: object) -> dict[str, object]:
    """A copy of a 0.1.0rc1 rubric record in the current format (ADR-041).

    Pure: the result is a deep copy, so ``record`` is never modified, and only
    ``format`` changes: the reviews, the scores and the render digest they are bound
    to are kept. It is not validated here; the caller passes it to
    :func:`parse_rubric`. A record that is not of the legacy format is
    ``ValidationError`` ``not_legacy``.
    """
    if not isinstance(record, Mapping) or record.get("format") != LEGACY_RUBRIC_FORMAT:
        raise _invalid("/format", "not a rubric of the legacy format", "not_legacy")
    return {**copy.deepcopy(dict(record)), "format": RUBRIC_FORMAT}


def parse_rubric(record: object, *, animated: bool, passed_hard_checks: bool) -> Rubric:
    """Validate a rubric record (a JSON object) and return it as a frozen :class:`Rubric`.

    ``animated`` selects the applicable categories; ``passed_hard_checks`` is the
    outcome of the example's quality report (:func:`moanart.api.evaluate_quality`).
    Raises ``TypeError`` when the flags are not ``bool`` and ``ValidationError``
    with ``context["field"]`` (a JSON pointer inside the record) and
    ``context["reason"]`` for every violation listed in the module docstring.
    """
    if type(animated) is not bool or type(passed_hard_checks) is not bool:
        raise TypeError("animated and passed_hard_checks must be bool")
    item = _object(record, "", _KEYS)
    if item["format"] == LEGACY_RUBRIC_FORMAT:
        raise UnsupportedVersion(
            "the rubric was written before the MoanArt rename; migrate it with migrate_rubric",
            json_pointer="/format",
            context={"field": "/format", "reason": "legacy_name", "replacement": RUBRIC_FORMAT},
        )
    _constant(item["format"], RUBRIC_FORMAT, "/format")
    professional = item["professional"]
    if type(professional) is not bool:
        raise _invalid("/professional", "professional must be a boolean", "invalid_type")
    rubric = Rubric(
        animated=animated,
        categories=_categories(item["categories"], animated),
        human_review=_human_review(item["human_review"]),
        agent_assessment=_agent_assessment(item["agent_assessment"], animated),
        professional=professional,
    )
    _check_review(rubric)
    _check_professional(rubric, passed_hard_checks)
    return rubric
