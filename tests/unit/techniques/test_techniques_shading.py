"""AC1/T1/T2 (MOANA-015): discrete light, authored facings, ramp indexes and band priority.

Oracles are written by hand from the table of ADR-028 (exposure of each facing,
``round_half_away(intensity * exposure / 6)``, clamp to the ramp) or computed with
Python sets (``band_i - union(later bands)``). Masks are built from raw bits, never
from the operators under test.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moanart.core.coordinates import Box
from moanart.core.errors import ValidationError
from moanart.geometry import Mask
from moanart.geometry.mask import _restore
from moanart.techniques import (
    COSINE,
    EXPOSURE_SCALE,
    FACINGS,
    LIGHT_DIRECTIONS,
    MAX_RAMP_STEP,
    MAX_SHADE_BANDS,
    Facing,
    ShadeLight,
    band_index,
    band_level,
    exposure,
    last_wins,
    ramp_index,
    resolve_bands,
)

PLANAR: tuple[Facing, ...] = ("n", "ne", "e", "se", "s", "sw", "w", "nw")


def mask_of(pixels: Iterable[tuple[int, int]]) -> Mask:
    """A mask holding exactly ``pixels`` over their bounding box, built from raw bits."""
    points = sorted(pixels)
    if not points:
        return Mask.empty()
    x0, y0 = min(x for x, _ in points), min(y for _, y in points)
    x1, y1 = max(x for x, _ in points) + 1, max(y for _, y in points) + 1
    bits = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    for x, y in points:
        bits[y - y0, x - x0] = 1
    return _restore(Box(x0, y0, x1, y1), (y1 - y0, x1 - x0), bits.tobytes())


def pixels_of(mask: Mask) -> frozenset[tuple[int, int]]:
    return frozenset((point.x, point.y) for point in mask.points())


def square(x0: int, y0: int, x1: int, y1: int) -> set[tuple[int, int]]:
    return {(x, y) for x in range(x0, x1) for y in range(y0, y1)}


def rotate(direction: str, turns: int) -> str:
    if direction not in PLANAR:
        return direction
    return PLANAR[(PLANAR.index(direction) + turns) % 8]


# --- exposure table (hand-written) ---------------------------------------------------------


def test_constants_match_the_contract() -> None:
    assert (*PLANAR, "front") == LIGHT_DIRECTIONS
    assert (*PLANAR, "front", "none") == FACINGS
    assert COSINE == (2, 1, 0, -1, -2)
    assert EXPOSURE_SCALE == 6
    assert MAX_RAMP_STEP == 4095
    assert MAX_SHADE_BANDS == 64


def test_exposure_of_a_low_north_west_light() -> None:
    """Light ``nw`` at height 1: in-plane weight ``3 - 1 = 2``, front ``2 * 1``."""
    light = ShadeLight("nw", 1, 1, 0)
    expected = {
        "nw": 4,
        "n": 2,
        "w": 2,
        "ne": 0,
        "sw": 0,
        "e": -2,
        "s": -2,
        "se": -4,
        "front": 2,
        "none": 0,
    }
    assert {facing: exposure(facing, light) for facing in FACINGS} == expected


@pytest.mark.parametrize(
    ("light", "planar", "front"),
    [
        (ShadeLight("front", 0, 1, 0), 0, 6),  # height is unused by a front light
        (ShadeLight("front", 3, 1, 0), 0, 6),
        (ShadeLight("e", 3, 1, 0), 0, 6),  # a light facing the viewer flattens the sides
        (ShadeLight("e", 0, 1, 0), None, 0),  # a grazing light leaves the front unexposed
    ],
)
def test_exposure_of_front_and_extreme_heights(
    light: ShadeLight, planar: int | None, front: int
) -> None:
    assert exposure("front", light) == front
    assert exposure("none", light) == 0
    if planar is not None:
        assert {exposure(facing, light) for facing in PLANAR} == {planar}
    else:
        sweep: tuple[Facing, ...] = ("e", "ne", "n", "nw", "w")
        assert [exposure(facing, light) for facing in sweep] == [
            6,
            3,
            0,
            -3,
            -6,
        ]


# --- T1: orientation changes ---------------------------------------------------------------


def test_t1_turning_the_light_swaps_the_lit_and_the_shadowed_band() -> None:
    nw = ShadeLight("nw", 0, 2, 2)
    se = ShadeLight("se", 0, 2, 2)
    # nw light: nw band 2 + 2 = 4, se band 2 - 2 = 0; reversed for an se light.
    assert (band_index("nw", 0, nw, 5), band_index("se", 0, nw, 5)) == (4, 0)
    assert (band_index("nw", 0, se, 5), band_index("se", 0, se, 5)) == (0, 4)
    # a quarter turn (ne light) leaves both bands perpendicular: ambient
    ne = ShadeLight("ne", 0, 2, 2)
    assert (band_index("nw", 0, ne, 5), band_index("se", 0, ne, 5)) == (2, 2)


@settings(max_examples=200, deadline=None)
@given(
    direction=st.sampled_from(LIGHT_DIRECTIONS),
    facing=st.sampled_from(FACINGS),
    height=st.integers(0, 3),
    intensity=st.integers(0, 40),
    turns=st.integers(0, 7),
)
def test_t1_rotating_light_and_facings_together_changes_nothing(
    direction: str, facing: str, height: int, intensity: int, turns: int
) -> None:
    light = ShadeLight(direction, height, intensity, 0)  # type: ignore[arg-type]  # sampled literal
    turned = ShadeLight(rotate(direction, turns), height, intensity, 0)  # type: ignore[arg-type]  # sampled literal
    assert exposure(rotate(facing, turns), turned) == exposure(facing, light)  # type: ignore[arg-type]  # sampled literal
    assert band_level(rotate(facing, turns), turned) == band_level(facing, light)  # type: ignore[arg-type]  # sampled literal


@settings(max_examples=100, deadline=None)
@given(
    direction=st.sampled_from(PLANAR),
    facing=st.sampled_from(PLANAR),
    height=st.integers(0, 3),
    intensity=st.integers(0, MAX_RAMP_STEP),
)
def test_t1_opposite_facings_get_opposite_levels_within_intensity(
    direction: str, facing: str, height: int, intensity: int
) -> None:
    light = ShadeLight(direction, height, intensity, 0)  # type: ignore[arg-type]  # sampled literal
    level = band_level(facing, light)  # type: ignore[arg-type]  # sampled literal
    assert band_level(rotate(facing, 4), light) == -level  # type: ignore[arg-type]  # sampled literal
    assert -intensity <= level <= intensity


@pytest.mark.parametrize(
    ("intensity", "score", "level"),
    [(3, 1, 1), (3, -1, -1), (1, 2, 0), (2, 2, 1), (1, 3, 1), (2, 3, 1), (4, 3, 2), (5, 3, 3)],
)
def test_levels_round_half_away_from_zero(intensity: int, score: int, level: int) -> None:
    """``h = 2`` gives exposure ``COSINE[d]``: 2, 1, 0, -1, -2; ``h = 0`` gives ``3 * C``."""
    height = 2 if abs(score) <= 2 else 0
    facing = {1: "ne", -1: "nw", 2: "e", 3: "ne"}[score]
    light = ShadeLight("e", height, intensity, 0)
    assert exposure(facing, light) == score  # type: ignore[arg-type]  # table key
    # intensity * score / 6, halves away from zero: 3/6 -> 1, 2/6 -> 0, 4/6 -> 1, 9/6 -> 2
    assert band_level(facing, light) == level  # type: ignore[arg-type]  # table key


# --- T1: clamp ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("step", "length", "index"),
    [
        (-5, 3, 0),
        (0, 3, 0),
        (2, 3, 2),
        (9, 3, 2),
        (4095, 5, 4),
        # a one-colour ramp: every step is its only colour
        (-4095, 1, 0),
        (0, 1, 0),
        (4095, 1, 0),
    ],
)
def test_t1_steps_are_clamped_to_the_ramp(step: int, length: int, index: int) -> None:
    assert ramp_index(step, length) == index


def test_t1_offsets_beyond_the_ramp_are_clamped() -> None:
    light = ShadeLight("e", 1, 2, 2)
    assert band_index("w", -3, light, 5) == 0  # 2 - 1 - 3 = -2
    assert band_index("e", 3, light, 5) == 4  # 2 + 1 + 3 = 6
    assert band_index("none", -MAX_RAMP_STEP, light, 3) == 0
    strongest = ShadeLight("e", 1, MAX_RAMP_STEP, MAX_RAMP_STEP)
    assert band_index("none", MAX_RAMP_STEP, strongest, 3) == 2


# --- T2: hand fixtures with 3- and 5-tone ramps -------------------------------------------


def test_t2_five_tone_ramp_under_an_east_light() -> None:
    """``e`` light at height 1, intensity 2, ambient 2 (exposures 4, 2, 0, -2, -4; front 2)."""
    light = ShadeLight("e", 1, 2, 2)
    expected = {
        "e": 3,  # 2 + round(8/6)
        "ne": 3,  # 2 + round(4/6)
        "se": 3,
        "n": 2,
        "s": 2,
        "nw": 1,  # 2 - round(4/6)
        "sw": 1,
        "w": 1,  # 2 - round(8/6)
        "front": 3,
        "none": 2,
    }
    assert {facing: band_index(facing, 0, light, 5) for facing in FACINGS} == expected
    strong = ShadeLight("e", 1, 3, 2)
    sweep: tuple[Facing, ...] = ("e", "ne", "n", "nw", "w")
    assert [band_index(f, 0, strong, 5) for f in sweep] == [4, 3, 2, 1, 0]


def test_t2_three_tone_ramp_under_a_front_light() -> None:
    light = ShadeLight("front", 0, 1, 0)
    assert band_index("front", 0, light, 3) == 1
    assert {band_index(f, 0, light, 3) for f in PLANAR} == {0}
    assert band_index("front", 1, light, 3) == 2
    assert band_index("front", 2, light, 3) == 2  # clamped


# --- AC1: overlaps take the last band ------------------------------------------------------


def test_ac1_overlap_goes_to_the_last_listed_band() -> None:
    first, second = square(0, 0, 5, 4), square(3, 0, 8, 4)
    parts = resolve_bands([mask_of(first), mask_of(second)])
    assert [pixels_of(part) for part in parts] == [first - second, second]
    swapped = resolve_bands([mask_of(second), mask_of(first)])
    assert [pixels_of(part) for part in swapped] == [second - first, first]


def test_t1_empty_bands_and_fully_covered_bands() -> None:
    covered = square(1, 1, 3, 3)
    parts = resolve_bands([Mask.empty(), mask_of(covered), mask_of(square(0, 0, 4, 4))])
    assert parts[0].is_empty and parts[1].is_empty
    assert pixels_of(parts[2]) == square(0, 0, 4, 4)
    assert resolve_bands([]) == ()


def test_last_wins_never_reads_later_masks_of_an_empty_band() -> None:
    def later() -> Iterator[Mask]:
        yield Mask.empty()
        raise AssertionError("a later mask was evaluated")

    assert last_wins(later()).is_empty


def test_last_wins_releases_each_later_mask() -> None:
    first = mask_of(square(0, 0, 6, 1))
    result = last_wins(iter([first, mask_of({(1, 0)}), Mask.empty(), mask_of({(4, 0), (9, 9)})]))
    assert pixels_of(result) == {(0, 0), (2, 0), (3, 0), (5, 0)}


pixel_sets = st.frozensets(st.tuples(st.integers(0, 7), st.integers(0, 7)), max_size=24)


@settings(max_examples=100, deadline=None)
@given(bands=st.lists(pixel_sets, max_size=6))
def test_ac1_visible_parts_are_disjoint_and_cover_the_union(
    bands: list[frozenset[tuple[int, int]]],
) -> None:
    parts = [pixels_of(part) for part in resolve_bands([mask_of(band) for band in bands])]
    for index, band in enumerate(bands):
        later = set().union(*bands[index + 1 :])
        assert parts[index] == band - later  # set oracle of "the last listed band wins"
    covered: set[tuple[int, int]] = set()
    for part in parts:
        assert not covered & part
        covered |= part
    assert covered == set().union(*bands)


# --- negative cases -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "field", "reason"),
    [
        (("up", 0, 0, 0), "direction", "unknown_direction"),
        (("N", 0, 0, 0), "direction", "unknown_direction"),
        (("n", 4, 0, 0), "height", "out_of_range"),
        (("n", True, 0, 0), "height", "not_integer"),
        (("n", 0, -1, 0), "intensity", "out_of_range"),
        (("n", 0, 4096, 0), "intensity", "out_of_range"),
        (("n", 0, 0, 1.0), "ambient", "not_integer"),
        (("n", 0, 0, -1), "ambient", "out_of_range"),
    ],
)
def test_invalid_lights_are_validation_errors(
    fields: tuple[object, ...], field: str, reason: str
) -> None:
    with pytest.raises(ValidationError) as raised:
        ShadeLight(*fields)  # type: ignore[arg-type]  # invalid on purpose
    assert (raised.value.context["field"], raised.value.context["reason"]) == (field, reason)


def test_invalid_facings_offsets_and_lengths() -> None:
    light = ShadeLight("n", 0, 1, 0)
    with pytest.raises(ValidationError) as facing:
        exposure("up", light)  # type: ignore[arg-type]  # invalid on purpose
    assert facing.value.context == {"field": "facing", "reason": "unknown_facing"}
    with pytest.raises(ValidationError) as offset:
        band_index("n", MAX_RAMP_STEP + 1, light, 3)
    assert offset.value.context["field"] == "offset"
    for length in (0, 4097, True):
        with pytest.raises(ValidationError) as size:
            ramp_index(0, length)
        assert size.value.context["field"] == "length"
    with pytest.raises(ValidationError) as step:
        ramp_index(1.5, 3)  # type: ignore[arg-type]  # invalid on purpose
    assert step.value.context == {"field": "step", "reason": "not_integer", "value_type": "float"}


def test_type_errors() -> None:
    with pytest.raises(TypeError):
        exposure("n", "light")  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError):
        last_wins([])
    with pytest.raises(TypeError):
        last_wins([mask_of({(0, 0)}), "mask"])  # type: ignore[list-item]  # invalid on purpose
    with pytest.raises(TypeError):
        resolve_bands("masks")  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(ValidationError) as many:
        resolve_bands([Mask.empty()] * (MAX_SHADE_BANDS + 1))
    assert many.value.context["field"] == "bands"
