"""Flood fill: exact colour, 4-connectivity, containment and budget (MOANA-006 T2/AC2)."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moanart.core.budget import RenderLimits
from moanart.core.canvas import Canvas
from moanart.core.coordinates import Box, Point
from moanart.core.errors import BudgetExceeded
from moanart.geometry import FLOOD_FILL_BYTES_PER_PIXEL, Mask, flood_fill, flood_fill_cost

LIMITS = RenderLimits()
PALETTE = {
    ".": (0, 0, 0, 0),
    "#": (10, 20, 30, 255),
    "o": (200, 100, 50, 255),
    "p": (200, 100, 50, 254),  # differs from "o" only in alpha
    "q": (200, 100, 51, 255),  # differs from "o" only in blue
    "t": (9, 9, 9, 0),  # transparent with garbage RGB: normalised to "."
}


def canvas(*rows: str) -> Canvas:
    array = np.array([[PALETTE[c] for c in row] for row in rows], dtype=np.uint8)
    return Canvas.from_array(array, limits=LIMITS)


def grid(mask: Mask, width: int, height: int) -> list[str]:
    return [
        "".join("#" if mask.contains(Point(x, y)) else "." for x in range(width))
        for y in range(height)
    ]


def test_fill_of_isolated_single_pixel() -> None:
    snapshot = canvas("###", "#o#", "###")
    mask = flood_fill(snapshot, Point(1, 1), limits=LIMITS)
    assert grid(mask, 3, 3) == ["...", ".#.", "..."]


def test_fill_of_uniform_canvas_covers_everything() -> None:
    snapshot = canvas("oooo", "oooo", "oooo")
    mask = flood_fill(snapshot, Point(3, 2), limits=LIMITS)
    assert grid(mask, 4, 3) == ["####", "####", "####"]
    assert mask.box == Box(0, 0, 4, 3) and mask.count == 12


def test_ac2_fill_does_not_cross_colour_boundaries() -> None:
    snapshot = canvas(
        "oo#oo",
        "oo#oo",
        "#####",
        "oo#oo",
    )
    assert grid(flood_fill(snapshot, Point(0, 0), limits=LIMITS), 5, 4) == [
        "##...",
        "##...",
        ".....",
        ".....",
    ]


def test_fill_is_four_connected_not_diagonal() -> None:
    snapshot = canvas("o#", "#o")
    assert grid(flood_fill(snapshot, Point(0, 0), limits=LIMITS), 2, 2) == ["#.", ".."]


def test_colour_match_is_exact_per_channel() -> None:
    snapshot = canvas("oopqo")
    assert grid(flood_fill(snapshot, Point(0, 0), limits=LIMITS), 5, 1) == ["##..."]
    assert grid(flood_fill(snapshot, Point(4, 0), limits=LIMITS), 5, 1) == ["....#"]


def test_transparent_pixels_match_after_alpha_normalisation() -> None:
    snapshot = canvas(".t#t.")
    assert grid(flood_fill(snapshot, Point(1, 0), limits=LIMITS), 5, 1) == ["##..."]


def test_fill_follows_a_winding_corridor() -> None:
    # A serpentine needs the scanline to go up and down and to revisit claimed runs.
    snapshot = canvas(
        "o#ooo",
        "o#o#o",
        "ooo#o",
        "####o",
        "ooooo",
        "o#o#o",
    )
    assert grid(flood_fill(snapshot, Point(0, 0), limits=LIMITS), 5, 6) == [
        "#.###",
        "#.#.#",
        "###.#",
        "....#",
        "#####",
        "#.#.#",
    ]


def test_seed_off_canvas_is_empty() -> None:
    snapshot = canvas("oo")
    for seed in (Point(-1, 0), Point(2, 0), Point(0, -1), Point(0, 1)):
        assert flood_fill(snapshot, seed, limits=LIMITS) == Mask.empty()


def test_fill_does_not_modify_the_snapshot() -> None:
    snapshot = canvas("o#o", "ooo")
    before = snapshot.to_bytes()
    flood_fill(snapshot, Point(0, 0), limits=LIMITS)
    assert snapshot.to_bytes() == before


def test_budget_rejection_happens_before_any_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = canvas("oooo", "oooo")  # A = 8

    def forbidden(_self: Canvas) -> object:
        raise AssertionError("snapshot copied before the budget check")

    monkeypatch.setattr(Canvas, "to_array", forbidden)
    limits = RenderLimits(max_pixel_visits=7, max_buffer_bytes=8 * FLOOD_FILL_BYTES_PER_PIXEL - 1)
    with pytest.raises(BudgetExceeded) as excinfo:
        flood_fill(snapshot, Point(0, 0), limits=limits)
    contexts = [dict(detail.context) for detail in excinfo.value.details]
    assert contexts == [
        {"resource": "pixel_visits", "limit": 7, "estimated": 8},
        {"resource": "buffer_bytes", "limit": 63, "estimated": 64},
    ]


def test_budget_admits_exact_limit() -> None:
    snapshot = canvas("oooo", "oooo")
    assert flood_fill_cost(snapshot) == (8, 8 * FLOOD_FILL_BYTES_PER_PIXEL)
    limits = RenderLimits(max_pixel_visits=8, max_buffer_bytes=8 * FLOOD_FILL_BYTES_PER_PIXEL)
    assert flood_fill(snapshot, Point(1, 1), limits=limits).count == 8


def test_fill_rejects_wrong_argument_types() -> None:
    snapshot = canvas("o")
    with pytest.raises(TypeError):
        flood_fill(np.zeros((1, 1, 4), np.uint8), Point(0, 0), limits=LIMITS)  # type: ignore[arg-type]  # misuse
    with pytest.raises(TypeError):
        flood_fill(snapshot, (0, 0), limits=LIMITS)  # type: ignore[arg-type]  # misuse
    with pytest.raises(TypeError):
        flood_fill(snapshot, Point(0, 0), limits=None)  # type: ignore[arg-type]  # misuse


def _reference_fill(cells: list[list[int]], seed: tuple[int, int]) -> set[tuple[int, int]]:
    """Plain breadth-first search over a colour grid, the textbook definition."""
    height, width = len(cells), len(cells[0])
    x0, y0 = seed
    target = cells[y0][x0]
    seen = {seed}
    frontier = [seed]
    while frontier:
        x, y = frontier.pop()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            inside = 0 <= nx < width and 0 <= ny < height
            if inside and (nx, ny) not in seen and cells[ny][nx] == target:
                seen.add((nx, ny))
                frontier.append((nx, ny))
    return seen


@settings(max_examples=150)
@given(st.data())
def test_fill_matches_breadth_first_reference(data: st.DataObject) -> None:
    width = data.draw(st.integers(1, 9))
    height = data.draw(st.integers(1, 7))
    cells = data.draw(
        st.lists(
            st.lists(st.integers(0, 2), min_size=width, max_size=width),
            min_size=height,
            max_size=height,
        )
    )
    seed = (data.draw(st.integers(0, width - 1)), data.draw(st.integers(0, height - 1)))
    colours = [(0, 0, 0, 255), (255, 255, 255, 255), (0, 0, 0, 254)]
    array = np.array([[colours[c] for c in row] for row in cells], dtype=np.uint8)
    snapshot = Canvas.from_array(array, limits=LIMITS)
    mask = flood_fill(snapshot, Point(*seed), limits=LIMITS)
    assert {(p.x, p.y) for p in mask.points()} == _reference_fill(cells, seed)


def test_one_by_one_canvas_fill() -> None:
    snapshot = canvas("o")
    assert grid(flood_fill(snapshot, Point(0, 0), limits=LIMITS), 1, 1) == ["#"]
    assert flood_fill(snapshot, Point(1, 0), limits=LIMITS).is_empty
