"""Typed edit batches: bounded, strict parsing with located errors (MOANA-018, ADR-024)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from moana.core import errors
from moana.core.limits import MAX_EDIT_COMMANDS
from moana.editing import (
    COMMAND_TYPES,
    MAX_TRANSLATION,
    EditBatch,
    InsertOperation,
    Reorder,
    SetColor,
    parse_edit_batch,
)
from moana.schema import ParseLimits

SNAPSHOT = "sha256:" + "0" * 64


def batch(*commands: dict[str, Any], **changes: Any) -> dict[str, Any]:
    tree: dict[str, Any] = {
        "schema_version": "1.0",
        "base_revision": 0,
        "base_snapshot": SNAPSHOT,
        "commands": list(commands),
    }
    tree.update(changes)
    return tree


RECOLOR = {"type": "set_color", "target_id": "body_fill", "color": "ink"}


def invalid(source: dict[str, Any]) -> errors.ValidationError:
    with pytest.raises(errors.ValidationError) as caught:
        parse_edit_batch(source)
    return caught.value


def test_catalogue_is_section_15_plus_set_parameters() -> None:
    assert COMMAND_TYPES == (
        "insert_operation",
        "remove",
        "reorder",
        "replace_palette_color",
        "set_color",
        "set_geometry",
        "set_parameters",
        "set_visibility",
        "translate",
    )


def test_bytes_mapping_and_model_give_the_same_batch() -> None:
    tree = batch(
        RECOLOR,
        {"type": "reorder", "target_id": "a", "after_id": None},
        {"type": "insert_operation", "layer_id": "l", "after_id": "a", "operation": {"id": "x"}},
    )
    from_mapping = parse_edit_batch(tree)
    assert parse_edit_batch(json.dumps(tree).encode("utf-8")) == from_mapping
    assert parse_edit_batch(from_mapping) is from_mapping
    assert isinstance(from_mapping, EditBatch)
    assert [type(c) for c in from_mapping.commands] == [SetColor, Reorder, InsertOperation]
    assert isinstance(from_mapping.commands, tuple)
    with pytest.raises(Exception, match="frozen"):
        setattr(from_mapping, "base_revision", 3)  # noqa: B010


@pytest.mark.parametrize(
    ("source", "pointer", "reason"),
    [
        (batch(), "/commands", "too_short"),
        (batch({"type": "bogus_command"}), "/commands/0/type", "union_tag_invalid"),
        (batch({"target_id": "x"}), "/commands/0", "union_tag_not_found"),
        (batch(RECOLOR, base_snapshot="sha256:ABC"), "/base_snapshot", "string_pattern_mismatch"),
        (batch(RECOLOR, base_revision=-1), "/base_revision", "greater_than_equal"),
        (batch(RECOLOR, base_revision=True), "/base_revision", "int_type"),
        (batch(RECOLOR, schema_version=1), "/schema_version", "literal_error"),
        (batch({**RECOLOR, "id": "x"}), "/commands/0/id", "extra_forbidden"),
        (
            batch({**RECOLOR, "target_id": "Bad Id"}),
            "/commands/0/target_id",
            "string_pattern_mismatch",
        ),
        (batch({"type": "reorder", "target_id": "a"}), "/commands/0/after_id", "missing"),
        (
            batch({"type": "translate", "target_id": "a", "dx": MAX_TRANSLATION + 1, "dy": 0}),
            "/commands/0/dx",
            "less_than_equal",
        ),
        (
            batch({"type": "replace_palette_color", "target_id": "a", "rgba": "red"}),
            "/commands/0/rgba",
            "string_pattern_mismatch",
        ),
    ],
)
def test_structural_errors_are_located(source: dict[str, Any], pointer: str, reason: str) -> None:
    error = invalid(source)
    assert [(d.json_pointer, d.context["reason"]) for d in error.details] == [(pointer, reason)]
    assert error.json_pointer == pointer


def test_errors_never_echo_untrusted_strings() -> None:
    error = invalid(batch({"type": "steal_secret_token"}))
    detail = error.details[0]
    assert "steal_secret_token" not in detail.message
    assert detail.context["expected"] == COMMAND_TYPES
    assert "steal_secret_token" not in repr(detail.context)


def test_too_many_commands() -> None:
    error = invalid(batch(*[RECOLOR] * (MAX_EDIT_COMMANDS + 1)))
    assert error.details[0].context["reason"] == "too_long"
    assert error.details[0].context["max_length"] == MAX_EDIT_COMMANDS


def test_other_versions_are_unsupported() -> None:
    with pytest.raises(errors.UnsupportedVersion) as caught:
        parse_edit_batch(batch(RECOLOR, schema_version="2.0"))
    assert caught.value.json_pointer == "/schema_version"


def test_reading_is_bounded_like_documents() -> None:
    with pytest.raises(errors.ValidationError) as caught:
        parse_edit_batch(b'{"a": 1, "a": 2}')
    assert caught.value.context["reason"] == "duplicate_key"
    with pytest.raises(errors.ValidationError) as caught:
        parse_edit_batch(batch(RECOLOR), limits=ParseLimits(max_nodes=5))
    assert caught.value.context["reason"] == "too_many_nodes"
    with pytest.raises(TypeError, match="batch"):
        parse_edit_batch(42)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("source", "reason"),
    [(b"\xff\xfe", "invalid_utf8"), (b"[]", "root_not_object"), (b"{", "invalid_json")],
)
def test_reader_errors_name_the_edit_batch(source: bytes, reason: str) -> None:
    with pytest.raises(errors.ValidationError) as caught:
        parse_edit_batch(source)
    assert caught.value.message.startswith("edit batch")
    assert "document" not in caught.value.message
    assert caught.value.context["reason"] == reason
