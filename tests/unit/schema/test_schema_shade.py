"""Schema 1.0 payload of ``shade`` (MOANA-015, MOANART.md sections 9, 10 and 12, ADR-028)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from moanart.core import errors
from moanart.schema import (
    OPERATION_MEMBERS,
    PLANNED_OPERATION_TYPES,
    SUPPORTED_OPERATION_TYPES,
    NodeMembers,
    ShadeOperation,
    canonical_json,
    document_ids,
    document_json_schema,
    normalize_document,
    validate_document,
)

POINTER = "/layers/0/operations/1"


def _band(**fields: Any) -> dict[str, Any]:
    return {"id": "lit", "mask_id": "area", "facing": "nw", "offset": 0} | fields


def _light(**fields: Any) -> dict[str, Any]:
    return {"light": {"direction": "n", "height": 0, "intensity": 0, "ambient": 0} | fields}


def _shade(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "shading",
        "type": "shade",
        "ramp": "tones",
        "ramp_order": "monotonic",
        "light": {"direction": "nw", "height": 1, "intensity": 2, "ambient": 1},
        "bands": [_band()],
    }
    return base | fields


@pytest.fixture
def shaded(minimal: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(minimal)
    document["palette"]["ramps"] = [{"id": "tones", "colors": ["ink", "cloth"]}]
    document["masks"] = [{"id": "area", "type": "ellipse", "box": [40, 32, 88, 104]}]
    document["layers"][0]["operations"].append(_shade())
    return document


def test_payload_validates_and_round_trips(shaded: dict[str, Any]) -> None:
    document = validate_document(shaded)
    operation = document.layers[0].operations[1]
    assert isinstance(operation, ShadeOperation)
    assert (operation.ramp, operation.light.direction, operation.bands[0].id) == (
        "tones",
        "nw",
        "lit",
    )
    again = validate_document(normalize_document(document))
    assert canonical_json(again) == canonical_json(document)
    assert normalize_document(document)["layers"][0]["operations"][1] == _shade()  # type: ignore[index]  # JSON tree


def test_shade_is_supported_with_a_ramp_and_band_masks() -> None:
    assert "shade" in SUPPORTED_OPERATION_TYPES
    assert "shade" not in PLANNED_OPERATION_TYPES
    assert OPERATION_MEMBERS["shade"] == NodeMembers(
        colors=(),
        masks=(),
        geometry=(),
        ramps=("ramp",),
        items=(("bands", NodeMembers(colors=(), masks=("mask_id",), geometry=())),),
        parameters=("light", "ramp_order"),
    )


def test_json_schema_describes_the_payload() -> None:
    definitions = document_json_schema()["$defs"]
    assert isinstance(definitions, dict)
    model = definitions["ShadeOperation"]
    assert set(model["required"]) == {"id", "type", "ramp", "ramp_order", "light", "bands"}
    assert model["properties"]["bands"]["minItems"] == 1
    assert model["properties"]["bands"]["maxItems"] == 64
    assert model["properties"]["ramp_order"]["enum"] == ["monotonic", "stylized"]
    light = definitions["Light"]
    assert (light["properties"]["height"]["minimum"], light["properties"]["height"]["maximum"]) == (
        0,
        3,
    )
    assert light["properties"]["direction"]["enum"][-1] == "front"
    band = definitions["ShadeBand"]
    assert band["properties"]["facing"]["enum"][-2:] == ["front", "none"]
    assert band["properties"]["offset"]["minimum"] == -4095


@pytest.mark.parametrize(
    ("fields", "member", "reason"),
    [
        ({"ramp_order": "loose"}, "ramp_order", "literal_error"),
        ({"bands": []}, "bands", "too_short"),
        ({"bands": [_band(id=f"b{i}") for i in range(65)]}, "bands", "too_long"),
        (_light(direction="up"), "light/direction", "literal_error"),
        (_light(height=4), "light/height", "less_than_equal"),
        (_light(intensity=4096), "light/intensity", "less_than_equal"),
        (_light(ambient=-1), "light/ambient", "greater_than_equal"),
        (_light(height=True), "light/height", "int_type"),
        (_light(spin=1), "light/spin", "extra_forbidden"),
        ({"light": {"direction": "n", "height": 0, "intensity": 0}}, "light/ambient", "missing"),
        ({"bands": [_band(facing="up")]}, "bands/0/facing", "literal_error"),
        ({"bands": [_band(offset=4096)]}, "bands/0/offset", "less_than_equal"),
        ({"bands": [_band(offset=-4096)]}, "bands/0/offset", "greater_than_equal"),
        ({"bands": [_band(offset=1.0)]}, "bands/0/offset", "int_type"),
        ({"bands": [_band(color="ink")]}, "bands/0/color", "extra_forbidden"),
        ({"color": "ink"}, "color", "extra_forbidden"),
    ],
)
def test_invalid_payloads_are_validation_errors(
    shaded: dict[str, Any], fields: dict[str, Any], member: str, reason: str
) -> None:
    shaded["layers"][0]["operations"][1] = _shade(**fields)
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(shaded)
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["reason"]) == (f"{POINTER}/{member}", reason)


@pytest.mark.parametrize("member", ["ramp", "ramp_order", "light", "bands"])
def test_every_member_is_required(shaded: dict[str, Any], member: str) -> None:
    del shaded["layers"][0]["operations"][1][member]
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(shaded)
    assert raised.value.details[0].json_pointer == f"{POINTER}/{member}"
    assert raised.value.details[0].context["reason"] == "missing"


@pytest.mark.parametrize(
    ("fields", "member", "reason"),
    [
        ({"ramp": "ghost"}, "ramp", "unknown_ramp"),
        ({"ramp": "ink"}, "ramp", "unknown_ramp"),  # a colour is not a ramp
        ({"bands": [_band(mask_id="ghost")]}, "bands/0/mask_id", "unknown_mask"),
        ({"bands": [_band(), _band(id="b2", mask_id="body")]}, "bands/1/mask_id", "unknown_mask"),
    ],
)
def test_unknown_references_are_reference_errors(
    shaded: dict[str, Any], fields: dict[str, Any], member: str, reason: str
) -> None:
    shaded["layers"][0]["operations"][1] = _shade(**fields)
    with pytest.raises(errors.ReferenceError) as raised:
        validate_document(shaded)
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["reason"]) == (f"{POINTER}/{member}", reason)


@pytest.mark.parametrize(
    ("bands", "pointer"),
    [
        ([_band(), _band()], f"{POINTER}/bands/1/id"),  # two bands with one ID
        ([_band(id="shading")], f"{POINTER}/bands/0/id"),  # the ID of its operation
        ([_band(id="area")], "/masks/0/id"),  # bands are declared before the masks
    ],
)
def test_band_ids_are_global(shaded: dict[str, Any], bands: list[Any], pointer: str) -> None:
    shaded["layers"][0]["operations"][1] = _shade(bands=bands)
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(shaded)
    duplicates = [
        d.json_pointer for d in raised.value.details if d.context["reason"] == "duplicate_id"
    ]
    assert duplicates == [pointer]


def test_documents_without_shade_keep_their_canonical_form(minimal: dict[str, Any]) -> None:
    assert "shade" not in canonical_json(validate_document(minimal)).decode("utf-8")


@pytest.mark.parametrize(
    ("fields", "member"),
    [
        (_light(intensity=True), "light/intensity"),
        (_light(ambient=True), "light/ambient"),
        ({"bands": [_band(offset=True)]}, "bands/0/offset"),
    ],
)
def test_booleans_are_not_integers(
    shaded: dict[str, Any], fields: dict[str, Any], member: str
) -> None:
    shaded["layers"][0]["operations"][1] = _shade(**fields)
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(shaded)
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["reason"]) == (f"{POINTER}/{member}", "int_type")


@pytest.mark.parametrize(
    "fields",
    [
        {"bands": [_band(id=f"b{i}") for i in range(64)]},
        {"bands": [_band(offset=4095), _band(id="b2", offset=-4095)]},
        _light(intensity=4095, ambient=4095, height=3),
        _light(direction="front", intensity=0, ambient=0),
    ],
)
def test_limits_are_inclusive(shaded: dict[str, Any], fields: dict[str, Any]) -> None:
    shaded["layers"][0]["operations"][1] = _shade(**fields)
    operation = validate_document(shaded).layers[0].operations[1]
    assert isinstance(operation, ShadeOperation)


def _tree_ids(tree: object) -> set[str]:
    """Every ``id`` member of a JSON tree, collected by hand."""
    if isinstance(tree, dict):
        own = {tree["id"]} if isinstance(tree.get("id"), str) else set()
        return own.union(*(_tree_ids(value) for value in tree.values()))
    if isinstance(tree, list):
        return set().union(*(_tree_ids(value) for value in tree))
    return set()


def test_document_ids_include_band_ids(shaded: dict[str, Any]) -> None:
    shaded["regions"] = [{"id": "zone", "mask_id": "area", "operation_ids": ["shading"]}]
    shaded["layers"][0]["operations"][1] = _shade(bands=[_band(), _band(id="rim")])
    identifiers = document_ids(validate_document(shaded))
    assert isinstance(identifiers, frozenset)
    assert {"lit", "rim", "shading", "tones", "area", "zone"} <= identifiers
    assert identifiers == _tree_ids(shaded)
