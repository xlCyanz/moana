"""Sequence rendering under one accumulated budget (MOANA-022 T1, AC2; ADR-032).

Expected totals are composed by hand from MOANA.md section 20 and ADR-032 (sum of
visits, sum of frame areas, largest working peak plus every retained RGBA), with the
per-frame inputs taken from the single-frame estimator that ADR-018 already fixes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from moana.core import errors
from moana.core.budget import Deadline, RenderLimits
from moana.render import (
    RESULT_OVERHEAD_BYTES,
    SequenceBudget,
    admit_sequence,
    estimate_cost,
    plan_frame,
    render,
    render_admitted,
    render_sequence,
)
from moana.render import sequence as sequence_module
from moana.schema import Document, validate_document


def document(width: int, layers: int = 1, color: str = "#FF0000FF") -> Document:
    return validate_document(
        {
            "schema_version": "1.0",
            "id": "doc",
            "canvas": {"width": width, "height": width},
            "palette": {"id": "pal", "colors": [{"id": "c", "rgba": color}]},
            "layers": [
                {
                    "id": f"l{i}",
                    "name": "L",
                    "operations": [
                        {"id": f"o{i}", "type": "rect", "color": "c", "box": [0, 0, 2, 2]}
                    ],
                }
                for i in range(layers)
            ],
        }
    )


def test_t1_results_follow_the_given_order_with_frame_ids() -> None:
    red, blue = document(4), document(4, color="#0000FFFF")
    results = render_sequence([("b", blue), ("a", red)])
    assert [r.provenance.frame_id for r in results] == ["b", "a"]
    assert results[0].rgba == render(blue).rgba
    assert results[1].rgba == render(red).rgba
    assert results[0].pixel(0, 0) == (0, 0, 255, 255)


def test_t1_accumulated_totals_are_checked_against_one_budget() -> None:
    small, large = document(4), document(8, layers=3)
    e_small, e_large = estimate_cost(small), estimate_cost(large)
    visits = e_small.pixel_visits + e_large.pixel_visits
    pixels = 16 + 64
    retained = 4 * pixels + 2 * RESULT_OVERHEAD_BYTES
    peak = max(e_small.buffer_bytes - 4 * 16, e_large.buffer_bytes - 4 * 64) + retained
    exact = RenderLimits(max_pixel_visits=visits, max_buffer_bytes=peak, max_frame_pixels=pixels)
    assert len(render_sequence([("s", small), ("l", large)], limits=exact)) == 2
    assert admit_sequence([e_small, e_large], limits=exact) == SequenceBudget(
        frames=2, pixel_visits=visits, buffer_bytes=peak, frame_pixels=pixels
    )
    tight = RenderLimits(
        max_pixel_visits=visits - 1, max_buffer_bytes=peak - 1, max_frame_pixels=pixels - 1
    )
    with pytest.raises(errors.BudgetExceeded) as raised:
        render_sequence([("s", small), ("l", large)], limits=tight)
    assert [dict(d.context) for d in raised.value.details] == [
        {"resource": "pixel_visits", "limit": visits - 1, "estimated": visits, "frames": 2},
        {"resource": "buffer_bytes", "limit": peak - 1, "estimated": peak, "frames": 2},
        {"resource": "frame_pixels", "limit": pixels - 1, "estimated": pixels, "frames": 2},
    ]
    assert raised.value.message == "sequence exceeds 3 budgets"
    with pytest.raises(errors.BudgetExceeded) as raised:
        render_sequence([("s", small), ("l", large)], limits=RenderLimits(max_frame_pixels=79))
    assert raised.value.message == "sequence exceeds 1 budget"


def test_ac2_a_frame_over_budget_alone_names_its_index_and_renders_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(sequence_module, "_render_validated", lambda *a: calls.append(a))
    frames = [("a", document(4)), ("b", document(4, layers=3))]
    with pytest.raises(errors.BudgetExceeded) as raised:
        render_sequence(frames, limits=RenderLimits(max_layers=2))
    assert raised.value.context["frame_index"] == 1
    assert raised.value.context["resource"] == "layers"
    assert calls == []


def bad_frames() -> list[Any]:
    doc = document(2)
    return [
        "ab",
        b"ab",
        5,
        [("a", doc, 1)],
        [["a", doc]],
        [(1, doc)],
        [("Bad ID", doc)],
        [("a", {})],
    ]


@pytest.mark.parametrize("frames", bad_frames())
def test_t1_malformed_sequences_are_type_errors(frames: Any) -> None:
    with pytest.raises(TypeError):
        render_sequence(frames)


def test_t1_sequence_length_and_unique_ids() -> None:
    doc = document(2)
    with pytest.raises(ValueError, match=r"1\.\.256"):
        render_sequence([])
    with pytest.raises(ValueError, match=r"1\.\.256"):
        render_sequence([(f"f{i}", doc) for i in range(257)])
    with pytest.raises(ValueError, match="unique"):
        render_sequence([("a", doc), ("a", doc)])
    with pytest.raises(TypeError):
        render_sequence([("a", doc)], limits=5)  # type: ignore[arg-type]


def test_t1_the_length_is_checked_before_any_pair() -> None:
    # 257 malformed pairs: the length is rejected before a pair is inspected.
    with pytest.raises(ValueError, match=r"1\.\.256"):
        render_sequence([5] * 257)  # type: ignore[list-item]


def test_t1_plan_frame_estimates_without_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(sequence_module, "_render_validated", lambda *a: calls.append(a))
    doc = document(4, layers=3)
    assert plan_frame(doc) == estimate_cost(doc)
    with pytest.raises(errors.BudgetExceeded) as alone:
        plan_frame(doc, limits=RenderLimits(max_layers=2))
    assert "frame_index" not in alone.value.context
    with pytest.raises(errors.BudgetExceeded) as indexed:
        plan_frame(doc, limits=RenderLimits(max_layers=2), frame_index=7)
    assert indexed.value.context["frame_index"] == 7
    assert indexed.value.context["resource"] == "layers"
    with pytest.raises(TypeError):
        plan_frame(doc, frame_index=True)
    assert calls == []


def test_t1_admit_sequence_checks_its_arguments() -> None:
    estimate = estimate_cost(document(2))
    calls: list[Callable[[], object]] = [
        lambda: admit_sequence("ab"),  # type: ignore[arg-type]
        lambda: admit_sequence(5),  # type: ignore[arg-type]
        lambda: admit_sequence([estimate, 5]),  # type: ignore[list-item]
        lambda: admit_sequence([estimate], limits=5),  # type: ignore[arg-type]
    ]
    for call in calls:
        with pytest.raises(TypeError):
            call()
    for estimates in ([], [estimate] * 257):
        with pytest.raises(ValueError, match=r"1\.\.256"):
            admit_sequence(estimates)
    budget = admit_sequence([estimate] * 256)
    assert budget.frames == 256
    assert budget.buffer_bytes == (
        estimate.buffer_bytes + 255 * (4 * 4) + 256 * RESULT_OVERHEAD_BYTES
    )


def test_t1_render_admitted_renders_only_the_admitted_document() -> None:
    red, blue = document(4), document(4, color="#0000FFFF")
    big = document(4, layers=2)
    estimate = plan_frame(red)
    result = render_admitted(red, frame_id="f", estimate=estimate)
    assert result.rgba == render(red).rgba
    assert result.provenance.frame_id == "f"
    # Same geometry and cost: another colour is still the admitted estimate.
    assert render_admitted(blue, frame_id="f", estimate=estimate).pixel(0, 0) == (0, 0, 255, 255)
    with pytest.raises(ValueError, match="not the one admitted"):
        render_admitted(big, frame_id="f", estimate=estimate)
    calls: list[Callable[[], object]] = [
        lambda: render_admitted(red, frame_id="Bad ID", estimate=estimate),
        lambda: render_admitted(red, frame_id=1, estimate=estimate),  # type: ignore[arg-type]
        lambda: render_admitted(red, frame_id="f", estimate=5),  # type: ignore[arg-type]
        lambda: render_admitted({}, frame_id="f", estimate=estimate),  # type: ignore[arg-type]
    ]
    for call in calls:
        with pytest.raises(TypeError):
            call()


def test_t1_deadline_is_checked_before_validating_each_frame() -> None:
    red = document(4)
    estimate = plan_frame(red)
    live = Deadline(60_000)
    assert render_admitted(red, frame_id="f", estimate=estimate, deadline=live).rgba == (
        render(red).rgba
    )
    assert len(render_sequence([("a", red), ("b", red)], deadline=live)) == 2
    expired = Deadline(1, clock=iter([0.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]).__next__)
    with pytest.raises(errors.BudgetExceeded) as caught:
        render_admitted(red, frame_id="f", estimate=estimate, deadline=expired)
    assert caught.value.context["stage"] == "validate_frame"
