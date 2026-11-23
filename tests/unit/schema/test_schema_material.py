"""Schema 1.0 payloads of ``material`` and ``selective_outline`` (MOANA-017, ADR-030)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from moanart.core import errors
from moanart.schema import (
    OPERATION_MEMBERS,
    PLANNED_OPERATION_TYPES,
    SUPPORTED_OPERATION_TYPES,
    MaterialOperation,
    NodeMembers,
    SelectiveOutlineOperation,
    canonical_json,
    document_ids,
    document_json_schema,
    normalize_document,
    validate_document,
)

POINTER = "/layers/0/operations/1"
BAND = NodeMembers(colors=(), masks=("mask_id",), geometry=())


def _band(**fields: Any) -> dict[str, Any]:
    return {"id": "lit", "mask_id": "area", "facing": "nw", "offset": 0} | fields


def _material(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "skin_mat",
        "type": "material",
        "preset": "skin",
        "version": 1,
        "ramp": "tones",
        "ramp_order": "monotonic",
        "light": {"direction": "nw", "height": 1, "intensity": 2, "ambient": 1},
        "density": 4,
        "scale": 2,
        "origin": [0, 0],
        "bands": [_band()],
    }
    return base | fields


def _selective(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "rim",
        "type": "selective_outline",
        "mask_id": "area",
        "width": 1,
        "side": "outer",
        "color": "ink",
        "ramp": "tones",
        "ramp_order": "stylized",
        "light": {"direction": "nw", "height": 1, "intensity": 2, "ambient": 1},
        "segments": [_band(id="seg")],
    }
    return base | fields


@pytest.fixture
def textured(minimal: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(minimal)
    document["palette"]["ramps"] = [{"id": "tones", "colors": ["ink", "cloth"]}]
    document["masks"] = [{"id": "area", "type": "ellipse", "box": [40, 32, 88, 104]}]
    document["layers"][0]["operations"].append(_material())
    return document


def _set(document: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    document["layers"][0]["operations"][1] = operation
    return document


def test_both_types_are_supported_and_have_member_rows() -> None:
    for kind in ("material", "selective_outline"):
        assert kind in SUPPORTED_OPERATION_TYPES and kind not in PLANNED_OPERATION_TYPES
    assert OPERATION_MEMBERS["material"] == NodeMembers(
        colors=(),
        masks=(),
        geometry=(),
        ramps=("ramp",),
        items=(("bands", BAND),),
        parameters=("light", "ramp_order", "density", "scale", "origin"),
    )
    assert OPERATION_MEMBERS["selective_outline"] == NodeMembers(
        colors=("color",),
        masks=("mask_id",),
        geometry=(),
        ramps=("ramp",),
        items=(("segments", BAND),),
        parameters=("light", "ramp_order", "width", "side"),
    )


def test_material_payload_validates_and_round_trips(textured: dict[str, Any]) -> None:
    document = validate_document(textured)
    operation = document.layers[0].operations[1]
    assert isinstance(operation, MaterialOperation)
    assert (operation.preset, operation.version, operation.anchor.x) == ("skin", 1, 0)
    again = validate_document(normalize_document(document))
    assert canonical_json(again) == canonical_json(document)
    assert normalize_document(document)["layers"][0]["operations"][1] == _material()  # type: ignore[index]  # JSON tree


def test_selective_outline_payload_validates_and_round_trips(textured: dict[str, Any]) -> None:
    document = validate_document(_set(textured, _selective()))
    operation = document.layers[0].operations[1]
    assert isinstance(operation, SelectiveOutlineOperation)
    assert operation.segments[0].id == "seg"
    assert normalize_document(document)["layers"][0]["operations"][1] == _selective()  # type: ignore[index]  # JSON tree


def test_json_schema_describes_both_payloads() -> None:
    definitions = document_json_schema()["$defs"]
    assert isinstance(definitions, dict)
    material = definitions["MaterialOperation"]
    assert set(material["required"]) == {
        "id",
        "type",
        "preset",
        "version",
        "ramp",
        "ramp_order",
        "light",
        "density",
        "scale",
        "origin",
        "bands",
    }
    properties = material["properties"]
    assert properties["preset"]["enum"] == ["skin", "cloth", "metal", "wood", "stone"]
    assert (properties["density"]["minimum"], properties["density"]["maximum"]) == (0, 64)
    assert (properties["scale"]["minimum"], properties["scale"]["maximum"]) == (1, 8)
    assert properties["bands"]["minItems"] == 1 and properties["bands"]["maxItems"] == 64
    selective = definitions["SelectiveOutlineOperation"]
    assert selective["properties"]["segments"]["minItems"] == 1
    assert "color" in selective["required"] and "segments" in selective["required"]


@pytest.mark.parametrize(
    ("fields", "member", "reason"),
    [
        ({"preset": "lava"}, "preset", "literal_error"),
        ({"version": 2}, "version", "unknown_preset_version"),
        ({"version": 0}, "version", "greater_than_equal"),
        ({"version": True}, "version", "int_type"),
        ({"density": 5}, "density", "less_than_equal"),  # skin allows 0..4
        ({"density": 65}, "density", "less_than_equal"),
        ({"density": -1}, "density", "greater_than_equal"),
        ({"density": 4.0}, "density", "int_type"),
        ({"scale": 3}, "scale", "less_than_equal"),  # skin allows 1..2
        ({"scale": 0}, "scale", "greater_than_equal"),
        ({"scale": 9}, "scale", "less_than_equal"),
        ({"origin": [2049, 0]}, "origin/0", "less_than_equal"),
        ({"origin": [0, -2049]}, "origin/1", "greater_than_equal"),
        ({"origin": [0]}, "origin/1", "missing"),
        ({"bands": []}, "bands", "too_short"),
        ({"bands": [_band(id=f"b{i}") for i in range(65)]}, "bands", "too_long"),
        ({"bands": [_band(facing="up")]}, "bands/0/facing", "literal_error"),
        ({"shader": "x * y"}, "shader", "extra_forbidden"),
        ({"color": "ink"}, "color", "extra_forbidden"),
    ],
)
def test_invalid_material_payloads(
    textured: dict[str, Any], fields: dict[str, Any], member: str, reason: str
) -> None:
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(_set(textured, _material(**fields)))
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["reason"]) == (f"{POINTER}/{member}", reason)


def test_density_and_scale_beyond_the_row_are_both_reported(textured: dict[str, Any]) -> None:
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(_set(textured, _material(density=20, scale=4)))
    assert [(d.json_pointer, d.context["reason"]) for d in raised.value.details] == [
        (f"{POINTER}/density", "less_than_equal"),
        (f"{POINTER}/scale", "less_than_equal"),
    ]


@pytest.mark.parametrize(
    "fields",
    [
        {"preset": "cloth", "density": 64, "scale": 4},
        {"preset": "stone", "density": 32, "scale": 4, "origin": [-2048, 2048]},
        {"preset": "metal", "density": 0, "scale": 1},
        {"preset": "wood", "density": 64, "scale": 1},
        {"preset": "skin", "density": 4, "scale": 2},
        {"bands": [_band(id=f"b{i}") for i in range(64)]},
    ],
)
def test_material_limits_are_inclusive(textured: dict[str, Any], fields: dict[str, Any]) -> None:
    operation = validate_document(_set(textured, _material(**fields))).layers[0].operations[1]
    assert isinstance(operation, MaterialOperation)


@pytest.mark.parametrize(
    ("fields", "member", "reason"),
    [
        ({"segments": []}, "segments", "too_short"),
        ({"segments": [_band(id=f"s{i}") for i in range(65)]}, "segments", "too_long"),
        ({"width": 17}, "width", "less_than_equal"),
        ({"side": "both"}, "side", "literal_error"),
        ({"ramp_order": "loose"}, "ramp_order", "literal_error"),
        ({"segments": [_band(offset=4096)]}, "segments/0/offset", "less_than_equal"),
    ],
)
def test_invalid_selective_outline_payloads(
    textured: dict[str, Any], fields: dict[str, Any], member: str, reason: str
) -> None:
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(_set(textured, _selective(**fields)))
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["reason"]) == (f"{POINTER}/{member}", reason)


@pytest.mark.parametrize(
    ("operation", "member", "reason"),
    [
        (_material(ramp="ghost"), "ramp", "unknown_ramp"),
        (_material(bands=[_band(mask_id="ghost")]), "bands/0/mask_id", "unknown_mask"),
        (_selective(ramp="ink"), "ramp", "unknown_ramp"),
        (_selective(color="ghost"), "color", "unknown_color"),
        (_selective(mask_id="ghost"), "mask_id", "unknown_mask"),
        (_selective(segments=[_band(mask_id="ghost")]), "segments/0/mask_id", "unknown_mask"),
    ],
)
def test_unknown_references(
    textured: dict[str, Any], operation: dict[str, Any], member: str, reason: str
) -> None:
    with pytest.raises(errors.ReferenceError) as raised:
        validate_document(_set(textured, operation))
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["reason"]) == (f"{POINTER}/{member}", reason)


def test_band_and_segment_ids_are_global(textured: dict[str, Any]) -> None:
    textured["layers"][0]["operations"].append(_selective(segments=[_band()]))
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(textured)
    duplicates = [
        d.json_pointer for d in raised.value.details if d.context["reason"] == "duplicate_id"
    ]
    assert duplicates == ["/layers/0/operations/2/segments/0/id"]
    textured["layers"][0]["operations"][2] = _selective()
    assert {"lit", "seg", "skin_mat", "rim"} <= document_ids(validate_document(textured))


def test_documents_without_materials_keep_their_canonical_form(minimal: dict[str, Any]) -> None:
    text = canonical_json(validate_document(minimal)).decode("utf-8")
    assert "material" not in text.replace('"materials":[]', "")
    assert "selective" not in text
