"""The member table matches the schema unions exactly (ADR-025)."""

from __future__ import annotations

from types import MappingProxyType
from typing import get_args

import pytest
from pydantic import BaseModel

from moana.schema import (
    MASK_MEMBERS,
    OPERATION_MEMBERS,
    SUPPORTED_MASK_TYPES,
    SUPPORTED_OPERATION_TYPES,
    MaskNode,
    NodeMembers,
    Operation,
)


def _models(union: object) -> dict[str, type[BaseModel]]:
    """``type`` literal -> model of an ``Annotated[A | B | ..., Field(...)]`` union."""
    members = get_args(get_args(union)[0])
    found: dict[str, type[BaseModel]] = {}
    for model in members:
        (literal,) = get_args(model.model_fields["type"].annotation)
        found[literal] = model
    return found


@pytest.mark.parametrize(
    ("table", "union", "supported"),
    [
        (OPERATION_MEMBERS, Operation, SUPPORTED_OPERATION_TYPES),
        (MASK_MEMBERS, MaskNode, SUPPORTED_MASK_TYPES),
    ],
)
def test_table_keys_are_exactly_the_union_types(
    table: MappingProxyType[str, NodeMembers], union: object, supported: frozenset[str]
) -> None:
    models = _models(union)
    assert set(table) == set(models) == supported


@pytest.mark.parametrize(
    ("table", "union"), [(OPERATION_MEMBERS, Operation), (MASK_MEMBERS, MaskNode)]
)
def test_every_listed_member_exists_on_its_model(
    table: MappingProxyType[str, NodeMembers], union: object
) -> None:
    models = _models(union)
    for kind, members in table.items():
        fields = models[kind].model_fields
        listed = members.colors + members.masks + members.geometry
        assert len(set(listed)) == len(listed), kind
        for name in listed:
            assert name in fields, (kind, name)
        assert {"id", "type"}.isdisjoint(listed)


def test_known_rows() -> None:
    assert OPERATION_MEMBERS["dither"] == NodeMembers(
        colors=("color_a", "color_b"), masks=("mask_id",), geometry=()
    )
    assert OPERATION_MEMBERS["rect"] == NodeMembers(colors=("color",), masks=(), geometry=("box",))
    assert MASK_MEMBERS["xor"] == NodeMembers(colors=(), masks=("masks",), geometry=())
    assert MASK_MEMBERS["path"].geometry == ("commands",)


def test_every_colour_and_mask_member_is_named_by_the_table() -> None:
    """No model has a colour or mask member the table forgets."""
    for table, union in ((OPERATION_MEMBERS, Operation), (MASK_MEMBERS, MaskNode)):
        for kind, model in _models(union).items():
            for name in model.model_fields:
                if name.startswith("color"):
                    assert name in table[kind].colors, (kind, name)
                if name in {"mask_id", "masks"}:
                    assert name in table[kind].masks, (kind, name)


def test_tables_are_read_only() -> None:
    with pytest.raises(TypeError):
        OPERATION_MEMBERS["new"] = NodeMembers((), (), ())  # type: ignore[index]  # read-only
