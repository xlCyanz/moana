"""AggDraw path adapter ``aggdraw-v1`` (MOANA-007, ADR-023).

AC1: closed paths give only a binary mask inside the path box. T1: small curves,
joins, closes, paths partly or wholly off the canvas and degenerate paths. Oracles
are independent of the backend: exact pixel-square geometry in 1/256 units (a pixel
whose square is inside a single simple subpath must be in the mask, the contract; one
whose square, grown by 1/2 pixel, misses a convex fixture is out, which only
characterises AggDraw 1.4.1 on those fixtures), the integer ``rect``/``polygon``
masks on those pixels, and symmetries of the input. Counterexamples A-D of ADR-023
record where 1.4.1 departs from both. Nothing compares against a stored render.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.metadata
import sys
from collections.abc import Iterable, Sequence
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import moana.geometry.paths as paths_module
from moana.core.coordinates import Box, Dimensions, Point
from moana.core.errors import BudgetExceeded, MoanaError, UnsupportedOperation
from moana.core.limits import MAX_PATH_CELLS
from moana.core.vector_path import PATH_UNITS, FixedPath, parse_path
from moana.geometry import (
    AGGDRAW_BACKEND,
    COVERAGE_THRESHOLD,
    TESTED_AGGDRAW_VERSIONS,
    Mask,
    path_backend,
    path_buffer_box,
    path_mask_box,
    rasterize_path,
    rasterize_polygon,
    rasterize_rect,
)
from moana.schema import SUPPORTED_PATH_BACKENDS

U = PATH_UNITS
Pixel = tuple[int, int]
Vertex = tuple[int, int]


def pixels(mask: Mask) -> set[Pixel]:
    return {(point.x, point.y) for point in mask.points()}


def closed(vertices: Sequence[Vertex], *, close: bool = True) -> FixedPath:
    commands: list[tuple[Any, ...]] = [("M", *vertices[0])]
    commands += [("L", *vertex) for vertex in vertices[1:]]
    if close:
        commands.append(("Z",))
    return parse_path(commands)


def scaled(vertices: Iterable[tuple[float, float]]) -> list[Vertex]:
    return [(round(x * U), round(y * U)) for x, y in vertices]


# --- Independent geometric oracles (exact integers in 1/256 units) --------------------


def cross(o: Vertex, a: Vertex, b: Vertex) -> int:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def hull(points: Iterable[Vertex]) -> list[Vertex]:
    """Convex hull (monotone chain), counter-clockwise in a y-up sense."""
    ordered = sorted(set(points))
    if len(ordered) <= 2:
        return ordered
    lower: list[Vertex] = []
    upper: list[Vertex] = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def square_corners(x: int, y: int, grow: int = 0) -> list[Vertex]:
    x0, y0, x1, y1 = x * U - grow, y * U - grow, (x + 1) * U + grow, (y + 1) * U + grow
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def inside_convex(polygon: list[Vertex], point: Vertex) -> bool:
    """Point inside or on a convex polygon given counter-clockwise by :func:`hull`."""
    count = len(polygon)
    return all(cross(polygon[i], polygon[(i + 1) % count], point) >= 0 for i in range(count))


def separated(a: list[Vertex], b: list[Vertex]) -> bool:
    """Separating axis test of two convex polygons (touching counts as overlapping)."""
    for polygon in (a, b):
        count = len(polygon)
        for i in range(count):
            p, q = polygon[i], polygon[(i + 1) % count]
            axis = (q[1] - p[1], p[0] - q[0])
            ra = [axis[0] * v[0] + axis[1] * v[1] for v in a]
            rb = [axis[0] * v[0] + axis[1] * v[1] for v in b]
            if max(ra) < min(rb) or max(rb) < min(ra):
                return True
    return False


def must_be_in(polygon: list[Vertex], dimensions: Dimensions) -> set[Pixel]:
    """Pixels whose whole square lies in the convex ``polygon`` (coverage 255)."""
    return {
        (x, y)
        for y in range(dimensions.height)
        for x in range(dimensions.width)
        if all(inside_convex(polygon, corner) for corner in square_corners(x, y))
    }


def may_be_in(polygon: list[Vertex], dimensions: Dimensions) -> set[Pixel]:
    """Pixels whose square grown by 1/2 pixel touches the convex ``polygon``."""
    return {
        (x, y)
        for y in range(dimensions.height)
        for x in range(dimensions.width)
        if not separated(square_corners(x, y, U // 2), polygon)
    }


def check_between(mask: Mask, polygon: Sequence[Vertex], dimensions: Dimensions) -> None:
    convex = hull(polygon)
    got = pixels(mask)
    assert must_be_in(convex, dimensions) <= got <= may_be_in(convex, dimensions)


# --- Backend and typed surface ---------------------------------------------------------


def test_backend_is_available_and_tested_here() -> None:
    status = path_backend()
    assert status.name == AGGDRAW_BACKEND == "aggdraw-v1"
    assert status.available and status.reason is None
    assert status.version in TESTED_AGGDRAW_VERSIONS
    assert isinstance(status.pillow_version, str)


def test_missing_backend_is_an_explicit_unsupported_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "aggdraw", None)  # makes ``import aggdraw`` fail
    status = path_backend()
    assert (status.available, status.version, status.reason) == (False, None, "missing")
    with pytest.raises(UnsupportedOperation) as raised:
        rasterize_path(closed(scaled([(0, 0), (2, 0), (2, 2)])), Dimensions(4, 4))
    context = raised.value.context
    assert context["reason"] == "backend_unavailable"
    assert context["cause"] == "missing"
    assert "version" not in context
    assert context["tested_versions"] == TESTED_AGGDRAW_VERSIONS


@pytest.mark.parametrize("version", ["1.3.19", "1.4.2", "2.0", None, 141])
def test_untested_version_is_an_explicit_unsupported_operation(
    monkeypatch: pytest.MonkeyPatch, version: object
) -> None:
    aggdraw = importlib.import_module("aggdraw")
    monkeypatch.setattr(aggdraw, "VERSION", version)
    monkeypatch.setattr(aggdraw, "__version__", version, raising=False)
    status = path_backend()
    assert (status.available, status.reason) == (False, "untested_version")
    with pytest.raises(UnsupportedOperation) as raised:
        rasterize_path(closed(scaled([(0, 0), (2, 0), (2, 2)])), Dimensions(4, 4))
    assert raised.value.context["cause"] == "untested_version"
    assert raised.value.context.get("version") == (version if isinstance(version, str) else None)


def test_pillow_version_comes_from_the_installed_distribution() -> None:
    assert path_backend().pillow_version == importlib.metadata.version("pillow")


def test_pillow_version_is_unknown_without_the_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    status = path_backend()
    assert status.available and status.pillow_version is None


class _BrokenImport(importlib.abc.MetaPathFinder):
    """Finder that makes ``import aggdraw`` raise something other than ImportError."""

    def find_spec(self, name: str, *_: object) -> None:
        if name == "aggdraw":
            raise RuntimeError("broken native build")
        return None


def test_a_backend_that_fails_to_import_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "aggdraw", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_BrokenImport(), *sys.meta_path])
    status = path_backend()
    assert (status.available, status.version, status.reason) == (False, None, "import_failed")
    with pytest.raises(UnsupportedOperation) as raised:
        rasterize_path(closed(scaled([(0, 0), (2, 0), (2, 2)])), Dimensions(4, 4))
    assert raised.value.context["cause"] == "import_failed"


@pytest.mark.parametrize("name", ["Draw", "Path", "Brush"])
def test_a_backend_without_the_used_api_is_incompatible(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delattr(importlib.import_module("aggdraw"), name)
    status = path_backend()
    assert (status.available, status.reason) == (False, "incompatible")
    assert status.version in TESTED_AGGDRAW_VERSIONS


@pytest.mark.parametrize("failure", [ValueError, MemoryError, OSError])
def test_backend_failures_while_drawing_become_domain_errors(
    monkeypatch: pytest.MonkeyPatch, failure: type[Exception]
) -> None:
    aggdraw = importlib.import_module("aggdraw")

    def broken(*_: object) -> object:
        raise failure("native failure with /private/path")

    monkeypatch.setattr(aggdraw, "Draw", broken)
    with pytest.raises(MoanaError) as raised:
        rasterize_path(closed(scaled([(0, 0), (2, 0), (2, 2)])), Dimensions(4, 4))
    assert type(raised.value) is MoanaError
    assert dict(raised.value.context) == {
        "reason": "backend_failure",
        "backend": AGGDRAW_BACKEND,
        "cause": failure.__name__,
    }
    assert "/private" not in str(raised.value)


def test_backend_is_a_supported_schema_backend() -> None:
    assert AGGDRAW_BACKEND in SUPPORTED_PATH_BACKENDS


def test_type_checks() -> None:
    path = closed(scaled([(0, 0), (2, 0), (2, 2)]))
    with pytest.raises(TypeError, match="FixedPath"):
        rasterize_path([("M", 0, 0)], Dimensions(4, 4))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Dimensions"):
        rasterize_path(path, (4, 4))  # type: ignore[arg-type]


def test_result_is_a_moana_mask_without_backend_objects() -> None:
    mask = rasterize_path(closed(scaled([(0, 0), (3, 0), (3, 3)])), Dimensions(4, 4))
    assert type(mask) is Mask
    assert mask.to_array().flags.writeable  # a copy, never the mask's own bits
    assert all(not type(value).__module__.startswith("aggdraw") for value in (mask, mask.box))


# --- AC1: binary masks inside the path box ----------------------------------------------


SHAPES: dict[str, list[tuple[Any, ...]]] = {
    "triangle": [("M", 1 * U, 1 * U), ("L", 13 * U, 3 * U), ("L", 4 * U, 12 * U), ("Z",)],
    "quadratic": [("M", 1 * U, 13 * U), ("Q", 7 * U, -5 * U, 13 * U, 13 * U), ("Z",)],
    "cubic": [("M", 2 * U, 12 * U), ("C", 0, 0, 14 * U, 0, 12 * U, 12 * U)],
    "fractional": [("M", 300, 450), ("L", 3000, 777), ("L", 2222, 3333), ("Z",)],
    "two_subpaths": [
        *[("M", 1 * U, 1 * U), ("L", 5 * U, 1 * U), ("L", 3 * U, 6 * U), ("Z",)],
        *[("M", 8 * U, 8 * U), ("Q", 14 * U, 8 * U, 14 * U, 14 * U), ("L", 8 * U, 14 * U)],
    ],
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_ac1_paths_give_binary_masks_inside_their_box(name: str) -> None:
    path = parse_path(SHAPES[name])
    dimensions = Dimensions(16, 16)
    mask = rasterize_path(path, dimensions)
    bits = mask.to_array()
    assert bits.dtype == bool  # binary: no coverage level survives
    assert mask.box == path_mask_box(path, dimensions)
    box = path.bounds
    assert box is not None
    assert all(box.contains(Point(x, y)) for x, y in pixels(mask))
    assert mask.count > 0


# --- T1: fixtures with independent oracles ----------------------------------------------


@settings(max_examples=40, deadline=None)
@given(
    st.integers(-6, 14),
    st.integers(-6, 14),
    st.integers(1, 10),
    st.integers(1, 10),
    st.booleans(),
)
def test_integer_rectangles_equal_the_integer_rect_mask(
    x0: int, y0: int, width: int, height: int, close: bool
) -> None:
    dimensions = Dimensions(12, 10)
    corners = [(x0, y0), (x0 + width, y0), (x0 + width, y0 + height), (x0, y0 + height)]
    path = closed([(x * U, y * U) for x, y in corners], close=close)
    expected = rasterize_rect(Box(x0, y0, x0 + width, y0 + height), dimensions)
    assert pixels(rasterize_path(path, dimensions)) == pixels(expected)


TRIANGLES = {
    "right": scaled([(1, 1), (11, 1), (1, 9)]),
    "obtuse": scaled([(0.5, 2.25), (13.75, 4.5), (3.125, 11.0)]),
    "thin": scaled([(1, 6), (14, 6.5), (1, 7)]),
    "spike_join": scaled([(2, 2), (14, 7.5), (2, 13), (3.5, 7.5)]),
    "clockwise": scaled([(1, 9), (11, 1), (1, 1)]),
}


@pytest.mark.parametrize("name", sorted(TRIANGLES))
def test_convex_and_join_fixtures_lie_between_the_geometric_oracles(name: str) -> None:
    vertices = TRIANGLES[name]
    dimensions = Dimensions(16, 16)
    mask = rasterize_path(closed(vertices), dimensions)
    if name == "spike_join":  # concave: inner oracle on its convex parts only
        got = pixels(mask)
        for part in (vertices[:2] + vertices[3:], [vertices[3], *vertices[1:3]]):
            assert must_be_in(hull(part), dimensions) <= got
        assert got <= may_be_in(hull(vertices), dimensions)
    else:
        check_between(mask, vertices, dimensions)


@pytest.mark.parametrize("name", ["right", "obtuse", "clockwise"])
def test_polygon_paths_agree_with_the_integer_polygon_where_guaranteed(name: str) -> None:
    """Only on pixels fully inside or clearly outside: elsewhere backends may differ."""
    vertices = TRIANGLES[name]
    dimensions = Dimensions(16, 16)
    path_pixels = pixels(rasterize_path(closed(vertices), dimensions))
    if all(x % U == 0 and y % U == 0 for x, y in vertices):
        integer = pixels(
            rasterize_polygon([Point(x // U, y // U) for x, y in vertices], dimensions)
        )
        convex = hull(vertices)
        sure_in, maybe = must_be_in(convex, dimensions), may_be_in(convex, dimensions)
        everywhere = {(x, y) for y in range(16) for x in range(16)}
        decided = sure_in | (everywhere - maybe)
        assert path_pixels & decided == integer & decided
    else:
        check_between(rasterize_path(closed(vertices), dimensions), vertices, dimensions)


@pytest.mark.parametrize("name", ["quadratic", "cubic"])
def test_curves_stay_within_the_hull_of_their_control_points(name: str) -> None:
    path = parse_path(SHAPES[name])
    controls = [point for command in path.commands for point in command.points]
    dimensions = Dimensions(16, 16)
    mask = rasterize_path(path, dimensions)
    assert pixels(mask) <= may_be_in(hull(controls), dimensions)
    assert mask.count > 0


def mirrored(commands: Sequence[tuple[Any, ...]], width: int) -> list[tuple[Any, ...]]:
    """Mirror about the vertical line ``x = width / 2`` (a pixel edge when even)."""
    result: list[tuple[Any, ...]] = []
    for op, *values in commands:
        result.append((op, *[width * U - v if i % 2 == 0 else v for i, v in enumerate(values)]))
    return result


@pytest.mark.parametrize(
    "commands",
    [
        [
            ("M", 8 * U, 1 * U),
            ("Q", 15 * U, 8 * U, 8 * U, 15 * U),
            ("Q", 1 * U, 8 * U, 8 * U, 1 * U),
        ],
        [("M", 3 * U, 13 * U), ("C", 3 * U, 1 * U, 13 * U, 1 * U, 13 * U, 13 * U), ("Z",)],
        [("M", 8 * U, 2 * U), ("L", 13 * U, 14 * U), ("L", 3 * U, 14 * U), ("Z",)],
    ],
)
def test_symmetric_inputs_give_symmetric_masks(commands: list[tuple[Any, ...]]) -> None:
    dimensions = Dimensions(16, 16)
    original = pixels(rasterize_path(parse_path(commands), dimensions))
    flipped = pixels(rasterize_path(parse_path(mirrored(commands, 16)), dimensions))
    assert flipped == {(15 - x, y) for x, y in original}
    assert original == {(15 - x, y) for x, y in original}  # these inputs are self-mirrored


def test_explicit_and_implicit_close_fill_the_same_pixels() -> None:
    dimensions = Dimensions(16, 16)
    for commands in SHAPES.values():
        explicit = [c for c in commands if c[0] != "Z"]
        with_close: list[tuple[Any, ...]] = []
        for index, command in enumerate(explicit):
            if command[0] == "M" and index:
                with_close.append(("Z",))
            with_close.append(command)
        with_close.append(("Z",))
        a = rasterize_path(parse_path(explicit), dimensions)
        b = rasterize_path(parse_path(with_close), dimensions)
        assert a == b


def test_fill_rule_is_nonzero_winding() -> None:
    dimensions = Dimensions(20, 20)
    star = scaled([(10, 1), (15.3, 17.3), (1.4, 6.7), (18.6, 6.7), (4.7, 17.3)])
    assert (10, 10) in pixels(rasterize_path(closed(star), dimensions))  # even-odd: hole
    outer = [(1, 1), (19, 1), (19, 19), (1, 19)]
    inner = [(6, 6), (14, 6), (14, 14), (6, 14)]

    def contour(vertices: list[Vertex]) -> list[tuple[Any, ...]]:
        return [("M", *vertices[0]), *[("L", *v) for v in vertices[1:]], ("Z",)]

    same = parse_path([*contour(scaled(outer)), *contour(scaled(inner))])
    hole = parse_path([*contour(scaled(outer)), *contour(scaled(inner)[::-1])])
    rect_outer = pixels(rasterize_rect(Box(1, 1, 19, 19), dimensions))
    rect_inner = pixels(rasterize_rect(Box(6, 6, 14, 14), dimensions))
    assert pixels(rasterize_path(same, dimensions)) == rect_outer
    assert pixels(rasterize_path(hole, dimensions)) == rect_outer - rect_inner


def test_partly_off_canvas_paths_are_clipped_without_wraparound() -> None:
    dimensions = Dimensions(8, 8)
    path = closed([(x * U, y * U) for x, y in [(-5, -3), (6, -3), (6, 4), (-5, 4)]])
    mask = rasterize_path(path, dimensions)
    assert mask.box == Box(0, 0, 6, 4)
    assert pixels(mask) == pixels(rasterize_rect(Box(0, 0, 6, 4), dimensions))
    curve = parse_path([("M", -4 * U, 4 * U), ("Q", 4 * U, -12 * U, 12 * U, 4 * U), ("Z",)])
    clipped = rasterize_path(curve, dimensions)
    assert clipped.box == Box(0, 0, 8, 4)
    assert all(0 <= x < 8 and 0 <= y < 8 for x, y in pixels(clipped))
    assert clipped.count > 0


def test_wholly_off_canvas_paths_are_empty_without_drawing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_: object) -> bytes:
        raise AssertionError("the backend must not draw an empty box")

    monkeypatch.setattr(paths_module, "_coverage", refuse)
    for vertices in ([(-9, -9), (-1, -9), (-1, -1)], [(20, 0), (30, 0), (30, 5)]):
        path = closed([(x * U, y * U) for x, y in vertices])
        assert rasterize_path(path, Dimensions(8, 8)).is_empty


def test_far_away_coordinates_cost_nothing_and_still_clip() -> None:
    edge = 1_048_576 * U
    path = closed([(-edge, -edge), (edge, -edge), (edge, edge), (-edge, edge)])
    dimensions = Dimensions(32, 16)
    assert pixels(rasterize_path(path, dimensions)) == pixels(
        rasterize_rect(Box(0, 0, 32, 16), dimensions)
    )


@pytest.mark.parametrize(
    "commands",
    [
        [("M", 1 * U, 1 * U), ("L", 6 * U + 77, 5 * U + 3), ("Z",)],  # back and forth
        [("M", 300, 300), ("L", 300, 300)],  # one point inside a pixel
        [("M", 1 * U, 1 * U), ("L", 4 * U, 4 * U), ("L", 7 * U, 7 * U), ("Z",)],  # collinear
    ],
)
def test_degenerate_paths_of_zero_area_draw_nothing(commands: list[tuple[Any, ...]]) -> None:
    mask = rasterize_path(parse_path(commands), Dimensions(8, 8))
    assert mask.is_empty


def test_flat_paths_on_pixel_edges_have_no_box() -> None:
    path = parse_path([("M", 0, 2 * U), ("L", 6 * U, 2 * U)])
    assert path_mask_box(path, Dimensions(8, 8)) is None
    assert rasterize_path(path, Dimensions(8, 8)).is_empty


def test_tested_backend_threshold_on_thin_slivers() -> None:
    """Characterisation of ``aggdraw-v1`` (1.4.1): coverage >= 128 decides the pixel.

    AggDraw grows the outline by about 1/4 px: a 1/4-px sliver covers 127/255 of a
    row (out) and a 1/2-px sliver 190/255 (in). The integer polygon has no such rule.
    """
    dimensions = Dimensions(8, 8)
    quarter = closed([(0, 2 * U), (8 * U, 2 * U), (8 * U, 2 * U + 64), (0, 2 * U + 64)])
    half = closed([(0, 2 * U), (8 * U, 2 * U), (8 * U, 2 * U + 128), (0, 2 * U + 128)])
    assert rasterize_path(quarter, dimensions).is_empty
    assert pixels(rasterize_path(half, dimensions)) == {(x, 2) for x in range(8)}
    assert COVERAGE_THRESHOLD == 128


@settings(max_examples=30, deadline=None)
@given(st.integers(-3, 3), st.integers(-3, 3))
def test_whole_pixel_translations_translate_the_mask(dx: int, dy: int) -> None:
    dimensions = Dimensions(24, 24)
    commands: list[tuple[Any, ...]] = [
        ("M", 6 * U + 37, 5 * U + 200),
        ("C", 4 * U, 18 * U, 19 * U, 2 * U, 16 * U, 15 * U),
    ]
    moved = [
        (op, *[v + (dx if i % 2 == 0 else dy) * U for i, v in enumerate(vals)])
        for op, *vals in commands
    ]
    original = pixels(rasterize_path(parse_path(commands), dimensions))
    shifted = pixels(rasterize_path(parse_path(moved), dimensions))
    assert shifted == {(x + dx, y + dy) for x, y in original}


def test_paths_inside_the_canvas_do_not_depend_on_its_size() -> None:
    for commands in SHAPES.values():
        path = parse_path(commands)
        small = pixels(rasterize_path(path, Dimensions(16, 16)))
        large = pixels(rasterize_path(path, Dimensions(64, 40)))
        assert small == large


def test_repeated_rasterisation_is_identical() -> None:
    path = parse_path(SHAPES["cubic"])
    first = rasterize_path(path, Dimensions(16, 16))
    assert all(rasterize_path(path, Dimensions(16, 16)) == first for _ in range(5))
    assert (
        first.to_array().tobytes() == rasterize_path(path, Dimensions(16, 16)).to_array().tobytes()
    )


# --- Engine limit of the backend ---------------------------------------------------------


def comb(teeth: int, size: int) -> FixedPath:
    """Zigzag of ``teeth`` full-height teeth: about ``2 * teeth * size`` cells."""
    step = size * U // teeth
    commands: list[tuple[Any, ...]] = [("M", 0, 0)]
    for i in range(teeth):
        commands += [("L", i * step + step // 2, size * U), ("L", (i + 1) * step, 0)]
    commands += [("L", size * U, size * U + U), ("L", 0, size * U + U), ("Z",)]
    return parse_path(commands)


def test_paths_that_could_overflow_the_cell_storage_are_rejected_before_drawing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_: object) -> bytes:
        raise AssertionError("the backend must not run")

    monkeypatch.setattr(paths_module, "_coverage", refuse)
    path = comb(600, 2048)
    assert path.cell_bound(path_buffer_box(Box(0, 0, 2048, 2048))) > MAX_PATH_CELLS
    with pytest.raises(BudgetExceeded) as raised:
        rasterize_path(path, Dimensions(2048, 2048))
    assert raised.value.context["resource"] == "path_cells"
    assert raised.value.context["limit"] == MAX_PATH_CELLS


def test_a_path_just_under_the_cell_bound_is_drawn_completely() -> None:
    """AGG drops cells past its storage silently; the bound keeps far below that."""
    dimensions = Dimensions(512, 512)
    path = comb(64, 512)
    assert path.cell_bound(path_buffer_box(Box(0, 0, 512, 512))) <= MAX_PATH_CELLS
    mask = rasterize_path(path, dimensions)
    # Each tooth is a triangle of base ``step`` and height 512: half of each column band.
    assert abs(mask.count - 512 * 512 // 2) <= 512 * 2 * 64 // 2
    for x in range(4, 512, 8):  # band centres just above the bottom are filled
        tooth = x * 64 // 512
        assert mask.contains(Point(tooth * 8 + 4, 508))


# --- Characterisation of AggDraw 1.4.1 outside the contract (ADR-023, section 4) --------
#
# The only pixel promise is that a pixel whose square is inside a single simple subpath
# is in the mask. These counterexamples record what 1.4.1 does elsewhere; a new tested
# version must re-run them and update ADR-023 if any outcome changes.


def box_contour(x0: int, y0: int, x1: int, y1: int, *, clockwise: bool) -> list[tuple[Any, ...]]:
    """Rectangle in pixels; clockwise in screen coordinates (y down)."""
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if not clockwise:
        corners.reverse()
    head, *rest = [(x * U, y * U) for x, y in corners]
    return [("M", *head), *[("L", *corner) for corner in rest], ("Z",)]


def test_case_a_one_pixel_wall_between_two_holes_is_out() -> None:
    commands = [
        *box_contour(0, 0, 7, 3, clockwise=True),
        *box_contour(1, 1, 3, 2, clockwise=False),
        *box_contour(4, 1, 6, 2, clockwise=False),
    ]
    dimensions = Dimensions(7, 3)
    wall = (3, 1)  # its square lies fully inside the outline (between the holes)
    assert all(
        inside_convex(hull(square_corners(0, 0) + square_corners(6, 2)), c)
        for c in square_corners(*wall)
    )
    got = pixels(rasterize_path(parse_path(commands), dimensions))
    assert wall not in got  # observed on 1.4.1: coverage 127, below the threshold
    assert {(0, 0), (6, 2), (3, 0), (3, 2)} <= got  # the outer frame is filled


def test_case_b_winding_minus_one_strip_through_a_shared_vertex_is_out() -> None:
    points = [(1, 3), (7, 3), (7, 9), (1, 9), (1, 3), (1, 2), (7, 2), (7, 1), (1, 1)]
    head, *rest = [(x * U, y * U) for x, y in points]
    path = parse_path([("M", *head), *[("L", *point) for point in rest], ("Z",)])
    got = pixels(rasterize_path(path, Dimensions(8, 10)))
    strip = {(x, 1) for x in range(1, 7)}  # winding -1, every square fully inside
    assert strip.isdisjoint(got)  # observed on 1.4.1: the whole strip disappears
    assert {(x, y) for x in range(1, 7) for y in range(3, 9)} <= got  # the big loop stays


def test_case_c_stacked_slivers_let_in_a_pixel_far_from_the_outline() -> None:
    sliver_points: list[Vertex] = [(3453, 2944), (2941, 2943), (2941, 2945)]
    sliver = [("M", *sliver_points[0]), *[("L", *v) for v in sliver_points[1:]], ("Z",)]
    square = box_contour(20, 11, 21, 12, clockwise=True)
    probe = (14, 11)
    grown = square_corners(*probe, U // 2)
    assert separated(grown, hull(sliver_points))  # no 1/2-pixel contact with the outline
    assert separated(grown, square_corners(20, 11))
    dimensions = Dimensions(24, 24)
    one = pixels(rasterize_path(parse_path([*sliver, *square]), dimensions))
    three = pixels(rasterize_path(parse_path([*sliver * 3, *square]), dimensions))
    assert probe not in one
    assert probe in three  # observed on 1.4.1: coverage accumulates with winding


def test_case_d_four_stacked_eighth_pixel_strips_fill_two_rows() -> None:
    def strip() -> list[tuple[Any, ...]]:
        y0, y1 = 2 * U - U // 16, 2 * U + U // 16  # 1/8 px across the edge y = 2
        return [("M", U, y0), ("L", 7 * U, y0), ("L", 7 * U, y1), ("L", U, y1), ("Z",)]

    dimensions = Dimensions(8, 5)
    assert rasterize_path(parse_path(strip()), dimensions).is_empty
    four = pixels(rasterize_path(parse_path(strip() * 4), dimensions))
    assert four == {(x, y) for x in range(1, 7) for y in (1, 2)}  # observed on 1.4.1


def test_the_box_cut_is_not_local() -> None:
    """The mask is coverage >= 128 cut to the box of every point (a property of the
    whole path): a far subpath widens the box and lets in threshold pixels of the
    grown outline next to another subpath. The cut, not the backend, keeps them out.
    """
    saw: list[tuple[Any, ...]] = [("M", 9 * U, 10 * U)]
    for k in range(8):
        saw += [
            ("L", 13 * U, 10 * U + (2 * k + 1) * 32),
            ("L", 12 * U + 128, 10 * U + (2 * k + 2) * 32),
        ]
    saw += [("L", 9 * U, 12 * U), ("Z",)]
    far = [("M", 20 * U, 20 * U), ("L", 21 * U, 20 * U), ("L", 21 * U, 21 * U), ("Z",)]
    dimensions = Dimensions(24, 24)
    alone = rasterize_path(parse_path(saw), dimensions)
    together = pixels(rasterize_path(parse_path([*saw, *far]), dimensions))
    assert alone.box == Box(9, 10, 13, 12)
    gained = {pixel for pixel in together - pixels(alone) if pixel[0] < 16}
    assert gained == {(13, 10), (13, 11)}  # outside the saw's own box: cut when alone
