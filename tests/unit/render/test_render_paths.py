"""Render of ``path`` operations and path mask leaves (MOANA-007, ADR-023).

AC1: the RGBA result holds only the palette colour or transparency (no AA colour)
and nothing outside the path box. AC2: invalid payloads, unvalidated models and a
missing or untested backend fail with domain errors before the adapter runs.
``budget-v4`` figures are computed by hand from the formulas of
``moana.render.budget``; the property "admitted by ``plan_budget`` => rendered" and
peak memory are checked as for the other primitives.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import subprocess
import sys
import tracemalloc
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import moana.geometry.paths as paths_module
from moana.api import inspect_document
from moana.core.budget import RenderLimits
from moana.core.coordinates import Dimensions
from moana.core.errors import BudgetExceeded, UnsupportedOperation, ValidationError
from moana.core.limits import MAX_PATH_CELLS, GeometryLimits
from moana.core.vector_path import PATH_UNITS, parse_path
from moana.geometry import rasterize_path
from moana.render import ESTIMATOR_VERSION, estimate_cost, plan_budget, render
from moana.render import pipeline as pipeline_module
from moana.schema import Document, canonical_json, validate_document

U = PATH_UNITS
RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)
INK: RGBA = (16, 32, 48, 255)
GOLD: RGBA = (250, 200, 0, 255)
SQUARE: list[list[Any]] = [
    ["M", U, U],
    ["L", 5 * U, U],
    ["L", 5 * U, 5 * U],
    ["L", U, 5 * U],
    ["Z"],
]
CURVE: list[list[Any]] = [
    ["M", 2 * U, 14 * U],
    ["C", 0, -2 * U, 16 * U, -2 * U, 14 * U, 14 * U],
    ["Z"],
]


def path_op(name: str, commands: list[list[Any]], color: str = "ink") -> dict[str, Any]:
    return {
        "id": name,
        "type": "path",
        "backend": "aggdraw-v1",
        "color": color,
        "commands": commands,
    }


def doc(
    width: int,
    height: int,
    operations: list[dict[str, Any]],
    *,
    masks: list[dict[str, Any]] | None = None,
    mask_id: str | None = None,
    profile: str = "strict",
) -> Document:
    layer: dict[str, Any] = {"id": "l", "name": "L", "operations": operations}
    if mask_id is not None:
        layer["mask_id"] = mask_id
    return validate_document(
        {
            "schema_version": "1.0",
            "id": "doc",
            "canvas": {"width": width, "height": height, "profile": profile},
            "palette": {
                "id": "pal",
                "colors": [
                    {"id": "ink", "rgba": "#102030FF"},
                    {"id": "gold", "rgba": "#FAC800FF"},
                ],
            },
            "masks": masks or [],
            "layers": [layer],
        }
    )


def grid(result: Any) -> dict[tuple[int, int], RGBA]:
    return {(x, y): result.pixel(x, y) for y in range(result.height) for x in range(result.width)}


class _Refuse:
    """Replaces the adapter: any call is a test failure."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls = 0
        monkeypatch.setattr(pipeline_module, "rasterize_path", self)
        monkeypatch.setattr(paths_module, "_coverage", self)

    def __call__(self, *_: object) -> Any:
        self.calls += 1
        raise AssertionError("the path adapter must not run")


# --- AC1 -------------------------------------------------------------------------------


def test_ac1_render_has_only_palette_colours_inside_the_path_boxes() -> None:
    document = doc(16, 16, [path_op("curve", CURVE), path_op("sq", SQUARE, "gold")])
    result = render(document)
    pixels = grid(result)
    assert set(pixels.values()) <= {CLEAR, INK, GOLD}
    curve = rasterize_path(parse_path(CURVE), Dimensions(16, 16))
    square = rasterize_path(parse_path(SQUARE), Dimensions(16, 16))
    for (x, y), value in pixels.items():
        in_square = 1 <= x < 5 and 1 <= y < 5  # the square's box, by hand
        expected = GOLD if in_square else INK if (x, y) in set(curve_points(curve)) else CLEAR
        assert value == expected
    assert square.count == 16
    curve_box = parse_path(CURVE).bounds
    assert curve_box is not None
    assert all(curve_box.x0 <= x < curve_box.x1 for x, _ in curve_points(curve))


def curve_points(mask: Any) -> list[tuple[int, int]]:
    return [(point.x, point.y) for point in mask.points()]


def test_ac1_rgba_profile_keeps_binary_coverage() -> None:
    """Even in ``rgba``, coverage never becomes partial alpha."""
    result = render(doc(16, 16, [path_op("curve", CURVE)], profile="rgba"))
    assert {value[3] for value in grid(result).values()} == {0, 255}


def test_path_mask_leaf_clips_a_layer_to_the_path() -> None:
    masks = [{"id": "shape", "type": "path", "backend": "aggdraw-v1", "commands": CURVE}]
    fill = {"id": "fill", "type": "rect", "box": [0, 0, 16, 16], "color": "ink"}
    result = render(doc(16, 16, [fill], masks=masks, mask_id="shape"))
    expected = set(curve_points(rasterize_path(parse_path(CURVE), Dimensions(16, 16))))
    painted = {xy for xy, value in grid(result).items() if value == INK}
    assert painted == expected
    assert set(grid(result).values()) == {CLEAR, INK}


def test_off_canvas_path_produces_an_empty_bounds_warning() -> None:
    far: list[list[Any]] = [
        ["M", 40 * U, 40 * U],
        ["L", 44 * U, 40 * U],
        ["L", 44 * U, 44 * U],
        ["Z"],
    ]
    result = render(doc(8, 8, [path_op("far", far)]))
    assert [w.json_pointer for w in result.warnings] == ["/layers/0/operations/0"]
    assert set(grid(result).values()) == {CLEAR}


# --- Provenance ------------------------------------------------------------------------


def test_provenance_records_the_backend_and_versions_only_with_paths() -> None:
    with_paths = render(doc(8, 8, [path_op("sq", SQUARE)])).provenance
    status = paths_module.path_backend()
    assert with_paths.vector_backend == "aggdraw-v1"
    assert with_paths.vector_backend_versions == (
        f"aggdraw=={status.version}",
        f"pillow=={status.pillow_version}",
    )
    mapping = with_paths.to_mapping()
    assert mapping["vector_backend_versions"] == list(with_paths.vector_backend_versions)
    assert with_paths.estimator_version == ESTIMATOR_VERSION == "budget-v4"
    plain = render(doc(8, 8, [{"id": "r", "type": "rect", "box": [0, 0, 2, 2], "color": "ink"}]))
    assert plain.provenance.vector_backend is None
    assert plain.provenance.vector_backend_versions == ()


def test_provenance_omits_an_unknown_pillow_version(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    provenance = render(doc(8, 8, [path_op("sq", SQUARE)])).provenance
    assert provenance.vector_backend_versions == (
        f"aggdraw=={paths_module.path_backend().version}",
    )


# --- AC2 -------------------------------------------------------------------------------


@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings")
def test_ac2_unvalidated_models_fail_validation_before_the_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refuse = _Refuse(monkeypatch)
    document = doc(8, 8, [path_op("sq", SQUARE)])
    operation = document.layers[0].operations[0]
    for commands in (
        (("L", 0, 0), ("L", 1, 1)),
        (("M", 0, 0), ("A", 1, 1)),
        (("M", 0, 0), ("L", 1.5, 1)),
        (("M", 0, 0), ("L", 2**40, 1)),
        tuple([("M", 0, 0)] + [("L", 1, 1)] * 5000),
    ):
        broken = operation.model_copy(update={"commands": commands})
        layer = document.layers[0].model_copy(update={"operations": (broken,)})
        unvalidated = document.model_copy(update={"layers": (layer,)})
        with pytest.raises(ValidationError):
            render(unvalidated)
    assert refuse.calls == 0


@pytest.mark.parametrize("hidden", [False, True])
def test_ac2_missing_backend_fails_before_budget_and_raster(
    monkeypatch: pytest.MonkeyPatch, hidden: bool
) -> None:
    refuse = _Refuse(monkeypatch)
    monkeypatch.setattr(pipeline_module, "plan_budget", refuse)
    monkeypatch.setitem(sys.modules, "aggdraw", None)
    document = doc(8, 8, [path_op("sq", SQUARE)])
    if hidden:  # a hidden layer still needs the backend: the document uses paths
        layer = document.layers[0].model_copy(update={"visible": False})
        document = document.model_copy(update={"layers": (layer,)})
    with pytest.raises(UnsupportedOperation) as raised:
        render(document)
    assert raised.value.json_pointer == "/layers/0/operations/0/backend"
    assert raised.value.context["reason"] == "backend_unavailable"
    assert raised.value.context["cause"] == "missing"
    assert refuse.calls == 0


def test_ac2_untested_version_names_the_version_and_the_mask_leaf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refuse = _Refuse(monkeypatch)
    aggdraw = importlib.import_module("aggdraw")
    monkeypatch.setattr(aggdraw, "VERSION", "9.9.9")
    masks = [{"id": "shape", "type": "path", "backend": "aggdraw-v1", "commands": SQUARE}]
    fill = {"id": "fill", "type": "rect", "box": [0, 0, 8, 8], "color": "ink"}
    with pytest.raises(UnsupportedOperation) as raised:
        render(doc(8, 8, [fill], masks=masks, mask_id="shape"))
    assert raised.value.json_pointer == "/masks/0/backend"
    assert raised.value.context["version"] == "9.9.9"
    assert raised.value.context["cause"] == "untested_version"
    assert refuse.calls == 0


@pytest.mark.parametrize("version", [None, "9.9.9"])
def test_renderer_and_adapter_report_the_same_backend_error(
    monkeypatch: pytest.MonkeyPatch, version: str | None
) -> None:
    if version is None:
        monkeypatch.setitem(sys.modules, "aggdraw", None)
    else:
        monkeypatch.setattr(importlib.import_module("aggdraw"), "VERSION", version)
    document = doc(8, 8, [path_op("sq", SQUARE)])
    with pytest.raises(UnsupportedOperation) as from_render:
        render(document)
    with pytest.raises(UnsupportedOperation) as from_adapter:
        rasterize_path(parse_path(SQUARE), Dimensions(8, 8))
    assert dict(from_render.value.context) == dict(from_adapter.value.context)
    assert from_render.value.context["tested_versions"] == paths_module.TESTED_AGGDRAW_VERSIONS
    assert from_render.value.message == from_adapter.value.message
    assert from_adapter.value.json_pointer is None


def test_documents_without_paths_render_without_the_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "aggdraw", None)
    plain = doc(4, 4, [{"id": "r", "type": "rect", "box": [0, 0, 2, 2], "color": "ink"}])
    assert render(plain).pixel(0, 0) == INK


# --- Budget (budget-v4) ----------------------------------------------------------------


def test_budget_v4_hand_oracle_for_a_square_path() -> None:
    """8x8 canvas (A = 64), one visible layer, the square [1, 5) x [1, 5) as a path.

    Path: S = 4 segments; box 4x4 = 16; buffer 6x6 = 36; Manhattan length 16 px,
    so cells = min(2*16 + 3*4, 3*4*(6+6+1)) = min(44, 156) = 44.
    Raster = 4 + 44 + 3*36 = 156; operation visits = 156 + 16 (paint) = 172.
    Frame visits = 3A + 2A + 172 = 320 + 172 = 492.
    Mask bytes = 16 + 2*36 + 24*44 + 256*5 commands + 128 KiB native heap
               = 16 + 72 + 1056 + 1280 + 131072 = 133496.
    Bytes = max(40A, 14A + 80*16) + 133496 + 4A = 2560 + 133496 + 256 = 136312.
    """
    estimate = estimate_cost(doc(8, 8, [path_op("sq", SQUARE)]))
    assert estimate.estimator_version == "budget-v4"
    assert estimate.operation_costs[0].pixel_visits == 172
    assert estimate.operation_costs[0].mask_bytes == 133496
    assert estimate.pixel_visits == 492
    assert estimate.buffer_bytes == 136312


def test_budget_of_an_off_canvas_path_counts_only_its_segments() -> None:
    far: list[list[Any]] = [["M", 40 * U, 40 * U], ["Q", 60 * U, 40 * U, 44 * U, 44 * U], ["Z"]]
    path = parse_path(far)
    estimate = estimate_cost(doc(8, 8, [path_op("far", far)]))
    assert estimate.operation_costs[0].pixel_visits == path.segments  # nothing to paint
    assert estimate.operation_costs[0].mask_bytes == 0


def test_path_mask_leaf_budget_uses_the_same_raster_formula() -> None:
    masks = [{"id": "shape", "type": "path", "backend": "aggdraw-v1", "commands": SQUARE}]
    fill = {"id": "fill", "type": "rect", "box": [0, 0, 8, 8], "color": "ink"}
    estimate = estimate_cost(doc(8, 8, [fill], masks=masks, mask_id="shape"))
    mask_cost = estimate.operation_costs[1]
    assert mask_cost.json_pointer == "/layers/0/mask_id"
    # floor 1 + raster 156 (as above) + copy 16 + clear outside A = 64
    assert mask_cost.pixel_visits == 1 + 156 + 16 + 64
    assert mask_cost.mask_bytes == 133496 + 16


def comb(teeth: int, size: int) -> list[list[Any]]:
    step = size * U // teeth
    commands: list[list[Any]] = [["M", 0, 0]]
    for i in range(teeth):
        commands += [["L", i * step + step // 2, size * U], ["L", (i + 1) * step, 0]]
    return [*commands, ["L", size * U, size * U + U], ["L", 0, size * U + U], ["Z"]]


def test_path_cells_over_the_engine_limit_are_rejected_by_the_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refuse = _Refuse(monkeypatch)
    document = doc(2048, 2048, [path_op("comb", comb(600, 2048))])
    huge = RenderLimits(max_pixel_visits=10**12, max_buffer_bytes=2**40, host_override=True)
    with pytest.raises(BudgetExceeded) as raised:
        plan_budget(document, huge)
    details = [(d.json_pointer, d.context["resource"]) for d in raised.value.details]
    assert details == [("/layers/0/operations/0", "path_cells")]
    assert raised.value.context["limit"] == MAX_PATH_CELLS
    with pytest.raises(BudgetExceeded):
        render(document, limits=huge)
    report = inspect_document(document, limits=huge)
    assert [item.resource for item in report.budget.exceeded] == ["path_cells"]
    assert refuse.calls == 0


def test_path_coordinates_are_checked_against_geometry_limits() -> None:
    document = doc(8, 8, [path_op("sq", [["M", 0, 0], ["L", 9 * U, 0], ["L", 0, -12 * U - 1]])])
    limits = RenderLimits(geometry=GeometryLimits(max_coordinate=12))
    with pytest.raises(BudgetExceeded) as raised:
        plan_budget(document, limits)
    assert raised.value.context == {"resource": "coordinate", "limit": 12, "estimated": 13}
    assert raised.value.json_pointer == "/layers/0/operations/0"


def test_peak_memory_of_paths_stays_within_the_estimate() -> None:
    teeth = comb(40, 256)
    document = doc(256, 256, [path_op("comb", teeth), path_op("curve", CURVE, "gold")])
    estimate = plan_budget(document)
    tracemalloc.start()
    try:
        render(document)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak <= estimate.buffer_bytes


coordinate = st.integers(-4 * U, 14 * U)
command = st.one_of(
    st.tuples(st.just("L"), coordinate, coordinate),
    st.tuples(st.just("Q"), coordinate, coordinate, coordinate, coordinate),
    st.tuples(st.just("C"), *[coordinate] * 6),
)


@settings(max_examples=40, deadline=None)
@given(
    width=st.integers(1, 12),
    height=st.integers(1, 12),
    start=st.tuples(coordinate, coordinate),
    body=st.lists(command, min_size=1, max_size=6),
    close=st.booleans(),
    as_mask=st.booleans(),
)
def test_plan_budget_admission_means_render_succeeds_with_paths(
    width: int,
    height: int,
    start: tuple[int, int],
    body: list[tuple[Any, ...]],
    close: bool,
    as_mask: bool,
) -> None:
    commands = [["M", *start], *[list(c) for c in body], *([["Z"]] if close else [])]
    if as_mask:
        masks = [{"id": "shape", "type": "path", "backend": "aggdraw-v1", "commands": commands}]
        fill = {"id": "fill", "type": "rect", "box": [0, 0, width, height], "color": "ink"}
        document = doc(width, height, [fill], masks=masks, mask_id="shape")
    else:
        document = doc(width, height, [path_op("p", commands)])
    estimate = plan_budget(document)
    exact = RenderLimits(
        max_pixel_visits=estimate.pixel_visits,
        max_buffer_bytes=estimate.buffer_bytes,
        max_frame_pixels=estimate.frame_pixels,
        max_operations=1,
        max_layers=1,
    )
    result = render(document, limits=exact)
    assert {result.pixel(x, y) for y in range(height) for x in range(width)} <= {CLEAR, INK}


def test_planning_a_path_document_loads_neither_aggdraw_nor_pillow() -> None:
    """``import moana.render`` and the cost plan of a path stay free of AggDraw."""
    probe = (
        "import sys, moana.render, moana.schema; "
        "doc = moana.schema.validate_document(sys.stdin.buffer.read()); "
        "moana.render.plan_budget(doc); "
        "heavy = {'PIL', 'aggdraw'}; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in heavy))"
    )
    source = canonical_json(doc(16, 16, [path_op("square", SQUARE)]))
    result = subprocess.run(
        [sys.executable, "-c", probe], input=source, capture_output=True, check=True, timeout=60
    )
    assert result.stdout.decode("utf-8").strip() == "[]"
