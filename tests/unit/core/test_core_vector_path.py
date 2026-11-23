"""Fixed-point path grammar, flattening and bounds (MOANA-007, ADR-023).

Expected values are computed by hand from the rules in the ``moanart.core.vector_path``
docstring: Bernstein points, the ``64 n^2 >= k D`` step rule and round-half-even.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from moanart.core.coordinates import Box
from moanart.core.errors import ValidationError
from moanart.core.limits import MAX_PATH_COMMANDS, MAX_PATH_CURVE_SEGMENTS, MAX_PATH_SEGMENTS
from moanart.core.vector_path import (
    FLATNESS_UNITS,
    MAX_PATH_COORDINATE,
    PATH_BACKEND_FIXED_BYTES,
    PATH_COMMAND_POINTS,
    PATH_UNITS,
    FixedPath,
    PathCommand,
    curve_steps,
    parse_path,
    path_buffer_box,
    path_raster_bytes,
    path_raster_visits,
)

U = PATH_UNITS


def reason_of(commands: Any) -> tuple[object, object]:
    with pytest.raises(ValidationError) as raised:
        parse_path(commands)
    context = raised.value.context
    assert context["field"] == "commands"
    return context["reason"], context.get("index")


def square(x0: int, y0: int, x1: int, y1: int) -> list[tuple[Any, ...]]:
    return [("M", x0, y0), ("L", x1, y0), ("L", x1, y1), ("L", x0, y1), ("Z",)]


@pytest.mark.parametrize(
    ("commands", "expected"),
    [
        ("M 0 0", ("not_sequence", None)),
        (b"M", ("not_sequence", None)),
        (None, ("not_sequence", None)),
        ([("M", 0, 0)], ("out_of_range", None)),
        ([("M", 0, 0)] + [("L", 1, 1)] * MAX_PATH_COMMANDS, ("out_of_range", None)),
        ([("M", 0, 0), "L"], ("not_command", 1)),
        ([("M", 0, 0), ()], ("not_command", 1)),
        ([("M", 0, 0), 7], ("not_command", 1)),
        ([("M", 0, 0), ("A", 1, 1)], ("unknown_command", 1)),
        ([("M", 0, 0), ("l", 1, 1)], ("unknown_command", 1)),
        ([("M", 0, 0), (1, 1, 1)], ("unknown_command", 1)),
        ([("M", 0, 0), ("L", 1)], ("wrong_arity", 1)),
        ([("M", 0, 0), ("Q", 1, 1, 2)], ("wrong_arity", 1)),
        ([("M", 0, 0), ("L", 1, 1), ("Z", 0)], ("wrong_arity", 2)),
        ([("M", 0, 0), ("L", True, 1)], ("not_integer", 1)),
        ([("M", 0, 0), ("L", 1.0, 1)], ("not_integer", 1)),
        ([("M", 0, 0), ("L", "1", 1)], ("not_integer", 1)),
        ([("M", 0, 0), ("L", MAX_PATH_COORDINATE + 1, 0)], ("out_of_range", 1)),
        ([("M", -MAX_PATH_COORDINATE - 1, 0), ("L", 0, 0)], ("out_of_range", 0)),
        ([("M", 0, 0), ("L", 0, 10**40)], ("out_of_range", 1)),
        ([("L", 0, 0), ("L", 1, 1)], ("path_start", 0)),
        ([("Z",), ("L", 1, 1)], ("path_start", 0)),
        ([("M", 0, 0), ("Z",)], ("empty_subpath", 1)),
        ([("M", 0, 0), ("M", 1, 1), ("L", 2, 2)], ("empty_subpath", 1)),
        ([("M", 0, 0), ("L", 1, 1), ("M", 5, 5)], ("empty_subpath", 2)),
        ([("M", 0, 0), ("L", 1, 1), ("Z",), ("L", 2, 2)], ("command_after_close", 3)),
        ([("M", 0, 0), ("L", 1, 1), ("Z",), ("Z",)], ("command_after_close", 3)),
    ],
)
def test_invalid_commands_raise_located_validation_errors(
    commands: Any, expected: tuple[object, object]
) -> None:
    assert reason_of(commands) == expected


def test_too_many_segments_is_reported_at_the_command_that_crosses_the_limit() -> None:
    wild = ("C", 0, 400 * U, 400 * U, -400 * U, 0, 0)  # D huge: 64 segments each
    commands = [("M", 0, 0), *[wild] * (MAX_PATH_COMMANDS - 1)]
    reason, index = reason_of(commands)
    assert reason == "too_many_segments"
    # 1 (the M) + 64 k > 65 536 first holds for the k = 1024th curve, at index 1024.
    assert index == MAX_PATH_SEGMENTS // MAX_PATH_CURVE_SEGMENTS == 1024


def test_valid_paths_keep_every_command_and_accept_lists() -> None:
    path = parse_path([["M", 0, 0], ["L", 512, 0], ["Q", 512, 512, 0, 512], ["Z"]])
    assert [command.op for command in path.commands] == ["M", "L", "Q", "Z"]
    assert path.commands[2].points == ((512, 512), (0, 512))
    assert path.commands[3].points == ()
    edge = MAX_PATH_COORDINATE
    assert parse_path([("M", -edge, -edge), ("L", edge, edge)]).reach == edge // U


def test_explicit_and_implicit_close_count_the_same_segments() -> None:
    explicit = parse_path(square(0, 0, U, U))
    implicit = parse_path(square(0, 0, U, U)[:-1])
    assert explicit.segments == implicit.segments == 4
    assert list(explicit.outline()) == list(implicit.outline())


def test_two_subpaths_each_add_their_closing_edge() -> None:
    path = parse_path([*square(0, 0, U, U), *square(2 * U, 0, 3 * U, U)[:-1]])
    assert path.segments == 8
    starts = [point for begins, point in path.outline() if begins]
    assert starts == [(0, 0), (2 * U, 0)]


@pytest.mark.parametrize(
    ("points", "steps"),
    [
        (((0, 0), (5, 5), (10, 0)), 1),  # D = 20: 64 >= 20
        (((0, 0), (32, 32), (0, 64)), 1),  # D = 64: 64 >= 64
        (((0, 0), (33, 32), (0, 64)), 2),  # D = 66: 256 >= 66 > 64
        (((0, 0), (1024, 1024), (2048, 0)), 6),  # D = 2048: n^2 >= 32
        (((0, 0), (0, 0), (0, 0)), 1),
        (((0, 0), (100, 0), (100, 0), (0, 0)), 3),  # D = 100, 3D = 300: n^2 >= 4.7
        (((0, 0), (10**8, 0), (-(10**8), 0), (0, 0)), MAX_PATH_CURVE_SEGMENTS),
    ],
)
def test_curve_steps_follow_the_flatness_rule(points: Any, steps: int) -> None:
    assert curve_steps(points) == steps


def test_curve_steps_rejects_other_degrees() -> None:
    with pytest.raises(ValueError, match="curve"):
        curve_steps(((0, 0), (1, 1)))


@given(
    st.lists(st.tuples(st.integers(-4096, 4096), st.integers(-4096, 4096)), min_size=3, max_size=4)
)
def test_chosen_steps_bound_the_chord_error(points: list[tuple[int, int]]) -> None:
    """Sample the exact curve and measure its distance to the flattened polyline.

    Independent of the step formula: every sampled point of the exact Bezier curve
    lies within ``FLATNESS_UNITS`` (1/16 px) plus one unit of rounding of the
    polyline that ``outline()`` yields. Coordinates up to 16 px stay below the clamp.
    """
    op = "Q" if len(points) == 3 else "C"
    path = parse_path([("M", *points[0]), (op, *[v for point in points[1:] for v in point])])
    polyline = [vertex for _, vertex in path.outline()]
    assert curve_steps(points) < MAX_PATH_CURVE_SEGMENTS
    degree = len(points) - 1
    worst = 0.0
    for k in range(SAMPLES + 1):
        t = k / SAMPLES
        weights = [math.comb(degree, i) * (1 - t) ** (degree - i) * t**i for i in range(degree + 1)]
        x = sum(w * point[0] for w, point in zip(weights, points, strict=True))
        y = sum(w * point[1] for w, point in zip(weights, points, strict=True))
        worst = max(worst, distance_to_polyline((x, y), polyline))
    assert worst <= FLATNESS_UNITS + 1


SAMPLES = 256


def distance_to_polyline(point: tuple[float, float], polyline: list[tuple[int, int]]) -> float:
    if len(polyline) == 1:
        return math.dist(point, polyline[0])
    best = math.inf
    for (ax, ay), (bx, by) in itertools.pairwise(polyline):
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        t = 0.0 if length == 0 else ((point[0] - ax) * dx + (point[1] - ay) * dy) / length
        t = min(1.0, max(0.0, t))
        best = min(best, math.dist(point, (ax + t * dx, ay + t * dy)))
    return best


def test_quadratic_points_are_exact_bernstein_values_rounded_half_even() -> None:
    # P0=(0,0), P1=(2048,2048), P2=(4096,0): D=4096, n^2 >= 64 -> n = 8.
    path = parse_path([("M", 0, 0), ("Q", 2048, 2048, 4096, 0)])
    points = [point for _, point in path.outline()]
    # x(t) = 4096 t; y(t) = 4096 t (1 - t) with t = k/8, exact here.
    assert points == [(0, 0)] + [(512 * k, 64 * k * (8 - k)) for k in range(1, 9)]
    assert path.segments == 1 + 8


def test_cubic_rounding_ties_go_to_even() -> None:
    # P = (0,0), (1,0), (2,0), (3,0): x(t) = 3t. D = 0 -> n = 1: only the end point.
    assert [p for _, p in parse_path([("M", 0, 0), ("C", 1, 0, 2, 0, 3, 0)]).outline()] == [
        (0, 0),
        (3, 0),
    ]
    # Quadratic with D = 132 + |x0| <= 138 -> n = 2: the midpoint is (P0 + 2 P1 + P2) / 4,
    # x = 1/4 -> 0 and y = 132/4 = 33.
    path = parse_path([("M", 1, 0), ("Q", 0, 66, 0, 0)])
    assert [p for _, p in path.outline()] == [(1, 0), (0, 33), (0, 0)]
    tie = parse_path([("M", 2, 0), ("Q", 0, 66, 0, 0)])  # x mid = 2/4 = 0.5 -> 0 (even)
    assert [p for _, p in tie.outline()][1] == (0, 33)
    odd = parse_path([("M", 6, 0), ("Q", 0, 66, 0, 0)])  # x mid = 6/4 = 1.5 -> 2 (even)
    assert [p for _, p in odd.outline()][1] == (2, 33)
    negative = parse_path([("M", -6, 0), ("Q", 0, 66, 0, 0)])  # -1.5 -> -2 (mirror)
    assert [p for _, p in negative.outline()][1] == (-2, 33)


def test_bounds_are_the_pixel_box_of_every_point() -> None:
    assert parse_path(square(U, U, 5 * U, 5 * U)).bounds == Box(1, 1, 5, 5)
    assert parse_path(square(U + 1, U + 255, 5 * U - 1, 5 * U + 1)).bounds == Box(1, 1, 5, 6)
    assert parse_path(square(-U - 1, -1, 0, 1)).bounds == Box(-2, -1, 0, 1)
    curve = parse_path([("M", 0, 0), ("C", 0, 9 * U, 3 * U, -2 * U, 3 * U, 0)])
    assert curve.bounds == Box(0, -2, 3, 9)  # control points, not just end points


@pytest.mark.parametrize(
    "commands",
    [
        [("M", 0, 0), ("L", 4 * U, 0), ("Z",)],  # flat horizontally
        [("M", U, 0), ("L", U, 4 * U)],  # vertical on a pixel edge
    ],
)
def test_flat_paths_on_pixel_edges_have_no_bounds(commands: Any) -> None:
    assert parse_path(commands).bounds is None


def test_reach_rounds_away_from_zero() -> None:
    assert parse_path([("M", 0, 0), ("L", 1, -1)]).reach == 1
    assert parse_path([("M", 0, 0), ("L", 2 * U, -U)]).reach == 2
    assert parse_path([("M", 0, 0), ("L", 0, 0)]).reach == 0


def test_manhattan_length_counts_control_polygons_and_closing_edges() -> None:
    assert parse_path(square(0, 0, 2 * U, U)).manhattan_length == 6
    # M (0,0) Q (U,U) (2U,0): 2U + 2U = 4U, closing 2U -> 6
    assert parse_path([("M", 0, 0), ("Q", U, U, 2 * U, 0)]).manhattan_length == 6
    two = parse_path([("M", 0, 0), ("L", U, 0), ("M", 0, 0), ("L", 0, 1)])
    assert two.manhattan_length == 3  # 2U + 2 units = 2.008 px, rounded up


def test_cell_bound_is_the_smaller_of_length_and_box_bounds() -> None:
    path = parse_path(square(0, 0, 2 * U, U))  # 4 segments, length 6 px
    assert path.cell_bound(Box(0, 0, 100, 100)) == 2 * 6 + 3 * 4
    large = parse_path(square(0, 0, 100 * U, 100 * U))  # length 400 px
    assert large.cell_bound(Box(0, 0, 2, 2)) == 3 * 4 * (2 + 2 + 1)
    assert isinstance(path, FixedPath)


# --- Hand-built values are validated too ----------------------------------------------


def test_command_table_is_read_only() -> None:
    with pytest.raises(TypeError):
        PATH_COMMAND_POINTS["A"] = 1  # type: ignore[index]


@pytest.mark.parametrize(
    ("op", "points", "reason"),
    [
        ("A", ((0, 0),), "unknown_command"),
        (7, ((0, 0),), "unknown_command"),
        ("L", [(0, 0)], "wrong_arity"),
        ("L", (), "wrong_arity"),
        ("Q", ((0, 0),), "wrong_arity"),
        ("L", ((0,),), "wrong_arity"),
        ("L", ([0, 0],), "wrong_arity"),
        ("L", ((0, True),), "not_integer"),
        ("L", ((0, 0.5),), "not_integer"),
        ("L", ((MAX_PATH_COORDINATE + 1, 0),), "out_of_range"),
    ],
)
def test_path_commands_validate_themselves(op: Any, points: Any, reason: str) -> None:
    with pytest.raises(ValidationError) as raised:
        PathCommand(op, points)
    assert raised.value.context["reason"] == reason
    assert "index" not in raised.value.context


@pytest.mark.parametrize(
    ("commands", "expected"),
    [
        ([PathCommand("M", ((0, 0),)), PathCommand("L", ((U, U),))], ("not_sequence", None)),
        ((), ("out_of_range", None)),
        ((PathCommand("M", ((0, 0),)),), ("out_of_range", None)),
        ((PathCommand("M", ((0, 0),)), ("L", 1, 1)), ("not_command", 1)),
        ((PathCommand("L", ((0, 0),)), PathCommand("L", ((U, U),))), ("path_start", 0)),
        ((PathCommand("M", ((0, 0),)), PathCommand("Z", ())), ("empty_subpath", 1)),
    ],
)
def test_fixed_paths_validate_themselves(commands: Any, expected: tuple[object, object]) -> None:
    with pytest.raises(ValidationError) as raised:
        FixedPath(commands)
    context = raised.value.context
    assert (context["reason"], context.get("index")) == expected


def test_segments_are_derived_and_cannot_be_passed() -> None:
    commands = tuple(parse_path(square(0, 0, 4 * U, 4 * U)).commands)
    path = FixedPath(commands)
    assert path.segments == 4 and path == parse_path(square(0, 0, 4 * U, 4 * U))
    with pytest.raises(TypeError):
        FixedPath(commands, 0)  # type: ignore[call-arg]
    wild = PathCommand("C", ((0, 0), (MAX_PATH_COORDINATE, 0), (0, MAX_PATH_COORDINATE)))
    bomb = (PathCommand("M", ((0, 0),)), *[wild] * (MAX_PATH_SEGMENTS // 64))
    with pytest.raises(ValidationError) as raised:
        FixedPath(bomb)
    assert raised.value.context["reason"] == "too_many_segments"


def test_raster_formulas_by_hand() -> None:
    """Square [1, 5)^2 in an 8x8 canvas: box 4x4, buffer 6x6, S = 4, cells 44."""
    path = parse_path(square(U, U, 5 * U, 5 * U))
    box = Box(1, 1, 5, 5)
    assert path_buffer_box(box) == Box(0, 0, 6, 6)
    assert path_raster_visits(path, box) == 4 + 44 + 3 * 36
    assert path_raster_visits(path, None) == 4
    assert path_raster_bytes(path, box) == 16 + 72 + 24 * 44 + 256 * 5 + PATH_BACKEND_FIXED_BYTES
    assert path_raster_bytes(path, None) == 0
