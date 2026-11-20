"""Integer source-over composition of layers and groups (MOANA-009, ADR-017)."""

from __future__ import annotations

import tracemalloc

import numpy as np
import numpy.typing as npt
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moana.core.coordinates import Box, Dimensions, Point
from moana.core.errors import BudgetExceeded, ValidationError
from moana.core.limits import GeometryLimits
from moana.geometry import Mask, rasterize_ellipse, rasterize_pixel, rasterize_rect
from moana.layers import (
    COMPOSITE_TEMP_BYTES_PER_PIXEL,
    DeferredMask,
    Fill,
    Group,
    Layer,
    LayerTree,
    compose,
    composition_cost,
    tile_pixels,
)
from moana.layers import composite as composite_module
from moana.palette import Rgba

LIMITS = DEFAULT_RENDER_LIMITS
RGBA = tuple[int, int, int, int]


# --- Independent scalar oracle written from MOANA.md section 11 ------------------


def _round_half_up(n: int, d: int) -> int:
    return (2 * n + d) // (2 * d)


def _over(dst: RGBA, src: RGBA, opacity: int) -> RGBA:
    sa = _round_half_up(src[3] * opacity, 255)
    da = dst[3]
    total = sa * 255 + da * (255 - sa)
    if total == 0:
        return (0, 0, 0, 0)
    alpha = _round_half_up(total, 255)
    if alpha == 0:
        return (0, 0, 0, 0)
    channels = tuple(
        _round_half_up(src[c] * sa * 255 + dst[c] * da * (255 - sa), total) for c in range(3)
    )
    return (channels[0], channels[1], channels[2], alpha)


Grid = dict[tuple[int, int], RGBA]


def _oracle_nodes(nodes: tuple[Layer | Group, ...], dims: Dimensions) -> Grid:
    clear: RGBA = (0, 0, 0, 0)
    target: Grid = {(x, y): clear for x in range(dims.width) for y in range(dims.height)}
    for node in nodes:
        if not node.visible:
            continue
        if isinstance(node, Group):
            buffer = _oracle_nodes(node.children, dims)
        else:
            buffer = {key: clear for key in target}
            for fill in node.fills:
                color = fill.color.as_tuple()
                assert isinstance(fill.mask, Mask)  # the oracle uses eager masks
                for point in fill.mask.points():
                    key = (point.x, point.y)
                    buffer[key] = _over(buffer[key], color, 255)
        for key in target:
            target[key] = _over(target[key], buffer[key], node.opacity)
    return target


def _pixels(array: npt.NDArray[np.uint8], dims: Dimensions) -> Grid:
    grid: Grid = {}
    for y in range(dims.height):
        for x in range(dims.width):
            r, g, b, a = (int(value) for value in array[y, x])
            grid[(x, y)] = (r, g, b, a)
    return grid


def _render(tree: LayerTree) -> Grid:
    return _pixels(compose(tree, limits=LIMITS).to_array(), tree.dimensions)


def _rect(box: Box, dims: Dimensions, color: RGBA) -> Fill:
    return Fill(rasterize_rect(box, dims), Rgba(*color))


D4 = Dimensions(4, 2)


# --- AC1: semitransparent fixture against a hand computation -------------------------


def test_ac1_semitransparent_fixture_matches_hand_computation() -> None:
    base = Layer("base", "Base", (_rect(Box(0, 0, 4, 2), D4, (200, 100, 50, 255)),))
    top = Layer("top", "Top", (_rect(Box(1, 0, 3, 2), D4, (0, 0, 255, 128)),), opacity=200)
    tree = LayerTree(D4, (base, Group("g", "G", (top,), opacity=128)))
    # Layer buffer: blue a=128 (sa=128, D=32640, a=128, B=255).
    # Into the group at opacity 200: sa=round(128*200/255)=round(100.39)=100, a=100.
    # Onto the base at 128: sa=round(100*128/255)=round(50.20)=50, D=65025, a=255;
    # R=round(200*255*205/65025)=round(160.78)=161, G=round(80.39)=80,
    # B=round((255*50*255+50*255*205)/65025)=round(90.19)=90.
    grid = _render(tree)
    assert grid[(1, 0)] == grid[(2, 1)] == (161, 80, 90, 255)
    assert grid[(0, 0)] == grid[(3, 1)] == (200, 100, 50, 255)


def test_semitransparent_over_transparent_keeps_straight_colour() -> None:
    layer = Layer("l", "L", (_rect(Box(0, 0, 1, 1), D4, (10, 20, 30, 77)),))
    assert _render(LayerTree(D4, (layer,)))[(0, 0)] == (10, 20, 30, 77)


fills_strategy = st.lists(
    st.tuples(
        st.integers(0, 5),
        st.integers(0, 4),
        st.integers(1, 3),
        st.integers(1, 3),
        st.tuples(
            *(st.integers(0, 255) for _ in range(3)), st.sampled_from([0, 1, 127, 128, 254, 255])
        ),
    ),
    max_size=3,
)
opacities = st.sampled_from([0, 1, 64, 127, 128, 254, 255])


@settings(max_examples=60, deadline=None)
@given(
    first=fills_strategy,
    second=fills_strategy,
    third=fills_strategy,
    opacity_a=opacities,
    opacity_b=opacities,
    group_opacity=opacities,
    visible=st.booleans(),
)
def test_ac1_random_trees_match_the_scalar_oracle(
    first: list[tuple[int, int, int, int, RGBA]],
    second: list[tuple[int, int, int, int, RGBA]],
    third: list[tuple[int, int, int, int, RGBA]],
    opacity_a: int,
    opacity_b: int,
    group_opacity: int,
    visible: bool,
) -> None:
    dims = Dimensions(6, 5)

    def fills(specs: list[tuple[int, int, int, int, RGBA]]) -> tuple[Fill, ...]:
        return tuple(_rect(Box(x, y, x + w, y + h), dims, color) for x, y, w, h, color in specs)

    tree = LayerTree(
        dims,
        (
            Layer("a", "A", fills(first), opacity=opacity_a),
            Group(
                "g",
                "G",
                (
                    Layer("b", "B", fills(second), opacity=opacity_b),
                    Layer("c", "C", fills(third), visible=visible),
                ),
                opacity=group_opacity,
            ),
        ),
    )
    assert _render(tree) == _oracle_nodes(tree.children, dims)


# --- AC2: order, visibility and group opacity applied once ------------------------------


RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)


def test_ac2_order_decides_which_colour_is_on_top() -> None:
    red = Layer("red", "Red", (_rect(Box(0, 0, 2, 1), D4, RED),))
    blue = Layer("blue", "Blue", (_rect(Box(1, 0, 3, 1), D4, BLUE),))
    red_below = _render(LayerTree(D4, (red, blue)))
    blue_below = _render(LayerTree(D4, (blue, red)))
    assert (red_below[(1, 0)], blue_below[(1, 0)]) == (BLUE, RED)
    assert {k for k in red_below if red_below[k] != blue_below[k]} == {(1, 0)}


def test_ac2_hiding_a_layer_removes_exactly_its_pixels() -> None:
    red = Layer("red", "Red", (_rect(Box(0, 0, 2, 1), D4, RED),))
    blue = Layer("blue", "Blue", (_rect(Box(1, 0, 3, 1), D4, BLUE),), visible=False)
    grid = _render(LayerTree(D4, (red, blue)))
    assert grid[(1, 0)] == RED and grid[(2, 0)] == (0, 0, 0, 0)


def test_ac2_group_opacity_is_applied_once_to_the_group_result() -> None:
    # Two opaque children overlap at (1, 0). Group at 128: the overlap shows only the
    # top child at sa=128 (a=128, B=255). Per-child opacity would instead blend red
    # at 128 under blue at 128: a = round((128*255 + 128*127)/255) = 192, mixed RGB.
    red = Layer("red", "Red", (_rect(Box(0, 0, 2, 1), D4, RED),))
    blue = Layer("blue", "Blue", (_rect(Box(1, 0, 3, 1), D4, BLUE),))
    grid = _render(LayerTree(D4, (Group("g", "G", (red, blue), opacity=128),)))
    assert grid[(1, 0)] == (0, 0, 255, 128)
    per_child = _over(_over((0, 0, 0, 0), RED, 128), BLUE, 128)
    assert per_child == (85, 0, 170, 192)
    assert grid[(1, 0)] != per_child


# --- T1: alpha 0/1/127/255 and transparent normalisation ---------------------------


@pytest.mark.parametrize(
    ("src", "dst", "expected"),
    [
        # alpha 0 leaves the destination untouched, even with residual RGB.
        ((90, 80, 70, 0), (10, 20, 30, 200), (10, 20, 30, 200)),
        # alpha 1 over opaque white: sa=1, D=65025; R=round((0+255*255*254)/65025)=254.
        ((0, 0, 0, 1), (255, 255, 255, 255), (254, 254, 254, 255)),
        # alpha 127 over opaque black: R=round(200*127*255/65025)=round(99.61)=100.
        ((200, 0, 0, 127), (0, 0, 0, 255), (100, 0, 0, 255)),
        # alpha 255 replaces.
        ((1, 2, 3, 255), (200, 200, 200, 99), (1, 2, 3, 255)),
        # alpha 127 over alpha 127: D=127*255+127*128=48641, a=round(190.75)=191.
        ((255, 0, 0, 127), (0, 0, 255, 127), (170, 0, 85, 191)),
    ],
)
def test_t1_alpha_cases_match_hand_values(src: RGBA, dst: RGBA, expected: RGBA) -> None:
    assert _over(dst, src, 255) == expected
    below = Layer("dst", "Dst", (_rect(Box(0, 0, 1, 1), D4, dst),))
    above = Layer("src", "Src", (_rect(Box(0, 0, 1, 1), D4, src),))
    assert _render(LayerTree(D4, (below, above)))[(0, 0)] == expected


def test_t1_transparent_result_is_normalised_to_zero() -> None:
    residual = Layer("r", "R", (_rect(Box(0, 0, 4, 2), D4, (99, 88, 77, 0)),))
    faded = Layer("f", "F", (_rect(Box(0, 0, 4, 2), D4, (99, 88, 77, 255)),), opacity=0)
    tiny = Layer("t", "T", (_rect(Box(0, 0, 4, 2), D4, (99, 88, 77, 1)),), opacity=127)
    for tree in (
        LayerTree(D4, (residual,)),
        LayerTree(D4, (faded,)),
        LayerTree(D4, (tiny,)),  # sa = round(127/255) = 0
    ):
        array = compose(tree, limits=LIMITS).to_array()
        assert not array.any()


# --- T2: nesting, depth limit, hidden nodes, locked, budget ---------------------------


def _nest(depth: int, leaf: Layer) -> Group:
    node: Layer | Group = leaf
    for level in range(depth, 0, -1):
        node = Group(f"g{level}", f"G{level}", (node,))
    assert isinstance(node, Group)
    return node


def test_t2_nested_groups_compose_like_the_oracle() -> None:
    dims = Dimensions(3, 3)
    inner = Group(
        "inner",
        "Inner",
        (
            Layer("x", "X", (_rect(Box(0, 0, 2, 2), dims, (255, 0, 0, 200)),)),
            Layer("y", "Y", (_rect(Box(1, 1, 3, 3), dims, (0, 255, 0, 255)),), opacity=100),
        ),
        opacity=180,
    )
    outer = Group("outer", "Outer", (inner,), opacity=90)
    base = Layer("base", "Base", (_rect(Box(0, 0, 3, 3), dims, (0, 0, 255, 255)),))
    tree = LayerTree(dims, (base, outer))
    assert _render(tree) == _oracle_nodes(tree.children, dims)


def test_t2_maximum_depth_composes_and_one_more_is_rejected() -> None:
    leaf = Layer("leaf", "Leaf", (_rect(Box(0, 0, 1, 1), D4, RED),))
    deepest = LayerTree(D4, (_nest(16, leaf),))
    assert _render(deepest)[(0, 0)] == RED
    assert composition_cost(deepest).group_depth == 16
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(D4, (_nest(17, leaf),))
    assert excinfo.value.context["reason"] == "too_deep"


def test_t2_hidden_group_skips_its_subtree_and_costs_nothing() -> None:
    leaf = Layer("leaf", "Leaf", (_rect(Box(0, 0, 4, 2), D4, RED),))
    hidden = LayerTree(D4, (Group("g", "G", (leaf,), visible=False),))
    assert not compose(hidden, limits=LIMITS).to_array().any()
    cost = composition_cost(hidden)
    # Counts include hidden nodes (as budget-v1 counts document layers); work does not.
    assert (cost.layers, cost.operations, cost.group_depth) == (2, 1, 0)
    assert cost.pixel_visits == 3 * D4.area  # root: clear, normalise, copy


def test_t2_locked_does_not_change_the_render() -> None:
    fill = _rect(Box(0, 0, 3, 1), D4, (12, 34, 56, 200))
    free = LayerTree(D4, (Layer("l", "L", (fill,)),))
    locked = LayerTree(
        D4, (Group("g", "G", (Layer("l", "L", (fill,), locked=True),), locked=True),)
    )
    assert compose(free, limits=LIMITS) == compose(locked, limits=LIMITS)


def test_t2_budget_is_checked_before_any_buffer() -> None:
    dims = Dimensions(256, 256)
    tree = LayerTree(dims, (Layer("l", "L", (_rect(Box(0, 0, 256, 256), dims, RED),)),))
    cost = composition_cost(tree)
    tight = RenderLimits(max_buffer_bytes=cost.buffer_bytes - 1)
    tracemalloc.start()
    try:
        with pytest.raises(BudgetExceeded) as excinfo:
            compose(tree, limits=tight)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert excinfo.value.context["resource"] == "buffer_bytes"
    assert peak < 16 * 1024  # no canvas-sized buffer (64 KiB of mask) was allocated
    assert compose(tree, limits=RenderLimits(max_buffer_bytes=cost.buffer_bytes))


@pytest.mark.parametrize(
    ("limits", "resource"),
    [
        (RenderLimits(max_layers=1), "layers"),
        (RenderLimits(max_operations=1), "operations"),
        (RenderLimits(max_pixel_visits=10), "pixel_visits"),
        (RenderLimits(max_frame_pixels=7), "frame_pixels"),
    ],
)
def test_t2_other_budgets_are_enforced(limits: RenderLimits, resource: str) -> None:
    layers = tuple(Layer(f"l{i}", "L", (_rect(Box(0, 0, 1, 1), D4, RED),)) for i in range(2))
    with pytest.raises(BudgetExceeded) as excinfo:
        compose(LayerTree(D4, layers), limits=limits)
    assert resource in {detail.context["resource"] for detail in excinfo.value.details}


def test_peak_memory_stays_within_the_cost_estimate() -> None:
    dims = Dimensions(128, 96)
    leaf = Layer(
        "leaf",
        "Leaf",
        (
            _rect(Box(0, 0, 128, 96), dims, (10, 20, 30, 128)),
            _rect(Box(5, 5, 100, 90), dims, (200, 20, 30, 255)),
        ),
    )
    tree = LayerTree(
        dims, (Layer("base", "Base", (_rect(Box(0, 0, 128, 96), dims, RED),)), _nest(3, leaf))
    )
    cost = composition_cost(tree)
    tracemalloc.start()
    try:
        compose(tree, limits=LIMITS)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= cost.buffer_bytes


def test_empty_tree_and_empty_masks_give_a_transparent_canvas() -> None:
    assert not compose(LayerTree(D4, ()), limits=LIMITS).to_array().any()
    off = Fill(rasterize_pixel(Point(9, 9), D4), Rgba(*RED))
    assert off.mask == Mask.empty()
    assert not compose(LayerTree(D4, (Layer("l", "L", (off,)),)), limits=LIMITS).to_array().any()


class _SpyDeadline(Deadline):
    __slots__ = ("stages",)

    def __init__(self) -> None:
        super().__init__(60_000)
        self.stages: list[str] = []

    def checkpoint(self, stage: str) -> None:
        self.stages.append(stage)
        super().checkpoint(stage)


def test_deadline_is_checked_per_visible_node_and_fill() -> None:
    fill = _rect(Box(0, 0, 1, 1), D4, RED)
    tree = LayerTree(
        D4,
        (
            Layer("a", "A", (fill, fill)),
            Layer("b", "B", (fill,), visible=False),
            Group("g", "G", (Layer("c", "C", (fill,)),)),
        ),
    )
    spy = _SpyDeadline()
    compose(tree, limits=LIMITS, deadline=spy)
    assert spy.stages == [
        "compose_node",  # a
        "compose_fill",
        "compose_fill",
        "compose_node",  # g
        "compose_node",  # c
        "compose_fill",
    ]


def test_expired_deadline_stops_composition() -> None:
    now = [0.0]
    deadline = Deadline(1, clock=lambda: now[0])
    now[0] = 1.0
    with pytest.raises(BudgetExceeded):
        compose(LayerTree(D4, (Layer("a", "A"),)), limits=LIMITS, deadline=deadline)


def test_compose_requires_render_limits() -> None:
    with pytest.raises(TypeError):
        compose(LayerTree(D4, ()), limits=None)  # type: ignore[arg-type]  # deliberate misuse
    with pytest.raises(TypeError):
        composition_cost("tree")  # type: ignore[arg-type]  # deliberate misuse


def test_geometry_limits_are_checked_before_composing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(composite_module, "_compose_into", lambda *args: calls.append(1))
    limits = RenderLimits(geometry=GeometryLimits(max_dimension=2))
    with pytest.raises(BudgetExceeded) as excinfo:
        compose(LayerTree(D4, (Layer("a", "A"),)), limits=limits)
    assert excinfo.value.context["resource"] == "canvas_dimension"
    assert calls == []


def test_multi_tile_canvas_with_off_canvas_shapes_matches_the_oracle() -> None:
    # 70 x 130: A // 4 = 2275 pixels per tile, i.e. 64 rows x 35 columns, so the
    # canvas splits into 3 x 2 tiles; shapes start above/left of the canvas, cross tile
    # borders and end in the last partial tile.
    dims = Dimensions(70, 130)
    assert tile_pixels(dims) == 2275
    layer = Layer(
        "shapes",
        "Shapes",
        (
            Fill(rasterize_rect(Box(-5, -7, 66, 70), dims), Rgba(200, 30, 10, 180)),
            Fill(rasterize_ellipse(Box(-20, 40, 90, 140), dims), Rgba(10, 200, 30, 120)),
            Fill(rasterize_rect(Box(60, 120, 80, 140), dims), Rgba(0, 0, 255, 255)),
        ),
    )
    group = Group(
        "g",
        "G",
        (Layer("over", "Over", (_rect(Box(30, 60, 70, 70), dims, (255, 255, 0, 90)),)),),
        opacity=200,
    )
    tree = LayerTree(dims, (layer, group))
    assert _render(tree) == _oracle_nodes(tree.children, dims)


def test_one_by_one_canvas() -> None:
    dims = Dimensions(1, 1)
    tree = LayerTree(
        dims,
        (
            Layer("a", "A", (_rect(Box(0, 0, 1, 1), dims, (100, 50, 25, 200)),), opacity=128),
            Layer("b", "B", (_rect(Box(-3, -3, 4, 4), dims, (0, 0, 255, 60)),)),
        ),
    )
    assert _render(tree) == _oracle_nodes(tree.children, dims)


@pytest.mark.parametrize("dims", [Dimensions(512, 64), Dimensions(64, 512), Dimensions(4, 300)])
def test_kernel_temporaries_stay_within_the_declared_tile_bound(dims: Dimensions) -> None:
    pixels = tile_pixels(dims)
    parent = np.full((dims.height, dims.width, 4), 90, dtype=np.uint8)
    child = np.full((dims.height, dims.width, 4), 200, dtype=np.uint8)
    fill = _rect(Box(0, 0, dims.width, dims.height), dims, (1, 2, 3, 128))
    tracemalloc.start()
    try:
        composite_module._composite(parent, child, 128, pixels)
        _, composite_peak = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        composite_module._paint(parent, fill, pixels)
        _, paint_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    bound = COMPOSITE_TEMP_BYTES_PER_PIXEL * pixels
    assert composite_peak <= bound
    assert paint_peak <= bound + dims.area  # plus the mask copy, counted separately


def test_schema_documents_stay_within_the_budget_working_set() -> None:
    # Without groups: (3 * 4A + A + tile temporaries) <= budget-v2's 4A + 4A + 32A.
    for dims in (Dimensions(4, 4), Dimensions(128, 63), Dimensions(500, 7), Dimensions(2048, 64)):
        tree = LayerTree(dims, (Layer("l", "L"),))
        assert composition_cost(tree).buffer_bytes <= 40 * dims.area


# --- Deferred masks (ADR-018) -------------------------------------------------------


def _deferred(box: Box, dims: Dimensions, built: list[Box]) -> DeferredMask:
    def build() -> Mask:
        built.append(box)
        return rasterize_rect(box, dims)

    return DeferredMask(box.clip_to(dims), build)


def test_deferred_masks_compose_like_eager_masks_and_build_lazily() -> None:
    dims = Dimensions(6, 5)
    boxes = (Box(0, 0, 4, 3), Box(2, 1, 6, 5), Box(1, 2, 3, 4))
    colors = ((200, 10, 10, 255), (10, 200, 10, 128), (10, 10, 200, 77))
    built: list[Box] = []
    deferred = tuple(
        Fill(_deferred(box, dims, built), Rgba(*color))
        for box, color in zip(boxes, colors, strict=True)
    )
    eager = tuple(_rect(box, dims, color) for box, color in zip(boxes, colors, strict=True))
    lazy_tree = LayerTree(dims, (Layer("l", "L", deferred, opacity=200),))
    assert built == []  # validation and costing never build a mask
    eager_cost = composition_cost(LayerTree(dims, (Layer("l", "L", eager, opacity=200),)))
    lazy_cost = composition_cost(lazy_tree)
    assert lazy_cost.pixel_visits == eager_cost.pixel_visits
    # the built mask lives inside compose, next to its copy: one more A of bytes
    assert lazy_cost.buffer_bytes == eager_cost.buffer_bytes + dims.area
    assert _render(lazy_tree) == _render(LayerTree(dims, (Layer("l", "L", eager, opacity=200),)))
    assert built == list(boxes)  # once each, in array order


def test_hidden_or_empty_deferred_masks_are_never_built() -> None:
    dims = Dimensions(4, 4)
    built: list[Box] = []
    outside = DeferredMask(None, lambda: pytest.fail("built a mask with no box"))
    hidden = Layer("h", "H", (Fill(_deferred(Box(0, 0, 2, 2), dims, built), Rgba(1, 2, 3, 255)),))
    tree = LayerTree(
        dims,
        (
            Layer("h", "H", hidden.fills, visible=False),
            Group("g", "G", (Layer("in", "In", (Fill(outside, Rgba(1, 2, 3, 255)),)),)),
        ),
    )
    assert _render(tree)[(0, 0)] == (0, 0, 0, 0)
    assert built == []


def test_deferred_mask_must_stay_inside_its_declared_box() -> None:
    dims = Dimensions(4, 4)
    wrong = DeferredMask(Box(0, 0, 1, 1), lambda: rasterize_rect(Box(0, 0, 2, 2), dims))
    tree = LayerTree(dims, (Layer("l", "L", (Fill(wrong, Rgba(1, 2, 3, 255)),)),))
    with pytest.raises(RuntimeError, match="declared box"):  # caller bug, not user input
        compose(tree, limits=LIMITS)
    empty = DeferredMask(Box(0, 0, 1, 1), Mask.empty)
    LayerTree(dims, (Layer("l", "L", (Fill(empty, Rgba(1, 2, 3, 255)),)),))
    assert _render(LayerTree(dims, (Layer("l", "L", (Fill(empty, Rgba(1, 2, 3, 255)),)),)))[
        (0, 0)
    ] == (0, 0, 0, 0)
    not_a_mask = DeferredMask(Box(0, 0, 1, 1), lambda: "mask")  # type: ignore[arg-type,return-value]  # misuse
    with pytest.raises(TypeError):
        compose(
            LayerTree(dims, (Layer("l", "L", (Fill(not_a_mask, Rgba(1, 2, 3, 255)),)),)),
            limits=LIMITS,
        )


def test_deferred_mask_fields_and_identity() -> None:
    with pytest.raises(TypeError):
        DeferredMask((0, 0, 1, 1), Mask.empty)  # type: ignore[arg-type]  # not a Box
    with pytest.raises(TypeError):
        DeferredMask(None, "build")  # type: ignore[arg-type]  # not callable
    first = DeferredMask(None, Mask.empty)
    assert first == first and first != DeferredMask(None, Mask.empty)
    outside = DeferredMask(Box(0, 0, 9, 9), Mask.empty)
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(Dimensions(4, 4), (Layer("l", "L", (Fill(outside, Rgba(0, 0, 0, 255)),)),))
    assert excinfo.value.context["reason"] == "outside_canvas"
