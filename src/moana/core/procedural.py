"""Deterministic per-cell randomness keyed by identity (MOANA.md section 14, ADR-018).

It lives in ``core`` so that ``techniques`` (dithering, noise, materials), which may
not import ``render`` (MOANA.md section 3), can use it.

A procedural effect never shares a stream: each value is derived from the SHA-256 of
the canonical JSON array ``[seed, operation_id, x, y, channel, algorithm_version]``
(no spaces, UTF-8). ``u`` is the first 8 bytes of that digest read big-endian and a
value in ``range(n)`` is ``u * n // 2**64``. Adding, removing or reordering other
operations therefore never changes the sequence of an operation; only its own ID,
the document seed, the cell and :data:`RNG_VERSION` do. Nothing here reads a clock,
``hash()`` or global state. This is not cryptography: it is a versioned,
reproducible sequence.
"""

from __future__ import annotations

import hashlib
import json
from typing import Final

from moana.core.coordinates import MAX_COORDINATE, require_int
from moana.core.ids import check_id

__all__ = ["MAX_CHANNEL", "MAX_SEED", "RNG_VERSION", "cell_choice", "cell_unit"]

RNG_VERSION: Final = "cell-sha256-v1"
MAX_SEED: Final = 2**64 - 1
MAX_CHANNEL: Final = 2**32 - 1
_UNIT_RANGE: Final = 2**64


def _key(seed: int, operation_id: str, x: int, y: int, channel: int, version: str) -> bytes:
    require_int(seed, "seed", minimum=0, maximum=MAX_SEED)
    check_id(operation_id)
    require_int(x, "x", minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE)
    require_int(y, "y", minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE)
    require_int(channel, "channel", minimum=0, maximum=MAX_CHANNEL)
    if type(version) is not str or not version:
        raise TypeError("version must be a non-empty str")
    array = [seed, operation_id, x, y, channel, version]
    return json.dumps(array, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def cell_unit(
    seed: int, operation_id: str, x: int, y: int, channel: int, *, version: str = RNG_VERSION
) -> int:
    """The 64-bit value ``u`` of one cell: first 8 digest bytes, big-endian."""
    digest = hashlib.sha256(_key(seed, operation_id, x, y, channel, version)).digest()
    return int.from_bytes(digest[:8], "big")


def cell_choice(
    seed: int,
    operation_id: str,
    x: int,
    y: int,
    channel: int,
    n: int,
    *,
    version: str = RNG_VERSION,
) -> int:
    """A value in ``range(n)`` for one cell: ``u * n // 2**64`` (``1 <= n <= 2**64``)."""
    require_int(n, "n", minimum=1, maximum=_UNIT_RANGE)
    return cell_unit(seed, operation_id, x, y, channel, version=version) * n // _UNIT_RANGE
