"""modelo → plan and plan → raster: budgets reject before any buffer (T1, T2, AC2).

Every oracle is a lower bound computed by hand from MOANART.md sections 5, 6 and 20,
never the estimator's output: a W x H RGBA canvas needs at least ``4·W·H`` bytes and
``W·H`` visits to be cleared; a Bresenham line visits ``max(|dx|, |dy|) + 1`` pixels
before clipping; an animation of ``n`` frames accumulates ``n·W·H`` frame pixels; an
export at scale ``s`` needs at least ``4·(s·W)·(s·H)`` bytes for its pixels. When the
lower bound already exceeds the limit, the request must fail with ``BudgetExceeded``
while the allocation tripwire is armed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from moanart.animation import render_animation
from moanart.api import Deadline, RenderLimits, export_png, load_document, render
from moanart.core.errors import BudgetExceeded, ValidationError
from moanart.core.limits import GeometryLimits
from moanart.schema import Document

from .corpus import ROOT, minimal_tree
from .guards import (
    assert_bounded,
    assert_clean_error,
    bounded_settings,
    forbid_allocation,
    forbid_effects,
    measure,
    peak_bytes,
    pointers,
    reasons,
    tree_state,
)

pytestmark = pytest.mark.security

BOUNDED = bounded_settings(30)
MAX_COORDINATE = 1_048_576  # MOANART.md section 5


def _tree(width: int = 128, height: int = 128) -> dict[str, Any]:
    tree = minimal_tree()
    tree["canvas"] = {"width": width, "height": height, "profile": "strict"}
    tree["layers"][0]["operations"][0]["box"] = [0, 0, width, height]
    return tree


def _resource(error: BudgetExceeded) -> set[object]:
    found = {error.context.get("resource")}
    found.update(detail.context.get("resource") for detail in error.details)
    return found


@BOUNDED
@given(st.integers(1, 2048), st.integers(1, 2048), st.data())
def test_t2_property_canvas_over_the_byte_budget_never_allocates(
    width: int, height: int, data: st.DataObject
) -> None:
    lower_bound = 4 * width * height
    limit = data.draw(st.integers(1, lower_bound - 1))
    document = load_document(_tree(width, height))
    with forbid_allocation(), pytest.raises(BudgetExceeded) as caught:
        render(document, limits=RenderLimits(max_buffer_bytes=limit))
    assert "buffer_bytes" in _resource(caught.value)


@BOUNDED
@given(st.integers(1, 2048), st.integers(1, 2048), st.data())
def test_t2_property_canvas_over_the_visit_budget_never_allocates(
    width: int, height: int, data: st.DataObject
) -> None:
    assume(width * height > 1)
    limit = data.draw(st.integers(1, width * height - 1))
    document = load_document(_tree(width, height))
    with forbid_allocation(), pytest.raises(BudgetExceeded) as caught:
        render(document, limits=RenderLimits(max_pixel_visits=limit))
    assert "pixel_visits" in _resource(caught.value)


def test_t1_huge_unclipped_lines_are_charged_before_clipping() -> None:
    tree = _tree(16, 16)
    span = MAX_COORDINATE
    line = {"type": "line", "start": [-span, 0], "end": [span, 0], "color": "ink"}
    count = 64  # 64 x (2·span + 1) > 1.3e8 > 1e8 default visits
    tree["layers"][0]["operations"] = [{**line, "id": f"line_{i}"} for i in range(count)]
    document = load_document(tree)
    assert count * (2 * span + 1) > 100_000_000
    with forbid_allocation(), pytest.raises(BudgetExceeded) as caught:
        render(document)
    assert "pixel_visits" in _resource(caught.value)


def test_t1_coordinates_beyond_the_contract_are_rejected_by_the_model() -> None:
    tree = _tree(16, 16)
    tree["layers"][0]["operations"][0]["box"] = [0, 0, MAX_COORDINATE + 2, 1]
    with forbid_effects(), pytest.raises(ValidationError) as caught:
        load_document(tree)
    assert_clean_error(caught.value)
    assert "/layers/0/operations/0/box/2" in pointers(caught.value)
    (detail,) = caught.value.details
    assert detail.context["le"] == MAX_COORDINATE + 1  # an excluded edge may reach max + 1


def test_t1_canvas_area_beyond_the_contract_is_rejected_by_the_model() -> None:
    tree = _tree(16, 16)
    tree["canvas"]["width"] = 2049  # MOANART.md section 5: 2048 per axis
    with forbid_effects(), pytest.raises(ValidationError) as caught:
        load_document(tree)
    assert_clean_error(caught.value)
    (detail,) = caught.value.details
    assert (detail.json_pointer, detail.context["le"]) == ("/canvas/width", 2048)


def test_t2_lowered_geometry_limits_reject_before_allocation() -> None:
    document = load_document(_tree(256, 256))
    limits = RenderLimits(geometry=GeometryLimits(max_dimension=128))
    with forbid_allocation(), pytest.raises(BudgetExceeded) as caught:
        render(document, limits=limits)
    assert_clean_error(caught.value)
    found = {
        (d.json_pointer, d.context["resource"], d.context["estimated"])
        for d in caught.value.details
    }
    assert found == {
        ("/canvas/width", "canvas_dimension", 256),
        ("/canvas/height", "canvas_dimension", 256),
    }


def test_t2_operation_count_is_budgeted_before_rasterising() -> None:
    tree = _tree(16, 16)
    operation = tree["layers"][0]["operations"][0]
    tree["layers"][0]["operations"] = [{**operation, "id": f"op_{i}"} for i in range(11)]
    document = load_document(tree)
    with forbid_allocation(), pytest.raises(BudgetExceeded) as caught:
        render(document, limits=RenderLimits(max_operations=10))
    assert "operations" in _resource(caught.value)


def test_t2_budget_cannot_be_raised_by_a_request_without_the_host() -> None:
    with pytest.raises(ValidationError) as caught:
        RenderLimits(max_buffer_bytes=256 * 1024 * 1024 + 1)
    assert_clean_error(caught.value)
    assert reasons(caught.value) == {"out_of_range"}
    assert caught.value.context["field"] == "max_buffer_bytes"
    assert caught.value.context["maximum"] == 256 * 1024 * 1024
    raised = RenderLimits(max_buffer_bytes=256 * 1024 * 1024 + 1, host_override=True)
    assert raised.max_buffer_bytes > 256 * 1024 * 1024


def test_t2_expired_deadline_stops_before_any_buffer() -> None:
    document = load_document(_tree(64, 64))
    ticks = iter([0.0])  # created at t = 0, every later reading is far past the budget

    def clock() -> float:
        return next(ticks, 3600.0)

    with forbid_allocation(), pytest.raises(BudgetExceeded) as caught:
        render(document, deadline=Deadline(1, clock=clock))
    assert caught.value.context["resource"] == "time"


def test_t2_hostile_canvas_is_rejected_within_bounded_memory() -> None:
    document = load_document(_tree(2048, 2048))  # 16 MiB of RGBA if it were allocated
    error, peak = peak_bytes(
        lambda: render(document, limits=RenderLimits(max_buffer_bytes=1024 * 1024))
    )
    assert isinstance(error, BudgetExceeded)
    assert peak < 1024 * 1024  # the rejection costs far less than the refused buffer


# --- animations: accumulated frames ----------------------------------------------------


def _slime() -> Document:
    return load_document(ROOT / "examples/specs/bouncing-slime.moanart.json")


def test_t2_animation_over_the_frame_budget_renders_no_frame() -> None:
    document = _slime()
    animation = document.animations[0]
    frames = len(animation.frames)
    pixels = document.canvas.width * document.canvas.height
    limits = RenderLimits(max_frame_pixels=frames * pixels - 1)
    with forbid_allocation(), pytest.raises(BudgetExceeded) as caught:
        render_animation(document, animation.id, limits=limits)
    assert "frame_pixels" in _resource(caught.value)
    single = RenderLimits(max_frame_pixels=pixels - 1)
    with forbid_allocation(), pytest.raises(BudgetExceeded):
        render(document, frame_id=animation.frames[0].id, limits=single)


# --- export: the scaled image is budgeted before Pillow and before the file -----------


@pytest.mark.parametrize("scale", [8, 64])
def test_t2_export_over_budget_writes_nothing_and_allocates_nothing(
    tmp_path: Path, scale: int
) -> None:
    result = render(load_document(_tree(128, 128)))
    lower_bound = 4 * (128 * scale) ** 2
    limits = RenderLimits(max_buffer_bytes=lower_bound - 1)
    destination = tmp_path / "out.png"
    before = tree_state(tmp_path)
    with forbid_effects():
        rejection = measure(lambda: export_png(result, destination, scale=scale, limits=limits))
    error = assert_clean_error(assert_bounded(rejection), tmp_path)
    assert isinstance(error, BudgetExceeded)
    assert tree_state(tmp_path) == before
    assert not destination.exists()
