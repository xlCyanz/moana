"""Cost plan before raster: hand-computed oracles, exact limits and no allocation.

Expected values are derived by hand from the budget-v3 formulas documented in
``moanart.render.budget`` and MOANART.md section 20, never from the implementation.
"""

from __future__ import annotations

import subprocess
import sys
import tracemalloc
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from moanart.core import errors
from moanart.core.budget import Deadline, RenderLimits
from moanart.core.limits import GeometryLimits
from moanart.render import budget as budget_module
from moanart.render import estimate_cost, plan_budget
from moanart.schema import Document, validate_document

A128 = 128 * 128
A2048 = 2048 * 2048


def document(
    width: int = 128,
    height: int = 128,
    layers: list[list[dict[str, Any]]] | None = None,
    hidden: frozenset[int] = frozenset(),
) -> Document:
    specs = [[]] if layers is None else layers
    counter = iter(range(1_000_000))
    return validate_document(
        {
            "schema_version": "1.0",
            "id": "doc",
            "canvas": {"width": width, "height": height},
            "palette": {"id": "pal", "colors": [{"id": "ink", "rgba": "#000000FF"}]},
            "layers": [
                {
                    "id": f"layer{index}",
                    "name": "L",
                    "visible": index not in hidden,
                    "operations": [
                        {"id": f"op{next(counter)}", "color": "ink", **operation}
                        for operation in operations
                    ],
                }
                for index, operations in enumerate(specs)
            ],
        }
    )


def test_minimal_rect_matches_hand_oracle() -> None:
    estimate = estimate_cost(document(layers=[[{"type": "rect", "box": [40, 32, 88, 104]}]]))
    rect = 48 * 72  # 3456
    # 3A (clear, normalise, copy) + 2A (layer clear, composite) + raster + paint
    assert estimate.pixel_visits == 5 * A128 + 2 * rect == 88_832
    # 4A canvas + 4A layer + 32A accumulator + mask, plus one retained 4A result
    assert estimate.buffer_bytes == 40 * A128 + rect + 4 * A128 == 724_352
    assert estimate.frame_pixels == A128
    assert (estimate.operations, estimate.layers, estimate.frames) == (1, 1, 1)
    assert estimate.estimator_version == "budget-v8"
    (cost,) = estimate.operation_costs
    assert (cost.json_pointer, cost.pixel_visits, cost.mask_bytes) == (
        "/layers/0/operations/0",
        2 * rect,
        rect,
    )


@pytest.mark.parametrize(
    ("operation", "visits", "mask"),
    [
        # visits = raster work + one paint pass over the clipped mask box
        ({"type": "pixel", "at": [5, 5]}, 2, 1),
        ({"type": "pixel", "at": [128, 0]}, 0, 0),  # excluded edge: off canvas
        ({"type": "pixel", "at": [-1, 3]}, 0, 0),
        # Bresenham steps before clipping + paint of clipped bbox x[0,128) y[0,6)
        ({"type": "line", "start": [-1_000_000, 0], "end": [1_000_000, 5]}, 2_000_769, 768),
        ({"type": "line", "start": [3, 3], "end": [3, 3]}, 2, 1),
        ({"type": "line", "start": [500, 500], "end": [400, 520]}, 101, 0),
        ({"type": "rect", "box": [-10, -10, 10, 10]}, 200, 100),
        ({"type": "rect", "box": [-1_048_576, -1_048_576, 1_048_577, 1_048_577]}, 2 * A128, A128),
        ({"type": "ellipse", "box": [120, 120, 140, 130]}, 128, 64),
        ({"type": "ellipse", "box": [200, 0, 210, 10]}, 0, 0),
        # bounds Box(0,0,10,4): area 40 + 4 rows x 3 vertices + paint 40
        ({"type": "polygon", "points": [[0, 0], [10, 0], [0, 4]]}, 92, 40),
        ({"type": "polygon", "points": [[0, 0], [5, 0], [9, 0]]}, 0, 0),  # no centre
        (
            {"type": "polygon", "points": [[-50, -50], [200, -50], [-50, 200]]},
            2 * A128 + 128 * 3,
            A128,
        ),
    ],
)
def test_operation_costs(operation: dict[str, Any], visits: int, mask: int) -> None:
    (cost,) = estimate_cost(document(layers=[[operation]])).operation_costs
    assert (cost.pixel_visits, cost.mask_bytes) == (visits, mask)


@given(st.integers(-20, 20), st.integers(-20, 20), st.integers(1, 30), st.integers(1, 30))
def test_rect_visits_equal_independent_pixel_count(x0: int, y0: int, w: int, h: int) -> None:
    pixels = {
        (x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h) if 0 <= x < 16 and 0 <= y < 12
    }
    estimate = estimate_cost(
        document(16, 12, layers=[[{"type": "rect", "box": [x0, y0, x0 + w, y0 + h]}]])
    )
    assert estimate.operation_costs[0].pixel_visits == 2 * len(pixels)  # raster + paint


def test_hidden_layers_cost_nothing_but_count_operations() -> None:
    rect = {"type": "rect", "box": [0, 0, 128, 128]}
    estimate = estimate_cost(document(layers=[[rect], [rect]], hidden=frozenset({1})))
    assert estimate.pixel_visits == 3 * A128 + 2 * A128 + 2 * A128
    assert estimate.operations == 2
    assert [c.json_pointer for c in estimate.operation_costs] == ["/layers/0/operations/0"]


def test_request_exactly_at_each_limit_is_admitted() -> None:
    doc = document(layers=[[{"type": "rect", "box": [40, 32, 88, 104]}]])
    exact = RenderLimits(
        max_pixel_visits=88_832,
        max_buffer_bytes=724_352,
        max_frame_pixels=A128,
        max_operations=1,
        max_layers=1,
    )
    assert plan_budget(doc, exact).pixel_visits == 88_832


@pytest.mark.parametrize(
    ("overrides", "resource", "limit", "estimated", "pointer"),
    [
        ({"max_pixel_visits": 88_831}, "pixel_visits", 88_831, 88_832, "/layers/0/operations/0"),
        ({"max_buffer_bytes": 724_351}, "buffer_bytes", 724_351, 724_352, None),
        ({"max_frame_pixels": A128 - 1}, "frame_pixels", A128 - 1, A128, None),
        ({"max_operations": 0}, "operations", 0, 1, "/layers"),
        ({"max_layers": 0}, "layers", 0, 1, "/layers"),
    ],
)
def test_one_unit_over_a_limit_reports_resource_limit_and_estimate(
    overrides: dict[str, Any], resource: str, limit: int, estimated: int, pointer: str | None
) -> None:
    doc = document(layers=[[{"type": "rect", "box": [40, 32, 88, 104]}]])
    with pytest.raises(errors.BudgetExceeded) as raised:
        plan_budget(doc, RenderLimits(**overrides))
    error = raised.value
    assert (error.code, error.exit_code) == ("BUDGET_EXCEEDED", 3)
    assert dict(error.context) == {"resource": resource, "limit": limit, "estimated": estimated}
    assert error.json_pointer == pointer
    assert len(error.details) == 1


def test_many_frames_accumulate_until_the_frame_budget() -> None:
    doc = document(2048, 2048, layers=[])
    four = plan_budget(doc, frames=4)
    assert four.frame_pixels == 4 * A2048 == 16_777_216  # exactly the default budget
    assert four.pixel_visits == 4 * 3 * A2048
    assert four.buffer_bytes == 40 * A2048 + 4 * 4 * A2048  # 224 MiB <= 256 MiB
    with pytest.raises(errors.BudgetExceeded) as raised:
        plan_budget(doc, frames=5)
    assert [d.context["resource"] for d in raised.value.details] == ["frame_pixels"]


@pytest.mark.parametrize("frames", [0, -1, True, 16_777_217])
def test_frame_count_is_validated(frames: int) -> None:
    with pytest.raises(errors.ValidationError):
        estimate_cost(document(), frames=frames)


def test_deep_layer_stacks_exceed_visits_before_any_raster() -> None:
    doc = document(2048, 2048, layers=[[] for _ in range(128)])
    with pytest.raises(errors.BudgetExceeded) as raised:
        plan_budget(doc)
    detail = raised.value.details[0]
    assert dict(detail.context) == {
        "resource": "pixel_visits",
        "limit": 100_000_000,
        "estimated": 3 * A2048 + 128 * 2 * A2048,
    }
    assert detail.json_pointer is None
    host = RenderLimits(max_pixel_visits=2 * 10**9, host_override=True)
    assert plan_budget(doc, host).pixel_visits == 259 * A2048


def test_huge_coordinates_cost_their_unclipped_segments() -> None:
    line = {"type": "line", "start": [-1_048_576, -1_048_576], "end": [1_048_576, 1_048_576]}
    per_line = 2_097_153 + A128  # unclipped steps + paint of the clipped (full) bbox
    doc = document(layers=[[line] * 48])  # 48 x 2 113 537 > 100 000 000
    with pytest.raises(errors.BudgetExceeded) as raised:
        plan_budget(doc)
    detail = raised.value.details[0]
    assert detail.context["estimated"] == 5 * A128 + 48 * per_line
    assert detail.json_pointer == "/layers/0/operations/0"
    assert plan_budget(document(layers=[[line] * 47])).pixel_visits == 5 * A128 + 47 * per_line


def test_lowered_geometry_limits_reject_canvas_and_coordinates() -> None:
    doc = document(layers=[[{"type": "rect", "box": [40, 32, 88, 104]}]])
    limits = RenderLimits(geometry=GeometryLimits(max_dimension=64, max_coordinate=100))
    with pytest.raises(errors.BudgetExceeded) as raised:
        plan_budget(doc, limits)
    found = [
        (d.context["resource"], d.json_pointer, d.context["estimated"])
        for d in raised.value.details
    ]
    assert found == [
        ("canvas_dimension", "/canvas/width", 128),
        ("canvas_dimension", "/canvas/height", 128),
        ("coordinate", "/layers/0/operations/0", 103),
    ]
    area = RenderLimits(geometry=GeometryLimits(max_area=128 * 127))
    with pytest.raises(errors.BudgetExceeded) as raised:
        plan_budget(doc, area)
    assert raised.value.details[0].context["resource"] == "canvas_area"


@pytest.mark.parametrize(
    ("operation", "reach"),
    [
        ({"type": "pixel", "at": [3, -90]}, 90),
        ({"type": "line", "start": [0, 0], "end": [-95, 2]}, 95),
        ({"type": "ellipse", "box": [0, 0, 92, 5]}, 91),
        ({"type": "polygon", "points": [[0, 0], [99, 0], [0, 1]]}, 99),
    ],
)
def test_coordinate_reach_per_operation(operation: dict[str, Any], reach: int) -> None:
    limits = RenderLimits(geometry=GeometryLimits(max_coordinate=reach - 1))
    with pytest.raises(errors.BudgetExceeded) as raised:
        plan_budget(document(layers=[[operation]]), limits)
    assert raised.value.details[0].context["estimated"] == reach
    plan_budget(
        document(layers=[[operation]]), RenderLimits(geometry=GeometryLimits(max_coordinate=reach))
    )


def test_expired_deadline_stops_estimation() -> None:
    clock = iter([0.0, 10.0])
    deadline = Deadline(1, clock=lambda: next(clock))
    with pytest.raises(errors.BudgetExceeded) as raised:
        plan_budget(document(), deadline=deadline)
    assert raised.value.context["resource"] == "time"


@pytest.mark.security
def test_rejection_happens_without_allocating_raster_buffers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T1: fake allocators record any raster reservation during a rejected request."""
    import numpy as np
    from PIL import Image

    calls: list[str] = []

    def fake(name: str) -> Any:
        def allocate(*args: object, **kwargs: object) -> None:
            calls.append(name)
            raise AssertionError(f"{name} called while budgeting")

        return allocate

    for name in ("empty", "zeros", "ones", "full", "empty_like", "zeros_like", "ndarray"):
        monkeypatch.setattr(np, name, fake(f"numpy.{name}"))
    monkeypatch.setattr(Image, "new", fake("PIL.Image.new"))

    doc = document(2048, 2048, layers=[[{"type": "rect", "box": [0, 0, 2048, 2048]}] * 50])
    tracemalloc.start()
    try:
        with pytest.raises(errors.BudgetExceeded):
            plan_budget(doc, frames=4)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert calls == []
    assert peak < 1024 * 1024  # far below one 2048 x 2048 RGBA frame (16 MiB)


def test_budget_modules_do_not_load_raster_libraries() -> None:
    probe = (
        "import sys, moanart.core.budget; "
        "heavy = {'numpy', 'PIL', 'aggdraw'}; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in heavy))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, encoding="utf-8", check=True
    )
    assert result.stdout.strip() == "[]"


def test_budget_module_imports_no_raster_code() -> None:
    """``moanart.render`` now loads the rasterisers; the estimator itself never does."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(budget_module.__file__).read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            prefix = "moanart." if node.module == "moanart" else f"{node.module}."
            names += [node.module, *(prefix + alias.name for alias in node.names)]
        elif isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
    forbidden = (
        "numpy",
        "PIL",
        "aggdraw",
        "moanart.geometry",
        "moanart.layers",
        "moanart.core.canvas",
    )
    assert names
    assert not [name for name in names if name.startswith(forbidden)]


def test_estimate_is_pure_and_repeatable() -> None:
    doc = document(layers=[[{"type": "line", "start": [0, 0], "end": [9, 3]}]])
    assert estimate_cost(doc) == estimate_cost(doc)


def test_collinear_diagonal_polygon_is_an_accepted_overestimate() -> None:
    """Upper bound, not exact: the even-odd mask is empty but its bounds are costed."""
    polygon = {"type": "polygon", "points": [[0, 0], [5, 5], [10, 10]]}
    (cost,) = estimate_cost(document(layers=[[polygon]])).operation_costs
    assert (cost.pixel_visits, cost.mask_bytes) == (100 + 10 * 3 + 100, 100)


def test_counts_are_rejected_before_costing_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    import moanart.render.budget as budget

    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("operations costed after a count was already exceeded")

    monkeypatch.setattr(budget, "estimate_cost", unexpected)
    doc = document(layers=[[{"type": "pixel", "at": [0, 0]}] * 3])
    with pytest.raises(errors.BudgetExceeded) as raised:
        plan_budget(doc, RenderLimits(max_operations=2))
    assert dict(raised.value.context) == {"resource": "operations", "limit": 2, "estimated": 3}


def test_deadline_is_checked_within_long_layers() -> None:
    doc = document(layers=[[{"type": "pixel", "at": [0, 0]}] * 300])
    # clock reads: start, layer check, then op 256 already expired
    ticks = iter([0.0, 0.0] + [5.0] * 10)
    with pytest.raises(errors.BudgetExceeded) as raised:
        estimate_cost(doc, deadline=Deadline(1000, clock=lambda: next(ticks)))
    assert raised.value.context["stage"] == "estimate_operation"
    # plan: start, layer, op 256 in the estimate, then op 256 of the geometry check
    ticks = iter([0.0, 0.0, 0.0] + [5.0] * 10)
    with pytest.raises(errors.BudgetExceeded) as raised:
        plan_budget(doc, deadline=Deadline(1000, clock=lambda: next(ticks)))
    assert raised.value.context["stage"] == "check_geometry"


def test_frame_count_follows_section_17() -> None:
    small = document(4, 4, layers=[])
    assert plan_budget(small, frames=256).frame_pixels == 256 * 16
    with pytest.raises(errors.ValidationError):
        plan_budget(small, frames=257)
