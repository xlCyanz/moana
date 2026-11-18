"""Translate Pydantic errors into located, non-sensitive Moana error details.

Pydantic locations include discriminator tags and validator names that are not part
of the JSON document. :func:`pointer_for` walks the validated tree alongside the
location and keeps only the members and indexes that exist, so every pointer
addresses the input (RFC 6901). Messages never echo untrusted strings: the only
context strings are schema constants (reasons, patterns, supported operation types,
planned capability names). Member names longer than 64 characters are not copied
into pointers (see :mod:`moana.schema._pointers`).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from pydantic_core import ErrorDetails

from moana.core.errors import ErrorDetail, UnsupportedOperation, ValidationError
from moana.schema._pointers import ROOT, Location, child_pointer
from moana.schema.capabilities import (
    PLANNED_BLEND_MODES,
    PLANNED_COLLECTIONS,
    PLANNED_LAYER_FIELDS,
    PLANNED_MASK_TYPES,
    PLANNED_OPERATION_TYPES,
    SUPPORTED_MASK_TYPES,
    SUPPORTED_OPERATION_TYPES,
)

__all__ = ["pointer_for", "pydantic_details"]

_SAFE_STRING_CONTEXT: Final = frozenset({"pattern"})
_OWN_MESSAGES: Final = {
    "union_tag_invalid": "Operation type is not part of schema 1.0",
    "union_tag_not_found": "Operation requires a 'type' member",
}
_MASK_MESSAGES: Final = {
    "union_tag_invalid": "Mask type is not part of schema 1.0",
    "union_tag_not_found": "Mask requires a 'type' member",
}
_TAGGED_TYPES: Final = SUPPORTED_OPERATION_TYPES | SUPPORTED_MASK_TYPES


def _in_masks(error: ErrorDetails) -> bool:
    """Whether an error lies in the root ``masks`` collection (mask discriminator)."""
    return error["loc"][:1] == ("masks",)


def pointer_for(tree: object, location: Sequence[str | int]) -> str:
    """Map a Pydantic location onto the JSON Pointer of the input node."""
    current: object = tree
    place: Location = ROOT
    last = len(location) - 1
    for position, segment in enumerate(location):
        if isinstance(segment, str) and _is_label(current, segment, position == last):
            continue
        if isinstance(current, dict) and isinstance(segment, str):
            current = current.get(segment)
        elif isinstance(current, list) and isinstance(segment, int) and 0 <= segment < len(current):
            current = current[segment]
        else:
            current = None
        place = child_pointer(place, segment)
    return place[0]


def _is_label(current: object, segment: str, is_last: bool) -> bool:
    """Whether a location segment names a validator or union branch, not a member."""
    if not isinstance(current, dict | list):
        return current is not None or not is_last  # labels below a scalar input
    if not isinstance(current, dict):
        return True
    if current.get("type") == segment and segment in _TAGGED_TYPES and not is_last:
        return True  # discriminator tag, even if the input also has such a member
    return segment not in current and not is_last


def _context(error: ErrorDetails) -> dict[str, object]:
    context: dict[str, object] = {"reason": error["type"]}
    if error["type"] in {"union_tag_invalid", "union_tag_not_found"}:
        expected = SUPPORTED_MASK_TYPES if _in_masks(error) else SUPPORTED_OPERATION_TYPES
        context["expected"] = tuple(sorted(expected))
    for key, value in (error.get("ctx") or {}).items():
        if _is_safe_context(key, value):
            context[key] = value
    return context


def _is_safe_context(key: str, value: object) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, str) and key in _SAFE_STRING_CONTEXT)


def _planned_capability(error: ErrorDetails) -> str | None:
    """Return the planned capability an error refers to, if any."""
    kind, location, value = error["type"], error["loc"], error.get("input")
    if kind == "union_tag_invalid":
        tag = (error.get("ctx") or {}).get("tag")
        planned = PLANNED_MASK_TYPES if _in_masks(error) else PLANNED_OPERATION_TYPES
        return tag if isinstance(tag, str) and tag in planned else None
    if kind == "literal_error" and location[-1:] == ("blend",):
        return value if isinstance(value, str) and value in PLANNED_BLEND_MODES else None
    if kind == "unsupported_capability" and location[-1:] and location[-1] in PLANNED_COLLECTIONS:
        return str(location[-1])
    if kind == "extra_forbidden" and len(location) == 3 and location[0] == "layers":
        name = location[-1]
        return name if name in PLANNED_LAYER_FIELDS else None
    return None


def pydantic_details(tree: object, errors: Iterable[ErrorDetails]) -> list[ErrorDetail]:
    """Convert Pydantic errors to details, marking planned capabilities as unsupported."""
    details: list[ErrorDetail] = []
    for error in errors:
        if error["type"] == "none_required":
            continue  # the hidden ``None`` branch of optional members; null is rejected
        pointer = pointer_for(tree, error["loc"])
        if error["type"] == "union_tag_invalid":
            pointer += "/type"
        capability = _planned_capability(error)
        if capability is not None:
            details.append(
                ErrorDetail(
                    UnsupportedOperation.code,
                    "Capability is recognised but not implemented in schema 1.0",
                    json_pointer=pointer,
                    context={"reason": "planned_capability", "capability": capability},
                )
            )
            continue
        details.append(
            ErrorDetail(
                ValidationError.code,
                (_MASK_MESSAGES if _in_masks(error) else _OWN_MESSAGES).get(
                    error["type"], error["msg"]
                ),
                json_pointer=pointer,
                context=_context(error),
            )
        )
    return details
