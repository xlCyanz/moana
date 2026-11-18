"""Bounded JSON reading and canonical encoding of project files (ADR-029).

The manifest embeds a whole document plus assets and history, so it cannot use the
document reader of ``moana.schema`` (20 000 nodes). This reader applies the project
bounds instead: bytes, then a linear scan of depth and nodes before ``json.loads``,
duplicate member names and non-finite numbers rejected. The embedded document is
then validated by ``moana.schema`` with its own, stricter limits.
"""

from __future__ import annotations

import json
import math
import re
from typing import Final

from moana.core.errors import ValidationError

__all__ = ["canonical_bytes", "measure_shape", "read_json_object"]

# Strings (consumed to their closing quote without backtracking), brackets and bare
# scalar words; the same tokenisation as the document reader of ``moana.schema``.
_TOKEN: Final = re.compile(r'"(?:[^"\\]|\\[\s\S])*+(?:"|\\?\Z)(\s*:)?|[\[{]|[\]}]|[^\s,:"\[\]{}]++')


def _error(message: str, reason: str, **extra: int) -> ValidationError:
    return ValidationError(message, context={"field": "manifest", "reason": reason, **extra})


def measure_shape(text: str) -> tuple[int, int]:
    """Maximum nesting depth and node count, counted as the readers count them.

    Every value is a node (member names are not); the root container has depth 1.
    """
    depth = deepest = nodes = 0
    for match in _TOKEN.finditer(text):
        token = match.group()
        if token in "[{":
            depth += 1
            nodes += 1
            deepest = max(deepest, depth)
        elif token in "]}":
            depth -= 1
        elif match.group(1) is None:
            nodes += 1
    return deepest, nodes


def _check_shape(text: str, max_depth: int, max_nodes: int) -> None:
    depth = nodes = 0
    for match in _TOKEN.finditer(text):
        token = match.group()
        if token in "[{":
            depth += 1
            nodes += 1
            if depth > max_depth:
                raise _error("the manifest nesting is too deep", "too_deep", maximum=max_depth)
        elif token in "]}":
            depth -= 1
        elif match.group(1) is None:
            nodes += 1
        if nodes > max_nodes:
            raise _error("the manifest has too many nodes", "too_many_nodes", maximum=max_nodes)


class _Duplicate(ValueError):
    pass


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _Duplicate(key)
        result[key] = value
    return result


class _NonFinite(ValueError):
    pass


def _reject_constant(name: str) -> object:
    raise _NonFinite(name)


def _finite_float(text: str) -> float:
    value = float(text)
    if math.isinf(value):  # 1e999 overflows to infinity
        raise _NonFinite(text)
    return value


def read_json_object(data: bytes, *, max_bytes: int, max_depth: int, max_nodes: int) -> object:
    """Parse untrusted UTF-8 JSON under the bounds; the root may be any JSON value.

    ``ValidationError`` reasons: ``too_large``, ``invalid_utf8``, ``too_deep``,
    ``too_many_nodes``, ``duplicate_key``, ``non_finite_number`` (NaN, Infinity or a
    number that overflows to infinity) and ``invalid_json``.
    """
    if len(data) > max_bytes:
        raise _error("the manifest exceeds the byte limit", "too_large", maximum=max_bytes)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _error("the manifest is not valid UTF-8", "invalid_utf8") from None
    _check_shape(text, max_depth, max_nodes)
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except _Duplicate:
        raise _error("the manifest has a duplicate member name", "duplicate_key") from None
    except _NonFinite:
        raise _error("NaN and Infinity are not allowed", "non_finite_number") from None
    except ValueError:  # JSONDecodeError, oversized integers
        raise _error("the manifest is not valid JSON", "invalid_json") from None


def canonical_bytes(tree: object) -> bytes:
    """Sorted keys, no spaces, UTF-8, no NaN: the encoding of ``canonical_json``."""
    return json.dumps(
        tree, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
