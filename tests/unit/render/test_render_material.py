"""AC1/AC2/T1/T2 (MOANA-017): ``material`` and ``selective_outline`` rendered (ADR-030).

Pixel oracles are hand-written grids or the rules of ADR-030 restated here (the
``shade`` index ``clamp(ambient + level + offset)``, then ``+ texture offset`` and a
second clamp), with seeded cells recomputed from MOANA.md section 14 with ``hashlib``.
``budget-v8`` figures are computed by hand.
"""

from __future__ import annotations

import hashlib
import json
import tracemalloc
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.api import inspect_document
from moana.core import errors
from moana.core.budget import RenderLimits
from moana.core.coordinates import Box, Dimensions, Point
from moana.core.materials import MATERIAL_PRESETS
from moana.palette import RAMP_LUMINANCE_NOT_INCREASING
from moana.render import estimate_cost, plan_budget, render
from moana.render.budget import (
    ESTIMATOR_VERSION,
    MATERIAL_CELL_BYTES,
    MATERIAL_FIXED_BYTES,
    MATERIAL_HASH_VISITS,
    MATERIAL_PASSES,
    fill_count,
    mask_estimates,
    material_cost,
    outline_box,
    selective_outline_cost,
    shade_later,
)
from moana.render.pipeline import _material_part, _outline_base, _outline_segment, _plan_masks
from moana.schema import Document, MaterialOperation, SelectiveOutlineOperation, validate_document
from moana.techniques import MaterialTexture, texture_cells

ROOT = Path(__file__).resolve().parents[3]
RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)
TONES: dict[str, RGBA] = {
    "t0": (32, 32, 64, 255),
    "t1": (64, 64, 112, 255),
    "t2": (96, 96, 160, 255),
    "t3": (144, 144, 208, 255),
    "t4": (208, 208, 240, 255),
    "ink": (8, 8, 8, 255),
    "body": (120, 40, 40, 255),
}
HEX = {key: "#{:02X}{:02X}{:02X}{:02X}".format(*value) for key, value in TONES.items()}
SYMBOL = {value: key[-1] for key, value in TONES.items()} | {
    CLEAR: ".",
    TONES["ink"]: "k",
    TONES["body"]: "b",
}
SEED = 99


def light(direction: str = "n", height: int = 0, intensity: int = 0, ambient: int = 1) -> Any:
    return {"direction": direction, "height": height, "intensity": intensity, "ambient": ambient}


def band(band_id: str, mask_id: str, facing: str = "none", offset: int = 0) -> dict[str, Any]:
    return {"id": band_id, "mask_id": mask_id, "facing": facing, "offset": offset}


def material(
    bands: list[dict[str, Any]],
    *,
    preset: str = "cloth",
    density: int = 64,
    scale: int = 1,
    origin: tuple[int, int] = (0, 0),
    lamp: dict[str, Any] | None = None,
    op_id: str = "mat",
    order: str = "monotonic",
) -> dict[str, Any]:
    return {
        "id": op_id,
        "type": "material",
        "preset": preset,
        "version": 1,
        "ramp": "ramp",
        "ramp_order": order,
        "light": lamp or light(),
        "density": density,
        "scale": scale,
        "origin": list(origin),
        "bands": bands,
    }


def selective(
    segments: list[dict[str, Any]],
    *,
    mask_id: str = "core",
    width: int = 1,
    side: str = "outer",
    lamp: dict[str, Any] | None = None,
    order: str = "monotonic",
) -> dict[str, Any]:
    return {
        "id": "rim",
        "type": "selective_outline",
        "mask_id": mask_id,
        "width": width,
        "side": side,
        "color": "ink",
        "ramp": "ramp",
        "ramp_order": order,
        "light": lamp or light("n", 0, 1, 1),
        "segments": segments,
    }


def tree(
    width: int,
    height: int,
    operations: list[dict[str, Any]],
    masks: list[dict[str, Any]],
    *,
    tones: int = 3,
    seed: int = SEED,
    profile: str = "strict",
) -> dict[str, Any]:
    ramp = ["t0", "t2", "t4"] if tones == 3 else ["t0", "t1", "t2", "t3", "t4"]
    return {
        "schema_version": "1.0",
        "id": "doc",
        "seed": seed,
        "canvas": {"width": width, "height": height, "profile": profile},
        "palette": {
            "id": "pal",
            "colors": [{"id": key, "rgba": value} for key, value in HEX.items()],
            "ramps": [{"id": "ramp", "colors": ramp}],
        },
        "masks": masks,
        "layers": [{"id": "volume", "name": "Volumen", "operations": operations}],
    }


def rect(mask_id: str, box: list[int]) -> dict[str, Any]:
    return {"id": mask_id, "type": "rect", "box": box}


def grid(document: Document) -> list[str]:
    result = render(document)
    return [
        "".join(SYMBOL[result.pixel(x, y)] for x in range(result.width))
        for y in range(result.height)
    ]


def oracle_choice(seed: int, op: str, x: int, y: int, channel: int, n: int) -> int:
    key = json.dumps([seed, op, x, y, channel, "cell-sha256-v1"], separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") * n // 2**64


def oracle_offset(
    name: str, density: int, scale: int, origin: tuple[int, int], x: int, y: int, op: str = "mat"
) -> int:
    cx, cy = (x - origin[0]) // scale, (y - origin[1]) // scale
    candidate = {
        "skin": True,
        "stone": True,
        "cloth": cy % 2 == 0 and (cx // 2 + cy // 2) % 2 == 0,
        "metal": (cx - cy) % 4 == 0,
        "wood": cy % 3 == 0,
    }[name]
    if not candidate or oracle_choice(SEED, op, cx, cy, 0, 64) >= density:
        return 0
    if name == "stone":
        return -1 if oracle_choice(SEED, op, cx, cy, 1, 2) == 0 else 1
    return 1 if name == "metal" else -1


WHOLE = [rect("whole", [0, 0, 8, 4])]


# --- AC1 / T1: hand-written fixtures per preset ---------------------------------------------


def test_t1_cloth_weave_moves_basket_pixels_one_step_down() -> None:
    """Ambient 1 (t2); marked cells (pairs on even rows, alternating every two rows)
    take 1 - 1 = 0 (t0)."""
    document = validate_document(tree(8, 4, [material([band("b", "whole")])], WHOLE))
    assert grid(document) == ["00220022", "22222222", "22002200", "22222222"]
    assert render(document).warnings == ()


def test_t1_metal_streak_moves_diagonal_pixels_one_step_up() -> None:
    document = validate_document(
        tree(8, 4, [material([band("b", "whole")], preset="metal")], WHOLE)
    )
    assert grid(document) == ["42224222", "24222422", "22422242", "22242224"]


def test_t1_wood_grain_with_scale_two_and_an_offset_origin() -> None:
    """Cells of 2 x 2 from (0, 1): cell rows 0 (y 1-2) and 3 (y 7) are grain; y 0 is cell
    row -1, whose floor is -1 (not a multiple of 3)."""
    masks = [rect("whole", [0, 0, 4, 8])]
    op = material([band("b", "whole")], preset="wood", scale=2, origin=(0, 1))
    assert grid(validate_document(tree(4, 8, [op], masks))) == [
        "2222",
        "0000",
        "0000",
        "2222",
        "2222",
        "2222",
        "2222",
        "0000",
    ]


def test_t1_clamp_keeps_texture_steps_inside_the_ramp() -> None:
    dark = material([band("b", "whole")], lamp=light(ambient=0))
    assert grid(validate_document(tree(8, 4, [dark], WHOLE))) == ["00000000"] * 4
    bright = material([band("b", "whole", offset=4095)], preset="metal")
    assert grid(validate_document(tree(8, 4, [bright], WHOLE))) == ["44444444"] * 4


def test_t1_one_pixel_canvas() -> None:
    """Cell (0, 0) is a weave candidate (marked: t0); from origin (1, 0) the pixel lies in
    cell (-1, 0), where ``(-1 div 2 + 0) mod 2 = 1``: not a candidate (t2)."""
    one = [rect("whole", [0, 0, 1, 1])]
    assert grid(validate_document(tree(1, 1, [material([band("b", "whole")])], one))) == ["0"]
    moved = material([band("b", "whole")], origin=(1, 0))
    assert grid(validate_document(tree(1, 1, [moved], one))) == ["2"]


def test_t1_band_entirely_off_the_canvas_paints_nothing() -> None:
    masks = [rect("off", [5, 5, 9, 9])]
    document = validate_document(tree(4, 4, [material([band("b", "off")])], masks))
    assert grid(document) == ["...."] * 4


def test_t1_zero_density_is_plain_band_shading() -> None:
    for name in MATERIAL_PRESETS:
        op = material([band("b", "whole")], preset=name[0], density=0)
        assert grid(validate_document(tree(8, 4, [op], WHOLE))) == ["22222222"] * 4


@pytest.mark.parametrize("name", ["skin", "stone"])
def test_t1_seeded_presets_match_the_independent_oracle(name: str) -> None:
    row = MATERIAL_PRESETS[(name, 1)]
    masks = [{"id": "blob", "type": "ellipse", "box": [1, 1, 15, 11]}]
    op = material(
        [band("b", "blob")],
        preset=name,
        density=row.max_density,
        scale=1,
        origin=(3, 2),
        lamp=light(ambient=1),
    )
    result = render(validate_document(tree(16, 12, [op], masks)))
    ramp = [TONES["t0"], TONES["t2"], TONES["t4"]]
    inside = {(x, y) for x in range(16) for y in range(12) if result.pixel(x, y) != CLEAR}
    assert len(inside) > 100
    for x, y in inside:
        index = min(max(1 + oracle_offset(name, row.max_density, 1, (3, 2), x, y), 0), 2)
        assert result.pixel(x, y) == ramp[index], (x, y)


band_box = st.tuples(st.integers(-2, 6), st.integers(-2, 6), st.integers(1, 6), st.integers(1, 6))


@settings(max_examples=40, deadline=None)
@given(
    name=st.sampled_from(["skin", "cloth", "metal", "wood", "stone"]),
    boxes=st.lists(band_box, min_size=1, max_size=3),
    offsets=st.lists(st.integers(-2, 2), min_size=3, max_size=3),
    scale=st.integers(1, 2),
    origin=st.tuples(st.integers(-3, 3), st.integers(-3, 3)),
)
def test_ac1_every_pixel_is_the_ramp_step_of_its_last_band_plus_its_texel(
    name: str,
    boxes: list[tuple[int, int, int, int]],
    offsets: list[int],
    scale: int,
    origin: tuple[int, int],
) -> None:
    density = MATERIAL_PRESETS[(name, 1)].max_density
    masks = [rect(f"m{i}", [x, y, x + w, y + h]) for i, (x, y, w, h) in enumerate(boxes)]
    bands = [band(f"b{i}", f"m{i}", offset=offsets[i]) for i in range(len(masks))]
    op = material(bands, preset=name, density=density, scale=scale, origin=origin)
    result = render(validate_document(tree(6, 6, [op], masks, tones=5)))
    ramp = [TONES[f"t{i}"] for i in range(5)]
    for x in range(6):
        for y in range(6):
            owners = [
                i for i, (bx, by, w, h) in enumerate(boxes) if bx <= x < bx + w and by <= y < by + h
            ]
            if not owners:
                assert result.pixel(x, y) == CLEAR
                continue
            step = min(max(1 + offsets[owners[-1]], 0), 4)  # ambient 1, no exposure
            step += oracle_offset(name, density, scale, origin, x, y)
            assert result.pixel(x, y) == ramp[min(max(step, 0), 4)], (x, y)


def test_ac1_the_light_and_facings_follow_the_shade_rule() -> None:
    """``nw`` light, height 0, intensity 1, ambient 1: ``nw`` band 2, ``se`` band 0; cloth
    weave moves marked pixels of each band one step down (clamped at 0)."""
    masks = [rect("left", [0, 0, 4, 2]), rect("right", [4, 0, 8, 2])]
    bands = [band("lit", "left", "nw"), band("dark", "right", "se")]
    op = material(bands, lamp=light("nw", 0, 1, 1))
    assert grid(validate_document(tree(8, 2, [op], masks))) == ["22440000", "44440000"]


# --- AC2 / T2: same seed, same texture; nothing else changes it -------------------------


def _stone(op_id: str = "mat", seed: int = SEED, extra: list[dict[str, Any]] | None = None) -> Any:
    masks = [rect("whole", [0, 0, 12, 12]), rect("side", [0, 12, 12, 16])]
    op = material([band("b", "whole")], preset="stone", density=32, scale=1, op_id=op_id)
    operations = [*(extra or []), op]
    return validate_document(tree(12, 16, operations, masks, seed=seed))


def _region(document: Document) -> list[RGBA]:
    result = render(document)
    return [result.pixel(x, y) for y in range(12) for x in range(12)]


def test_ac2_same_seed_same_texture_and_another_operation_changes_nothing() -> None:
    base = _region(_stone())
    assert _region(_stone()) == base
    dither = {
        "id": "dots",
        "type": "dither",
        "size": 2,
        "coverage": 2,
        "origin": [0, 0],
        "color_a": "ink",
        "color_b": "body",
        "mask_id": "side",
    }
    other = material([band("b2", "side")], preset="stone", density=32, op_id="pebble")
    assert _region(_stone(extra=[dither, other])) == base
    assert _region(_stone(seed=SEED + 1)) != base
    assert _region(_stone(op_id="rock")) != base


@pytest.mark.parametrize(("dx", "dy"), [(1, 0), (3, 2), (-2, 5)])
def test_t2_a_frame_that_moves_mask_and_origin_together_moves_every_pixel(dx: int, dy: int) -> None:
    def frame(shift: tuple[int, int]) -> Document:
        x, y = 4 + shift[0], 4 + shift[1]
        masks = [{"id": "blob", "type": "ellipse", "box": [x, y, x + 10, y + 8]}]
        op = material([band("b", "blob")], preset="stone", density=24, origin=(x, y))
        return validate_document(tree(24, 24, [op], masks))

    first, moved = render(frame((0, 0))), render(frame((dx, dy)))
    for y in range(24):
        for x in range(24):
            if 0 <= x + dx < 24 and 0 <= y + dy < 24:
                assert first.pixel(x, y) == moved.pixel(x + dx, y + dy)
    assert render(frame((0, 0))).rgba == first.rgba  # repeated frames never flicker


def test_ramp_warnings_follow_ramp_order() -> None:
    source = tree(8, 4, [material([band("b", "whole")])], WHOLE)
    source["palette"]["ramps"][0]["colors"] = ["t4", "t0", "t2"]
    warned = render(validate_document(source)).warnings
    assert [w.code for w in warned] == [RAMP_LUMINANCE_NOT_INCREASING]
    assert warned[0].json_pointer == "/layers/0/operations/0/ramp"
    source["layers"][0]["operations"][0]["ramp_order"] = "stylized"
    assert render(validate_document(source)).warnings == ()


# --- selective outline -----------------------------------------------------------------


def _outlined(segments: list[dict[str, Any]], masks: list[dict[str, Any]], **kw: Any) -> Document:
    body = {"id": "fill", "type": "rect", "box": [2, 2, 6, 6], "color": "body"}
    return validate_document(
        tree(8, 8, [body, selective(segments, **kw)], [rect("core", [2, 2, 6, 6]), *masks])
    )


def test_selective_outline_lights_the_segment_facing_the_light() -> None:
    """``n`` light, height 0, intensity 1, ambient 1: a segment facing ``n`` takes
    1 + round(6 / 6) = 2 (t4); ring pixels outside every segment take ``ink``."""
    document = _outlined([band("top", "upper", "n")], [rect("upper", [0, 0, 8, 3])])
    assert grid(document) == [
        "........",
        ".444444.",
        ".4bbbb4.",
        ".kbbbbk.",
        ".kbbbbk.",
        ".kbbbbk.",
        ".kkkkkk.",
        "........",
    ]


def test_selective_outline_last_segment_wins_and_turning_the_light_swaps_tones() -> None:
    masks = [rect("upper", [0, 0, 8, 3]), rect("right", [5, 0, 8, 8])]
    segments = [band("top", "upper", "n"), band("east", "right", "s")]
    assert grid(_outlined(segments, masks)) == [
        "........",
        ".444400.",
        ".4bbbb0.",
        ".kbbbb0.",
        ".kbbbb0.",
        ".kbbbb0.",
        ".kkkk00.",
        "........",
    ]
    turned = _outlined(segments, masks, lamp=light("s", 0, 1, 1))
    assert grid(turned)[1] == ".000044." and grid(turned)[6] == ".kkkk44."


def test_selective_outline_segment_hidden_by_a_later_segment_paints_nothing() -> None:
    """``top`` is fully covered by the later ``all`` segment, so its visible part is
    empty (the shade rule: the last segment wins) and only ``all`` paints the ring:
    facing ``s`` against an ``n`` light takes t0 everywhere; no ``ink`` remains."""
    masks = [rect("upper", [0, 0, 8, 3]), rect("whole", [0, 0, 8, 8])]
    segments = [band("top", "upper", "n"), band("all", "whole", "s")]
    assert grid(_outlined(segments, masks)) == [
        "........",
        ".000000.",
        ".0bbbb0.",
        ".0bbbb0.",
        ".0bbbb0.",
        ".0bbbb0.",
        ".000000.",
        "........",
    ]


def test_selective_outline_inner_side_and_segments_off_the_ring() -> None:
    masks = [rect("upper", [0, 0, 8, 3]), rect("far", [20, 20, 24, 24])]
    segments = [band("top", "upper", "n"), band("lost", "far", "s")]
    document = _outlined(segments, masks, side="inner")
    assert grid(document) == [
        "........",
        "........",
        "..4444..",
        "..kbbk..",
        "..kbbk..",
        "..kkkk..",
        "........",
        "........",
    ]


def test_selective_outline_of_an_empty_mask_warns_and_paints_nothing() -> None:
    masks = [rect("upper", [0, 0, 8, 3]), rect("gone", [30, 30, 32, 32])]
    document = _outlined([band("top", "upper", "n")], masks, mask_id="gone")
    result = render(document)
    assert [w.code for w in result.warnings] == ["empty_bounds"]
    assert grid(document)[1] == "........"


def test_selective_outline_colours_are_the_colour_and_ramp_colours() -> None:
    masks = [{"id": "upper", "type": "polygon", "points": [[0, 0], [8, 0], [0, 8]]}]
    result = render(_outlined([band("top", "upper", "nw")], masks, lamp=light("nw", 1, 2, 1)))
    seen = {result.pixel(x, y) for x in range(8) for y in range(8)}
    assert seen <= {CLEAR, TONES["body"], TONES["ink"], TONES["t0"], TONES["t2"], TONES["t4"]}


# --- budget-v8 -----------------------------------------------------------------------------


def test_budget_v8_material_hand_oracle() -> None:
    """8 x 4 canvas (A = 32); cloth (2 parts, 1 channel) at scale 2 over ``left``
    [0, 0, 5, 4] (20 px; leaf 21 visits, 20 bytes). Cells: x 0..2, y 0..1 = 6.

    Band: 21 + 4 x 20 = 101 visits, 20 + 20 + 8192 = 8232 bytes. Texture:
    6 x (64 + 2) + 3 x 20 = 456 visits; 2 x 20 + 5 x 6 + 2 x 5 + 8 x 9 + 16384 = 16536
    bytes. Two parts: 2 x (101 + 456) = 1114 visits; peak 16536.
    """
    masks = [rect("left", [0, 0, 5, 4])]
    op = material([band("b", "left")], scale=2)
    document = validate_document(tree(8, 4, [op], masks))
    estimate = plan_budget(document)
    assert (MATERIAL_HASH_VISITS, MATERIAL_PASSES, MATERIAL_CELL_BYTES) == (64, 3, 5)
    assert MATERIAL_FIXED_BYTES == 16384
    assert estimate.operation_costs[0].pixel_visits == 1114
    assert estimate.operation_costs[0].mask_bytes == 16536
    assert estimate.pixel_visits == 5 * 32 + 1114
    assert estimate.buffer_bytes == 1280 + 16536 + 128
    assert estimate.estimator_version == ESTIMATOR_VERSION == "budget-v8"
    assert estimate.fills == fill_count(document) == 2


def test_budget_v8_selective_outline_hand_oracle() -> None:
    """8 x 8 canvas (A = 64); ``core`` [2, 2, 6, 6] (17 visits, 16 bytes), outer width 1:
    X = [1, 1, 7, 7] (36 px), P = 9 x 9 = 81. Ring: 17 + 16 x 81 = 1313 visits;
    16 + 16 + (72 + 324 + 144 + 972 + 4096) + 72 = 5712 bytes. Segment ``upper``
    [0, 0, 8, 3] (25 visits, 24 bytes) meets X.

    Base: 1313 + 4 x 36 + (25 + 36) = 1518 visits; max(5712, 72, 36 + 24 + 24576) +
    8192 = 32828 bytes. Segment over [1, 1, 7, 3] (12 px): 25 + 4 x 24 = 121 band
    visits, + 1313 + 3 x 12 + 24 + 36 = 1530 visits; held 24 + 36 + 12 + 24576 + 8192 =
    32840 bytes.
    """
    document = _outlined([band("top", "upper", "n")], [rect("upper", [0, 0, 8, 3])])
    estimate = plan_budget(document)
    cost = estimate.operation_costs[1]
    assert (cost.pixel_visits, cost.mask_bytes) == (1518 + 1530, 32840)
    assert estimate.fills == fill_count(document) == 3  # the body rect, base and segment


def test_documents_without_materials_cost_as_in_budget_v7() -> None:
    """``budget-v8`` adds terms only for the new types: a ``shade`` costs as before."""
    masks = [rect("left", [0, 0, 5, 4]), rect("right", [3, 0, 8, 4])]
    shade = {
        "id": "shading",
        "type": "shade",
        "ramp": "ramp",
        "ramp_order": "monotonic",
        "light": light("nw", 0, 1, 1),
        "bands": [band("lit", "left", "nw"), band("dark", "right", "se")],
    }
    estimate = plan_budget(validate_document(tree(8, 4, [shade], masks)))
    assert estimate.operation_costs[0].pixel_visits == 243  # the budget-v7 oracle
    assert estimate.operation_costs[0].mask_bytes == 32808


def test_empty_bands_and_unvalidated_documents() -> None:
    masks = [rect("left", [0, 0, 5, 4]), rect("far", [20, 20, 24, 24])]
    op = material([band("lost", "far"), band("b", "left")])
    estimate = estimate_cost(validate_document(tree(8, 4, [op], masks)))
    assert estimate.fills == 4
    estimates = mask_estimates(validate_document(tree(8, 4, [op], masks)))
    recipe = MATERIAL_PRESETS[("cloth", 1)]
    alone = material_cost([estimates["left"]], recipe, 1, (0, 0))
    assert material_cost([estimates["far"], estimates["left"]], recipe, 1, (0, 0)) == alone
    ghost = tree(4, 4, [material([band("b", "ghost")])], [])
    with pytest.raises(errors.ReferenceError) as raised:
        estimate_cost(Document.model_validate(ghost))
    assert raised.value.context["reason"] == "unknown_mask"
    ghost = tree(
        4, 4, [selective([band("s", "ghost")], mask_id="core")], [rect("core", [0, 0, 2, 2])]
    )
    with pytest.raises(errors.ReferenceError):
        estimate_cost(Document.model_validate(ghost))
    unknown = validate_document(
        tree(4, 4, [material([band("b", "core")])], [rect("core", [0, 0, 2, 2])])
    )
    operation = unknown.layers[0].operations[0]
    object.__setattr__(operation, "version", 9)  # bypass the frozen model: no recipe 9
    with pytest.raises(errors.ReferenceError) as raised:
        estimate_cost(unknown)
    assert raised.value.context["reason"] == "unknown_preset_version"


def test_inspect_summarises_both_operations() -> None:
    document = _outlined([band("top", "upper", "n")], [rect("upper", [0, 0, 8, 3])])
    summary = inspect_document(document).layers[0].operations[1]
    assert (summary.type, summary.color) == ("selective_outline", "ink")
    textured = validate_document(tree(8, 4, [material([band("b", "whole")])], WHOLE))
    summary = inspect_document(textured).layers[0].operations[0]
    assert (summary.type, summary.color) == ("material", None)


# --- peak memory (tracemalloc) ------------------------------------------------------------


def _measure(build: Any) -> int:
    build()  # warm-up: the coverage tracer allocates on first run
    tracemalloc.start()
    try:
        build()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return int(peak)


SLOW = pytest.mark.slow


@pytest.mark.parametrize(
    ("width", "height", "name", "scale", "later"),
    [
        (16, 16, "stone", 1, 0),
        (128, 128, "cloth", 1, 0),
        (128, 128, "stone", 1, 2),  # the only case that folds later bands
        (512, 64, "metal", 1, 0),
        pytest.param(256, 256, "stone", 2, 0, marks=SLOW),
        pytest.param(2048, 64, "wood", 4, 0, marks=SLOW),
        pytest.param(64, 2048, "stone", 4, 0, marks=SLOW),
        pytest.param(2048, 1, "skin", 1, 0, marks=SLOW),
        pytest.param(1, 2048, "cloth", 1, 0, marks=SLOW),
    ],
)
def test_material_part_fill_peak_stays_within_its_cost(
    width: int, height: int, name: str, scale: int, later: int
) -> None:
    """Band 0 covers the canvas (an ellipse); ``later`` smaller rect bands fold into it.

    Hashing is slow in Python, so the long boxes keep the cell count small while the
    box-wide rows of the selection reach the 2048-pixel axis.
    """
    masks: list[dict[str, Any]] = [{"id": "m0", "type": "ellipse", "box": [0, 0, width, height]}]
    masks += [
        rect(f"m{i}", [0, 0, max(1, width // 2 + i), max(1, height // 3 + i)])
        for i in range(1, later + 1)
    ]
    ids = [m["id"] for m in masks]
    row = MATERIAL_PRESETS[(name, 1)]
    op = material(
        [band(f"b{i}", m) for i, m in enumerate(ids)],
        preset=name,
        density=row.max_density // 2,
        scale=scale,
        origin=(3, -5),
    )
    document = validate_document(tree(width, height, [op], masks, profile="rgba"))
    dims = Dimensions(width, height)
    nodes = _plan_masks(document, dims)
    estimates = mask_estimates(document)
    _, bound = material_cost([estimates[m] for m in ids], row, scale, (3, -5))
    boxes = [estimates[m].box for m in ids]
    fill = tuple(nodes[ids[j]] for j in (0, *shade_later(boxes, 0)))
    texture = MaterialTexture(name, 1, row.max_density // 2, scale, Point(3, -5), SEED, "mat")  # type: ignore[arg-type]
    for part in row.parts:
        peak = _measure(lambda part=part: _material_part(fill, texture, part, dims, None))
        assert peak <= bound, (part, peak, bound)


@pytest.mark.parametrize("size", [16, 128, 512, pytest.param(2048, marks=SLOW)])
@pytest.mark.parametrize("segments", [1, 3])
def test_selective_outline_fill_peaks_stay_within_its_cost(size: int, segments: int) -> None:
    masks: list[dict[str, Any]] = [
        {"id": "core", "type": "ellipse", "box": [2, 2, size - 2, size - 2]}
    ]
    masks += [rect(f"s{i}", [0, i, size - i, size // 2 + i]) for i in range(segments)]
    ids = [f"s{i}" for i in range(segments)]
    op = selective([band(f"g{i}", m, "n") for i, m in enumerate(ids)], width=2)
    document = validate_document(tree(size, size, [op], masks, profile="rgba"))
    operation = document.layers[0].operations[0]
    assert isinstance(operation, SelectiveOutlineOperation)
    dims = Dimensions(size, size)
    nodes = _plan_masks(document, dims)
    estimates = mask_estimates(document)
    segment_estimates = [estimates[m] for m in ids]
    _, bound = selective_outline_cost(estimates["core"], 2, "outer", segment_estimates, dims)
    work = outline_box(estimates["core"].box, 2, "outer", dims)
    assert work is not None
    segment_nodes = tuple(nodes[m] for m in ids)
    peak = _measure(lambda: _outline_base(operation, nodes["core"], segment_nodes, dims, None))
    assert peak <= bound, ("base", peak, bound)
    boxes = [estimates[m].box for m in ids]
    for index in range(segments):
        fold = tuple(nodes[ids[j]] for j in (index, *shade_later(boxes, index)))
        peak = _measure(
            lambda fold=fold: _outline_segment(operation, nodes["core"], fold, dims, None)
        )
        assert peak <= bound, (index, peak, bound)


def test_peak_memory_of_a_whole_render_stays_within_the_estimate() -> None:
    size = 160
    masks: list[dict[str, Any]] = [
        {"id": "big", "type": "ellipse", "box": [10, 10, 150, 150]},
        {"id": "shadow", "type": "rect", "box": [80, 10, 150, 150]},
        rect("upper", [0, 0, size, 60]),
    ]
    op = material([band("b0", "big"), band("b1", "shadow", "se")], preset="stone", density=20)
    outline = selective([band("g", "upper", "n")], mask_id="big")
    document = validate_document(tree(size, size, [op, outline], masks, tones=5))
    estimate = plan_budget(document)
    render(document)
    tracemalloc.start()
    try:
        render(document)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= estimate.buffer_bytes


box_strategy = st.tuples(
    st.integers(-3, 6), st.integers(-3, 6), st.integers(1, 6), st.integers(1, 6)
)


@settings(max_examples=40, deadline=None)
@given(
    width=st.integers(1, 8),
    height=st.integers(1, 8),
    boxes=st.lists(box_strategy, min_size=1, max_size=3),
    name=st.sampled_from(["skin", "cloth", "metal", "wood", "stone"]),
    layer_mask=st.booleans(),
)
def test_plan_budget_admission_means_render_succeeds(
    width: int,
    height: int,
    boxes: list[tuple[int, int, int, int]],
    name: str,
    layer_mask: bool,
) -> None:
    """With limits exactly at the plan, the compositor's own check never rejects."""
    masks = [rect(f"s{i}", [x, y, x + w, y + h]) for i, (x, y, w, h) in enumerate(boxes)]
    bands = [band(f"b{i}", m["id"]) for i, m in enumerate(masks)]
    ops = [
        material(bands, preset=name, density=MATERIAL_PRESETS[(name, 1)].max_density),
        selective([band(f"g{i}", m["id"], "n") for i, m in enumerate(masks)], mask_id="s0"),
    ]
    source = tree(width, height, ops, masks)
    if layer_mask:
        source["layers"][0]["mask_id"] = "s0"
    document = validate_document(source)
    estimate = plan_budget(document)
    exact = RenderLimits(
        max_pixel_visits=estimate.pixel_visits,
        max_buffer_bytes=estimate.buffer_bytes,
        max_frame_pixels=estimate.frame_pixels,
        max_operations=fill_count(document),
        max_layers=1,
    )
    assert render(document, limits=exact).width == width


# --- examples ---------------------------------------------------------------------------------

EXAMPLES = ["skin", "cloth", "metal", "wood", "stone"]


@pytest.mark.parametrize("name", EXAMPLES)
def test_material_examples_use_only_their_palette_and_record_provenance(name: str) -> None:
    path = ROOT / "examples" / "specs" / f"material-{name}.moana.json"
    document = validate_document(json.loads(path.read_text(encoding="utf-8")))
    operation = document.layers[0].operations[0]
    assert isinstance(operation, MaterialOperation) and operation.preset == name
    assert document.metadata is not None and document.metadata.provenance is not None
    assert "sin assets" in document.metadata.provenance
    assert "PENDIENTE" in document.metadata.provenance
    result = render(document)
    assert result.warnings == ()
    palette = {
        color.id: tuple(int(color.rgba[i : i + 2], 16) for i in (1, 3, 5, 7))
        for color in document.palette.colors
    }
    seen = {result.pixel(x, y) for x in range(32) for y in range(32)}
    assert seen <= set(palette.values()) | {CLEAR}
    assert len(seen & {palette[f"{name}_{i}"] for i in range(5)}) >= 3
    # the selective outline: the upper-left segment takes ramp step 3 - 2 = 1, the rest ink
    assert palette[f"{name}_1"] in seen and palette["ink"] in seen
    assert render(document).rgba == result.rgba
    # the flat shade over the shadow side keeps the darkest step off the ink (art review)
    darkest, ink = palette[f"{name}_0"], palette["ink"]
    for y in range(32):
        for x in range(32):
            if result.pixel(x, y) != darkest:
                continue
            near = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
            assert all(result.pixel(u, v) != ink for u, v in near if 0 <= u < 32 and 0 <= v < 32)


# SHA-256 of the RGBA of every example (seed 17): a released v1 row must never change
# them. If one breaks, a recipe changed: add a new version instead (ADR-030).
EXAMPLE_DIGESTS = {
    "skin": "735ab667228503142278c5acd653f32f895569543736ae41438bbe0d52864533",
    "cloth": "6e485c02fa2ae9ad31012bd4c3f73aee57bd9bf7bc04dda25b580166f37031b8",
    "metal": "63ee83217252b8c8a0e17ac45ec78f4b84343d0083021460bed04a05b988f916",
    "wood": "5b747c14480952ab739a076acdbe1a3498c5889f8b80ef6c1d1aa56342d00e09",
    "stone": "4dab10cbfeda70d0ab80b335c2122dd3924ba0bce10273f80e59d705797ad39a",
}


@pytest.mark.parametrize("name", EXAMPLES)
def test_t2_recipe_golden_of_every_example(name: str) -> None:
    path = ROOT / "examples" / "specs" / f"material-{name}.moana.json"
    document = validate_document(json.loads(path.read_text(encoding="utf-8")))
    assert hashlib.sha256(render(document).rgba).hexdigest() == EXAMPLE_DIGESTS[name]


# texture_cells of a fixed span per v1 row (seed 17, key "golden", density = row max,
# scale 1): the bytes are ``offset + 1``. Independent of the examples' masks and light.
TEXTURE_DIGESTS = {
    "skin": "e26ad5aeca704bef0a49f1589e68e94ba996485b6a5c66d6c0a48645cf064625",
    "cloth": "558dbd8ffcad569b30add877753b710834d98969c9019395c4087ba457ef01b0",
    "metal": "190163b369e38491a328854c6964d925e5cd8762a4044c36ce2e2c791af919e1",
    "wood": "d558f606c094a82fde3b325e9e889d8ed6d39c9933e3eb1a5ebee189d62e7048",
    "stone": "bb862a9999f4f4147b96937193e86b81a813039881dd1f2168df1e82d03d8e20",
}


@pytest.mark.parametrize("name", EXAMPLES)
def test_t2_recipe_golden_of_every_preset_row(name: str) -> None:
    row = MATERIAL_PRESETS[(name, 1)]
    texture = MaterialTexture(name, 1, row.max_density, 1, Point(0, 0), 17, "golden")  # type: ignore[arg-type]
    cells = texture_cells(texture, Box(-8, -8, 24, 24))
    assert hashlib.sha256(cells).hexdigest() == TEXTURE_DIGESTS[name]
