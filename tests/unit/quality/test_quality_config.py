"""Evaluation configuration of quality reports (MOANA-026): canonical, checked, frozen."""

from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from moana.core.errors import ValidationError
from moana.quality import (
    DEFAULT_RULES,
    HARD_RULES,
    MAX_QUALITY_REGIONS,
    QUALITY_RULES,
    RULE_SET_VERSION,
    RULE_SEVERITY,
    SOFT_RULES,
    QualityConfig,
    RegionSettings,
    Suppression,
)


def reason(error: pytest.ExceptionInfo[ValidationError]) -> object:
    return error.value.context["reason"]


def test_rules_are_split_into_hard_errors_and_soft_warnings() -> None:
    assert HARD_RULES + SOFT_RULES == QUALITY_RULES
    assert {RULE_SEVERITY[rule] for rule in HARD_RULES} == {"error"}
    assert {RULE_SEVERITY[rule] for rule in SOFT_RULES} == {"warning"}
    assert list(HARD_RULES) == [
        "canvas_dimensions",
        "alpha_normalized",
        "palette_strict",
        "outside_mask",
    ]


def test_defaults_and_canonical_mapping() -> None:
    config = QualityConfig()
    assert config.rules == DEFAULT_RULES and config.region_ids == ()
    assert "temporal_change" not in DEFAULT_RULES  # opt-in: a pose change is usually intended
    assert tuple(rule for rule in QUALITY_RULES if rule != "temporal_change") == DEFAULT_RULES
    assert (config.connectivity, config.cluster_connectivity) == (4, 8)
    mapping = config.to_mapping()
    assert mapping["rule_set"] == RULE_SET_VERSION == "quality-v1"
    assert (mapping["max_colors"], mapping["max_singleton_permille"]) == (32, 50)
    assert (mapping["min_noise_singletons"], mapping["max_changed_permille"]) == (8, 900)
    assert (mapping["max_listed_singletons"], mapping["cluster_connectivity"]) == (16, 8)
    text = json.dumps(mapping, sort_keys=True, separators=(",", ":"))
    assert config.digest == "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.max_colors = 3  # type: ignore[misc]  # frozen on purpose


def test_collections_are_canonicalised() -> None:
    first = QualityConfig(
        rules=["noise", "singleton"],  # type: ignore[arg-type]  # any sequence is accepted
        containment=["b", "a"],  # type: ignore[arg-type]
        regions=[RegionSettings("z"), RegionSettings("c", max_colors=4)],  # type: ignore[arg-type]
        suppressions=[
            Suppression("noise", "b"),
            Suppression("singleton", "a"),
            Suppression("singleton", "b"),
        ],  # type: ignore[arg-type]
    )
    assert first.rules == ("singleton", "noise")
    assert first.containment == ("a", "b")
    assert [item.region_id for item in first.regions] == ["c", "z"]
    assert [(s.region_id, s.rule_id) for s in first.suppressions] == [
        ("a", "singleton"),
        ("b", "singleton"),
        ("b", "noise"),
    ]
    assert first.region_ids == ("a", "b", "c", "z")
    assert first.enabled("noise") and not first.enabled("palette_strict")
    second = QualityConfig(
        rules=("singleton", "noise"),
        containment=("a", "b"),
        regions=(RegionSettings("c", max_colors=4), RegionSettings("z")),
        suppressions=(
            Suppression("singleton", "b"),
            Suppression("noise", "b"),
            Suppression("singleton", "a"),
        ),
    )
    assert first == second and first.digest == second.digest


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"rules": ("blur",)}, "unknown_rule"),
        ({"rules": ("noise", "noise")}, "duplicate_reference"),
        ({"connectivity": 6}, "unsupported"),
        ({"connectivity": True}, "unsupported"),
        ({"cluster_connectivity": 6}, "unsupported"),
        ({"containment": ("a", "a")}, "duplicate_reference"),
        ({"containment": ("A",)}, "invalid_id"),
        (
            {"regions": (RegionSettings("a"), RegionSettings("a", max_colors=2))},
            "duplicate_reference",
        ),
        (
            {"suppressions": (Suppression("noise", "a"), Suppression("noise", "a"))},
            "duplicate_reference",
        ),
        (
            {"containment": tuple(f"r{i}" for i in range(MAX_QUALITY_REGIONS + 1))},
            "too_many_regions",
        ),
    ],
)
def test_invalid_configuration(options: dict[str, object], expected: str) -> None:
    with pytest.raises(ValidationError) as caught:
        QualityConfig(**options)  # type: ignore[arg-type]  # invalid on purpose
    assert reason(caught) == expected


def test_region_limit_counts_distinct_regions() -> None:
    names = tuple(f"r{i}" for i in range(MAX_QUALITY_REGIONS))
    config = QualityConfig(
        containment=names,
        regions=tuple(RegionSettings(name) for name in names),
        suppressions=tuple(Suppression("noise", name) for name in names),
    )
    assert len(config.region_ids) == MAX_QUALITY_REGIONS


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"max_colors": 0}, "out_of_range"),
        ({"max_colors": 4097}, "out_of_range"),
        ({"max_colors": True}, "not_integer"),
        ({"max_singleton_permille": 1001}, "out_of_range"),
        ({"min_noise_singletons": 0}, "out_of_range"),
        ({"max_listed_singletons": -1}, "out_of_range"),
        ({"max_changed_permille": -1}, "out_of_range"),
        ({"max_changed_permille": 1.5}, "not_integer"),
    ],
)
def test_invalid_thresholds(options: dict[str, object], expected: str) -> None:
    with pytest.raises(ValidationError) as caught:
        QualityConfig(**options)  # type: ignore[arg-type]  # invalid on purpose
    assert reason(caught) == expected
    assert caught.value.context["field"] == next(iter(options))


@pytest.mark.parametrize(
    "options",
    [
        {"rules": "noise"},
        {"rules": 5},
        {"regions": ("a",)},
        {"suppressions": (("noise", "a"),)},
    ],
)
def test_invalid_collection_types(options: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        QualityConfig(**options)  # type: ignore[arg-type]  # invalid on purpose


def test_suppressions_and_region_settings_validate_their_fields() -> None:
    with pytest.raises(ValidationError) as caught:
        Suppression("blur", "eye")  # type: ignore[arg-type]  # invalid on purpose
    assert reason(caught) == "unknown_rule"
    with pytest.raises(ValidationError):
        Suppression("noise", "Eye")
    with pytest.raises(ValidationError):
        RegionSettings("eye", max_colors=0)
    with pytest.raises(ValidationError):
        RegionSettings("eye", max_singleton_permille=1001)
    with pytest.raises(ValidationError):
        RegionSettings("Eye")
    assert RegionSettings("eye", max_colors=3).to_mapping() == {
        "max_colors": 3,
        "max_singleton_permille": None,
        "region_id": "eye",
    }
    assert Suppression("noise", "eye").to_mapping() == {"region_id": "eye", "rule_id": "noise"}
