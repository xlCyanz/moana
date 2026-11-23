"""Layer tree validation: IDs, names, opacity, profile and depth (MOANA-009, ADR-017)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from moanart.core.coordinates import Box, Dimensions
from moanart.core.errors import ValidationError
from moanart.core.limits import MAX_GROUP_DEPTH, MAX_LAYERS, MAX_OPERATIONS
from moanart.geometry import rasterize_rect
from moanart.layers import MAX_NAME_BYTES, Fill, Group, Layer, LayerTree
from moanart.palette import Rgba

DIMS = Dimensions(4, 4)
SOLID = Fill(rasterize_rect(Box(0, 0, 2, 2), DIMS), Rgba(1, 2, 3, 255))


def _reason(excinfo: pytest.ExceptionInfo[ValidationError]) -> object:
    return excinfo.value.context.get("reason")


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"id": "Bad"}, "invalid_id"),
        ({"name": 3}, "not_string"),
        ({"name": "x" * (MAX_NAME_BYTES + 1)}, "too_long"),
        ({"name": "é" * (MAX_NAME_BYTES // 2 + 1)}, "too_long"),
        ({"name": "\ud800"}, "invalid_utf8"),
        ({"visible": 1}, "not_boolean"),
        ({"locked": None}, "not_boolean"),
        ({"opacity": 256}, "out_of_range"),
        ({"opacity": -1}, "out_of_range"),
        ({"opacity": 1.0}, "not_integer"),
        ({"opacity": True}, "not_integer"),
        ({"blend": "multiply"}, "unsupported_blend"),
    ],
)
def test_layer_fields_are_validated(kwargs: dict[str, object], reason: str) -> None:
    fields: dict[str, object] = {"id": "layer", "name": "Layer", **kwargs}
    with pytest.raises(ValidationError) as excinfo:
        Layer(**fields)  # type: ignore[arg-type]  # invalid on purpose
    assert _reason(excinfo) == reason


def test_group_fields_are_validated() -> None:
    with pytest.raises(ValidationError):
        Group("g", "G", opacity=300)
    with pytest.raises(TypeError):
        Group("g", "G", children=[Layer("l", "L")])  # type: ignore[arg-type]  # list
    with pytest.raises(TypeError):
        Group("g", "G", children=("layer",))  # type: ignore[arg-type]  # not a node
    with pytest.raises(ValidationError):
        Group("g", "G", children=tuple(Layer(f"l{i}", "L") for i in range(MAX_LAYERS + 1)))


def test_layer_fill_count_is_bounded() -> None:
    Layer("l", "L", (SOLID,) * MAX_OPERATIONS)
    with pytest.raises(ValidationError) as excinfo:
        Layer("l", "L", (SOLID,) * (MAX_OPERATIONS + 1))
    assert _reason(excinfo) == "out_of_range"


def test_fill_and_layer_types_are_checked() -> None:
    with pytest.raises(TypeError):
        Fill("mask", Rgba(0, 0, 0, 0))  # type: ignore[arg-type]  # deliberate misuse
    with pytest.raises(TypeError):
        Fill(SOLID.mask, (0, 0, 0, 0))  # type: ignore[arg-type]  # deliberate misuse
    with pytest.raises(TypeError):
        Layer("l", "L", fills=[SOLID])  # type: ignore[arg-type]  # list, not tuple
    with pytest.raises(TypeError):
        Layer("l", "L", fills=("fill",))  # type: ignore[arg-type]  # not a Fill


def test_tree_types_are_checked() -> None:
    with pytest.raises(TypeError):
        LayerTree((4, 4), ())  # type: ignore[arg-type]  # deliberate misuse
    with pytest.raises(TypeError):
        LayerTree(DIMS, [Layer("l", "L")])  # type: ignore[arg-type]  # list
    with pytest.raises(TypeError):
        LayerTree(DIMS, ("layer",))  # type: ignore[arg-type]  # not a node
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(DIMS, (), profile="cmyk")  # type: ignore[arg-type]  # invalid on purpose
    assert _reason(excinfo) == "unknown_profile"


def test_ids_are_unique_across_layers_and_groups() -> None:
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(DIMS, (Layer("a", "A"), Group("g", "G", (Layer("a", "Again"),))))
    assert _reason(excinfo) == "duplicate_id"
    assert excinfo.value.context["node_id"] == "a"
    with pytest.raises(ValidationError):
        LayerTree(DIMS, (Group("x", "X", (Layer("x", "Same as group"),)),))


@pytest.mark.parametrize("node", ["layer", "group"])
def test_t2_strict_rejects_intermediate_opacity(node: str) -> None:
    child = Layer("l", "L", opacity=128 if node == "layer" else 255)
    root = Group("g", "G", (child,), opacity=128 if node == "group" else 255)
    LayerTree(DIMS, (root,), profile="rgba")
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(DIMS, (root,), profile="strict")
    assert _reason(excinfo) == "partial_opacity"
    assert excinfo.value.context["profile"] == "strict"
    assert excinfo.value.context["node_id"] == ("l" if node == "layer" else "g")


def test_strict_rejects_partial_alpha_fills_but_accepts_0_and_255() -> None:
    opaque = Fill(SOLID.mask, Rgba(1, 2, 3, 255))
    clear = Fill(SOLID.mask, Rgba(0, 0, 0, 0))
    LayerTree(DIMS, (Layer("l", "L", (opaque, clear)),), profile="strict")
    partial = Fill(SOLID.mask, Rgba(1, 2, 3, 128))
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(DIMS, (Layer("l", "L", (opaque, partial)),), profile="strict")
    assert (_reason(excinfo), excinfo.value.context["fill"]) == ("partial_alpha", 1)


def test_strict_accepts_opacity_255_trees() -> None:
    tree = LayerTree(DIMS, (Group("g", "G", (Layer("l", "L", (SOLID,)),)),), profile="strict")
    assert tree.profile == "strict"


def test_t2_depth_limit_counts_nested_groups() -> None:
    node: Layer | Group = Layer("leaf", "Leaf")
    for level in range(MAX_GROUP_DEPTH):
        node = Group(f"g{level}", "G", (node,))
    LayerTree(DIMS, (node,))
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(DIMS, (Group("top", "Top", (node,)),))
    # The innermost group is the 17th level and is the one reported.
    assert (_reason(excinfo), excinfo.value.context["node_id"]) == ("too_deep", "g0")


def test_layer_count_is_bounded_across_groups() -> None:
    half = MAX_LAYERS // 2 + 1
    first = Group("a", "A", tuple(Layer(f"a{i}", "L") for i in range(half)))
    second = Group("b", "B", tuple(Layer(f"b{i}", "L") for i in range(half)))
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(DIMS, (first, second))
    assert _reason(excinfo) == "out_of_range"


def test_groups_count_towards_the_128_node_limit() -> None:
    layers = tuple(Layer(f"l{i}", "L") for i in range(MAX_LAYERS - 2))
    LayerTree(DIMS, (*layers, Group("a", "A"), Group("b", "B")))
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(DIMS, (*layers, Group("a", "A"), Group("b", "B", (Layer("x", "X"),))))
    assert _reason(excinfo) == "out_of_range"
    with pytest.raises(ValidationError):
        LayerTree(DIMS, tuple(Group(f"g{i}", "G") for i in range(MAX_LAYERS + 1)))


def test_fill_mask_must_fit_the_canvas() -> None:
    wide = Fill(rasterize_rect(Box(0, 0, 8, 1), Dimensions(8, 8)), Rgba(0, 0, 0, 255))
    with pytest.raises(ValidationError) as excinfo:
        LayerTree(DIMS, (Layer("l", "L", (wide,)),))
    assert (_reason(excinfo), excinfo.value.context["fill"]) == ("outside_canvas", 0)


def test_walk_lists_nodes_bottom_to_top_depth_first() -> None:
    tree = LayerTree(
        DIMS,
        (Layer("a", "A"), Group("g", "G", (Layer("b", "B"), Group("h", "H", (Layer("c", "C"),))))),
    )
    assert [(node.id, depth) for node, depth in tree.walk()] == [
        ("a", 0),
        ("g", 0),
        ("b", 1),
        ("h", 1),
        ("c", 2),
    ]


def test_nodes_are_immutable_values() -> None:
    layer = Layer("l", "L", (SOLID,))
    with pytest.raises(AttributeError):
        layer.opacity = 1  # type: ignore[misc]  # frozen on purpose
    assert layer == Layer("l", "L", (SOLID,))
    assert hash(layer) == hash(Layer("l", "L", (SOLID,)))


# --- Architecture -------------------------------------------------------------------

LAYERS = Path(__file__).resolve().parents[3] / "src/moanart/layers"


def test_layers_imports_only_core_palette_geometry_numpy_and_stdlib() -> None:
    paths = sorted(LAYERS.glob("*.py"))
    assert paths
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                assert (
                    name.split(".")[0] in sys.stdlib_module_names
                    or name.split(".")[0] == "numpy"
                    or name.startswith(("moanart.core", "moanart.palette", "moanart.geometry"))
                    or name.startswith("moanart.layers")
                ), f"{path.name} imports {name}"
                assert name != "moanart.core.pillow_adapter"


def test_importing_layers_loads_neither_pillow_nor_pydantic() -> None:
    probe = (
        "import sys, moanart.layers; "
        "heavy = {'PIL', 'aggdraw', 'pydantic'}; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in heavy))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, encoding="utf-8", check=True
    )
    assert result.stdout.strip() == "[]"
