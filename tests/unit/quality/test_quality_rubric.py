"""MOANA-027 AC2: only a person's review with >= 4 everywhere makes an example professional.

The human review below is a **test fixture**, not a review: its reviewer is the
literal ``"fixture"`` and it exists only to show that a well-formed record is
accepted. No example of the real corpus has a human review (see
``tests/integration/test_art_corpus.py``).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from moanart.core.errors import UnsupportedVersion, ValidationError
from moanart.quality import (
    AGENT_NOTICE,
    ANIMATION_CATEGORIES,
    MIN_PROFESSIONAL_SCORE,
    RUBRIC_CATEGORIES,
    STATIC_CATEGORIES,
    applicable_categories,
    migrate_rubric,
    parse_rubric,
)

FINGERPRINT = "sha256:" + "0" * 64


def pending(animated: bool = False) -> dict[str, Any]:
    return {
        "format": "moanart-rubric/1",
        "categories": {
            name: {"status": "pending_human_review", "score": None, "justification": None}
            for name in applicable_categories(animated=animated)
        },
        "human_review": None,
        "agent_assessment": None,
        "professional": False,
    }


def reviewed(score: int = 4, animated: bool = False) -> dict[str, Any]:
    record = pending(animated)
    for name in record["categories"]:
        record["categories"][name] = {
            "status": "reviewed",
            "score": score,
            "justification": "fixture justification",
        }
    record["human_review"] = {
        "reviewer": "fixture",
        "reviewer_kind": "human",
        "date": "2026-11-19",
        "render_fingerprint": FINGERPRINT,
    }
    return record


def agent(scores: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "notice": AGENT_NOTICE,
        "assessor_kind": "ai_agent",
        "agent": "test agent",
        "date": "2026-11-19",
        "scores": {"legibility": {"score": 5, "justification": "agent opinion"}}
        if scores is None
        else scores,
    }


def reason(record: object, *, animated: bool = False, passed: bool = True) -> tuple[str, str]:
    with pytest.raises(ValidationError) as caught:
        parse_rubric(record, animated=animated, passed_hard_checks=passed)
    context = caught.value.context
    return str(context["field"]), str(context["reason"])


def test_categories_follow_section_19() -> None:
    assert RUBRIC_CATEGORIES == (
        "legibility",
        "silhouette",
        "clusters",
        "palette",
        "light_material",
        "temporal_continuity",
    )
    assert RUBRIC_CATEGORIES[:5] == STATIC_CATEGORIES
    assert applicable_categories(animated=True) == ANIMATION_CATEGORIES == RUBRIC_CATEGORIES
    assert applicable_categories(animated=False) == STATIC_CATEGORIES
    assert MIN_PROFESSIONAL_SCORE == 4


@pytest.mark.parametrize("animated", [False, True])
def test_pending_record_is_accepted_and_not_professional(animated: bool) -> None:
    rubric = parse_rubric(pending(animated), animated=animated, passed_hard_checks=True)
    assert rubric.pending == applicable_categories(animated=animated)
    assert rubric.human_review is None
    assert not rubric.professional
    assert not rubric.meets_professional_bar


@pytest.mark.parametrize("animated", [False, True])
def test_fixture_human_review_makes_a_professional_example(animated: bool) -> None:
    record = reviewed(MIN_PROFESSIONAL_SCORE, animated)
    record["professional"] = True
    rubric = parse_rubric(record, animated=animated, passed_hard_checks=True)
    assert rubric.professional and rubric.meets_professional_bar
    assert rubric.pending == ()
    assert rubric.human_review is not None
    assert rubric.human_review.reviewer == "fixture"
    assert all(item.score == MIN_PROFESSIONAL_SCORE for item in rubric.categories)


def test_reviewed_but_not_claimed_professional_is_accepted() -> None:
    rubric = parse_rubric(reviewed(2), animated=False, passed_hard_checks=False)
    assert not rubric.professional
    assert not rubric.meets_professional_bar


def test_professional_without_human_review_is_rejected() -> None:
    record = pending()
    record["professional"] = True
    with pytest.raises(ValidationError) as caught:
        parse_rubric(record, animated=False, passed_hard_checks=True)
    assert caught.value.context["reason"] == "not_professional"
    assert caught.value.context["cause"] == "no_human_review"


def test_agent_assessment_never_makes_an_example_professional() -> None:
    record = pending()
    record["agent_assessment"] = agent(
        {name: {"score": 5, "justification": "agent opinion"} for name in STATIC_CATEGORIES}
    )
    rubric = parse_rubric(record, animated=False, passed_hard_checks=True)
    assert rubric.agent_assessment is not None
    assert rubric.agent_assessment.scores[0] == ("legibility", 5, "agent opinion")
    assert not rubric.meets_professional_bar
    record["professional"] = True
    assert reason(record) == ("/professional", "not_professional")


def test_one_low_score_blocks_professional() -> None:
    record = reviewed(5, animated=True)
    record["categories"]["temporal_continuity"]["score"] = MIN_PROFESSIONAL_SCORE - 1
    record["professional"] = True
    with pytest.raises(ValidationError) as caught:
        parse_rubric(record, animated=True, passed_hard_checks=True)
    assert caught.value.context["cause"] == "low_score"


def test_failed_hard_checks_block_professional() -> None:
    record = reviewed(5)
    record["professional"] = True
    with pytest.raises(ValidationError) as caught:
        parse_rubric(record, animated=False, passed_hard_checks=False)
    assert caught.value.context["cause"] == "hard_checks"


def test_reviewed_category_needs_a_human_review() -> None:
    record = reviewed(4)
    record["human_review"] = None
    assert reason(record) == ("/human_review", "missing_human_review")


def test_human_review_must_cover_every_category() -> None:
    record = reviewed(4)
    record["categories"]["palette"] = {
        "status": "pending_human_review",
        "score": None,
        "justification": None,
    }
    assert reason(record) == ("/categories/palette", "incomplete_review")


def mutate(path: tuple[str, ...], value: object, base: dict[str, Any]) -> dict[str, Any]:
    record = copy.deepcopy(base)
    node = record
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return record


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("format",), "moanart-rubric/2", ("/format", "invalid_value")),
        (("professional",), 1, ("/professional", "invalid_type")),
        (("professional",), "true", ("/professional", "invalid_type")),
        (("categories",), [], ("/categories", "invalid_type")),
        (
            ("categories", "temporal_continuity"),
            {"status": "pending_human_review", "score": None, "justification": None},
            ("/categories/temporal_continuity", "not_applicable"),
        ),
        (
            ("categories", "palette", "status"),
            "approved",
            ("/categories/palette/status", "invalid_value"),
        ),
        (("categories", "palette", "score"), 3, ("/categories/palette", "pending_with_score")),
        (
            ("categories", "palette", "justification"),
            "early note",
            ("/categories/palette", "pending_with_score"),
        ),
        (("categories", "palette"), "pending", ("/categories/palette", "invalid_type")),
        (("categories", "palette", "extra"), 1, ("/categories/palette/extra", "unknown_field")),
        (("agent_assessment",), [], ("/agent_assessment", "invalid_type")),
        (
            ("agent_assessment",),
            {**agent(), "notice": "x"},
            ("/agent_assessment/notice", "invalid_value"),
        ),
        (
            ("agent_assessment",),
            {**agent(), "assessor_kind": "human"},
            ("/agent_assessment/assessor_kind", "invalid_value"),
        ),
        (
            ("agent_assessment",),
            {**agent(), "scores": []},
            ("/agent_assessment/scores", "invalid_type"),
        ),
        (
            ("agent_assessment",),
            agent({"temporal_continuity": {"score": 4, "justification": "x"}}),
            ("/agent_assessment/scores", "not_applicable"),
        ),
        (
            ("agent_assessment",),
            agent({"legibility": {"score": 6, "justification": "x"}}),
            ("/agent_assessment/scores/legibility/score", "invalid_score"),
        ),
        (
            ("agent_assessment",),
            {**agent(), "agent": " "},
            ("/agent_assessment/agent", "invalid_text"),
        ),
        (
            ("agent_assessment",),
            {**agent(), "date": "19/11/2026"},
            ("/agent_assessment/date", "invalid_date"),
        ),
    ],
)
def test_malformed_pending_records_are_rejected(
    path: tuple[str, ...], value: object, expected: tuple[str, str]
) -> None:
    assert reason(mutate(path, value, pending())) == expected


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("categories", "clusters", "score"), 0, ("/categories/clusters/score", "invalid_score")),
        (
            ("categories", "clusters", "score"),
            True,
            ("/categories/clusters/score", "invalid_score"),
        ),
        (
            ("categories", "clusters", "score"),
            None,
            ("/categories/clusters/score", "invalid_score"),
        ),
        (
            ("categories", "clusters", "justification"),
            "   ",
            ("/categories/clusters/justification", "invalid_text"),
        ),
        (
            ("categories", "clusters", "justification"),
            "x" * 2001,
            ("/categories/clusters/justification", "invalid_text"),
        ),
        (
            ("human_review", "reviewer_kind"),
            "ai_agent",
            ("/human_review/reviewer_kind", "invalid_value"),
        ),
        (("human_review", "reviewer"), "", ("/human_review/reviewer", "invalid_text")),
        (("human_review", "reviewer"), "\u200b\u200b", ("/human_review/reviewer", "invalid_text")),
        (
            ("human_review", "reviewer_kind"),
            "Human",
            ("/human_review/reviewer_kind", "invalid_value"),
        ),
        (
            ("human_review", "reviewer_kind"),
            "HUMAN",
            ("/human_review/reviewer_kind", "invalid_value"),
        ),
        (
            ("human_review", "reviewer_kind"),
            " human",
            ("/human_review/reviewer_kind", "invalid_value"),
        ),
        (
            ("human_review", "reviewer_kind"),
            "person",
            ("/human_review/reviewer_kind", "invalid_value"),
        ),
        (("categories", "clusters", "score"), 4.0, ("/categories/clusters/score", "invalid_score")),
        (
            ("human_review", "render_fingerprint"),
            "sha256:" + "A" * 64,
            ("/human_review/render_fingerprint", "invalid_fingerprint"),
        ),
        (
            ("human_review", "render_fingerprint"),
            None,
            ("/human_review/render_fingerprint", "invalid_fingerprint"),
        ),
        (("human_review", "date"), "2026-02-30", ("/human_review/date", "invalid_date")),
        (("human_review", "date"), 20261119, ("/human_review/date", "invalid_date")),
        (("human_review",), "fixture", ("/human_review", "invalid_type")),
    ],
)
def test_malformed_reviews_are_rejected(
    path: tuple[str, ...], value: object, expected: tuple[str, str]
) -> None:
    assert reason(mutate(path, value, reviewed())) == expected


def test_static_record_is_incomplete_for_an_animation() -> None:
    assert reason(pending(animated=False), animated=True) == (
        "/categories/temporal_continuity",
        "missing_category",
    )


def test_human_review_keeps_the_reviewed_render() -> None:
    rubric = parse_rubric(reviewed(), animated=False, passed_hard_checks=True)
    assert rubric.human_review is not None
    assert rubric.human_review.render_fingerprint == FINGERPRINT


def test_missing_and_unknown_members_are_rejected() -> None:
    record = pending()
    del record["categories"]["silhouette"]
    assert reason(record) == ("/categories/silhouette", "missing_category")
    record = pending()
    del record["professional"]
    assert reason(record) == ("/professional", "missing_field")
    assert reason({**pending(), "score": 5}) == ("/score", "unknown_field")
    assert reason({1: "x"}) == ("", "invalid_type")
    assert reason(None) == ("", "invalid_type")


def test_flags_must_be_bool() -> None:
    with pytest.raises(TypeError):
        parse_rubric(pending(), animated=1, passed_hard_checks=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        parse_rubric(pending(), animated=False, passed_hard_checks=None)  # type: ignore[arg-type]


def test_records_are_frozen() -> None:
    rubric = parse_rubric(reviewed(), animated=False, passed_hard_checks=True)
    with pytest.raises(AttributeError):
        rubric.professional = True  # type: ignore[misc]


# MOANA-037 T3: rubric records written by 0.1.0rc1, before the rename (ADR-041).
def legacy(record: dict[str, Any]) -> dict[str, Any]:
    assert record["format"] == "moanart-rubric/1"
    return {**record, "format": "moana-rubric/1"}


@pytest.mark.parametrize("animated", [False, True])
def test_t3_legacy_rubric_is_rejected_then_migrated(animated: bool) -> None:
    record = legacy(reviewed(animated=animated))
    original = copy.deepcopy(record)
    with pytest.raises(UnsupportedVersion) as error:
        parse_rubric(record, animated=animated, passed_hard_checks=True)
    assert error.value.context == {
        "field": "/format",
        "reason": "legacy_name",
        "replacement": "moanart-rubric/1",
    }
    assert "migrate_rubric" in error.value.message
    migrated = migrate_rubric(record)
    assert record == original
    assert migrated == reviewed(animated=animated)
    rubric = parse_rubric(migrated, animated=animated, passed_hard_checks=True)
    assert rubric == parse_rubric(
        reviewed(animated=animated), animated=animated, passed_hard_checks=True
    )


@pytest.mark.parametrize("record", [pending(), {"format": "other"}, [], None])
def test_t3_only_legacy_rubrics_migrate(record: object) -> None:
    with pytest.raises(ValidationError) as error:
        migrate_rubric(record)
    assert error.value.context["reason"] == "not_legacy"


def test_t3_real_rc1_rubric_migrates_and_parses() -> None:
    import json
    from pathlib import Path

    entry = json.loads(
        (Path(__file__).resolve().parents[2] / "fixtures/rename/rc1/frog.corpus.json").read_text(
            encoding="utf-8"
        )
    )
    record = entry["rubric"]
    with pytest.raises(UnsupportedVersion):
        parse_rubric(record, animated=False, passed_hard_checks=True)
    rubric = parse_rubric(migrate_rubric(record), animated=False, passed_hard_checks=True)
    assert rubric.professional is False  # no human review: still pending after the rename
