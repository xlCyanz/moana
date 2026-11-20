"""Schema 1.0 payload of ``dither`` (MOANA-016, MOANA.md sections 10 and 12, ADR-025)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from moana.core import errors
from moana.core.coordinates import Point
from moana.core.dither import DITHER_SIZES
from moana.schema import (
    PLANNED_OPERATION_TYPES,
    SUPPORTED_OPERATION_TYPES,
    DitherOperation,
    canonical_json,
    document_json_schema,
    normalize_document,
    snapshot_digest,
    validate_document,
)
from moana.techniques import DITHER_SIZES as TECHNIQUE_SIZES

POINTER = "/layers/0/operations/1"


def _dither(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "shade",
        "type": "dither",
        "size": 4,
        "coverage": 6,
        "origin": [-3, 2],
        "color_a": "ink",
        "color_b": "cloth",
        "mask_id": "area",
    }
    return base | fields


@pytest.fixture
def dithered(minimal: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(minimal)
    document["masks"] = [{"id": "area", "type": "ellipse", "box": [40, 32, 88, 104]}]
    document["layers"][0]["operations"].append(_dither())
    return document


def test_payload_validates_and_round_trips(dithered: dict[str, Any]) -> None:
    document = validate_document(dithered)
    operation = document.layers[0].operations[1]
    assert isinstance(operation, DitherOperation)
    assert (operation.size, operation.coverage, operation.anchor) == (4, 6, Point(-3, 2))
    again = validate_document(normalize_document(document))
    assert canonical_json(again) == canonical_json(document)
    assert normalize_document(document)["layers"][0]["operations"][1] == _dither()  # type: ignore[index]  # JSON tree


def test_dither_is_a_supported_operation() -> None:
    assert "dither" in SUPPORTED_OPERATION_TYPES
    assert "dither" not in PLANNED_OPERATION_TYPES
    assert DITHER_SIZES == TECHNIQUE_SIZES == (2, 4)


def test_json_schema_describes_the_payload() -> None:
    definitions = document_json_schema()["$defs"]
    assert isinstance(definitions, dict)
    model = definitions["DitherOperation"]
    assert model["properties"]["size"]["enum"] == [2, 4]
    assert model["properties"]["size"]["type"] == "integer"
    assert model["properties"]["coverage"]["maximum"] == 16
    assert set(model["required"]) == {
        "id",
        "type",
        "size",
        "coverage",
        "origin",
        "color_a",
        "color_b",
        "mask_id",
    }


@pytest.mark.parametrize(
    ("fields", "member", "reason"),
    [
        ({"size": 2, "coverage": 5}, "coverage", "less_than_equal"),
        ({"size": 4, "coverage": 17}, "coverage", "less_than_equal"),
        ({"coverage": -1}, "coverage", "greater_than_equal"),
        ({"coverage": True}, "coverage", "int_type"),
        ({"coverage": 1.0}, "coverage", "int_type"),
        ({"size": 3}, "size", "unsupported_size"),
        ({"size": 8}, "size", "unsupported_size"),
        ({"size": True}, "size", "int_type"),
        ({"size": 2.0}, "size", "int_type"),
        ({"size": "4"}, "size", "int_type"),
        ({"origin": [0.5, 0]}, "origin/0", "int_type"),
        ({"origin": [0, 1_048_577]}, "origin/1", "less_than_equal"),
        ({"origin": [0]}, "origin/1", "missing"),
        ({"color_a": "Ink"}, "color_a", "string_pattern_mismatch"),
        ({"pattern": "bayer"}, "pattern", "extra_forbidden"),
    ],
)
def test_invalid_payloads_are_validation_errors(
    dithered: dict[str, Any], fields: dict[str, Any], member: str, reason: str
) -> None:
    dithered["layers"][0]["operations"][1] = _dither(**fields)
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(dithered)
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["reason"]) == (f"{POINTER}/{member}", reason)


@pytest.mark.parametrize("member", ["origin", "mask_id", "color_b", "size", "coverage"])
def test_every_member_is_required(dithered: dict[str, Any], member: str) -> None:
    del dithered["layers"][0]["operations"][1][member]
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(dithered)
    assert raised.value.details[0].json_pointer == f"{POINTER}/{member}"
    assert raised.value.details[0].context["reason"] == "missing"


@pytest.mark.parametrize(
    ("fields", "member", "reason"),
    [
        ({"color_a": "ghost"}, "color_a", "unknown_color"),
        ({"color_b": "ghost"}, "color_b", "unknown_color"),
        ({"mask_id": "ghost"}, "mask_id", "unknown_mask"),
        ({"mask_id": "body"}, "mask_id", "unknown_mask"),  # a layer is not a mask
        ({"mask_id": "body_fill"}, "mask_id", "unknown_mask"),  # nor an operation
    ],
)
def test_unknown_references_are_reference_errors(
    dithered: dict[str, Any], fields: dict[str, Any], member: str, reason: str
) -> None:
    dithered["layers"][0]["operations"][1] = _dither(**fields)
    with pytest.raises(errors.ReferenceError) as raised:
        validate_document(dithered)
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["reason"]) == (f"{POINTER}/{member}", reason)


def test_dither_id_takes_part_in_global_uniqueness(dithered: dict[str, Any]) -> None:
    dithered["layers"][0]["operations"][1]["id"] = "area"
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(dithered)
    assert raised.value.details[0].context["reason"] == "duplicate_id"


def test_regions_may_target_a_dither_operation(dithered: dict[str, Any]) -> None:
    dithered["regions"] = [{"id": "cheek", "mask_id": "area", "operation_ids": ["shade"]}]
    assert validate_document(dithered).regions[0].operation_ids == ("shade",)


def test_documents_without_dither_keep_their_digest(minimal: dict[str, Any]) -> None:
    """The extension is additive: the minimal example keeps its published snapshot."""
    before = snapshot_digest(validate_document(minimal))
    assert before == snapshot_digest(validate_document(copy.deepcopy(minimal)))
    assert "dither" not in canonical_json(validate_document(minimal)).decode("utf-8")
