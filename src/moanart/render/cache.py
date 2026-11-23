"""Opt-in, byte-bounded LRU cache of finished layer buffers (MOANA-032, ADR-038).

Rendering is deterministic, so a layer whose pixels depend on exactly the same
inputs gives exactly the same layer buffer (painted fills, clipped by its semantic
mask, before its opacity). A :class:`RenderCache` passed to
:func:`moanart.render.render` (or :func:`~moanart.render.render_admitted` and
:func:`~moanart.render.render_sequence`) keeps those buffers between calls, so after an
edit only the layers whose inputs changed are painted again; the others are
composited from the cache. There is no cache unless the caller creates one.

**Key** (private ``_layer_key``, versioned by :data:`CACHE_KEY_FORMAT`):
``sha256`` of the canonical JSON of the cache format,
``RENDERER_VERSION``, ``RENDERER_BACKEND``, ``ESTIMATOR_VERSION``, ``RNG_VERSION``,
the NumPy version and the vector backend versions of the document (AggDraw/Pillow,
when it has paths), the canvas size and profile, the document seed, the layer
without the members that do not change its buffer (``name``, ``locked``, ``visible``
and ``opacity``, applied when it is composited), every mask the layer uses with all
their operands (:func:`moanart.schema.mask_dependencies`), and the resolved RGBA of
every colour and ramp its operations reference (members from
:data:`moanart.schema.OPERATION_MEMBERS`). An edit therefore changes the key of every
consumer of what it changed, transitively, and of nothing else; two renderer,
backend, estimator or library versions never share an entry.

**Bounds**: an entry costs ``len(pixels) + ENTRY_OVERHEAD_BYTES``; the sum never
exceeds ``max_bytes`` (``1..MAX_CACHE_BYTES``). Inserting evicts least recently used
entries first; an entry larger than ``max_bytes`` is never stored. Entries are
immutable ``bytes`` copied on insert, so neither the renderer nor a caller can alter
them. The cache memory is the caller's, bounded by ``max_bytes``, and separate from
the request budget: every render with a cache is still validated, planned and
admitted by :func:`~moanart.render.plan_budget` and the composition budget before any
buffer exists, and the ``deadline`` is still checked before every layer.

A cache is not thread-safe: use one per thread or serialise its renders.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from typing import Final

import numpy as np

from moanart.core.coordinates import require_int
from moanart.core.procedural import RNG_VERSION
from moanart.palette import Palette
from moanart.render.budget import ESTIMATOR_VERSION
from moanart.render.result import RENDERER_BACKEND, RENDERER_VERSION
from moanart.schema import OPERATION_MEMBERS, Document, MaskNode, mask_dependencies
from moanart.schema import Layer as DocumentLayer

__all__ = [
    "CACHE_KEY_FORMAT",
    "ENTRY_OVERHEAD_BYTES",
    "MAX_CACHE_BYTES",
    "CacheStats",
    "RenderCache",
]

CACHE_KEY_FORMAT: Final = "moanart-layer-cache/1"
"""Version of the key recipe; a change of recipe changes every key."""
MAX_CACHE_BYTES: Final = 256 * 1024 * 1024
"""Largest ``max_bytes`` of a cache (the default ``max_buffer_bytes`` of a request)."""
ENTRY_OVERHEAD_BYTES: Final = 256
"""Bytes accounted per entry besides its pixels: the key string, the ``bytes`` header
and the ordered-dict slot (about 220 bytes on CPython 3.12; rounded up)."""
_NON_PIXEL_MEMBERS: Final = frozenset({"name", "locked", "visible", "opacity"})
"""Layer members that never change its buffer (opacity is applied when compositing)."""


@dataclass(frozen=True, slots=True)
class CacheStats:
    """Counters of a :class:`RenderCache` since it was created or cleared.

    ``rejected`` counts entries larger than ``max_bytes`` that were not stored. With
    a cache smaller than one layer buffer, every render of that layer counts one
    miss and then one rejection: expected behaviour, not a key failure.
    """

    entries: int
    used_bytes: int
    max_bytes: int
    hits: int
    misses: int
    stores: int
    evictions: int
    rejected: int


class RenderCache:
    """LRU cache of finished layer buffers bounded by ``max_bytes`` (ADR-038).

    ``max_bytes`` is an ``int`` (not ``bool``) in ``1..MAX_CACHE_BYTES``; otherwise
    ``ValidationError`` (``not_integer``, ``out_of_range``). Pass the same cache to
    successive renders; reusing it never changes a pixel, a digest, a warning or a
    provenance value (AC1).
    """

    __slots__ = (
        "_entries",
        "_evictions",
        "_hits",
        "_max_bytes",
        "_misses",
        "_rejected",
        "_stores",
        "_used",
    )

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = require_int(max_bytes, "max_bytes", minimum=1, maximum=MAX_CACHE_BYTES)
        self._entries: OrderedDict[str, bytes] = OrderedDict()
        self._used = 0
        self._hits = self._misses = self._stores = self._evictions = self._rejected = 0

    @property
    def max_bytes(self) -> int:
        """Upper bound of :attr:`used_bytes`."""
        return self._max_bytes

    @property
    def used_bytes(self) -> int:
        """Accounted bytes of the entries: pixels plus ``ENTRY_OVERHEAD_BYTES`` each."""
        return self._used

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: object) -> bool:
        return key in self._entries

    def keys(self) -> tuple[str, ...]:
        """Keys from least to most recently used."""
        return tuple(self._entries)

    def stats(self) -> CacheStats:
        """A snapshot of the counters."""
        return CacheStats(
            entries=len(self._entries),
            used_bytes=self._used,
            max_bytes=self._max_bytes,
            hits=self._hits,
            misses=self._misses,
            stores=self._stores,
            evictions=self._evictions,
            rejected=self._rejected,
        )

    def clear(self) -> None:
        """Drop every entry and reset the counters."""
        self._entries.clear()
        self._used = 0
        self._hits = self._misses = self._stores = self._evictions = self._rejected = 0

    def get(self, key: str) -> bytes | None:
        """The immutable pixels of ``key`` (now the most recently used), or ``None``."""
        pixels = self._entries.get(key)
        if pixels is None:
            self._misses += 1
            return None
        self._entries.move_to_end(key)
        self._hits += 1
        return pixels

    def put(self, key: str, pixels: bytes | bytearray | memoryview) -> bool:
        """Store a copy of ``pixels`` under ``key``, evicting LRU entries to fit.

        Returns ``False`` (and stores nothing) when one entry alone exceeds
        ``max_bytes``. A key already present is replaced. ``used_bytes`` never
        exceeds ``max_bytes`` after the call.
        """
        if type(key) is not str:
            raise TypeError("key must be a str")
        if not isinstance(pixels, bytes | bytearray | memoryview):
            raise TypeError("pixels must be bytes, bytearray or memoryview")
        size = pixels.nbytes if isinstance(pixels, memoryview) else len(pixels)
        cost = size + ENTRY_OVERHEAD_BYTES
        if cost > self._max_bytes:
            self._rejected += 1
            return False
        self._discard(key)
        while self._used + cost > self._max_bytes:
            _, evicted = self._entries.popitem(last=False)
            self._used -= len(evicted) + ENTRY_OVERHEAD_BYTES
            self._evictions += 1
        self._entries[key] = bytes(pixels)  # an independent, immutable copy
        self._used += cost
        self._stores += 1
        return True

    def _discard(self, key: str) -> None:
        pixels = self._entries.pop(key, None)
        if pixels is not None:
            self._used -= len(pixels) + ENTRY_OVERHEAD_BYTES

    def __repr__(self) -> str:
        return (
            f"RenderCache(max_bytes={self._max_bytes}, used_bytes={self._used}, "
            f"entries={len(self._entries)})"
        )


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _hex(color: object) -> str:
    r, g, b, a = (getattr(color, channel) for channel in ("r", "g", "b", "a"))
    return f"#{r:02X}{g:02X}{b:02X}{a:02X}"


def _layer_references(layer: DocumentLayer) -> tuple[list[str], list[str], list[str]]:
    """Mask, colour and ramp IDs referenced by ``layer`` and its operations, in order."""
    masks = [] if layer.mask_id is None else [layer.mask_id]
    colors: list[str] = []
    ramps: list[str] = []
    for operation in layer.operations:
        row = OPERATION_MEMBERS[operation.type]
        colors.extend(str(getattr(operation, member)) for member in row.colors)
        ramps.extend(str(getattr(operation, member)) for member in row.ramps)
        masks.extend(str(getattr(operation, member)) for member in row.masks)
        for items, item_row in row.items:
            for item in getattr(operation, items):
                colors.extend(str(getattr(item, member)) for member in item_row.colors)
                ramps.extend(str(getattr(item, member)) for member in item_row.ramps)
                masks.extend(str(getattr(item, member)) for member in item_row.masks)
    return masks, colors, ramps


@dataclass(frozen=True, slots=True)
class _KeyContext:
    """What every layer key of one render shares: the prefix and a mask index.

    ``closures`` memoises :func:`moanart.schema.mask_dependencies` per mask ID for the
    render, so a mask referenced by several layers or operations is expanded once.
    """

    prefix: dict[str, object]
    masks: dict[str, MaskNode]
    closures: dict[str, tuple[str, ...]]

    def closure(self, document: Document, mask_id: str) -> tuple[str, ...]:
        found = self.closures.get(mask_id)
        if found is None:
            found = self.closures[mask_id] = mask_dependencies(document, mask_id)
        return found


def _document_prefix(document: Document, backend_versions: tuple[str, ...]) -> _KeyContext:
    """Key members shared by every layer of ``document`` (versions, canvas, seed)."""
    prefix: dict[str, object] = {
        "format": CACHE_KEY_FORMAT,
        "renderer": [RENDERER_VERSION, RENDERER_BACKEND, ESTIMATOR_VERSION, RNG_VERSION],
        "libraries": [f"numpy=={np.__version__}", *backend_versions],
        "canvas": [document.canvas.width, document.canvas.height, document.canvas.profile],
        "seed": document.seed,
    }
    return _KeyContext(prefix, {mask.id: mask for mask in document.masks}, {})


def _layer_key(
    document: Document,
    layer: DocumentLayer,
    palette: Palette,
    context: _KeyContext,
) -> str:
    """``sha256:`` key of the finished buffer of ``layer`` of a validated ``document``.

    ``context`` comes from :func:`_document_prefix` for the same document;
    ``palette`` is the document palette already resolved for its profile.
    """
    mask_ids, color_ids, ramp_ids = _layer_references(layer)
    closure: dict[str, None] = {}
    for mask_id in mask_ids:
        closure.update(dict.fromkeys(context.closure(document, mask_id)))
    content = {
        **context.prefix,
        "layer": layer.model_dump(mode="json", exclude=set(_NON_PIXEL_MEMBERS)),
        "masks": [context.masks[mask_id].model_dump(mode="json") for mask_id in sorted(closure)],
        "colors": {color_id: _hex(palette.color(color_id)) for color_id in color_ids},
        "ramps": {
            ramp_id: [_hex(color) for color in palette.ramp(ramp_id)] for ramp_id in ramp_ids
        },
    }
    return "sha256:" + hashlib.sha256(_canonical(content)).hexdigest()
