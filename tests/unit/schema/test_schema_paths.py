"""Path payloads of schema 1.0: operation and mask leaf (MOANA-007, ADR-023).

AC2 (schema side): unknown commands, invalid order, too many commands or segments
and coordinates of the wrong type or range are ``VALIDATION_ERROR`` with a pointer,
so nothing reaches the adapter. Expected pointers and reasons are written by hand.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic_core import ValidationError as PydanticValidationError

import moanart.schema.models as models_module
from moanart.core import errors
from moanart.core.limits import MAX_PATH_COMMANDS, MAX_PATH_SEGMENTS
from moanart.core.vector_path import MAX_PATH_COORDINATE, FixedPath, parse_path
from moanart.schema import (
    PLANNED_MASK_TYPES,
    PLANNED_OPERATION_TYPES,
    SUPPORTED_MASK_TYPES,
    SUPPORTED_OPERATION_TYPES,
    SUPPORTED_PATH_BACKENDS,
    PathMask,
    PathOperation,
    canonical_json,
    document_json_schema,
    snapshot_digest,
    validate_document,
)

POINTER = "/layers/0/operations/1"
TRIANGLE = [["M", 0, 0], ["L", 2048, 0], ["Q", 2048, 2048, 0, 2048], ["Z"]]


def with_path(minimal: dict[str, Any], **fields: Any) -> dict[str, Any]:
    operation: dict[str, Any] = {"id": "curve", "type": "path", "backend": "aggdraw-v1"}
    operation["color"] = "ink"
    operation["commands"] = TRIANGLE
    operation.update(fields)
    minimal["layers"][0]["operations"].append(operation)
    return minimal


def problems(source: dict[str, Any]) -> list[tuple[str, str | None, object]]:
    with pytest.raises(errors.MoanArtError) as raised:
        validate_document(source)
    return [(d.code, d.json_pointer, d.context.get("reason")) for d in raised.value.details]


def test_path_operation_and_mask_validate_and_expose_a_fixed_path(
    minimal: dict[str, Any],
) -> None:
    source = with_path(minimal)
    source["masks"] = [
        {"id": "shape", "type": "path", "backend": "aggdraw-v1", "commands": TRIANGLE}
    ]
    document = validate_document(source)
    operation = document.layers[0].operations[1]
    assert isinstance(operation, PathOperation)
    assert isinstance(document.masks[0], PathMask)
    assert isinstance(operation.path, FixedPath)
    assert operation.commands[2] == ("Q", 2048, 2048, 0, 2048)
    assert operation.path.segments == document.masks[0].path.segments
    assert validate_document(json.dumps(source).encode("utf-8")) == document


def test_capability_registry_moves_path_to_supported() -> None:
    assert "path" in SUPPORTED_OPERATION_TYPES and "path" not in PLANNED_OPERATION_TYPES
    assert "path" in SUPPORTED_MASK_TYPES and not PLANNED_MASK_TYPES
    assert frozenset({"aggdraw-v1"}) == SUPPORTED_PATH_BACKENDS


def test_canonical_form_keeps_commands_as_arrays(minimal: dict[str, Any]) -> None:
    document = validate_document(with_path(minimal))
    canonical = json.loads(canonical_json(document))
    assert canonical["layers"][0]["operations"][1]["commands"] == TRIANGLE
    assert canonical["layers"][0]["operations"][1]["backend"] == "aggdraw-v1"
    assert validate_document(canonical) == document
    assert snapshot_digest(validate_document(canonical)) == snapshot_digest(document)


def segment_bomb() -> list[list[Any]]:
    wild = ["C", 0, 102_400, 102_400, -102_400, 0, 0]  # 64 segments each
    return [["M", 0, 0], *[wild] * (MAX_PATH_SEGMENTS // 64)]


@pytest.mark.parametrize(
    ("fields", "pointer", "reason"),
    [
        ({"commands": [["M", 0, 0], ["A", 1, 1]]}, f"{POINTER}/commands/1", "path_command_invalid"),
        ({"commands": [["M", 0, 0], ["l", 1, 1]]}, f"{POINTER}/commands/1", "path_command_invalid"),
        ({"commands": [["M", 0, 0], []]}, f"{POINTER}/commands/1", "path_command_invalid"),
        ({"commands": [["M", 0, 0], "L"]}, f"{POINTER}/commands/1", "path_command_invalid"),
        ({"commands": [["M", 0, 0], [1, 1]]}, f"{POINTER}/commands/1", "path_command_invalid"),
        ({"commands": [["M", 0, 0], ["L", 1]]}, f"{POINTER}/commands/1/2", "missing"),
        ({"commands": [["M", 0, 0], ["Z", 1]]}, f"{POINTER}/commands/1", "too_long"),
        ({"commands": [["M", 0, 0], ["L", True, 1]]}, f"{POINTER}/commands/1/1", "int_type"),
        ({"commands": [["M", 0, 0], ["L", 1.0, 1]]}, f"{POINTER}/commands/1/1", "int_type"),
        ({"commands": [["M", 0, 0], ["L", "1", 1]]}, f"{POINTER}/commands/1/1", "int_type"),
        (
            {"commands": [["M", 0, 0], ["L", MAX_PATH_COORDINATE + 1, 1]]},
            f"{POINTER}/commands/1/1",
            "less_than_equal",
        ),
        (
            {"commands": [["M", -MAX_PATH_COORDINATE - 1, 0], ["L", 1, 1]]},
            f"{POINTER}/commands/0/1",
            "greater_than_equal",
        ),
        ({"commands": [["L", 0, 0], ["L", 1, 1]]}, f"{POINTER}/commands/0", "path_start"),
        ({"commands": [["M", 0, 0], ["Z"]]}, f"{POINTER}/commands/1", "empty_subpath"),
        (
            {"commands": [["M", 0, 0], ["L", 9, 9], ["Z"], ["L", 2, 2]]},
            f"{POINTER}/commands/3",
            "command_after_close",
        ),
        ({"commands": [["M", 0, 0]]}, f"{POINTER}/commands", "too_short"),
        ({"commands": []}, f"{POINTER}/commands", "too_short"),
        ({"commands": "M 0 0 L 1 1"}, f"{POINTER}/commands", "tuple_type"),
        (
            {"commands": [["M", 0, 0]] + [["L", 1, 1]] * MAX_PATH_COMMANDS},
            f"{POINTER}/commands",
            "too_long",
        ),
        ({"commands": segment_bomb()}, f"{POINTER}/commands/1024", "too_many_segments"),
        ({"backend": "skia"}, f"{POINTER}/backend", "literal_error"),
        ({"backend": None}, f"{POINTER}/backend", "literal_error"),
        ({"stroke": 2}, f"{POINTER}/stroke", "extra_forbidden"),
        ({"svg": "M0 0"}, f"{POINTER}/svg", "extra_forbidden"),
    ],
)
def test_invalid_path_payloads_are_located_validation_errors(
    minimal: dict[str, Any], fields: dict[str, Any], pointer: str, reason: str
) -> None:
    found = problems(with_path(minimal, **fields))
    assert found == [("VALIDATION_ERROR", pointer, reason)]


def test_missing_backend_member_is_required(minimal: dict[str, Any]) -> None:
    source = with_path(minimal)
    del source["layers"][0]["operations"][1]["backend"]
    assert problems(source) == [("VALIDATION_ERROR", f"{POINTER}/backend", "missing")]


def test_order_errors_carry_the_command_index(minimal: dict[str, Any]) -> None:
    source = with_path(minimal, commands=[["M", 0, 0], ["L", 9, 9], ["Z"], ["Z"]])
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(source)
    assert raised.value.details[0].context["index"] == 3
    assert raised.value.details[0].json_pointer == f"{POINTER}/commands/3"


def test_path_mask_leaf_errors_point_into_masks(minimal: dict[str, Any]) -> None:
    minimal["masks"] = [
        {
            "id": "shape",
            "type": "path",
            "backend": "aggdraw-v1",
            "commands": [["M", 0, 0], ["L", 1]],
        }
    ]
    assert problems(minimal) == [("VALIDATION_ERROR", "/masks/0/commands/1/2", "missing")]


def test_json_schema_describes_path_commands() -> None:
    schema = document_json_schema()
    defs: dict[str, Any] = schema["$defs"]  # type: ignore[assignment]
    operation = defs["PathOperation"]
    assert operation["properties"]["backend"]["const"] == "aggdraw-v1"
    commands = operation["properties"]["commands"]
    assert commands["minItems"] == 2 and commands["maxItems"] == MAX_PATH_COMMANDS
    shapes = commands["items"]["oneOf"]
    letters = sorted(item["prefixItems"][0]["const"] for item in shapes)
    assert letters == ["C", "L", "M", "Q", "Z"]
    for item in shapes:
        coordinates = item["prefixItems"][1:]
        assert all(c["maximum"] == MAX_PATH_COORDINATE for c in coordinates)
    assert "PathMask" in defs


def test_path_mask_leaf_order_errors_point_at_the_command(minimal: dict[str, Any]) -> None:
    minimal["masks"] = [
        {
            "id": "shape",
            "type": "path",
            "backend": "aggdraw-v1",
            "commands": [["M", 0, 0], ["L", 1, 1], ["Z"], ["L", 2, 2]],
        }
    ]
    assert problems(minimal) == [("VALIDATION_ERROR", "/masks/0/commands/3", "command_after_close")]


def test_each_path_model_parses_its_commands_once(
    minimal: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    real = parse_path

    def counted(commands: object) -> FixedPath:
        calls.append(1)
        return real(commands)

    monkeypatch.setattr(models_module, "parse_path", counted)
    minimal["masks"] = [
        {"id": "shape", "type": "path", "backend": "aggdraw-v1", "commands": TRIANGLE}
    ]
    document = validate_document(with_path(minimal))
    validated = len(calls)
    operation = document.layers[0].operations[1]
    mask = document.masks[0]
    assert isinstance(operation, PathOperation) and isinstance(mask, PathMask)
    for _ in range(50):
        assert operation.path is operation.path and mask.path is mask.path
    assert len(calls) == validated  # accessing ``.path`` never parses again
    replaced = operation.model_copy(update={"commands": (("M", 0, 0), ("L", 1, 1))})
    assert replaced.path.commands[1].points == ((1, 1),)  # new commands: parsed again
    assert len(calls) == validated + 1


def test_constructed_models_check_the_whole_path_too() -> None:
    """``model_construct`` skips field validation but still parses the commands once.

    A whole-path failure (no command index) is located at ``commands``.
    """
    with pytest.raises(PydanticValidationError) as raised:
        PathMask.model_construct(
            id="shape", type="path", backend="aggdraw-v1", commands=(("M", 0, 0),)
        )
    (error,) = raised.value.errors()
    assert (error["type"], error["loc"]) == ("out_of_range", ("commands",))
