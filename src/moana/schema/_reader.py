"""Bounded reading of untrusted JSON before model validation (MOANA.md sections 12, 20).

Bytes are size-checked before decoding, and nesting depth and node count are measured
by a linear token scan before :func:`json.loads` builds any object. The parser then
rejects duplicate keys, ``NaN`` and ``Infinity``. Mappings supplied by Python callers
go through the same depth and node limits while being copied into plain ``dict`` and
``list`` trees, so bytes and mappings reach the models in the same shape.

A *node* is a JSON value (object, array, string, number, boolean or null); member
names are not nodes. The root object has depth 1.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from moana.core.coordinates import require_int
from moana.core.errors import ErrorDetail, ValidationError
from moana.schema._pointers import ROOT, Location, child_pointer, detail_sort_key

__all__ = [
    "DEFAULT_PARSE_LIMITS",
    "MAX_DOCUMENT_BYTES",
    "MAX_DOCUMENT_DEPTH",
    "MAX_DOCUMENT_NODES",
    "ParseLimits",
    "read_json_bytes",
    "read_mapping",
]

MAX_DOCUMENT_BYTES: Final = 8 * 1024 * 1024
MAX_DOCUMENT_DEPTH: Final = 32
MAX_DOCUMENT_NODES: Final = 20_000

# Strings (always consumed to their closing quote or to the end of input, without
# backtracking, so the scan stays linear), brackets and bare scalar words.
_TOKEN: Final = re.compile(r'"(?:[^"\\]|\\[\s\S])*+(?:"|\\?\Z)(\s*:)?|[\[{]|[\]}]|[^\s,:"\[\]{}]++')


@dataclass(frozen=True, slots=True)
class ParseLimits:
    """Structural limits of a document; a host may lower them, never raise them."""

    max_bytes: int = MAX_DOCUMENT_BYTES
    max_depth: int = MAX_DOCUMENT_DEPTH
    max_nodes: int = MAX_DOCUMENT_NODES

    def __post_init__(self) -> None:
        require_int(self.max_bytes, "max_bytes", minimum=2, maximum=MAX_DOCUMENT_BYTES)
        require_int(self.max_depth, "max_depth", minimum=1, maximum=MAX_DOCUMENT_DEPTH)
        require_int(self.max_nodes, "max_nodes", minimum=1, maximum=MAX_DOCUMENT_NODES)


DEFAULT_PARSE_LIMITS: Final = ParseLimits()


class _NonFiniteNumber(ValueError):
    pass


class _JsonObject(dict[str, object]):
    """Parsed object that remembers duplicate member names for later reporting."""

    duplicates: tuple[str, ...] = ()


def _error(
    message: str, reason: str, *, pointer: str | None = None, **extra: int
) -> ValidationError:
    return ValidationError(message, json_pointer=pointer, context={"reason": reason, **extra})


def _check_shape(text: str, limits: ParseLimits) -> None:
    depth = nodes = 0
    for match in _TOKEN.finditer(text):
        token = match.group()
        if token in "[{":
            depth += 1
            nodes += 1
            if depth > limits.max_depth:
                raise _error("document nesting is too deep", "too_deep", maximum=limits.max_depth)
        elif token in "]}":
            depth -= 1
        elif match.group(1) is None:
            nodes += 1
        if nodes > limits.max_nodes:
            raise _error("document has too many nodes", "too_many_nodes", maximum=limits.max_nodes)


def _object_pairs(pairs: list[tuple[str, object]]) -> _JsonObject:
    result = _JsonObject()
    duplicates: list[str] = []
    for key, value in pairs:
        if key in result:
            duplicates.append(key)
        result[key] = value
    if duplicates:
        result.duplicates = tuple(duplicates)
    return result


def _reject_constant(name: str) -> object:
    raise _NonFiniteNumber(name)


def _duplicate_details(root: object) -> list[ErrorDetail]:
    details: list[ErrorDetail] = []
    stack: list[tuple[object, Location]] = [(root, ROOT)]
    while stack:
        value, location = stack.pop()
        if isinstance(value, _JsonObject):
            for key in value.duplicates:
                pointer, exact = child_pointer(location, key)
                details.append(
                    ErrorDetail(
                        ValidationError.code,
                        "object has a duplicate member name",
                        json_pointer=pointer,
                        context={"reason": "duplicate_key", "exact_pointer": exact},
                    )
                )
            stack.extend((item, child_pointer(location, k)) for k, item in value.items())
        elif isinstance(value, list):
            stack.extend((item, child_pointer(location, i)) for i, item in enumerate(value))
    return details


def read_json_bytes(data: bytes, limits: ParseLimits = DEFAULT_PARSE_LIMITS) -> dict[str, object]:
    """Parse untrusted UTF-8 JSON into a plain tree whose root is an object.

    Raises :class:`ValidationError` (code ``VALIDATION_ERROR``) with a ``reason`` in its
    context: ``not_bytes``, ``too_large``, ``invalid_utf8``, ``too_deep``,
    ``too_many_nodes``, ``invalid_json``, ``non_finite_number``, ``duplicate_key``
    (with one detail per duplicate, located by pointer) or ``root_not_object``.
    """
    if not isinstance(data, bytes):
        raise _error("document source must be bytes", "not_bytes")
    if len(data) > limits.max_bytes:
        raise _error("document exceeds the byte limit", "too_large", maximum=limits.max_bytes)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _error("document is not valid UTF-8", "invalid_utf8", offset=exc.start) from None
    _check_shape(text, limits)
    try:
        root = json.loads(text, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
    except _NonFiniteNumber:
        raise _error("NaN and Infinity are not allowed", "non_finite_number") from None
    except json.JSONDecodeError as exc:
        raise _error(
            "document is not valid JSON", "invalid_json", line=exc.lineno, column=exc.colno
        ) from None
    except ValueError:  # integers beyond the interpreter's digit limit
        raise _error("document contains an unreadable number", "invalid_json") from None
    duplicates = _duplicate_details(root)
    if duplicates:
        duplicates.sort(key=detail_sort_key)
        raise ValidationError(
            "document has duplicate member names",
            json_pointer=duplicates[0].json_pointer,
            context={"reason": "duplicate_key", "issue_count": len(duplicates)},
            details=duplicates,
        )
    if not isinstance(root, dict):
        raise _error("document root must be an object", "root_not_object", pointer="")
    # Replace the parser's dict subclass so models only see built-in containers.
    copied = _copy_tree(root, limits)
    assert isinstance(copied, dict)
    return copied


def _copy_tree(root: object, limits: ParseLimits) -> object:
    """Iteratively copy mappings/sequences into dict/list, enforcing depth and nodes."""
    holder: list[object] = [None]
    # Frame: value to copy, its container depth, its pointer, destination and slot.
    stack: list[tuple[object, int, Location, dict[str, object] | list[object], str | int]] = [
        (root, 1, ROOT, holder, 0)
    ]
    nodes = 0
    while stack:
        value, depth, location, destination, slot = stack.pop()
        nodes += 1
        if nodes > limits.max_nodes:
            raise _error("document has too many nodes", "too_many_nodes", maximum=limits.max_nodes)
        copied: object = value
        children: list[tuple[str | int, object]] = []
        if isinstance(value, Mapping | list | tuple):
            if depth > limits.max_depth:
                raise _error("document nesting is too deep", "too_deep", maximum=limits.max_depth)
            if isinstance(value, Mapping):
                copied = {}
                for name, child in value.items():
                    if not isinstance(name, str):
                        raise _error(
                            "object member names must be strings",
                            "non_string_key",
                            pointer=location[0],
                        )
                    children.append((name, child))
            else:
                copied = [None] * len(value)
                children = list(enumerate(value))
        _assign(destination, slot, copied)
        for name, child in reversed(children):
            assert isinstance(copied, dict | list)
            stack.append((child, depth + 1, child_pointer(location, name), copied, name))
    return holder[0]


def _assign(destination: dict[str, object] | list[object], slot: str | int, value: object) -> None:
    if isinstance(destination, dict):
        assert isinstance(slot, str)
        destination[slot] = value
    else:
        assert isinstance(slot, int)
        destination[slot] = value


def read_mapping(
    source: Mapping[str, object], limits: ParseLimits = DEFAULT_PARSE_LIMITS
) -> dict[str, object]:
    """Copy a caller-supplied mapping into a plain JSON-shaped tree under the limits.

    Tuples become lists so a mapping and its JSON encoding validate identically.
    Self-referencing containers fail the depth limit instead of looping.
    """
    if not isinstance(source, Mapping):
        raise _error("document root must be an object", "root_not_object", pointer="")
    copied = _copy_tree(source, limits)
    assert isinstance(copied, dict)
    return copied
