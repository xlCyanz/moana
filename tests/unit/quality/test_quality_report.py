"""T2/AC2 (MOANA-026): suppression, overlapping regions, order, non-mutation, limits.

Oracles are hand-made sprites whose findings are counted by hand; ordering and
reproducibility compare serialised reports byte for byte.
"""

from __future__ import annotations

import json
import random
import tracemalloc
from collections.abc import Callable

import pytest

from moanart.core.budget import Deadline, RenderLimits
from moanart.core.coordinates import Box, Dimensions
from moanart.core.digest import visual_digest
from moanart.core.errors import BudgetExceeded, ReferenceError, ValidationError
from moanart.geometry import Mask, rasterize_rect
from moanart.palette import Palette
from moanart.quality import (
    EXPLANATIONS,
    MAX_QUALITY_FINDINGS,
    MIN_LISTED_PER_RULE,
    QUALITY_RULES,
    SOFT_RULES,
    QualityConfig,
    QualityFinding,
    QualityReport,
    RegionSettings,
    Suppression,
    evaluate_quality,
    finding_sort_key,
    quality_cost,
)
from tests.fixtures.quality import (
    BODY,
    CANVAS,
    PALETTE,
    SPECKLED,
    STAIR,
    Frame,
    Raster,
    frames,
    raster,
)

EYES = [
    "........",
    ".ssssss.",
    ".slsslx.",
    ".ssssss.",
    "........",
]  # light pixels at (2, 2) and (5, 2), an off-palette pixel at (6, 2)
EYES_CANVAS = Dimensions(8, 5)
EYE_REGIONS: dict[str, Mask] = {
    "eye_left": rasterize_rect(Box(1, 1, 4, 4), EYES_CANVAS),
    "eye_right": rasterize_rect(Box(4, 1, 7, 4), EYES_CANVAS),
}


def eyes(config: QualityConfig) -> QualityReport:
    return evaluate_quality(
        raster(EYES), canvas=EYES_CANVAS, palette=PALETTE, config=config, regions=EYE_REGIONS
    )


def text(report: QualityReport) -> str:
    return json.dumps(report.to_mapping(), sort_keys=True, separators=(",", ":"))


def boxes(findings: tuple[QualityFinding, ...], rule: str) -> list[Box]:
    return [f.bbox for f in findings if f.rule_id == rule]


# --- AC2: suppression of one eye --------------------------------------------------


def test_ac2_suppressing_one_eye_hides_only_that_eye() -> None:
    report = eyes(QualityConfig(suppressions=(Suppression("singleton", "eye_left"),)))
    assert boxes(report.suppressed, "singleton") == [Box(2, 2, 3, 3)]
    assert report.suppressed[0].suppressed_by == "eye_left"
    assert boxes(report.findings, "singleton") == [Box(5, 2, 6, 3), Box(6, 2, 7, 3)]
    assert boxes(report.findings, "palette_strict") == [Box(6, 2, 7, 3)]
    assert all(f.suppressed_by is None for f in report.findings)


def test_ac2_errors_in_a_suppressed_region_stay_active() -> None:
    config = QualityConfig(suppressions=(Suppression("singleton", "eye_right"),))
    report = eyes(config)
    assert boxes(report.suppressed, "singleton") == [Box(5, 2, 6, 3), Box(6, 2, 7, 3)]
    assert boxes(report.findings, "singleton") == [Box(2, 2, 3, 3)]
    assert boxes(report.errors, "palette_strict") == [Box(6, 2, 7, 3)]
    assert not report.passed_hard_checks


def test_suppression_never_hides_a_finding_with_pixels_outside_its_region() -> None:
    config = QualityConfig(max_colors=2, suppressions=(Suppression("color_excess", "eye_left"),))
    report = eyes(config)  # colour excess covers both eyes and the body
    assert boxes(report.findings, "color_excess") == [Box(1, 1, 7, 4)]
    assert report.suppressed == ()


def test_hard_rules_cannot_be_suppressed() -> None:
    for rule in ("palette_strict", "outside_mask", "alpha_normalized", "canvas_dimensions"):
        with pytest.raises(ValidationError) as caught:
            Suppression(rule, "eye_left")
        assert caught.value.context["reason"] == "not_suppressible"


def test_soft_rule_suppressions_cover_every_soft_rule() -> None:
    region = {"all": rasterize_rect(Box(0, 0, 6, 6), CANVAS)}
    timeline = frames(
        [BODY, ["kk..kk", "k....k", "......", "......", "k....k", "kk..kk"], BODY, BODY]
    )
    flicker = frames([BODY, [*BODY[:2], ".klsk.", *BODY[3:]], BODY])
    config = QualityConfig(
        rules=QUALITY_RULES,
        max_colors=1,
        suppressions=tuple(Suppression(rule, "all") for rule in SOFT_RULES),
    )
    seen: set[str] = set()
    for timeline_frames in (timeline, flicker):
        report = evaluate_quality(
            raster(SPECKLED),
            canvas=CANVAS,
            palette=PALETTE,
            config=config,
            regions=region,
            frames=timeline_frames,
        )
        assert report.warnings == () and report.suppressed
        assert {f.suppressed_by for f in report.suppressed} == {"all"}
        seen |= {f.rule_id for f in report.suppressed}
    assert {"singleton", "color_excess", "noise", "temporal_change", "temporal_flicker"} <= seen


def test_partial_region_does_not_suppress_a_stair() -> None:
    # The irregular step spans [2, 7) x [1, 3); the region [0, 4) x [0, 5) holds only
    # part of it, so the warning stays active.
    dims = Dimensions(8, 5)
    config = QualityConfig(
        rules=("irregular_steps",), suppressions=(Suppression("irregular_steps", "left"),)
    )
    report = evaluate_quality(
        raster(STAIR),
        canvas=dims,
        palette=PALETTE,
        config=config,
        regions={"left": rasterize_rect(Box(0, 0, 4, 5), dims)},
    )
    assert boxes(report.findings, "irregular_steps") == [Box(2, 1, 7, 3)]
    assert report.suppressed == ()
    whole = {"left": rasterize_rect(Box(0, 0, 8, 5), dims)}
    report = evaluate_quality(
        raster(STAIR), canvas=dims, palette=PALETTE, config=config, regions=whole
    )
    assert boxes(report.suppressed, "irregular_steps") == [Box(2, 1, 7, 3)]


# --- T2: overlapping regions ---------------------------------------------------


def overlap(config: QualityConfig) -> QualityReport:
    grid = list(BODY)
    grid[3] = ".kslk."  # light pixel at (3, 3), inside both regions
    regions = {
        "a": rasterize_rect(Box(1, 1, 4, 4), CANVAS),
        "b": rasterize_rect(Box(3, 3, 5, 5), CANVAS),
    }
    return evaluate_quality(
        raster(grid), canvas=CANVAS, palette=PALETTE, config=config, regions=regions
    )


def test_t2_overlapping_regions_each_count_the_shared_pixel() -> None:
    config = QualityConfig(
        regions=(RegionSettings("b", max_colors=1), RegionSettings("a")), max_colors=1
    )
    report = overlap(config)
    metrics = {item.region_id: item.metrics for item in report.region_metrics}
    assert list(metrics) == ["a", "b"]
    # a = [1, 4) x [1, 4): k k k / k s s / k s l -> 9 pixels, 3 colours, l alone
    assert (metrics["a"].opaque_area, metrics["a"].distinct_colors) == (9, 3)
    assert (metrics["a"].clusters, metrics["a"].singletons) == (3, 1)
    assert metrics["a"].bbox == Box(1, 1, 4, 4) and metrics["a"].components == 1
    # b = [3, 5) x [3, 5): l k / k k -> 4 pixels, 2 colours
    assert (metrics["b"].opaque_area, metrics["b"].distinct_colors) == (4, 2)
    excess = [
        (f.region_id, dict(f.evidence)["distinct_colors"])
        for f in report.findings
        if f.rule_id == "color_excess"
    ]
    assert excess == [(None, 3), ("a", 3), ("b", 2)]


def test_t2_shared_pixel_is_suppressed_by_the_first_region_in_canonical_order() -> None:
    suppressions = (Suppression("singleton", "b"), Suppression("singleton", "a"))
    report = overlap(QualityConfig(suppressions=suppressions))
    (suppressed,) = report.suppressed
    assert suppressed.bbox == Box(3, 3, 4, 4) and suppressed.suppressed_by == "a"
    assert boxes(report.findings, "singleton") == []


def test_region_thresholds_override_the_global_ones() -> None:
    # Left third of SPECKLED: 18 opaque pixels, light singletons at x in {0, 2} on
    # rows 0, 2 and 4 -> 6 singletons, floor(6000 / 18) = 333 per mille.
    regions = {"left": rasterize_rect(Box(0, 0, 3, 6), CANVAS)}
    config = QualityConfig(
        max_singleton_permille=1000,  # never noisy globally
        min_noise_singletons=4,
        regions=(RegionSettings("left", max_singleton_permille=300),),
    )
    report = evaluate_quality(
        raster(SPECKLED), canvas=CANVAS, palette=PALETTE, config=config, regions=regions
    )
    (noise,) = [f for f in report.findings if f.rule_id == "noise"]
    assert noise.region_id == "left" and noise.bbox == Box(0, 0, 3, 5)
    assert dict(noise.evidence) == {
        "max_singleton_permille": 300,
        "opaque_area": 18,
        "singleton_permille": 333,
        "singletons": 6,
    }


# --- T2: order and reproducibility ------------------------------------------------


def test_t2_report_bytes_do_not_depend_on_configuration_order() -> None:
    items = [
        Suppression("singleton", "eye_right"),
        Suppression("noise", "eye_left"),
        Suppression("singleton", "eye_left"),
        Suppression("color_excess", "eye_right"),
    ]
    settings = [RegionSettings("eye_right", max_colors=1), RegionSettings("eye_left")]
    rules = list(QUALITY_RULES)
    texts = set()
    generator = random.Random(26)
    for _ in range(6):
        generator.shuffle(items)
        generator.shuffle(settings)
        generator.shuffle(rules)
        config = QualityConfig(
            rules=tuple(rules),
            suppressions=tuple(items),
            regions=tuple(settings),
            containment=tuple(generator.sample(["eye_right", "eye_left"], 2)),
        )
        texts.add(text(eyes(config)))
    assert len(texts) == 1


def test_findings_follow_rule_region_frame_y_x() -> None:
    report = eyes(QualityConfig(max_colors=1, regions=(RegionSettings("eye_left"),)))
    keys = [finding_sort_key(f) for f in report.findings]
    assert keys == sorted(keys)
    order = [(f.rule_id, f.region_id, f.bbox.y0, f.bbox.x0) for f in report.findings]
    assert order == [
        ("palette_strict", None, 2, 6),
        ("singleton", None, 2, 2),
        ("singleton", None, 2, 5),
        ("singleton", None, 2, 6),
        ("color_excess", None, 1, 1),
        ("color_excess", "eye_left", 1, 1),
    ]


def test_frame_findings_sort_after_the_still_image() -> None:
    timeline = frames([[*BODY[:2], ".kxsk.", *BODY[3:]], BODY])
    report = evaluate_quality(
        raster([*BODY[:4], ".kkkx.", BODY[5]]), canvas=CANVAS, palette=PALETTE, frames=timeline
    )
    errors = [(f.frame_id, f.bbox) for f in report.errors]
    assert errors == [(None, Box(4, 4, 5, 5)), ("f0", Box(2, 2, 3, 3))]


def test_ac2_report_is_identical_across_runs() -> None:
    config = QualityConfig(suppressions=(Suppression("singleton", "eye_left"),))
    first, second = eyes(config), eyes(config)
    assert first == second and text(first) == text(second)


# --- T2: non-mutation ---------------------------------------------------------------


def test_t2_inputs_are_not_modified() -> None:
    image = raster(EYES)
    timeline = frames([EYES, EYES])
    before = (visual_digest(8, 5, image.rgba), [f.result.rgba for f in timeline])
    config = QualityConfig(suppressions=(Suppression("singleton", "eye_left"),))
    snapshot = config.to_mapping()
    report = evaluate_quality(
        image,
        canvas=EYES_CANVAS,
        palette=PALETTE,
        config=config,
        regions=EYE_REGIONS,
        frames=timeline,
    )
    assert (visual_digest(8, 5, image.rgba), [f.result.rgba for f in timeline]) == before
    assert report.image_digest == before[0] and config.to_mapping() == snapshot
    assert EYE_REGIONS["eye_left"] == rasterize_rect(Box(1, 1, 4, 4), EYES_CANVAS)


# --- truncation, budgets and errors -------------------------------------------------


def isolated_pixels(side: int, colour: Callable[[int], bytes]) -> Raster:
    """Ink field with one isolated pixel at every even ``(x, y)``: ``(side / 2)^2`` of
    them, coloured by ``colour(i)`` (``i`` in row-major order)."""
    ink = bytes((27, 26, 46, 255))
    data = bytearray()
    index = 0
    for y in range(side):
        for x in range(side):
            if x % 2 == 0 and y % 2 == 0:
                data += colour(index)
                index += 1
            else:
                data += ink
    return Raster(side, side, bytes(data))


def unique(index: int) -> bytes:
    return bytes((index & 0xFF, index >> 8, 1, 255))  # never a palette value


def test_cap_keeps_every_rule_before_filling_in_report_order() -> None:
    # 96 x 96 = 9216 isolated pixels of distinct off-palette colours: each one is a
    # palette_strict error and a singleton; 9217 colours: one color_excess and one
    # noise warning.
    side, count = 192, 96 * 96
    config = QualityConfig(max_listed_singletons=count)
    report = evaluate_quality(
        isolated_pixels(side, unique),
        canvas=Dimensions(side, side),
        palette=PALETTE,
        config=config,
    )
    listed = dict.fromkeys(QUALITY_RULES, 0)
    for finding in report.findings:
        listed[finding.rule_id] += 1
    guaranteed = 2 * MIN_LISTED_PER_RULE + 2  # palette, singleton, color_excess, noise
    assert len(report.findings) == MAX_QUALITY_FINDINGS
    assert listed["singleton"] == MIN_LISTED_PER_RULE
    assert listed["color_excess"] == listed["noise"] == 1
    assert listed["palette_strict"] == MIN_LISTED_PER_RULE + MAX_QUALITY_FINDINGS - guaranteed
    assert report.omitted_findings_by_rule == (
        ("palette_strict", count - listed["palette_strict"]),
        ("singleton", count - MIN_LISTED_PER_RULE),
    )
    assert (report.error_count, report.warning_count) == (count, count + 2)
    assert report.truncated and report.to_mapping()["omitted_findings_by_rule"] == {
        "palette_strict": count - listed["palette_strict"],
        "singleton": count - MIN_LISTED_PER_RULE,
    }
    singles = [f.bbox for f in report.findings if f.rule_id == "singleton"]
    assert singles[:2] == [Box(0, 0, 1, 1), Box(2, 0, 3, 1)]  # first ones in report order


def test_off_palette_groups_are_capped_but_all_counted() -> None:
    side = 128
    data = b"".join(bytes((i & 0xFF, i >> 8, 1, 255)) for i in range(side * side))
    image = Raster(side, side, data)
    config = QualityConfig(rules=("palette_strict",))
    report = evaluate_quality(image, canvas=Dimensions(side, side), palette=PALETTE, config=config)
    assert report.error_count == side * side and not report.passed_hard_checks
    assert len(report.findings) == MAX_QUALITY_FINDINGS
    assert report.omitted_findings == side * side - MAX_QUALITY_FINDINGS
    first, second = report.findings[:2]
    assert (first.bbox, dict(first.evidence)["color"]) == (Box(0, 0, 1, 1), "#000001FF")
    assert (second.bbox, dict(second.evidence)["color"]) == (Box(1, 0, 2, 1), "#010001FF")


def test_suppressed_findings_are_capped_too() -> None:
    side, count = 192, 96 * 96
    dims = Dimensions(side, side)
    config = QualityConfig(
        rules=("singleton",),
        max_listed_singletons=count,
        suppressions=(Suppression("singleton", "all"),),
    )
    report = evaluate_quality(
        isolated_pixels(side, lambda _: bytes((150, 210, 120, 255))),
        canvas=dims,
        palette=PALETTE,
        config=config,
        regions={"all": rasterize_rect(Box(0, 0, side, side), dims)},
    )
    assert len(report.suppressed) == MAX_QUALITY_FINDINGS
    assert report.omitted_suppressed_by_rule == (("singleton", count - MAX_QUALITY_FINDINGS),)
    assert report.omitted_suppressed == count - MAX_QUALITY_FINDINGS
    assert report.truncated and report.findings == () and report.omitted_findings == 0


def test_explanations_are_read_only() -> None:
    with pytest.raises(TypeError):
        EXPLANATIONS["singleton"] = "changed"  # type: ignore[index]  # read-only on purpose
    assert set(EXPLANATIONS) == set(QUALITY_RULES)
    assert "Keep if intentional (eye, glint, particle)" in EXPLANATIONS["singleton"]
    assert "expected for deliberate dithering or texture" in EXPLANATIONS["noise"]
    assert "intended pose change" in EXPLANATIONS["temporal_change"]


def test_budget_is_admitted_before_any_analysis() -> None:
    config = QualityConfig()
    visits, held = quality_cost(CANVAS, config, 3)
    assert visits == 36 * (16 + 3 * 16)
    exact = RenderLimits(max_pixel_visits=visits, max_buffer_bytes=held)
    timeline = frames([BODY, BODY, BODY])
    evaluate_quality(raster(BODY), canvas=CANVAS, palette=PALETTE, frames=timeline, limits=exact)
    tight = RenderLimits(max_pixel_visits=visits - 1, max_buffer_bytes=held - 1)
    with pytest.raises(BudgetExceeded) as caught:
        evaluate_quality(
            raster(BODY), canvas=CANVAS, palette=PALETTE, frames=timeline, limits=tight
        )
    assert [d.context["resource"] for d in caught.value.details] == [
        "pixel_visits",
        "buffer_bytes",
    ]
    with pytest.raises(BudgetExceeded) as caught:
        evaluate_quality(
            raster(BODY),
            canvas=CANVAS,
            palette=PALETTE,
            limits=RenderLimits(max_buffer_bytes=quality_cost(CANVAS, config)[1] - 1),
        )
    assert caught.value.context["resource"] == "buffer_bytes"


def test_cost_counts_regions_frames_and_suppressions() -> None:
    # Held findings for 36 pixels: palette min(36, 4096) + 2 * 36 cluster findings
    # + 8 small rules * 2 * (2 + frames + regions) -> 140 alone, 156 with one region
    # setting and 192 with one frame; 1024 bytes each.
    plain = quality_cost(CANVAS, QualityConfig())
    regions = QualityConfig(
        regions=(RegionSettings("a"),), suppressions=(Suppression("noise", "b"),)
    )
    visits, held = quality_cost(CANVAS, regions)
    assert visits == plain[0] + 36 * (16 + 2)
    assert held == plain[1] + 8 * 36 + 2 * 2 * 36 + 16 * 1024
    assert quality_cost(CANVAS, QualityConfig(), 1)[1] == plain[1] + 16 * 36 + 52 * 1024
    with pytest.raises(TypeError):
        quality_cost((6, 6), QualityConfig())  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError):
        quality_cost(CANVAS, {})  # type: ignore[arg-type]  # invalid on purpose


def peak_of(run: Callable[[], object]) -> int:
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        start = tracemalloc.get_traced_memory()[0]
        run()
        return tracemalloc.get_traced_memory()[1] - start
    finally:
        tracemalloc.stop()


def high_entropy(side: int, seed: int) -> Raster:
    generator = random.Random(seed)
    return Raster(side, side, bytes(generator.randrange(256) | 1 for _ in range(4 * side * side)))


def test_measured_memory_of_a_high_entropy_image_stays_within_the_estimate() -> None:
    side = 128
    dims = Dimensions(side, side)
    image = high_entropy(side, 7)  # every pixel opaque, nearly every colour unique
    config = QualityConfig()
    reports: list[QualityReport] = []
    peak = peak_of(
        lambda: reports.append(evaluate_quality(image, canvas=dims, palette=PALETTE, config=config))
    )
    assert reports[0].error_count > MAX_QUALITY_FINDINGS  # capped but counted
    assert peak <= quality_cost(dims, config)[1]


def test_measured_memory_of_three_high_entropy_frames_stays_within_the_estimate() -> None:
    side = 256
    dims = Dimensions(side, side)
    image = high_entropy(side, 11)
    regions = {
        "a": rasterize_rect(Box(0, 0, 128, 256), dims),
        "b": rasterize_rect(Box(64, 64, 256, 256), dims),
    }
    config = QualityConfig(
        rules=QUALITY_RULES,
        regions=(RegionSettings("a"), RegionSettings("b")),
        suppressions=(Suppression("singleton", "a"), Suppression("noise", "b")),
    )
    timeline = tuple(Frame(f"f{i}", high_entropy(side, 20 + i)) for i in range(3))
    peak = peak_of(
        lambda: evaluate_quality(
            image, canvas=dims, palette=PALETTE, config=config, regions=regions, frames=timeline
        )
    )
    assert peak <= quality_cost(dims, config, len(timeline))[1]


def test_oversized_frames_are_not_analysed_beyond_their_size() -> None:
    # A 1 x 1 canvas with two 1024 x 1024 frames: admitted for the canvas only, the
    # frames are reported by size and never read, digested or copied.
    canvas = Dimensions(1, 1)
    big = Raster(1024, 1024, bytes(4 * 1024 * 1024))
    timeline = (Frame("f0", big), Frame("f1", big))
    config = QualityConfig()
    visits, held = quality_cost(canvas, config, len(timeline))
    exact = RenderLimits(max_pixel_visits=visits, max_buffer_bytes=held)
    reports: list[QualityReport] = []
    peak = peak_of(
        lambda: reports.append(
            evaluate_quality(
                raster(["k"]), canvas=canvas, palette=PALETTE, frames=timeline, limits=exact
            )
        )
    )
    (report,) = reports
    assert [(f.rule_id, f.frame_id, f.bbox) for f in report.errors] == [
        ("canvas_dimensions", "f0", Box(0, 0, 1024, 1024)),
        ("canvas_dimensions", "f1", Box(0, 0, 1024, 1024)),
    ]
    assert [m.digest for m in report.frame_metrics] == [None, None]
    assert peak <= held < 4 * 1024 * 1024


def test_deadline_is_checked() -> None:
    ticks = iter([0.0] + [10.0] * 100)
    expired = Deadline(1, clock=lambda: next(ticks))
    with pytest.raises(BudgetExceeded) as caught:
        evaluate_quality(raster(BODY), canvas=CANVAS, palette=PALETTE, deadline=expired)
    assert caught.value.context["resource"] == "time"
    relaxed = Deadline(60_000)
    config = QualityConfig(regions=(RegionSettings("body"),))
    report = evaluate_quality(
        raster(BODY),
        canvas=CANVAS,
        palette=PALETTE,
        config=config,
        deadline=relaxed,
        regions={"body": rasterize_rect(Box(1, 1, 5, 5), CANVAS)},
        frames=frames([BODY]),
    )
    assert report.region_metrics[0].metrics.opaque_area == 16


def test_deadline_expires_at_the_region_and_frame_stages() -> None:
    """A clock that expires after ``n`` reads, for every ``n`` up to a full run."""
    config = QualityConfig(regions=(RegionSettings("body"),))
    regions = {"body": rasterize_rect(Box(1, 1, 5, 5), CANVAS)}

    def run(reads: int) -> str | None:
        count = 0

        def clock() -> float:
            nonlocal count
            count += 1
            return 0.0 if count <= reads else 10.0

        try:
            evaluate_quality(
                raster(BODY),
                canvas=CANVAS,
                palette=PALETTE,
                config=config,
                regions=regions,
                frames=frames([BODY, BODY]),
                deadline=Deadline(1, clock=clock),
            )
        except BudgetExceeded as error:
            assert error.context["resource"] == "time"
            return str(error.context["stage"])
        return None

    stages = []
    reads = 1
    while (stage := run(reads)) is not None:
        stages.append(stage)
        reads += 1
    assert "quality_region" in stages and "quality_frame" in stages
    assert stages.index("quality_region") < stages.index("quality_frame")


def test_exactly_256_frames_are_accepted() -> None:
    one = Dimensions(1, 1)
    timeline = [Frame(f"f{i}", raster(["k"])) for i in range(256)]
    report = evaluate_quality(raster(["k"]), canvas=one, palette=PALETTE, frames=timeline)
    assert len(report.frame_metrics) == 256 and report.passed_hard_checks
    assert report.frame_metrics[-1].changed_pixels == 0


def test_too_many_frames_is_rejected_before_reading_them() -> None:
    timeline = [Frame(f"f{i}", Raster(1, 1, b"")) for i in range(257)]  # never read
    with pytest.raises(BudgetExceeded) as caught:
        evaluate_quality(raster(BODY), canvas=CANVAS, palette=PALETTE, frames=timeline)
    assert caught.value.context["resource"] == "frames"


@pytest.mark.parametrize(
    ("options", "error"),
    [
        ({"canvas": (6, 6)}, TypeError),
        ({"palette": "pal"}, TypeError),
        ({"config": {}}, TypeError),
        ({"limits": 5}, TypeError),
        ({"deadline": 5}, TypeError),
        ({"loop": 1}, TypeError),
        ({"regions": [("body", None)]}, TypeError),
        ({"frames": "f0"}, TypeError),
        ({"frames": [object()]}, TypeError),
        ({"frames": [Frame("F0", raster(BODY))]}, ValidationError),
        ({"frames": [Frame("f0", raster(BODY)), Frame("f0", raster(BODY))]}, ValidationError),
        ({"frames": [Frame("f0", object())]}, TypeError),  # type: ignore[arg-type]
        ({"frames": [Frame("f0", Raster(6, 6, b"\0"))]}, ValidationError),
    ],
)
def test_invalid_inputs(options: dict[str, object], error: type[Exception]) -> None:
    arguments: dict[str, object] = {"canvas": CANVAS, "palette": PALETTE, **options}
    with pytest.raises(error):
        evaluate_quality(raster(BODY), **arguments)  # type: ignore[arg-type]  # invalid on purpose


def test_invalid_images_and_regions() -> None:
    with pytest.raises(TypeError):
        evaluate_quality(object(), canvas=CANVAS, palette=PALETTE)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        evaluate_quality(Raster(6, 6, bytearray(144)), canvas=CANVAS, palette=PALETTE)  # type: ignore[arg-type]
    with pytest.raises(ValidationError) as caught:
        evaluate_quality(Raster(6, 6, bytes(143)), canvas=CANVAS, palette=PALETTE)
    assert caught.value.context["reason"] == "size_mismatch"
    config = QualityConfig(containment=("body",))
    with pytest.raises(ReferenceError) as missing:
        evaluate_quality(raster(BODY), canvas=CANVAS, palette=PALETTE, config=config)
    assert missing.value.context["reason"] == "unknown_region"
    bad: dict[str, object] = {"body": "mask"}
    with pytest.raises(TypeError):
        evaluate_quality(raster(BODY), canvas=CANVAS, palette=PALETTE, config=config, regions=bad)  # type: ignore[arg-type]  # invalid on purpose


def test_masks_are_clipped_to_the_canvas_and_may_be_empty() -> None:
    big = rasterize_rect(Box(0, 0, 10, 10), Dimensions(10, 10))
    outside = rasterize_rect(Box(8, 8, 10, 10), Dimensions(10, 10))
    config = QualityConfig(
        containment=("big",), regions=(RegionSettings("off"), RegionSettings("none"))
    )
    report = evaluate_quality(
        raster(BODY),
        canvas=CANVAS,
        palette=PALETTE,
        config=config,
        regions={"big": big, "off": outside, "none": Mask.empty()},
    )
    assert report.passed_hard_checks
    assert [m.metrics.opaque_area for m in report.region_metrics] == [0, 0]


def test_palette_values_with_alpha_zero_are_ignored() -> None:
    palette = Palette.from_mapping(
        {
            "id": "pal",
            "colors": [
                {"id": "clear", "rgba": "#00000000"},
                {"id": "ink", "rgba": "#1B1A2EFF"},
                {"id": "slime", "rgba": "#5AA050FF"},
            ],
        },
        profile="strict",
    )
    report = evaluate_quality(raster(BODY), canvas=CANVAS, palette=palette)
    assert report.passed_hard_checks


# --- loop seam ------------------------------------------------------------------------

LIT = [*BODY[:2], ".klsk.", *BODY[3:]]  # BODY with a light pixel at (2, 2)
SEAM = QualityConfig(rules=QUALITY_RULES, max_changed_permille=0)


def temporal(report: QualityReport) -> list[tuple[str, str | None, str | int | None]]:
    return [
        (f.rule_id, f.frame_id, dict(f.evidence).get("previous_frame_id"))
        for f in report.findings
        if f.rule_id.startswith("temporal")
    ]


def test_loop_compares_the_seam_from_the_last_frame_to_the_first() -> None:
    # BODY, LIT, LIT: one pixel of 16 opaque changes rest -> f1 (62 per mille > 0).
    timeline = frames([BODY, LIT, LIT])
    once = evaluate_quality(
        raster(BODY), canvas=CANVAS, palette=PALETTE, config=SEAM, frames=timeline
    )
    assert temporal(once) == [("temporal_change", "f1", "f0")]
    looped = evaluate_quality(
        raster(BODY), canvas=CANVAS, palette=PALETTE, config=SEAM, frames=timeline, loop=True
    )
    # Seam f2 -> f0 changes the pixel back; f0 is then a one-frame blip between f2 and
    # f1 (both LIT): flicker of f0 at (2, 2).
    assert temporal(looped) == [
        ("temporal_change", "f0", "f2"),
        ("temporal_change", "f1", "f0"),
        ("temporal_flicker", "f0", None),
    ]
    (flicker,) = [f for f in looped.findings if f.rule_id == "temporal_flicker"]
    assert flicker.bbox == Box(2, 2, 3, 3) and flicker.frame_index == 0
    (seam,) = [f for f in looped.findings if f.frame_id == "f0" and f.rule_id == "temporal_change"]
    assert dict(seam.evidence)["changed_permille"] == 62  # floor(1000 * 1 / 16)


def test_seam_flicker_of_the_last_frame() -> None:
    # BODY, BODY, LIT looped: f2 differs from f1 and from f0 = f1: flicker of f2.
    looped = evaluate_quality(
        raster(BODY),
        canvas=CANVAS,
        palette=PALETTE,
        frames=frames([BODY, BODY, LIT]),
        loop=True,
    )
    assert temporal(looped) == [("temporal_flicker", "f2", None)]


def test_no_seam_with_two_frames_or_an_unreadable_head() -> None:
    two = evaluate_quality(
        raster(BODY),
        canvas=CANVAS,
        palette=PALETTE,
        config=SEAM,
        frames=frames([BODY, LIT]),
        loop=True,
    )
    assert temporal(two) == [("temporal_change", "f1", "f0")]
    small = Raster(1, 1, bytes(4))  # not canvas-sized: never compared
    cases = (
        # first frame unreadable: no seam at all
        (
            (Frame("f0", small), Frame("f1", raster(BODY)), Frame("f2", raster(LIT))),
            [
                ("temporal_change", "f2", "f1"),
            ],
        ),
        # second frame unreadable: the seam f2 -> f0 is compared, no flicker of f0
        (
            (Frame("f0", raster(BODY)), Frame("f1", small), Frame("f2", raster(LIT))),
            [
                ("temporal_change", "f0", "f2"),
            ],
        ),
    )
    for timeline, expected in cases:
        report = evaluate_quality(
            raster(BODY), canvas=CANVAS, palette=PALETTE, config=SEAM, frames=timeline, loop=True
        )
        assert temporal(report) == expected


def test_strict_palette_without_opaque_values_rejects_every_opaque_pixel() -> None:
    clear = Palette.from_mapping(
        {"id": "pal", "colors": [{"id": "clear", "rgba": "#00000000"}]}, profile="strict"
    )
    config = QualityConfig(rules=("palette_strict",))
    report = evaluate_quality(raster(BODY), canvas=CANVAS, palette=clear, config=config)
    # BODY: 12 ink pixels on the ring and 4 slime pixels inside.
    assert [(dict(f.evidence)["color"], dict(f.evidence)["pixels"]) for f in report.errors] == [
        ("#1B1A2EFF", 12),
        ("#5AA050FF", 4),
    ]
