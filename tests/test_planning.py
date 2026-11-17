"""Negative tests protect the dependency/traceability gate from false success."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.planning import Issue, Requirement, validate_graph


def issue(identifier: str, dependencies: list[str] | None = None) -> Issue:
    return Issue(
        id=identifier,
        title="An independently testable module",
        phase="P1",
        status="planned",
        priority="P1",
        dependencies=dependencies or [],
        requirements=["R001"],
        scope="One observable result",
        out_of_scope="Unrelated modules",
        technical=["Bounded memory", "Immutable output"],
        acceptance=["Valid case succeeds", "Invalid case rejects before allocation"],
        tests=["Exact positive fixture", "Adversarial rejection"],
        evidence=[],
    )


def requirement(identifier: str = "R001") -> Requirement:
    return Requirement(
        id=identifier, description="A requirement", sections=[1], verification="Observable test"
    )


def test_dependency_order_is_deterministic_and_dependency_first() -> None:
    first = issue("MOA-001")
    second = issue("MOA-002", [first.id])
    third = issue("MOA-003", [first.id, second.id])
    assert validate_graph([third, first, second], [requirement()]) == [
        "MOA-001",
        "MOA-002",
        "MOA-003",
    ]


@pytest.mark.parametrize(
    "nodes, message",
    [
        ([issue("MOA-001", ["MOA-001"])], "cycle"),
        ([issue("MOA-001", ["MOA-002"]), issue("MOA-002", ["MOA-001"])], "cycle"),
        ([issue("MOA-001", ["MOA-999"])], "Unknown"),
        ([issue("MOA-001"), issue("MOA-001")], "Duplicate issue"),
        ([issue("MOA-001"), issue("MOA-002", ["MOA-001", "MOA-001"])], "Duplicate dependencies"),
    ],
)
def test_invalid_graphs_fail(nodes: list[Issue], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_graph(nodes, [requirement()])


def test_uncovered_and_unknown_requirements_fail() -> None:
    with pytest.raises(ValueError, match="Uncovered"):
        validate_graph([issue("MOA-001")], [requirement(), requirement("R002")])
    with pytest.raises(ValueError, match="Unknown"):
        validate_graph([issue("MOA-001")], [requirement("R002")])


def test_duplicate_requirement_ids_fail() -> None:
    with pytest.raises(ValueError, match="Duplicate requirement"):
        validate_graph([issue("MOA-001")], [requirement(), requirement()])


def test_completed_issue_requires_evidence_and_completed_dependencies() -> None:
    parent = issue("MOA-001")
    child = issue("MOA-002", [parent.id])
    child.status = "done"
    with pytest.raises(ValueError, match="without evidence"):
        validate_graph([parent, child], [requirement()])
    child.evidence = ["Command and observed result"]
    with pytest.raises(ValueError, match="unfinished dependencies"):
        validate_graph([parent, child], [requirement()])
    parent.status = "done"
    parent.evidence = ["Observed test result"]
    assert validate_graph([parent, child], [requirement()]) == [parent.id, child.id]


def test_phase_inversion_is_rejected() -> None:
    parent = issue("MOA-001")
    parent.phase = "P5"
    with pytest.raises(ValueError, match="Phase inversion"):
        validate_graph([parent, issue("MOA-002", [parent.id])], [requirement()])


def test_empty_acceptance_and_unknown_fields_are_rejected() -> None:
    data = issue("MOA-001").model_dump()
    data["acceptance"] = []
    with pytest.raises(ValidationError):
        Issue.model_validate(data)
    data = issue("MOA-001").model_dump()
    data["unreviewed_setting"] = True
    with pytest.raises(ValidationError):
        Issue.model_validate(data)
