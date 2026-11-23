"""render_with_regions: one validation, one budget for the render and its regions (ADR-027).

Oracles: masks written by hand as pixel sets and budget totals added up from
``plan_budget`` and ``mask_estimates`` with the formula of the module docstring.
"""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from moanart.core import errors
from moanart.core.budget import Deadline, RenderLimits
from moanart.render import plan_budget, render, render_with_regions
from moanart.render.budget import mask_estimates
from moanart.schema import Document, validate_document


def square(x0: int, y0: int, x1: int, y1: int) -> set[tuple[int, int]]:
    return {(x, y) for x in range(x0, x1) for y in range(y0, y1)}


def document() -> Document:
    source: dict[str, Any] = {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": 10, "height": 10},
        "palette": {"id": "pal", "colors": [{"id": "ink", "rgba": "#101820FF"}]},
        "masks": [
            {"id": "outer_sq", "type": "rect", "box": [2, 2, 8, 8]},
            {"id": "hole", "type": "rect", "box": [4, 4, 6, 6]},
            {"id": "shape", "type": "subtract", "masks": ["outer_sq", "hole"]},
            {"id": "dot", "type": "pixel", "at": [0, 9]},
        ],
        "regions": [
            {"id": "ring", "mask_id": "shape", "operation_ids": []},
            {"id": "spot", "mask_id": "dot", "operation_ids": []},
        ],
        "layers": [
            {
                "id": "l",
                "name": "L",
                "operations": [{"id": "r", "type": "rect", "box": [1, 1, 9, 9], "color": "ink"}],
            }
        ],
    }
    return validate_document(source)


def pixels(mask: Any) -> set[tuple[int, int]]:
    return {(p.x, p.y) for p in mask.points()}


def totals(
    doc: Document, region_masks: list[str], extra_visits: int, extra_bytes: int
) -> tuple[int, int]:
    """The admission formula, computed independently from the public estimates."""
    estimate = plan_budget(doc)
    estimates = mask_estimates(doc)
    regions = [estimates[mask_id] for mask_id in region_masks]
    visits = estimate.pixel_visits + extra_visits
    visits += sum(e.pixel_visits + (e.box.area if e.box else 0) for e in regions)
    held = 4 * 100 + extra_bytes + max(e.buffer_bytes for e in regions)
    return visits, max(estimate.buffer_bytes, held)


def test_render_and_lazy_region_masks() -> None:
    doc = document()
    result, masks = render_with_regions(doc, ["ring", "spot", "ring"])
    assert result.rgba == render(doc).rgba
    assert list(masks) == ["ring", "spot"] and len(masks) == 2  # duplicates read once
    assert pixels(masks["ring"]) == square(2, 2, 8, 8) - square(4, 4, 6, 6)
    assert pixels(masks["spot"]) == {(0, 9)}
    assert masks["ring"] == masks["ring"]  # evaluated again on every read, same pixels
    _, none = render_with_regions(doc, [])
    assert len(none) == 0


def test_unknown_region_fails_before_any_budget_or_raster() -> None:
    tiny = RenderLimits(max_pixel_visits=1)
    with pytest.raises(errors.ReferenceError) as raised:
        render_with_regions(document(), ["ghost"], limits=tiny)
    assert raised.value.context["reason"] == "unknown_region"


def test_admission_is_exact_for_the_whole_request() -> None:
    doc = document()
    visits, peak = totals(doc, ["shape", "dot"], 7, 50_000)
    request: dict[str, Any] = {"extra_visits": 7, "extra_bytes": 50_000}
    exact = RenderLimits(max_pixel_visits=visits, max_buffer_bytes=peak)
    render_with_regions(doc, ["ring", "spot"], limits=exact, **request)
    with pytest.raises(errors.BudgetExceeded) as both:
        render_with_regions(
            doc,
            ["ring", "spot"],
            limits=RenderLimits(max_pixel_visits=visits - 1, max_buffer_bytes=peak - 1),
            **request,
        )
    assert [d.context["resource"] for d in both.value.details] == ["pixel_visits", "buffer_bytes"]
    assert both.value.details[1].context["estimated"] == peak
    with pytest.raises(errors.BudgetExceeded) as one:
        render_with_regions(
            doc, ["ring", "spot"], limits=RenderLimits(max_buffer_bytes=peak - 1), **request
        )
    assert one.value.context["resource"] == "buffer_bytes" and len(one.value.details) == 1


def test_the_render_alone_is_checked_by_plan_budget() -> None:
    with pytest.raises(errors.BudgetExceeded) as raised:
        render_with_regions(document(), [], limits=RenderLimits(max_pixel_visits=10))
    assert raised.value.context["resource"] == "pixel_visits"


def test_deadline_expiring_while_a_region_is_read() -> None:
    ticks = itertools.count()
    clock_values: list[float] = []

    def clock() -> float:
        value = float(next(ticks))
        clock_values.append(value)
        return value

    deadline = Deadline(1_000_000, clock=clock)  # expires after 1000 s of fake time
    _, masks = render_with_regions(document(), ["ring"], deadline=deadline)
    for _ in range(1001):
        clock()
    with pytest.raises(errors.BudgetExceeded) as raised:
        masks["ring"]
    assert raised.value.context["resource"] == "time"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"document": {}}, "Document"),
        ({"region_ids": "ring"}, "region_ids"),
        ({"region_ids": 3}, "region_ids"),
        ({"extra_visits": -1}, "extra_visits"),
        ({"extra_bytes": True}, "extra_bytes"),
        ({"limits": 1}, "RenderLimits"),
        ({"deadline": 1}, "Deadline"),
    ],
)
def test_argument_types(arguments: dict[str, Any], message: str) -> None:
    call: dict[str, Any] = {"document": document(), "region_ids": ["ring"]} | arguments
    document_arg, ids = call.pop("document"), call.pop("region_ids")
    with pytest.raises(TypeError, match=message):
        render_with_regions(document_arg, ids, **call)
