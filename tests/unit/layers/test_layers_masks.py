"""Semantic layer masks in the compositor (MOANA-013, ADR-022).

AC1: a masked layer changes no pixel outside its mask. T2: mask nodes outside the
canvas and groups whose content is transformed (masks stay in canvas coordinates).
The scalar oracle is written from MOANART.md section 11 and works on Python sets.
"""

from __future__ import annotations

import tracemalloc
from collections.abc import Iterable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moanart.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moanart.core.coordinates import Box, Dimensions, Point
from moanart.core.errors import BudgetExceeded, ValidationError
from moanart.core.limits import MAX_MASK_DEPTH, MAX_MASK_OPERANDS
from moanart.geometry import (
    Mask,
    MaskOperator,
    Transform,
    rasterize_ellipse,
    rasterize_rect,
    transform_mask,
)
from moanart.layers import (
    DeferredMask,
    Fill,
    Group,
    Layer,
    LayerTree,
    MaskCombination,
    MaskShape,
    compose,
    composition_cost,
    mask_cost,
    mask_leaves,
)
from moanart.layers.composite import MASK_NODE_VISITS, MaskCost
from moanart.palette import Rgba

LIMITS = DEFAULT_RENDER_LIMITS
RGBA = tuple[int, int, int, int]
Grid = dict[tuple[int, int], RGBA]
Pixels = frozenset[tuple[int, int]]
CLEAR: RGBA = (0, 0, 0, 0)
RED: RGBA = (255, 0, 0, 255)
BLUE_HALF: RGBA = (0, 0, 255, 128)
D8 = Dimensions(8, 8)


def _round_half_up(n: int, d: int) -> int:
    return (2 * n + d) // (2 * d)


def _over(dst: RGBA, src: RGBA, opacity: int) -> RGBA:
    sa = _round_half_up(src[3] * opacity, 255)
    total = sa * 255 + dst[3] * (255 - sa)
    if total == 0:
        return CLEAR
    channels = [
        _round_half_up(src[c] * sa * 255 + dst[c] * dst[3] * (255 - sa), total) for c in range(3)
    ]
    return (channels[0], channels[1], channels[2], _round_half_up(total, 255))


def _box_pixels(box: Box) -> Pixels:
    return frozenset((x, y) for x in range(box.x0, box.x1) for y in range(box.y0, box.y1))


def _oracle(
    dims: Dimensions, layers: Iterable[tuple[list[tuple[Pixels, RGBA]], Pixels | None, int]]
) -> Grid:
    """Layers as (fills, mask pixels or None, opacity), composited bottom to top."""
    target: Grid = {(x, y): CLEAR for x in range(dims.width) for y in range(dims.height)}
    for fills, mask, opacity in layers:
        buffer: Grid = dict.fromkeys(target, CLEAR)
        for pixels, color in fills:
            for key in pixels:
                if key in buffer:
                    buffer[key] = _over(buffer[key], color, 255)
        for key in target:
            source = buffer[key] if mask is None or key in mask else CLEAR
            target[key] = _over(target[key], source, opacity)
    return target


def _grid(tree: LayerTree) -> Grid:
    array = compose(tree, limits=LIMITS).to_array()
    dims = tree.dimensions
    return {
        (x, y): tuple(int(v) for v in array[y, x])  # type: ignore[misc]
        for y in range(dims.height)
        for x in range(dims.width)
    }


def _rect_fill(box: Box, color: RGBA, dims: Dimensions = D8) -> Fill:

    return Fill(rasterize_rect(box, dims), Rgba(*color))


def _shape(name: str, box: Box, dims: Dimensions = D8) -> MaskShape:
    return MaskShape(name, rasterize_rect(box, dims))


FULL = Box(0, 0, 8, 8)
LEFT = Box(1, 1, 4, 5)
RIGHT = Box(3, 2, 7, 6)


# --- AC1: nothing outside the mask changes -------------------------------------------


def test_ac1_masked_layer_changes_no_pixel_outside_its_mask() -> None:
    base = Layer("base", "Base", (_rect_fill(FULL, RED),))
    mask = MaskCombination("eyes", "union", (_shape("left", LEFT), _shape("right", RIGHT)))
    top = Layer(
        "top",
        "Top",
        (_rect_fill(FULL, BLUE_HALF), _rect_fill(Box(2, 2, 6, 6), (0, 255, 0, 200))),
        opacity=180,
        mask=mask,
    )
    before = _grid(LayerTree(D8, (base,)))
    after = _grid(LayerTree(D8, (base, top)))
    inside = _box_pixels(LEFT) | _box_pixels(RIGHT)
    for key, value in before.items():
        if key not in inside:
            assert after[key] == value, key
    assert any(after[key] != before[key] for key in inside)
    fills = [(_box_pixels(FULL), BLUE_HALF), (_box_pixels(Box(2, 2, 6, 6)), (0, 255, 0, 200))]
    expected = _oracle(D8, [([(_box_pixels(FULL), RED)], None, 255), (fills, inside, 180)])
    assert after == expected


def test_ac1_layer_opacity_is_applied_once_inside_the_mask() -> None:
    base = Layer("base", "Base", (_rect_fill(FULL, RED),))
    top = Layer("top", "Top", (_rect_fill(FULL, BLUE_HALF),), opacity=128, mask=_shape("m", LEFT))
    grid = _grid(LayerTree(D8, (base, top)))
    # Inside: blue a=128 at opacity 128 -> sa=round(64.25)=64, D=65025, a=255;
    # R=round(255*255*191/65025)=191, B=round(255*64*255/65025)=64.
    assert grid[(1, 1)] == (191, 0, 64, 255) == _over(RED, BLUE_HALF, 128)
    assert grid[(0, 0)] == RED


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        ("union", _box_pixels(LEFT) | _box_pixels(RIGHT)),
        ("intersect", _box_pixels(LEFT) & _box_pixels(RIGHT)),
        ("subtract", _box_pixels(LEFT) - _box_pixels(RIGHT)),
        ("xor", _box_pixels(LEFT) ^ _box_pixels(RIGHT)),
    ],
)
def test_each_operator_clips_the_layer_to_its_set(operator: MaskOperator, expected: Pixels) -> None:
    mask = MaskCombination("m", operator, (_shape("a", LEFT), _shape("b", RIGHT)))
    grid = _grid(LayerTree(D8, (Layer("l", "L", (_rect_fill(FULL, RED),), mask=mask),)))
    assert {key for key, value in grid.items() if value != CLEAR} == expected


def test_nested_combinations_and_shared_nodes() -> None:
    left, right = _shape("left", LEFT), _shape("right", RIGHT)
    eyes = MaskCombination("eyes", "union", (left, right))
    open_eyes = MaskCombination("open", "subtract", (eyes, _shape("lid", Box(0, 1, 8, 2))))
    both = MaskCombination("both", "intersect", (open_eyes, eyes))  # ``eyes`` is shared
    expected = (_box_pixels(LEFT) | _box_pixels(RIGHT)) - _box_pixels(Box(0, 1, 8, 2))
    layer = Layer("l", "L", (_rect_fill(FULL, RED),), mask=both)
    grid = _grid(LayerTree(D8, (layer,)))
    assert {key for key, value in grid.items() if value != CLEAR} == expected
    assert [leaf.id for leaf in mask_leaves(both)] == ["left", "right", "lid"]
    assert (both.depth, open_eyes.depth, eyes.depth, left.depth) == (4, 3, 2, 1)


masks_strategy = st.lists(
    st.tuples(st.integers(-2, 7), st.integers(-2, 7), st.integers(1, 5), st.integers(1, 5)),
    min_size=2,
    max_size=4,
)


@settings(max_examples=60, deadline=None)
@given(
    operator=st.sampled_from(["union", "intersect", "subtract", "xor"]),
    boxes=masks_strategy,
    opacity=st.integers(0, 255),
    alpha=st.integers(0, 255),
)
def test_ac1_random_masks_match_the_scalar_oracle(
    operator: MaskOperator, boxes: list[tuple[int, int, int, int]], opacity: int, alpha: int
) -> None:
    dims = Dimensions(6, 5)
    shapes = tuple(
        _shape(f"s{i}", Box(x, y, x + w, y + h), dims) for i, (x, y, w, h) in enumerate(boxes)
    )
    sets = [_box_pixels(Box(x, y, x + w, y + h)) for x, y, w, h in boxes]
    first, rest = sets[0], sets[1:]
    if operator == "union":
        expected = first.union(*rest)
    elif operator == "intersect":
        expected = first.intersection(*rest)
    elif operator == "subtract":
        expected = first.difference(*rest)
    else:
        parity: set[tuple[int, int]] = set()
        for pixels in sets:
            parity ^= pixels
        expected = frozenset(parity)
    color: RGBA = (30, 60, 90, alpha)
    base = Layer("base", "Base", (_rect_fill(Box(0, 0, 6, 5), (200, 100, 50, 255), dims),))
    top = Layer(
        "top",
        "Top",
        (_rect_fill(Box(0, 0, 6, 5), color, dims),),
        opacity=opacity,
        mask=MaskCombination("m", operator, shapes),
    )
    oracle = _oracle(
        dims,
        [
            ([(_box_pixels(Box(0, 0, 6, 5)), (200, 100, 50, 255))], None, 255),
            ([(_box_pixels(Box(0, 0, 6, 5)), color)], expected, opacity),
        ],
    )
    assert _grid(LayerTree(dims, (base, top))) == oracle


# --- T2: masks outside the canvas and transformed groups ------------------------------


def test_t2_mask_fully_outside_the_canvas_hides_the_layer() -> None:
    off = MaskShape("off", rasterize_rect(Box(20, 20, 30, 30), D8))  # clipped away: empty
    assert off.box is None
    base = Layer("base", "Base", (_rect_fill(FULL, RED),))
    hidden = Layer("top", "Top", (_rect_fill(FULL, BLUE_HALF),), mask=off)
    assert _grid(LayerTree(D8, (base, hidden))) == _grid(LayerTree(D8, (base,)))
    disjoint = MaskCombination("none", "intersect", (_shape("a", Box(0, 0, 2, 2)), off))
    layer = Layer("top", "Top", (_rect_fill(FULL, RED),), mask=disjoint)
    assert set(_grid(LayerTree(D8, (layer,))).values()) == {CLEAR}


def test_t2_mask_storage_beyond_the_canvas_is_rejected() -> None:
    big = Dimensions(32, 32)
    beyond = MaskShape("beyond", rasterize_rect(Box(4, 4, 20, 20), big))  # box past 8 x 8
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(D8, (Layer("l", "L", mask=MaskCombination("u", "union", (beyond, beyond))),))
    context = excinfo.value.context
    assert (context["reason"], context["node_id"], context["mask_id"]) == (
        "outside_canvas",
        "l",
        "beyond",
    )


def test_t2_transformed_group_content_is_clipped_by_a_canvas_mask() -> None:
    """A transformed group moves its children's geometry, never their canvas masks."""

    shape = rasterize_ellipse(Box(0, 0, 4, 3), D8)
    transform = Transform(pivot=Point(1, 1), mirror=True, rotation=90, offset=Point(3, 2))
    moved = transform_mask(shape, transform, D8)
    mask_box = Box(2, 2, 6, 5)
    layer = Layer("l", "L", (Fill(moved, Rgba(*RED)),), mask=_shape("window", mask_box))
    grid = _grid(LayerTree(D8, (Group("g", "G", (layer,), opacity=255),)))
    moved_pixels = frozenset((p.x, p.y) for p in moved.points())
    expected = moved_pixels & _box_pixels(mask_box)
    assert {key for key, value in grid.items() if value != CLEAR} == expected
    assert expected and expected != moved_pixels  # the mask really clips something
    # Moving the mask with the content would select other pixels: masks are not local.
    moved_window = transform_mask(rasterize_rect(mask_box, D8), transform, D8)
    local = moved_pixels & frozenset((p.x, p.y) for p in moved_window.points())
    assert local != expected


def test_t2_group_opacity_applies_once_over_masked_children() -> None:
    inner = Layer("l", "L", (_rect_fill(FULL, BLUE_HALF),), opacity=200, mask=_shape("m", LEFT))
    tree = LayerTree(
        D8, (Layer("base", "B", (_rect_fill(FULL, RED),)), Group("g", "G", (inner,), opacity=128))
    )
    grid = _grid(tree)
    in_group = _over(CLEAR, BLUE_HALF, 200)
    assert grid[(1, 1)] == _over(RED, in_group, 128)
    assert grid[(7, 7)] == RED


# --- Laziness, deadline, cost and budget ---------------------------------------------


def _counting(box: Box, dims: Dimensions, calls: list[str], name: str) -> DeferredMask:
    def build() -> Mask:
        calls.append(name)
        return rasterize_rect(box, dims)

    return DeferredMask(box.clip_to(dims), build)


def test_deferred_leaves_are_built_per_reference_and_only_when_visible() -> None:
    calls: list[str] = []
    a = MaskShape("a", _counting(LEFT, D8, calls, "a"))
    b = MaskShape("b", _counting(RIGHT, D8, calls, "b"))
    shared = MaskCombination("ab", "union", (a, b))
    twice = MaskCombination("twice", "xor", (shared, a))
    visible = Layer("v", "V", (_rect_fill(FULL, RED),), mask=twice)
    hidden = Layer("h", "H", (_rect_fill(FULL, RED),), mask=shared, visible=False)
    grid = _grid(LayerTree(D8, (visible, hidden)))
    assert calls == ["a", "b", "a"]  # expanded expression, operand order
    expected = (_box_pixels(LEFT) | _box_pixels(RIGHT)) ^ _box_pixels(LEFT)
    assert {key for key, value in grid.items() if value != CLEAR} == expected


class _SpyDeadline(Deadline):
    __slots__ = ("stages",)

    def __init__(self) -> None:
        super().__init__(60_000)
        self.stages: list[str] = []

    def checkpoint(self, stage: str) -> None:
        self.stages.append(stage)
        super().checkpoint(stage)


def test_deadline_is_checked_before_each_mask_node() -> None:
    mask = MaskCombination("m", "union", (_shape("a", LEFT), _shape("b", RIGHT)))
    spy = _SpyDeadline()
    compose(LayerTree(D8, (Layer("l", "L", (), mask=mask),)), limits=LIMITS, deadline=spy)
    assert spy.stages == ["compose_node", "compose_mask", "compose_mask", "compose_mask"]


def test_mask_cost_matches_hand_formula() -> None:
    dims = Dimensions(4, 4)
    a = MaskShape("a", rasterize_rect(Box(0, 0, 2, 2), dims))
    b = MaskShape("b", rasterize_rect(Box(2, 1, 4, 3), dims))
    union = MaskCombination("u", "union", (a, b))
    cost = mask_cost(union, dims)
    # Box (0,0)-(4,3): 12 px. Leaves cost the floor 1 each; the union costs
    # 1 + 2*12 + (1 + 4) + (1 + 4) = 35; peak 12 + 4.
    assert (cost.box, cost.pixel_visits, cost.buffer_bytes) == (Box(0, 0, 4, 3), 35, 16)
    nested = MaskCombination("n", "subtract", (union, a))
    cost = mask_cost(nested, dims)
    # Box of union (12 px): 1 + 2*12 + (35 + 12) + (1 + 4) = 77; peak 12 + 16.
    assert (cost.box, cost.pixel_visits, cost.buffer_bytes) == (Box(0, 0, 4, 3), 77, 28)
    tree = LayerTree(dims, (Layer("l", "L", (), mask=union),))
    plain = composition_cost(LayerTree(dims, (Layer("l", "L"),)))
    masked = composition_cost(tree)
    # + the mask, copying its 12 bits and clearing outside it (A = 16)
    assert masked.pixel_visits == plain.pixel_visits + 35 + 12 + 16
    with pytest.raises(TypeError):
        mask_cost(a.mask, dims)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        mask_cost(union, (4, 4))  # type: ignore[arg-type]


def _tower(leaf: MaskShape, operator: MaskOperator, width: int, levels: int) -> MaskCombination:
    """``levels`` combinations, each over ``width`` references to the level below."""
    node: MaskShape | MaskCombination = leaf
    for level in range(levels):
        node = MaskCombination(f"c{level}", operator, (node,) * width)
    assert isinstance(node, MaskCombination)
    return node


def test_empty_mask_nodes_skip_their_operands() -> None:
    calls: list[str] = []
    outside = MaskShape("out", _counting(Box(20, 20, 24, 24), D8, calls, "out"))
    empty = MaskCombination("e", "union", (outside, outside))
    spy = _SpyDeadline()
    tree = LayerTree(D8, (Layer("l", "L", (_rect_fill(FULL, RED),), mask=empty),))
    assert _grid(tree) == {key: CLEAR for key in _grid(LayerTree(D8, ()))}
    compose(tree, limits=LIMITS, deadline=spy)
    assert calls == []  # no leaf is built, not even once
    assert spy.stages == ["compose_node", "compose_fill", "compose_mask"]  # operands skipped
    assert mask_cost(empty, D8) == MaskCost(None, MASK_NODE_VISITS, 0)
    # An empty intersection skips non-empty operands too.
    a, b = _shape("a", Box(0, 0, 2, 2)), _shape("b", Box(4, 4, 6, 6))
    assert mask_cost(MaskCombination("i", "intersect", (a, b)), D8) == MaskCost(None, 1, 0)


@pytest.mark.parametrize("operator", ["union", "intersect", "subtract", "xor"])
def test_wide_deep_dag_of_empty_masks_costs_the_floor(operator: MaskOperator) -> None:
    calls: list[str] = []
    leaf = MaskShape("out", _counting(Box(-9, -9, -1, -1), D8, calls, "out"))
    top = _tower(leaf, operator, MAX_MASK_OPERANDS, MAX_MASK_DEPTH - 1)  # 64^15 references
    assert mask_cost(top, D8) == MaskCost(None, MASK_NODE_VISITS, 0)
    tree = LayerTree(D8, (Layer("l", "L", (_rect_fill(FULL, RED),), mask=top),))
    plain = composition_cost(LayerTree(D8, (Layer("l", "L", (_rect_fill(FULL, RED),)),)))
    # The floor, no bits to copy, and clearing outside counted as A = 64.
    assert composition_cost(tree).pixel_visits == plain.pixel_visits + 1 + 0 + 64
    compose(tree, limits=LIMITS)  # finishes at once: the top node is empty
    assert calls == []


@pytest.mark.parametrize("operator", ["union", "intersect", "xor"])
def test_wide_deep_dag_of_full_masks_is_rejected_before_composing(operator: MaskOperator) -> None:
    calls: list[str] = []
    leaf = MaskShape("in", _counting(FULL, D8, calls, "in"))
    top = _tower(leaf, operator, MAX_MASK_OPERANDS, MAX_MASK_DEPTH - 1)
    # Every level folds 64 references of the level below: at least 64^15 leaves.
    assert mask_cost(top, D8).pixel_visits > MAX_MASK_OPERANDS ** (MAX_MASK_DEPTH - 1)
    tree = LayerTree(D8, (Layer("l", "L", (), mask=top),))
    with pytest.raises(BudgetExceeded) as raised:
        compose(tree, limits=LIMITS)
    assert raised.value.context["resource"] == "pixel_visits"
    assert calls == []


def test_small_shared_dag_cost_matches_the_hand_formula() -> None:
    dims = Dimensions(4, 4)
    leaf = _shape("a", Box(0, 0, 2, 2), dims)  # 4 px
    # Level 1: 1 + 2*4 + 2*(1 + 4) = 19. Level 2: 1 + 2*4 + 2*(19 + 4) = 55.
    assert mask_cost(_tower(leaf, "union", 2, 1), dims).pixel_visits == 19
    assert mask_cost(_tower(leaf, "union", 2, 2), dims).pixel_visits == 55
    outside = _shape("o", Box(4, 4, 6, 6), dims)
    # A union with an empty operand: 1 + 2*4 + (1 + 4) + (1 + 0) = 15.
    mixed = MaskCombination("m", "union", (leaf, MaskCombination("e", "xor", (outside, outside))))
    assert mask_cost(mixed, dims).pixel_visits == 15


def test_mask_costs_are_checked_before_composing() -> None:
    mask = MaskCombination("m", "union", (_shape("a", FULL), _shape("b", FULL)))
    tree = LayerTree(D8, (Layer("l", "L", (), mask=mask),))
    cost = composition_cost(tree)
    with pytest.raises(BudgetExceeded) as excinfo:
        compose(tree, limits=RenderLimits(max_pixel_visits=cost.pixel_visits - 1))
    assert excinfo.value.context["resource"] == "pixel_visits"
    compose(tree, limits=RenderLimits(max_pixel_visits=cost.pixel_visits))


def test_peak_memory_of_deep_masks_stays_within_the_cost() -> None:
    dims = Dimensions(128, 96)
    node: MaskShape | MaskCombination = _shape("s0", Box(0, 0, 128, 96), dims)
    for depth in range(1, MAX_MASK_DEPTH):
        other = _shape(f"s{depth}", Box(depth, depth, 128 - depth, 96 - depth), dims)
        node = MaskCombination(f"c{depth}", "xor" if depth % 2 else "union", (node, other))
    layer = Layer("l", "L", (_rect_fill(Box(0, 0, 128, 96), RED, dims),), mask=node)
    tree = LayerTree(dims, (layer,))
    cost = composition_cost(tree)
    tracemalloc.start()
    try:
        compose(tree, limits=LIMITS)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= cost.buffer_bytes


# --- Node validation ---------------------------------------------------------------


def test_mask_nodes_validate_their_fields() -> None:
    leaf = _shape("a", LEFT)
    with pytest.raises(TypeError):
        MaskShape("a", LEFT)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        MaskShape("Bad Id", leaf.mask)
    with pytest.raises(ValidationError) as excinfo:
        MaskCombination("m", "or", (leaf, leaf))  # type: ignore[arg-type]
    assert excinfo.value.context["reason"] == "unknown_operator"
    with pytest.raises(TypeError):
        MaskCombination("m", "union", [leaf, leaf])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        MaskCombination("m", "union", (leaf, LEFT))  # type: ignore[arg-type]
    for operands in ((leaf,), (leaf,) * (MAX_MASK_OPERANDS + 1)):
        with pytest.raises(ValidationError) as excinfo:
            MaskCombination("m", "union", operands)
        assert excinfo.value.context["reason"] == "out_of_range"
    assert len(MaskCombination("m", "union", (leaf,) * MAX_MASK_OPERANDS).operands) == 64
    with pytest.raises(TypeError):
        Layer("l", "L", mask=leaf.mask)  # type: ignore[arg-type]


def test_mask_depth_sixteen_is_accepted_and_seventeen_rejected() -> None:
    node: MaskShape | MaskCombination = _shape("s", LEFT)
    for depth in range(2, MAX_MASK_DEPTH + 1):
        node = MaskCombination(f"c{depth}", "union", (node, node))
    assert node.depth == MAX_MASK_DEPTH == 16
    with pytest.raises(ValidationError) as excinfo:
        MaskCombination("deep", "union", (node, node))
    assert excinfo.value.context["reason"] == "too_deep"
