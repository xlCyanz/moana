"""Shared ID and colour languages owned by core (ADR-014)."""

from __future__ import annotations

import pytest

from moana.core import (
    ID_PATTERN,
    RGBA_HEX_PATTERN,
    ValidationError,
    check_id,
    is_id,
    is_rgba_hex,
)
from moana.schema.models import ID_PATTERN as SCHEMA_ID_PATTERN
from moana.schema.models import RGBA_PATTERN as SCHEMA_RGBA_PATTERN


class Sneaky(str):
    """A str subclass must not pass as an ID or colour."""


def test_schema_publishes_the_core_languages() -> None:
    assert SCHEMA_ID_PATTERN == ID_PATTERN == "^[a-z][a-z0-9_-]{0,63}$"
    assert SCHEMA_RGBA_PATTERN == RGBA_HEX_PATTERN == "^#[0-9A-Fa-f]{8}$"


@pytest.mark.parametrize("value", ["a", "a" * 64, "ink_1-b", "z9"])
def test_valid_ids(value: str) -> None:
    assert is_id(value) and check_id(value) == value


@pytest.mark.parametrize(
    "value", ["", "A", "1a", "_a", "a" * 65, "ink\n", "ínk", "a b", Sneaky("ink"), None, 1]
)
def test_invalid_ids_rejected_without_echo(value: object) -> None:
    assert not is_id(value)
    with pytest.raises(ValidationError) as excinfo:
        check_id(value, "color")
    assert excinfo.value.context == {"field": "color", "reason": "invalid_id"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#00ff00FF", True),
        ("#00FF00", False),
        ("#00FF00FF\n", False),
        ("#\u0660\u0660FF00FF", False),  # Arabic-Indic digits
        (Sneaky("#00FF00FF"), False),
        (None, False),
    ],
)
def test_rgba_hex_language(value: object, expected: bool) -> None:
    assert is_rgba_hex(value) is expected
