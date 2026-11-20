"""Opt-in layer-buffer cache of the renderer (MOANA-032, ADR-038).

AC1: cache on/off gives the same ``RenderResult`` (RGBA, digest, warnings and
provenance). AC2: an edit changes the key of every consumer of what it changed,
transitively, and the cache never exceeds ``max_bytes``. T1: full render vs
cached/incremental render for palette, mask, layer (visibility, opacity, order) and
operation edits, and for animation frames; schema 1.0 has no groups, so ``render``
never builds a ``Group`` and the group case (opacity, nesting) is covered at the
``moana.layers.compose`` level with a recording ``LayerBuffers`` store. T2: LRU
eviction by bytes, separation of
renderer/backend/estimator versions, external mutation and budgets on hits.

The oracle is always the uncached render of the same document (the existing path),
never a stored output; each edit is also checked to change the image, so a stale
entry could not go unnoticed.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.animation import render_animation
from moana.core.budget import Deadline, RenderLimits
from moana.core.coordinates import Box, Dimensions
from moana.core.errors import BudgetExceeded, ValidationError
from moana.core.procedural import RNG_VERSION
from moana.geometry import rasterize_rect
from moana.layers import Fill, Group, Layer, LayerTree, compose
from moana.palette import Palette, Rgba
from moana.render import (
    ENTRY_OVERHEAD_BYTES,
    ESTIMATOR_VERSION,
    MAX_CACHE_BYTES,
    RENDERER_BACKEND,
    RENDERER_VERSION,
    RenderCache,
    plan_frame,
    render,
    render_admitted,
    render_sequence,
)
from moana.render import cache as cache_module
from moana.render.cache import _document_prefix, _layer_key
from moana.schema import Document, mask_dependencies, validate_document

ROOT = Path(__file__).resolve().parents[3]
WALK = ROOT / "examples" / "corpus" / "adventurer-walk" / "adventurer-walk.moana.json"
WIDTH, HEIGHT = 16, 12
ENTRY = WIDTH * HEIGHT * 4 + ENTRY_OVERHEAD_BYTES
BIG = 1 << 20


def tree() -> dict[str, Any]:
    """Four layers sharing masks and palette entries (rgba profile, 16x12).

    ``left`` is used by ``body`` (through the union ``both``) and by ``shading`` (a
    band); ``ink`` by ``body`` and ``pattern``; the ramp colours only by ``shading``.
    """
    lamp = {"direction": "nw", "height": 0, "intensity": 1, "ambient": 1}
    return {
        "schema_version": "1.0",
        "id": "doc",
        "seed": 7,
        "canvas": {"width": WIDTH, "height": HEIGHT, "profile": "rgba"},
        "palette": {
            "id": "pal",
            "colors": [
                {"id": "sky", "rgba": "#4080C0FF"},
                {"id": "ink", "rgba": "#102030FF"},
                {"id": "red", "rgba": "#E02020FF"},
                {"id": "t0", "rgba": "#202040FF"},
                {"id": "t1", "rgba": "#6060A0FF"},
                {"id": "t2", "rgba": "#C0C0F0FF"},
            ],
            "ramps": [{"id": "ramp", "colors": ["t0", "t1", "t2"]}],
        },
        "masks": [
            {"id": "left", "type": "rect", "box": [0, 0, 8, 12]},
            {"id": "right", "type": "rect", "box": [6, 0, 16, 12]},
            {"id": "both", "type": "union", "masks": ["left", "right"]},
            {"id": "blob", "type": "ellipse", "box": [3, 2, 13, 10]},
        ],
        "layers": [
            {
                "id": "back",
                "name": "Back",
                "operations": [
                    {"id": "fill", "type": "rect", "box": [0, 0, 16, 12], "color": "sky"}
                ],
            },
            {
                "id": "body",
                "name": "Body",
                "opacity": 200,
                "mask_id": "both",
                "operations": [
                    {"id": "torso", "type": "rect", "box": [1, 1, 15, 11], "color": "ink"}
                ],
            },
            {
                "id": "shading",
                "name": "Shading",
                "opacity": 160,
                "operations": [
                    {
                        "id": "shade",
                        "type": "shade",
                        "ramp": "ramp",
                        "ramp_order": "monotonic",
                        "light": lamp,
                        "bands": [
                            {"id": "lit", "mask_id": "left", "facing": "nw", "offset": 0},
                            {"id": "dark", "mask_id": "right", "facing": "se", "offset": 0},
                        ],
                    }
                ],
            },
            {
                "id": "pattern",
                "name": "Pattern",
                "operations": [
                    {
                        "id": "dots",
                        "type": "dither",
                        "size": 2,
                        "coverage": 2,
                        "origin": [0, 0],
                        "color_a": "red",
                        "color_b": "ink",
                        "mask_id": "blob",
                    },
                    {
                        "id": "rim",
                        "type": "outline",
                        "mask_id": "blob",
                        "color": "ink",
                        "width": 1,
                        "side": "inner",
                    },
                ],
            },
        ],
    }


def document(edit: Callable[[dict[str, Any]], None] | None = None) -> Document:
    data = tree()
    if edit is not None:
        edit(data)
    return validate_document(data)


def color(data: dict[str, Any], color_id: str, value: str) -> None:
    for entry in data["palette"]["colors"]:
        if entry["id"] == color_id:
            entry["rgba"] = value


def layer(data: dict[str, Any], layer_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(item for item in data["layers"] if item["id"] == layer_id)
    return found


def mask(data: dict[str, Any], mask_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(item for item in data["masks"] if item["id"] == mask_id)
    return found


def swap_order(data: dict[str, Any]) -> None:
    data["layers"][2], data["layers"][3] = data["layers"][3], data["layers"][2]


EDITS: dict[str, Callable[[dict[str, Any]], None]] = {
    "palette_ramp_colour": lambda d: color(d, "t0", "#90F090FF"),
    "palette_shared_colour": lambda d: color(d, "ink", "#F0F000FF"),
    "mask_leaf_geometry": lambda d: mask(d, "left").update(box=[0, 0, 4, 12]),
    "mask_combination_operands": lambda d: mask(d, "both").update(masks=["blob", "right"]),
    "layer_visibility": lambda d: layer(d, "pattern").update(visible=False),
    "layer_opacity": lambda d: layer(d, "body").update(opacity=90),
    "layer_mask_reference": lambda d: layer(d, "body").update(mask_id="blob"),
    "layer_order": swap_order,
    "operation_parameter": lambda d: layer(d, "pattern")["operations"][0].update(coverage=1),
    "operation_colour_reference": lambda d: layer(d, "back")["operations"][0].update(color="red"),
    "operation_geometry": lambda d: layer(d, "body")["operations"][0].update(box=[2, 2, 9, 9]),
    "seed": lambda d: d.update(seed=8),
}
INVISIBLE = {"seed"}  # no ``material`` here: the seed changes keys, not pixels


def keys(doc: Document) -> dict[str, str]:
    palette = Palette.from_mapping(doc.palette.model_dump(mode="json"), profile=doc.canvas.profile)
    context = _document_prefix(doc, ())
    return {item.id: _layer_key(doc, item, palette, context) for item in doc.layers}


# --- AC1 / T1: identical results with and without the cache --------------------------------


def test_ac1_cold_and_warm_renders_equal_the_uncached_render() -> None:
    doc = document()
    reference = render(doc)
    cache = RenderCache(BIG)
    assert render(doc, cache=cache) == reference  # cold: every layer stored
    assert cache.stats().stores == 4 and cache.stats().hits == 0
    assert render(doc, cache=cache) == reference  # warm: every layer reused
    assert cache.stats().hits == 4 and cache.stats().misses == 4
    assert reference.warnings == render(doc, cache=cache).warnings


@pytest.mark.parametrize("name", sorted(EDITS))
def test_t1_incremental_render_equals_full_render(name: str) -> None:
    base, edited = document(), document(EDITS[name])
    cache = RenderCache(BIG)
    before = render(base, cache=cache)
    full = render(edited)
    if name not in INVISIBLE:
        assert full.rgba != before.rgba  # the edit is visible: a stale entry would show
    assert render(edited, cache=cache) == full
    assert render(edited, cache=cache) == full  # and again, now fully warm


def test_t1_alternating_edits_reuse_entries_and_stay_exact() -> None:
    documents = [document(), document(EDITS["palette_ramp_colour"]), document(EDITS["seed"])]
    references = [render(doc) for doc in documents]
    cache = RenderCache(BIG)
    for _ in range(3):
        for doc, reference in zip(documents, references, strict=True):
            assert render(doc, cache=cache) == reference
    assert cache.stats().hits > cache.stats().misses


# --- AC2: transitive invalidation -----------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "changed"),
    [
        ("mask_leaf_geometry", {"body", "shading"}),  # body through the union ``both``
        ("mask_combination_operands", {"body"}),
        ("palette_ramp_colour", {"shading"}),
        ("palette_shared_colour", {"body", "pattern"}),
        ("operation_parameter", {"pattern"}),
        ("layer_mask_reference", {"body"}),
        ("seed", {"back", "body", "shading", "pattern"}),
        ("layer_opacity", set()),  # applied when compositing, not part of the buffer
        ("layer_visibility", set()),
        ("layer_order", set()),
    ],
)
def test_ac2_an_edit_changes_the_key_of_every_consumer_and_only_them(
    name: str, changed: set[str]
) -> None:
    before, after = keys(document()), keys(document(EDITS[name]))
    assert {layer_id for layer_id in before if before[layer_id] != after[layer_id]} == changed


def test_ac2_a_mask_edit_repaints_both_consumers_and_reuses_the_rest() -> None:
    cache = RenderCache(BIG)
    render(document(), cache=cache)
    edited = document(EDITS["mask_leaf_geometry"])
    hits, misses = cache.stats().hits, cache.stats().misses
    assert render(edited, cache=cache) == render(edited)
    assert cache.stats().misses - misses == 2  # body and shading
    assert cache.stats().hits - hits == 2  # back and pattern


def test_ac2_a_cache_smaller_than_the_document_stays_bounded_and_exact() -> None:
    cache = RenderCache(2 * ENTRY)  # room for two of the four layers
    for name in sorted(EDITS):
        doc = document(EDITS[name])
        assert render(doc, cache=cache) == render(doc)
        assert cache.used_bytes <= cache.max_bytes
    assert len(cache) == 2 and cache.stats().evictions > 0


def test_ac2_hidden_layers_and_empty_masks_are_not_stored() -> None:
    def hide(data: dict[str, Any]) -> None:
        data["masks"].append({"id": "gone", "type": "rect", "box": [40, 40, 50, 50]})
        layer(data, "body")["mask_id"] = "gone"  # clipped to nothing: draws nothing
        layer(data, "pattern")["visible"] = False

    doc = document(hide)
    cache = RenderCache(BIG)
    assert render(doc, cache=cache) == render(doc)
    assert render(doc, cache=cache) == render(doc)
    assert cache.stats().stores == 2  # back and shading


# --- T2: LRU by bytes, bounds and counters ---------------------------------------------------


def test_t2_lru_evicts_the_least_recently_used_entry_first() -> None:
    cache = RenderCache(3 * (100 + ENTRY_OVERHEAD_BYTES))
    for key in ("a", "b", "c"):
        assert cache.put(key, bytes(100))
    assert cache.get("a") == bytes(100)  # ``a`` becomes the most recent
    assert cache.put("d", bytes(100))
    assert cache.keys() == ("c", "a", "d")  # ``b`` was evicted
    assert cache.put("e", bytes(150))  # needs two slots: evicts ``c`` then ``a``
    assert cache.keys() == ("d", "e")
    assert cache.used_bytes == 250 + 2 * ENTRY_OVERHEAD_BYTES
    assert cache.stats().evictions == 3


def test_t2_an_entry_larger_than_the_cache_is_never_stored() -> None:
    cache = RenderCache(100 + ENTRY_OVERHEAD_BYTES)
    assert cache.put("fits", bytes(100))
    assert not cache.put("huge", bytes(101))
    assert cache.keys() == ("fits",) and cache.stats().rejected == 1
    assert cache.get("huge") is None


def test_t2_replacing_a_key_accounts_bytes_exactly() -> None:
    cache = RenderCache(1000)
    cache.put("k", bytes(300))
    cache.put("k", bytes(10))
    assert len(cache) == 1 and cache.used_bytes == 10 + ENTRY_OVERHEAD_BYTES
    cache.clear()
    assert len(cache) == 0 and cache.used_bytes == 0 and cache.stats().stores == 0


@settings(max_examples=150, deadline=None, derandomize=True)
@given(
    limit=st.integers(min_value=1, max_value=4000),
    steps=st.lists(st.tuples(st.booleans(), st.integers(0, 7), st.integers(0, 1200)), max_size=60),
)
def test_t2_property_lru_model_and_limit_after_every_insert(
    limit: int, steps: list[tuple[bool, int, int]]
) -> None:
    cache = RenderCache(limit)
    model: dict[str, int] = {}  # insertion order of a dict is the LRU order of the model
    for is_put, number, size in steps:
        key = f"k{number}"
        if is_put:
            stored = cache.put(key, bytes(size))
            assert stored == (size + ENTRY_OVERHEAD_BYTES <= limit)
            if stored:
                model.pop(key, None)
                while (
                    sum(s + ENTRY_OVERHEAD_BYTES for s in model.values())
                    + (size + ENTRY_OVERHEAD_BYTES)
                    > limit
                ):
                    del model[next(iter(model))]
                model[key] = size
        else:
            got = cache.get(key)
            assert (got is None) == (key not in model)
            if key in model:
                assert got == bytes(model[key])
                model[key] = model.pop(key)
        assert cache.used_bytes <= cache.max_bytes
        assert cache.used_bytes == sum(s + ENTRY_OVERHEAD_BYTES for s in model.values())
        assert cache.keys() == tuple(model)


@pytest.mark.parametrize("value", [0, -1, MAX_CACHE_BYTES + 1, True, 1.0, "64", None])
def test_t2_max_bytes_is_validated(value: object) -> None:
    with pytest.raises(ValidationError):
        RenderCache(value)  # type: ignore[arg-type]  # rejected values on purpose


def test_t2_max_bytes_bounds_are_accepted() -> None:
    assert RenderCache(1).max_bytes == 1
    assert RenderCache(MAX_CACHE_BYTES).max_bytes == MAX_CACHE_BYTES


def test_t2_bad_arguments_are_type_errors() -> None:
    cache = RenderCache(BIG)
    with pytest.raises(TypeError):
        cache.put(1, b"")  # type: ignore[arg-type]  # wrong key type on purpose
    with pytest.raises(TypeError):
        cache.put("k", [1, 2])  # type: ignore[arg-type]  # wrong payload type on purpose
    with pytest.raises(TypeError):
        render(document(), cache=object())  # type: ignore[arg-type]  # on purpose
    with pytest.raises(TypeError):
        render_animation(walk(), "walk", cache=object())  # type: ignore[arg-type]


# --- T2: versions never share entries --------------------------------------------------------


@pytest.mark.parametrize(
    "constant", ["RENDERER_VERSION", "RENDERER_BACKEND", "ESTIMATOR_VERSION", "RNG_VERSION"]
)
def test_t2_another_version_never_reuses_an_entry(
    monkeypatch: pytest.MonkeyPatch, constant: str
) -> None:
    doc = document()
    cache = RenderCache(BIG)
    render(doc, cache=cache)
    before = keys(doc)
    monkeypatch.setattr(cache_module, constant, "other-v9")
    after = keys(doc)
    assert all(before[item] != after[item] for item in before)
    hits = cache.stats().hits
    assert render(doc, cache=cache) == render(doc)
    assert cache.stats().hits == hits  # nothing reused across versions


def test_t2_library_and_vector_backend_versions_are_in_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = document()
    palette = Palette.from_mapping(doc.palette.model_dump(mode="json"), profile="rgba")
    body = doc.layers[1]
    plain = _layer_key(doc, body, palette, _document_prefix(doc, ()))
    vector = _layer_key(doc, body, palette, _document_prefix(doc, ("aggdraw==1.3.19",)))
    assert plain != vector
    monkeypatch.setattr(np, "__version__", "0.0.0")
    assert _layer_key(doc, body, palette, _document_prefix(doc, ())) != plain


# --- T2: no mutable alias in or out ----------------------------------------------------------


def test_t2_mutating_the_inserted_buffer_does_not_change_the_entry() -> None:
    cache = RenderCache(BIG)
    source = bytearray(b"\x01" * 64)
    view = memoryview(source)
    cache.put("a", source)
    cache.put("b", view)
    source[:] = b"\x02" * 64
    stored_a, stored_b = cache.get("a"), cache.get("b")
    assert type(stored_a) is bytes and stored_a == b"\x01" * 64
    assert type(stored_b) is bytes and stored_b == b"\x01" * 64


class Recorder:
    """A ``LayerBuffers`` store that records what ``compose`` offers and reuses."""

    def __init__(self, reuse: dict[str, bytes] | None = None) -> None:
        self.reuse = reuse or {}
        self.views: list[memoryview] = []

    def lookup(self, layer_id: str) -> bytes | None:
        return self.reuse.get(layer_id)

    def store(self, layer_id: str, pixels: memoryview) -> None:
        self.views.append(pixels)


def red_tree() -> LayerTree:
    dims = Dimensions(4, 3)
    fill = Fill(rasterize_rect(Box(0, 0, 2, 2), dims), Rgba(255, 0, 0, 255))
    return LayerTree(dims, (Layer("only", "Only", (fill,), opacity=128),), profile="rgba")


def test_t2_compose_offers_a_read_only_view_and_reuses_read_only_bytes() -> None:
    limits = RenderLimits()
    recorder = Recorder()
    painted = compose(red_tree(), limits=limits, buffers=recorder)
    (view,) = recorder.views
    assert view.readonly
    with pytest.raises(TypeError):
        view[0, 0, 0] = 1  # the store cannot write the buffer
    stored = bytes(view)
    reused = compose(red_tree(), limits=limits, buffers=Recorder({"only": stored}))
    assert reused == painted == compose(red_tree(), limits=limits)


def test_t2_a_store_returning_the_wrong_size_is_a_programming_error() -> None:
    with pytest.raises(RuntimeError, match="bytes of another size"):
        compose(red_tree(), limits=RenderLimits(), buffers=Recorder({"only": b"\x00"}))


def test_t2_a_store_returning_a_mutable_buffer_is_a_programming_error() -> None:
    mutable = cast(bytes, bytearray(4 * 3 * 4))  # a store that breaks the protocol
    with pytest.raises(RuntimeError, match="not bytes"):
        compose(red_tree(), limits=RenderLimits(), buffers=Recorder({"only": mutable}))


def test_t2_results_are_bytes_and_cannot_alias_the_cache() -> None:
    cache = RenderCache(BIG)
    doc = document()
    first = render(doc, cache=cache)
    assert type(first.rgba) is bytes
    entries = [cache.get(key) for key in cache.keys()]  # noqa: SIM118 - LRU order
    second = render(doc, cache=cache)
    assert second == first
    assert [cache.get(key) for key in cache.keys()] == entries  # noqa: SIM118


# --- T2: budgets and deadline still apply on hits ---------------------------------------------


def test_t2_budgets_are_enforced_before_any_hit() -> None:
    doc = document()
    cache = RenderCache(BIG)
    render(doc, cache=cache)
    stats = cache.stats()
    with pytest.raises(BudgetExceeded):
        render(doc, limits=RenderLimits(max_pixel_visits=10), cache=cache)
    assert cache.stats() == stats  # rejected before the cache was even consulted


def test_t2_the_deadline_is_checked_on_a_warm_cache() -> None:
    doc = document()
    cache = RenderCache(BIG)
    render(doc, cache=cache)
    ticks = iter(range(10_000))

    def clock() -> float:
        return float(next(ticks))  # one second per reading: expires on the first check

    with pytest.raises(BudgetExceeded):
        render(doc, deadline=Deadline(1, clock=clock), cache=cache)


# --- T1: animation frames and sequences --------------------------------------------------------


def walk() -> Document:
    return validate_document(WALK.read_bytes())


def test_t1_animation_frames_cached_equal_uncached() -> None:
    doc = walk()
    reference = render_animation(doc, "walk")
    cache = RenderCache(BIG)
    cold = render_animation(doc, "walk", cache=cache)
    warm = render_animation(doc, "walk", cache=cache)
    assert cold == reference and warm == reference
    assert cache.stats().hits > 0


def test_t1_sequences_and_admitted_frames_accept_the_cache() -> None:
    base, edited = document(), document(EDITS["mask_leaf_geometry"])
    pairs = [("f0", base), ("f1", edited), ("f2", base)]
    cache = RenderCache(BIG)
    assert render_sequence(pairs, cache=cache) == render_sequence(pairs)
    estimate = plan_frame(edited)
    admitted = render_admitted(edited, frame_id="f9", estimate=estimate, cache=cache)
    assert admitted == render_admitted(edited, frame_id="f9", estimate=estimate)


def test_t1_a_deep_copy_of_the_document_hits_the_same_entries() -> None:
    doc = document()
    cache = RenderCache(BIG)
    render(doc, cache=cache)
    hits = cache.stats().hits
    assert render(copy.deepcopy(doc), cache=cache) == render(doc)
    assert cache.stats().hits - hits == 4


def test_t2_membership_and_repr_describe_the_cache_without_its_pixels() -> None:
    cache = RenderCache(1000)
    cache.put("k", bytes(10))
    assert "k" in cache and "other" not in cache
    assert repr(cache) == (
        f"RenderCache(max_bytes=1000, used_bytes={10 + ENTRY_OVERHEAD_BYTES}, entries=1)"
    )


def test_t2_a_live_deadline_is_checked_for_every_key_and_changes_nothing() -> None:
    doc = document()
    readings: list[int] = []

    def clock() -> float:
        readings.append(1)
        return 0.0  # never expires: only counts the checks

    cache = RenderCache(BIG)
    assert render(doc, deadline=Deadline(1000, clock=clock)) == render(doc)
    without = len(readings)
    readings.clear()
    assert render(doc, deadline=Deadline(1000, clock=clock), cache=cache) == render(doc)
    assert len(readings) == without + 4  # one ``cache_key`` check per visible layer


# --- AC2: the key recipe is unchanged by the per-render mask memo ---------------------------


def reference_key(doc: Document, layer_id: str) -> str:
    """The key recipe of ADR-038 written out again, without the memo or the mask index."""
    item = next(entry for entry in doc.layers if entry.id == layer_id)
    palette = Palette.from_mapping(doc.palette.model_dump(mode="json"), profile="rgba")
    used = [] if item.mask_id is None else [item.mask_id]
    colors: dict[str, str] = {}
    ramps: dict[str, list[str]] = {}

    def hexa(value: Rgba) -> str:
        return f"#{value.r:02X}{value.g:02X}{value.b:02X}{value.a:02X}"

    for operation in item.operations:
        data = operation.model_dump(mode="json")
        used += [data[k] for k in ("mask_id",) if k in data]
        used += [entry["mask_id"] for k in ("bands", "segments") for entry in data.get(k, ())]
        colors |= {
            data[k]: hexa(palette.color(data[k]))
            for k in ("color", "color_a", "color_b")
            if k in data
        }
        if "ramp" in data:
            ramps[data["ramp"]] = [hexa(value) for value in palette.ramp(data["ramp"])]
    closure = sorted({name for mask_id in used for name in mask_dependencies(doc, mask_id)})
    by_id = {entry.id: entry for entry in doc.masks}
    content = {
        "format": "moana-layer-cache/1",
        "renderer": [RENDERER_VERSION, RENDERER_BACKEND, ESTIMATOR_VERSION, RNG_VERSION],
        "libraries": [f"numpy=={np.__version__}"],
        "canvas": [WIDTH, HEIGHT, "rgba"],
        "seed": doc.seed,
        "layer": item.model_dump(mode="json", exclude={"name", "locked", "visible", "opacity"}),
        "masks": [by_id[name].model_dump(mode="json") for name in closure],
        "colors": colors,
        "ramps": ramps,
    }
    blob = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("name", [None, "mask_leaf_geometry", "palette_shared_colour"])
def test_ac2_memoised_keys_equal_the_written_out_recipe(name: str | None) -> None:
    doc = document(None if name is None else EDITS[name])
    computed = keys(doc)  # one context shared by every layer: ``left`` expanded once
    assert computed == {item.id: reference_key(doc, item.id) for item in doc.layers}


# --- T1: groups (layers level; schema 1.0 has no groups) ------------------------------------


class Prefilled:
    """A ``LayerBuffers`` store that keeps copies on the first pass and reuses them."""

    def __init__(self) -> None:
        self.entries: dict[str, bytes] = {}
        self.hits = 0

    def lookup(self, layer_id: str) -> bytes | None:
        found = self.entries.get(layer_id)
        self.hits += found is not None
        return found

    def store(self, layer_id: str, pixels: memoryview) -> None:
        self.entries[layer_id] = bytes(pixels)


def group_tree() -> LayerTree:
    """Nested groups with opacity != 255 over a base layer (rgba profile, 6x5)."""
    dims = Dimensions(6, 5)

    def layer_of(name: str, box: Box, rgba: Rgba, opacity: int = 255) -> Layer:
        return Layer(name, name, (Fill(rasterize_rect(box, dims), rgba),), opacity=opacity)

    inner = Group(
        "inner",
        "Inner",
        (
            layer_of("dot", Box(2, 1, 5, 4), Rgba(0, 200, 40, 255), opacity=170),
            layer_of("glow", Box(1, 2, 4, 5), Rgba(250, 250, 0, 128)),
        ),
        opacity=140,
    )
    outer = Group(
        "outer",
        "Outer",
        (layer_of("band", Box(0, 0, 6, 2), Rgba(200, 30, 30, 255)), inner),
        opacity=200,
    )
    base = layer_of("base", Box(0, 0, 6, 5), Rgba(20, 40, 160, 255))
    return LayerTree(dims, (base, outer), profile="rgba")


def test_t1_groups_with_opacity_and_nesting_reuse_layer_buffers_exactly() -> None:
    limits = RenderLimits()
    reference = compose(group_tree(), limits=limits)
    store = Prefilled()
    first = compose(group_tree(), limits=limits, buffers=store)
    assert set(store.entries) == {"base", "band", "dot", "glow"}  # layers, not groups
    second = compose(group_tree(), limits=limits, buffers=store)
    assert store.hits == 4
    assert first.to_bytes() == second.to_bytes() == reference.to_bytes()
