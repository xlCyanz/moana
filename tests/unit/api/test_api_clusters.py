"""AC2 (MOANA-014): a glint kept by a region exception; the analysis never edits.

The sprite is drawn by hand on an 8 x 8 canvas: a 6 x 6 body, a one-pixel white glint
inside it (region ``eye_glint``) and a stray one-pixel dust mote outside it. Both
pixels are singletons; only the glint lies in the exception's region.
"""

from __future__ import annotations

import copy
import itertools
from functools import partial
from typing import Any

import pytest

from moanart.api import (
    AVAILABLE_FUNCTIONS,
    CLUSTER_RULES,
    ClusterException,
    analyze_clusters,
    capabilities,
    snapshot_digest,
)
from moanart.core import errors
from moanart.core.budget import Deadline, RenderLimits
from moanart.core.coordinates import Box, Point
from moanart.core.limits import MAX_CLUSTER_EXCEPTIONS
from moanart.geometry import cover_bytes
from moanart.render import plan_budget
from moanart.render.budget import mask_estimates
from moanart.schema import canonical_json, normalize_document, validate_document
from moanart.techniques import cluster_bytes

SPRITE: dict[str, Any] = {
    "schema_version": "1.0",
    "id": "glint_demo",
    "canvas": {"width": 8, "height": 8},
    "palette": {
        "id": "pal",
        "colors": [
            {"id": "skin", "rgba": "#C87828FF"},
            {"id": "glint", "rgba": "#FFFFFFFF"},
            {"id": "dust", "rgba": "#808080FF"},
        ],
    },
    "masks": [{"id": "glint_spot", "type": "pixel", "at": [3, 3]}],
    "regions": [{"id": "eye_glint", "mask_id": "glint_spot", "operation_ids": ["eye"]}],
    "layers": [
        {
            "id": "body",
            "name": "Body",
            "operations": [
                {"id": "torso", "type": "rect", "box": [1, 1, 7, 7], "color": "skin"},
                {"id": "eye", "type": "pixel", "at": [3, 3], "color": "glint"},
                {"id": "mote", "type": "pixel", "at": [7, 0], "color": "dust"},
            ],
        }
    ],
}


def document() -> Any:
    return validate_document(copy.deepcopy(SPRITE))


def test_ac2_without_exception_the_glint_warns() -> None:
    report = analyze_clusters(document())
    assert report.connectivity == 4
    assert [(c.color, c.box, c.area, c.seed) for c in report.clusters] == [
        ("#808080FF", Box(7, 0, 8, 1), 1, Point(7, 0)),
        ("#C87828FF", Box(1, 1, 7, 7), 35, Point(1, 1)),
        ("#FFFFFFFF", Box(3, 3, 4, 4), 1, Point(3, 3)),
    ]
    assert [(f.rule_id, f.box, f.region_id) for f in report.warnings] == [
        ("singleton", Box(7, 0, 8, 1), None),
        ("singleton", Box(3, 3, 4, 4), None),
    ]
    assert report.suppressed == ()


def test_ac2_region_exception_keeps_the_glint_without_warning() -> None:
    source = document()
    before = (canonical_json(source), snapshot_digest(source), normalize_document(source))
    report = analyze_clusters(
        source, exceptions=[ClusterException("eye_glint", ("singleton",))], connectivity=8
    )
    assert [f.box for f in report.warnings] == [Box(7, 0, 8, 1)]  # the dust still warns
    (kept,) = report.suppressed
    assert (kept.rule_id, kept.box, kept.region_id) == ("singleton", Box(3, 3, 4, 4), "eye_glint")
    assert report.clusters[2].area == 1  # the glint is still there: no cleanup
    assert (canonical_json(source), snapshot_digest(source), normalize_document(source)) == before


def test_unknown_region_and_wrong_document() -> None:
    with pytest.raises(errors.ReferenceError) as raised:
        analyze_clusters(document(), exceptions=[ClusterException("nose", CLUSTER_RULES)])
    assert raised.value.context["reason"] == "unknown_region"
    with pytest.raises(TypeError, match="Document"):
        analyze_clusters(SPRITE)  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError):
        analyze_clusters(document(), exceptions=["eye_glint"])  # type: ignore[list-item]  # invalid on purpose


def test_render_budgets_apply_to_the_analysis() -> None:
    with pytest.raises(errors.BudgetExceeded):
        analyze_clusters(document(), limits=RenderLimits(max_pixel_visits=10))


def test_facade_lists_the_analysis_and_the_outline() -> None:
    assert "analyze_clusters" in AVAILABLE_FUNCTIONS
    listing = capabilities()
    assert "analyze_clusters" in listing.functions and "outline" in listing.operations


def test_example_outlined_slime_keeps_its_glints_by_exception() -> None:
    """examples/specs/outlined-slime.moanart.json: two glints, both in ``eye_glints``."""
    from pathlib import Path

    from moanart.api import load_document

    example = Path(__file__).resolve().parents[3] / "examples/specs/outlined-slime.moanart.json"
    slime = load_document(example)
    glints = [Box(8, 13, 9, 14), Box(14, 13, 15, 14)]
    assert [f.box for f in analyze_clusters(slime).warnings] == glints
    report = analyze_clusters(slime, exceptions=[ClusterException("eye_glints", ("singleton",))])
    assert report.warnings == () and [f.box for f in report.suppressed] == glints


TINY = RenderLimits(max_pixel_visits=1, max_buffer_bytes=1)


@pytest.mark.parametrize(
    ("settings", "reason"),
    [
        ({"connectivity": 6}, "unsupported_connectivity"),
        (
            {"exceptions": [ClusterException("eye_glint", ("singleton",))] * 2},
            "duplicate_reference",
        ),
        (
            {
                "exceptions": [
                    ClusterException(f"r{i}", ("singleton",))
                    for i in range(MAX_CLUSTER_EXCEPTIONS + 1)
                ]
            },
            "too_many_exceptions",
        ),
    ],
)
def test_settings_fail_before_validation_and_rendering(
    settings: dict[str, Any], reason: str
) -> None:
    """With limits no render could meet, the settings error still comes first."""
    with pytest.raises(errors.ValidationError) as raised:
        analyze_clusters(document(), limits=TINY, **settings)
    assert raised.value.context["reason"] == reason


def test_unknown_region_fails_before_rendering() -> None:
    with pytest.raises(errors.ReferenceError) as raised:
        analyze_clusters(
            document(), exceptions=[ClusterException("nose", ("singleton",))], limits=TINY
        )
    assert raised.value.context["reason"] == "unknown_region"


def test_one_budget_covers_render_regions_cover_and_analysis() -> None:
    source = document()
    dims = source.canvas.dimensions
    region = mask_estimates(source)["glint_spot"]
    render_estimate = plan_budget(source)
    held = 4 * dims.area + cluster_bytes(dims) + cover_bytes(dims) + region.buffer_bytes
    visits = render_estimate.pixel_visits + region.pixel_visits + 1 + 2 * dims.area
    exceptions = [ClusterException("eye_glint", ("singleton",))]
    exact = RenderLimits(
        max_pixel_visits=visits, max_buffer_bytes=max(held, render_estimate.buffer_bytes)
    )
    assert analyze_clusters(source, exceptions=exceptions, limits=exact).suppressed
    with pytest.raises(errors.BudgetExceeded) as raised:
        analyze_clusters(
            source,
            exceptions=exceptions,
            limits=RenderLimits(max_pixel_visits=visits - 1, max_buffer_bytes=held - 1),
        )
    assert [d.context["estimated"] for d in raised.value.details] == [visits, held]


def next_tick(ticks: itertools.count[int]) -> float:
    return float(next(ticks))


def test_deadline_reaches_the_regions_and_the_analysis() -> None:
    stages = []
    for call in itertools.count(1):
        deadline = Deadline(1000 * call, clock=partial(next_tick, itertools.count()))
        try:
            analyze_clusters(
                document(),
                exceptions=[ClusterException("eye_glint", ("singleton",))],
                deadline=deadline,
            )
        except errors.BudgetExceeded as raised:
            stages.append(raised.context["stage"])
            continue
        break
    assert "mask_cover" in stages and "cluster_findings" in stages
    assert stages.index("mask_cover") < stages.index("cluster_runs")
