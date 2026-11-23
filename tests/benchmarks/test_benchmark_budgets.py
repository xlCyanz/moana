"""AC2: adverse cases keep the safety budgets although they would miss every target.

Each case must raise ``BudgetExceeded`` with its resource before the rasteriser runs
and with a Python heap peak far below one RGBA buffer of its canvas. No latency is
asserted.
"""

from __future__ import annotations

from typing import Any

import pytest

from moanart import api
from moanart.animation import evaluate_animation
from moanart.core import BudgetExceeded, RenderLimits
from moanart.core.budget import DEFAULT_MAX_FRAME_PIXELS, DEFAULT_MAX_PIXEL_VISITS
from moanart.render import plan_frame
from moanart.schema import validate_document

from . import adversarial
from .corpus import canonical_bytes, static_document

pytestmark = [pytest.mark.benchmark, pytest.mark.security]

CANVAS_AREA = 2048 * 2048


@pytest.fixture(scope="module")
def cases() -> dict[str, Any]:
    return adversarial.budget_cases()


def _fails_fast(case: dict[str, Any]) -> None:
    assert case["rejected"] is True and case["error_code"] == "BUDGET_EXCEEDED"
    assert case["rasterize_calls"] == 0
    assert case["tracemalloc_peak_bytes"] < adversarial.canvas_bytes() // 4


def test_ac2_oversized_static_is_rejected_on_pixel_visits(cases: dict[str, Any]) -> None:
    case = cases["oversized_static"]
    _fails_fast(case)
    assert case["resources"] == ["pixel_visits"]
    assert case["context"]["limit"] == DEFAULT_MAX_PIXEL_VISITS
    # 512 full-canvas rects: raster plus paint pass alone are 2 x 512 x A visits.
    assert case["context"]["estimated"] > 2 * 512 * CANVAS_AREA


def test_ac2_operation_budget_rejects_the_benchmark_corpus(cases: dict[str, Any]) -> None:
    case = cases["operations_over_limit"]
    _fails_fast(case)
    assert case["context"] == {"resource": "operations", "limit": 499, "estimated": 500}


def test_ac2_cumulative_animation_budget_is_checked_before_any_frame(
    cases: dict[str, Any],
) -> None:
    case = cases["cumulative_animation"]
    _fails_fast(case)
    assert case["resources"] == ["buffer_bytes", "frame_pixels", "pixel_visits"]
    assert case["context"]["frames"] == 16


def test_ac2_every_frame_alone_fits_the_budget() -> None:
    document = validate_document(canonical_bytes(adversarial.cumulative_animation()))
    estimates = [plan_frame(f.document) for f in evaluate_animation(document, "huge_loop")]
    assert len(estimates) == 16
    assert all(e.frame_pixels == CANVAS_AREA <= DEFAULT_MAX_FRAME_PIXELS for e in estimates)
    assert sum(e.frame_pixels for e in estimates) == 16 * CANVAS_AREA > DEFAULT_MAX_FRAME_PIXELS


def test_ac2_the_budget_error_reaches_the_public_facade() -> None:
    document = validate_document(canonical_bytes(static_document()))
    with pytest.raises(BudgetExceeded) as raised:
        api.render(document, limits=RenderLimits(max_buffer_bytes=1024))
    assert raised.value.context["resource"] == "buffer_bytes"


def test_ac2_a_request_within_budget_is_not_reported_as_rejected() -> None:
    document = validate_document(canonical_bytes(static_document()))
    assert adversarial.rejection(lambda: api.render(document)) == {
        "rejected": False,
        "rasterize_calls": 500,
    }
