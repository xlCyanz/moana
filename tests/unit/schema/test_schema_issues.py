"""Error details: pointer mapping, ordering and context filtering."""

from __future__ import annotations

from typing import Any

import pytest

from moana.core import errors
from moana.schema import EllipseOperation, validate_document
from moana.schema._issues import pointer_for, pydantic_details
from moana.schema._pointers import detail_sort_key


def detail(pointer: str | None, code: str = "VALIDATION_ERROR") -> errors.ErrorDetail:
    return errors.ErrorDetail(code, "m", json_pointer=pointer)


def test_sort_key_orders_indexes_numerically_and_tolerates_any_token() -> None:
    items = [
        detail("/a/10"),
        detail("/a/2"),
        detail("/a/²"),
        detail("/a/2", "REFERENCE_ERROR"),
        detail(""),
        detail(None),
    ]
    ordered = sorted(items, key=detail_sort_key)
    assert [(d.json_pointer, d.code) for d in ordered] == [
        (None, "VALIDATION_ERROR"),
        ("", "VALIDATION_ERROR"),
        ("/a/2", "REFERENCE_ERROR"),
        ("/a/2", "VALIDATION_ERROR"),
        ("/a/10", "VALIDATION_ERROR"),
        ("/a/²", "VALIDATION_ERROR"),
    ]


def test_extra_member_with_unicode_digit_name_is_reported(minimal: dict[str, Any]) -> None:
    minimal["²"] = 1
    minimal["1"] = 1
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(minimal)
    assert [d.json_pointer for d in raised.value.details] == ["/1", "/²"]


def test_pointer_skips_labels_and_escapes_members() -> None:
    tree = {"a/b": [{"t": 1}], "s": "text"}
    assert pointer_for(tree, ("a/b", 0, "rect", "t")) == "/a~1b/0/t"
    assert pointer_for(tree, ("a/b", 0, "missing")) == "/a~1b/0/missing"
    assert pointer_for(tree, ("s", "function-after[x]")) == "/s"
    assert pointer_for(tree, ("a/b", 5)) == "/a~1b/5"
    assert pointer_for(tree, ("a/b", "function-after[x]", 0)) == "/a~1b/0"
    assert pointer_for({"x" * 65: {"y": 1}}, ("x" * 65, "y")) == ""


def test_context_keeps_only_numeric_and_schema_strings() -> None:
    (only,) = pydantic_details(
        {"x": 1},
        [
            {
                "type": "custom",
                "loc": ("x",),
                "msg": "m",
                "input": 1,
                "ctx": {"limit": 3, "flag": True, "pattern": "^a$", "tag": "untrusted"},
            }
        ],
    )
    assert dict(only.context) == {"reason": "custom", "limit": 3, "pattern": "^a$"}


def test_ellipse_exposes_core_box() -> None:
    operation = EllipseOperation.model_validate(
        {"id": "e", "type": "ellipse", "box": [0, 0, 3, 2], "color": "ink"}
    )
    assert (operation.bbox.width, operation.bbox.height) == (3, 2)


def test_unhashable_blend_is_a_validation_error(minimal: dict[str, Any]) -> None:
    values: tuple[object, ...] = (["multiply"], {})
    for value in values:
        minimal["layers"][0]["blend"] = value
        with pytest.raises(errors.ValidationError) as raised:
            validate_document(minimal)
        assert [d.json_pointer for d in raised.value.details] == ["/layers/0/blend"]


def test_discriminator_tag_is_not_confused_with_a_member(minimal: dict[str, Any]) -> None:
    operation = minimal["layers"][0]["operations"][0]
    del operation["box"]
    operation["rect"] = 1
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(minimal)
    found = {(d.json_pointer, d.context["reason"]) for d in raised.value.details}
    assert found == {
        ("/layers/0/operations/0/box", "missing"),
        ("/layers/0/operations/0/rect", "extra_forbidden"),
    }


def test_long_extra_member_name_is_not_copied(minimal: dict[str, Any]) -> None:
    name = "secret" * 20
    minimal["layers"][0][name] = 1
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(minimal)
    assert raised.value.json_pointer == "/layers/0"
    assert name not in repr(raised.value.details)


def test_unknown_type_lists_supported_operations(minimal: dict[str, Any]) -> None:
    minimal["layers"][0]["operations"][0]["type"] = "spray"
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(minimal)
    assert raised.value.details[0].context["expected"] == (
        "ellipse",
        "line",
        "path",
        "pixel",
        "polygon",
        "rect",
    )
