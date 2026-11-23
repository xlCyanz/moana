"""MOANA-026: ``moanart.api.evaluate_quality`` composes render, regions, animation and quality."""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import moanart.api.quality as quality_facade
import moanart.render.regions as render_regions
from moanart.animation import evaluate_animation, render_animation
from moanart.api import (
    AVAILABLE_FUNCTIONS,
    QualityConfig,
    QualityReport,
    RegionSettings,
    Suppression,
    capabilities,
    evaluate_quality,
    load_document,
    snapshot_digest,
)
from moanart.core.budget import RenderLimits
from moanart.core.coordinates import Box
from moanart.core.errors import BudgetExceeded, ReferenceError
from moanart.quality import QUALITY_RULES, quality_cost
from moanart.render import admit_sequence, plan_frame, render

ROOT = Path(__file__).resolve().parents[3]
SLIME = ROOT / "examples/specs/bouncing-slime.moanart.json"
EYES = ROOT / "examples/specs/masked-eyes.moanart.json"


def text(report: QualityReport) -> str:
    return json.dumps(report.to_mapping(), sort_keys=True, separators=(",", ":"))


def changed(first: bytes, second: bytes) -> int:
    """Pixels whose normalised RGBA differs (independent oracle over raw bytes)."""
    count = 0
    for offset in range(0, len(first), 4):
        a, b = first[offset : offset + 4], second[offset : offset + 4]
        a = bytes(4) if a[3] == 0 else a
        b = bytes(4) if b[3] == 0 else b
        count += a != b
    return count


def opaque_union(first: bytes, second: bytes) -> int:
    """Pixels with alpha > 0 in either image (independent oracle over raw bytes)."""
    return sum(1 for offset in range(3, len(first), 4) if first[offset] or second[offset])


def test_t2_temporal_stability_of_the_bouncing_slime() -> None:
    document = load_document(SLIME)
    config = QualityConfig(rules=QUALITY_RULES, max_changed_permille=500)
    report = evaluate_quality(document, config=config, animation_id="bounce")
    animation = render_animation(document, "bounce")
    rendered = animation.frames
    rows = report.frame_metrics
    assert [m.frame_id for m in rows] == [f.frame_id for f in rendered]
    assert [m.digest for m in rows] == [f.result.digest for f in rendered]
    area = document.canvas.width * document.canvas.height
    expected = [None] + [
        changed(a.result.rgba, b.result.rgba) for a, b in itertools.pairwise(rendered)
    ]
    assert [m.changed_pixels for m in rows] == expected
    assert [m.changed_permille for m in rows] == [
        None if value is None else value * 1000 // area for value in expected
    ]
    # loop_count 0 plays forever: the seam fall -> rest is compared too.
    assert animation.loop_count == 0
    pairs = [*itertools.pairwise(rendered), (rendered[-1], rendered[0])]
    oracle = set()
    for before, after in pairs:
        moved = changed(before.result.rgba, after.result.rgba)
        union = opaque_union(before.result.rgba, after.result.rgba)
        if moved * 1000 // union > 500:
            oracle.add((after.frame_id, before.frame_id, moved, moved * 1000 // union, union))
    temporal = {
        (
            f.frame_id,
            dict(f.evidence)["previous_frame_id"],
            dict(f.evidence)["changed_pixels"],
            dict(f.evidence)["changed_permille"],
            dict(f.evidence)["opaque_union"],
        )
        for f in report.findings
        if f.rule_id == "temporal_change"
    }
    assert temporal == oracle and len(oracle) == 4  # every step moves over half the sprite
    assert ("rest", "fall", 143, 871, 164) in temporal  # the seam
    assert [f for f in report.findings if f.rule_id == "temporal_flicker"] == []
    assert report.passed_hard_checks
    assert report.image_digest == render(document).digest
    default = evaluate_quality(document, animation_id="bounce")
    assert [f for f in default.findings if f.rule_id.startswith("temporal")] == []


def test_unknown_animation_is_rejected_before_any_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def never(*args: object, **kwargs: object) -> None:
        raise AssertionError("rendered")

    monkeypatch.setattr(quality_facade, "render_with_regions", never)
    with pytest.raises(ReferenceError) as caught:
        evaluate_quality(load_document(SLIME), animation_id="jump")
    assert caught.value.context["reason"] == "unknown_animation"


def test_whole_request_is_admitted_against_one_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    document = load_document(SLIME)
    config = QualityConfig()
    base = plan_frame(document)
    frames = evaluate_animation(document, "bounce")
    sequence = admit_sequence([plan_frame(item.document) for item in frames])
    quality = quality_cost(document.canvas.dimensions, config, len(frames))
    total = base.pixel_visits + sequence.pixel_visits + quality[0]
    limit = total - 1
    assert max(base.pixel_visits, sequence.pixel_visits, quality[0]) < limit  # each fits

    def never(*args: object, **kwargs: object) -> None:
        raise AssertionError("rendered")

    monkeypatch.setattr(render_regions, "_render_validated", never)
    monkeypatch.setattr(quality_facade, "render_animation", never)
    with pytest.raises(BudgetExceeded) as caught:
        evaluate_quality(
            document,
            config=config,
            animation_id="bounce",
            limits=RenderLimits(max_pixel_visits=limit),
        )
    assert caught.value.context["resource"] == "pixel_visits"
    assert caught.value.context["estimated"] == total
    monkeypatch.undo()
    exact = evaluate_quality(
        document, config=config, animation_id="bounce", limits=RenderLimits(max_pixel_visits=total)
    )
    assert exact.passed_hard_checks


def test_frame_pixels_of_base_and_animation_are_admitted_together() -> None:
    document = load_document(SLIME)
    area = document.canvas.width * document.canvas.height  # 256; four frames
    with pytest.raises(BudgetExceeded) as caught:
        evaluate_quality(
            document, animation_id="bounce", limits=RenderLimits(max_frame_pixels=5 * area - 1)
        )
    assert caught.value.context == {
        "resource": "frame_pixels",
        "limit": 5 * area - 1,
        "estimated": 5 * area,
    }
    report = evaluate_quality(
        document, animation_id="bounce", limits=RenderLimits(max_frame_pixels=5 * area)
    )
    assert len(report.frame_metrics) == 4


def test_quality_never_modifies_the_document() -> None:
    document = load_document(EYES)
    before = (snapshot_digest(document), document.model_dump(mode="json"))
    config = QualityConfig(
        regions=(RegionSettings("eye_left"),),
        suppressions=(Suppression("singleton", "eye_right"),),
        containment=("eyes_region",),
    )
    first = evaluate_quality(document, config=config)
    assert (snapshot_digest(document), document.model_dump(mode="json")) == before
    assert text(first) == text(evaluate_quality(document, config=config))
    assert [m.region_id for m in first.region_metrics] == ["eye_left"]
    # the face lies outside the eyes: containment of the eyes alone fails, as it must
    (outside,) = first.errors
    assert outside.rule_id == "outside_mask" and outside.bbox == Box(1, 1, 15, 15)


def test_facade_errors() -> None:
    document = load_document(EYES)
    with pytest.raises(TypeError):
        evaluate_quality(EYES)  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError):
        evaluate_quality(document, config={})  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError):
        evaluate_quality(document, animation_id=3)  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(ReferenceError) as missing:
        evaluate_quality(document, config=QualityConfig(containment=("nose",)))
    assert missing.value.context["reason"] == "unknown_region"
    with pytest.raises(TypeError):
        evaluate_quality(document, limits=5)  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(BudgetExceeded):
        evaluate_quality(document, limits=RenderLimits(max_pixel_visits=100))


def test_listed_as_available() -> None:
    assert "evaluate_quality" in AVAILABLE_FUNCTIONS
    assert "evaluate_quality" in capabilities().functions


SCRIPT = """
import json, sys
from moanart.api import evaluate_quality, load_document
report = evaluate_quality(load_document(sys.argv[1]), animation_id="bounce")
print(json.dumps(report.to_mapping(), sort_keys=True, separators=(",", ":")))
"""


def test_ac2_report_is_identical_across_processes_and_hash_seeds() -> None:
    outputs = set()
    for seed in ("0", "1234"):
        environment = {**os.environ, "PYTHONHASHSEED": seed}
        completed = subprocess.run(
            [sys.executable, "-c", SCRIPT, str(SLIME)],
            capture_output=True,
            check=True,
            encoding="utf-8",
            env=environment,
        )
        outputs.add(completed.stdout.strip())
    local = text(evaluate_quality(load_document(SLIME), animation_id="bounce"))
    assert outputs == {local}
