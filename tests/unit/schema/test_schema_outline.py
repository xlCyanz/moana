"""Schema 1.0 payload of ``outline`` (MOANA-014, MOANA.md sections 8 and 12, ADR-027)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from moana.core import errors
from moana.core.limits import MAX_MORPHOLOGY_RADIUS
from moana.schema import (
    OPERATION_MEMBERS,
    PLANNED_OPERATION_TYPES,
    SUPPORTED_OPERATION_TYPES,
    NodeMembers,
    OutlineOperation,
    canonical_json,
    document_json_schema,
    normalize_document,
    validate_document,
)
from moana.techniques import MAX_OUTLINE_WIDTH

POINTER = "/layers/0/operations/1"


def _outline(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "rim",
        "type": "outline",
        "mask_id": "area",
        "width": 2,
        "side": "outer",
        "color": "ink",
    }
    return base | fields


@pytest.fixture
def outlined(minimal: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(minimal)
    document["masks"] = [{"id": "area", "type": "ellipse", "box": [40, 32, 88, 104]}]
    document["layers"][0]["operations"].append(_outline())
    return document


def test_payload_validates_and_round_trips(outlined: dict[str, Any]) -> None:
    document = validate_document(outlined)
    operation = document.layers[0].operations[1]
    assert isinstance(operation, OutlineOperation)
    assert (operation.mask_id, operation.width, operation.side) == ("area", 2, "outer")
    again = validate_document(normalize_document(document))
    assert canonical_json(again) == canonical_json(document)
    assert normalize_document(document)["layers"][0]["operations"][1] == _outline()  # type: ignore[index]  # JSON tree


def test_outline_is_supported_with_one_colour_one_mask_and_no_geometry() -> None:
    assert "outline" in SUPPORTED_OPERATION_TYPES
    assert "outline" not in PLANNED_OPERATION_TYPES
    assert OPERATION_MEMBERS["outline"] == NodeMembers(
        colors=("color",), masks=("mask_id",), geometry=()
    )
    assert MAX_OUTLINE_WIDTH == MAX_MORPHOLOGY_RADIUS == 16


def test_json_schema_describes_the_payload() -> None:
    definitions = document_json_schema()["$defs"]
    assert isinstance(definitions, dict)
    model = definitions["OutlineOperation"]
    assert model["properties"]["width"]["minimum"] == 1
    assert model["properties"]["width"]["maximum"] == 16
    assert model["properties"]["side"]["enum"] == ["outer", "inner"]
    assert set(model["required"]) == {"id", "type", "mask_id", "width", "side", "color"}


@pytest.mark.parametrize(
    ("fields", "member", "reason"),
    [
        ({"width": 0}, "width", "greater_than_equal"),
        ({"width": 17}, "width", "less_than_equal"),
        ({"width": True}, "width", "int_type"),
        ({"width": 1.0}, "width", "int_type"),
        ({"width": "1"}, "width", "int_type"),
        ({"side": "both"}, "side", "literal_error"),
        ({"side": "Outer"}, "side", "literal_error"),
        ({"color": "Ink"}, "color", "string_pattern_mismatch"),
        ({"mask_id": 3}, "mask_id", "string_type"),
        ({"connectivity": 8}, "connectivity", "extra_forbidden"),
    ],
)
def test_invalid_payloads_are_validation_errors(
    outlined: dict[str, Any], fields: dict[str, Any], member: str, reason: str
) -> None:
    outlined["layers"][0]["operations"][1] = _outline(**fields)
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(outlined)
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["reason"]) == (f"{POINTER}/{member}", reason)


@pytest.mark.parametrize("member", ["mask_id", "width", "side", "color"])
def test_every_member_is_required(outlined: dict[str, Any], member: str) -> None:
    del outlined["layers"][0]["operations"][1][member]
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(outlined)
    assert raised.value.details[0].json_pointer == f"{POINTER}/{member}"
    assert raised.value.details[0].context["reason"] == "missing"


@pytest.mark.parametrize(
    ("fields", "member", "reason"),
    [
        ({"color": "ghost"}, "color", "unknown_color"),
        ({"mask_id": "ghost"}, "mask_id", "unknown_mask"),
        ({"mask_id": "body"}, "mask_id", "unknown_mask"),  # a layer is not a mask
    ],
)
def test_unknown_references_are_reference_errors(
    outlined: dict[str, Any], fields: dict[str, Any], member: str, reason: str
) -> None:
    outlined["layers"][0]["operations"][1] = _outline(**fields)
    with pytest.raises(errors.ReferenceError) as raised:
        validate_document(outlined)
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["reason"]) == (f"{POINTER}/{member}", reason)


def test_documents_without_outline_keep_their_canonical_form(minimal: dict[str, Any]) -> None:
    assert "outline" not in canonical_json(validate_document(minimal)).decode("utf-8")
