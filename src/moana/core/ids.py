"""Lexical languages shared by every module: IDs and canonical colours (ADR-014).

One owner for the patterns that ``schema`` publishes in the JSON Schema and that
``palette`` (and later ``layers``, ``editing``) check without depending on
``schema``. The unanchored ``*_REGEX`` forms are used with :func:`re.fullmatch`, so
a trailing newline never matches as it would with ``$`` in Python; the anchored
``*_PATTERN`` forms are the JSON Schema / Pydantic spelling of the same language.
"""

from __future__ import annotations

import re
from typing import Final

from moana.core.errors import ValidationError

__all__ = [
    "ID_PATTERN",
    "ID_REGEX",
    "RGBA_HEX_PATTERN",
    "RGBA_HEX_REGEX",
    "check_id",
    "is_id",
    "is_rgba_hex",
]

ID_REGEX: Final = "[a-z][a-z0-9_-]{0,63}"
ID_PATTERN: Final = f"^{ID_REGEX}$"
# ASCII only: the class is spelled out so no Unicode digit can match.
RGBA_HEX_REGEX: Final = "#[0-9A-Fa-f]{8}"
RGBA_HEX_PATTERN: Final = f"^{RGBA_HEX_REGEX}$"

_ID: Final = re.compile(ID_REGEX)
_RGBA_HEX: Final = re.compile(RGBA_HEX_REGEX)


def is_id(value: object) -> bool:
    """Whether ``value`` is exactly a ``str`` (not a subclass) in the ID language."""
    return type(value) is str and _ID.fullmatch(value) is not None


def is_rgba_hex(value: object) -> bool:
    """Whether ``value`` is exactly a ``str`` spelling ``#RRGGBBAA`` (either case)."""
    return type(value) is str and _RGBA_HEX.fullmatch(value) is not None


def check_id(value: object, field: str = "id") -> str:
    """Return ``value`` if it is an ID; otherwise ``ValidationError`` without echo."""
    if not is_id(value):
        raise ValidationError(
            f"{field} must be a Moana ID",
            context={"field": field, "reason": "invalid_id"},
        )
    assert isinstance(value, str)  # narrowed by is_id
    return value
