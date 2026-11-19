"""T1/AC1 (MOANA-026): every rule on a known defect and on its corrected version.

The corpus lives in :mod:`tests.fixtures.quality`; boxes and evidence there are
counted by hand. Metrics are checked against independent pure-Python counts.
"""

from __future__ import annotations

from collections import deque

import pytest

from moana.core.coordinates import Box, Dimensions
from moana.geometry import Mask, rasterize_rect
from moana.quality import (
    EXPLANATIONS,
    HARD_RULES,
    REPORT_NOTICE,
    QualityConfig,
    QualityFinding,
    QualityReport,
    evaluate_quality,
)
from tests.fixtures.quality import (
    BODY,
    CANVAS,
    CASES,
    COLORS,
    PALETTE,
    RGBA_PALETTE,
    Case,
    Frame,
    Raster,
    frames,
    raster,
)

BODY_REGION = {"body": rasterize_rect(Box(1, 1, 5, 5), CANVAS)}


def run(case: Case, *, fixed: bool) -> QualityReport:
    grid = case.fixed if fixed else case.defect
    timeline = case.fixed_frames if fixed else case.defect_frames
    image = raster(grid)
    regions: dict[str, Mask] = BODY_REGION if case.config.get("containment") else {}
    return evaluate_quality(
        image,
        canvas=Dimensions(image.width, image.height),
        palette=PALETTE,
        config=QualityConfig(**case.config),  # type: ignore[arg-type]  # fixture options
        regions=regions,
        frames=frames(timeline),
    )


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_t1_defect_reports_the_expected_finding(case: Case) -> None:
    report = run(case, fixed=False)
    (finding,) = [f for f in report.findings if f.rule_id == case.rule]
    assert finding.bbox == Box(*case.box)
    assert dict(finding.evidence) == case.evidence
    assert finding.explanation == EXPLANATIONS[case.rule]  # type: ignore[index]  # fixture rule
    expected_severity = "error" if case.rule in HARD_RULES else "warning"
    assert finding.severity == expected_severity
    assert report.passed_hard_checks is (expected_severity == "warning")


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_t1_corrected_version_has_no_finding_of_that_rule(case: Case) -> None:
    report = run(case, fixed=True)
    assert [f for f in report.findings if f.rule_id == case.rule] == []
    assert report.passed_hard_checks


def test_ac1_off_palette_is_an_error_and_a_singleton_a_warning() -> None:
    image = raster([*BODY[:2], ".kxlk.", ".kssk.", *BODY[4:]])
    report = evaluate_quality(image, canvas=CANVAS, palette=PALETTE)
    by_rule = {(f.rule_id, f.severity, f.bbox) for f in report.findings}
    assert ("palette_strict", "error", Box(2, 2, 3, 3)) in by_rule
    assert ("singleton", "warning", Box(3, 2, 4, 3)) in by_rule  # the light pixel
    assert not report.passed_hard_checks and report.error_count == 1
    assert report.errors == tuple(f for f in report.findings if f.rule_id == "palette_strict")
    assert report.warning_count == len(report.warnings) == 2  # x and l are singletons


def test_rgba_profile_has_no_palette_rule() -> None:
    image = raster([*BODY[:2], ".kxsk.", *BODY[3:]])
    report = evaluate_quality(image, canvas=CANVAS, palette=RGBA_PALETTE)
    assert all(f.rule_id != "palette_strict" for f in report.findings)
    assert report.passed_hard_checks


def test_canvas_dimensions_is_an_error_and_stops_the_other_rules() -> None:
    image = raster([row[:5] for row in [*BODY[:2], ".kxsk", *BODY[3:]]])  # 5 x 6
    report = evaluate_quality(image, canvas=CANVAS, palette=PALETTE)
    (finding,) = report.findings
    assert finding.rule_id == "canvas_dimensions" and finding.bbox == Box(0, 0, 5, 6)
    assert dict(finding.evidence) == {
        "expected_height": 6,
        "expected_width": 6,
        "height": 6,
        "width": 5,
    }
    assert (report.width, report.height, report.region_metrics) == (5, 6, ())
    assert report.metrics is None and report.image_digest is None  # never analysed
    off = QualityConfig(rules=("singleton",))
    assert evaluate_quality(image, canvas=CANVAS, palette=PALETTE, config=off).findings == ()


def test_wrong_size_frame_is_reported_and_skipped_by_temporal_rules() -> None:
    small = Raster(5, 6, raster([row[:5] for row in BODY]).rgba)
    timeline = (frames([BODY])[0], Frame("f1", small))
    report = evaluate_quality(raster(BODY), canvas=CANVAS, palette=PALETTE, frames=timeline)
    (finding,) = report.findings
    assert (finding.rule_id, finding.frame_id, finding.frame_index) == (
        "canvas_dimensions",
        "f1",
        1,
    )
    assert [m.changed_pixels for m in report.frame_metrics] == [None, None]
    skipped = report.frame_metrics[1]
    assert (skipped.digest, skipped.distinct_colors, skipped.opaque_area, skipped.bbox) == (
        None,
        None,
        None,
        None,
    )


def test_disabled_rules_report_nothing() -> None:
    case = next(c for c in CASES if c.rule == "palette_strict")
    report = evaluate_quality(
        raster(case.defect),
        canvas=CANVAS,
        palette=PALETTE,
        config=QualityConfig(rules=()),
        frames=frames([case.defect, BODY, case.defect]),
    )
    assert report.findings == () and report.passed_hard_checks
    assert report.metrics is not None and report.metrics.distinct_colors == 3  # always computed


def components(grid: list[str], *, by_color: bool, diagonal: bool = False) -> list[int]:
    """Areas of 4- (or 8-) connected components by breadth-first search (oracle)."""
    steps = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if diagonal:
        steps += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    seen: set[tuple[int, int]] = set()
    areas: list[int] = []
    for y, row in enumerate(grid):
        for x, char in enumerate(row):
            if char == "." or (x, y) in seen:
                continue
            seen.add((x, y))
            queue, area = deque([(x, y)]), 0
            while queue:
                cx, cy = queue.popleft()
                area += 1
                for nx, ny in ((cx + dx, cy + dy) for dx, dy in steps):
                    if 0 <= ny < len(grid) and 0 <= nx < len(row) and (nx, ny) not in seen:
                        other = grid[ny][nx]
                        if other != "." and (other == char or not by_color):
                            seen.add((nx, ny))
                            queue.append((nx, ny))
            areas.append(area)
    return areas


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_metrics_match_independent_counts(case: Case) -> None:
    grid = case.defect
    if any("g" in row for row in grid):
        return  # the non-normalised transparent pixel is no colour of the oracle
    report = evaluate_quality(
        raster(grid), canvas=Dimensions(len(grid[0]), len(grid)), palette=PALETTE
    )
    metrics = report.metrics
    assert metrics is not None
    clusters = components(grid, by_color=True, diagonal=True)  # cluster_connectivity 8
    opaque = [(x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if c != "."]
    assert metrics.distinct_colors == len({c for row in grid for c in row} - {"."})
    assert metrics.opaque_area == len(opaque)
    assert metrics.components == len(components(grid, by_color=False))
    assert metrics.clusters == len(clusters)
    assert metrics.singletons == clusters.count(1)
    assert metrics.singleton_permille == clusters.count(1) * 1000 // len(opaque)
    xs, ys = [x for x, _ in opaque], [y for _, y in opaque]
    assert metrics.bbox == Box(min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def test_empty_image_metrics_and_notice() -> None:
    report = evaluate_quality(raster(["......"] * 6), canvas=CANVAS, palette=PALETTE)
    assert report.metrics is not None
    assert report.metrics.to_mapping() == {
        "bbox": None,
        "clusters": 0,
        "components": 0,
        "distinct_colors": 0,
        "opaque_area": 0,
        "singleton_permille": 0,
        "singletons": 0,
    }
    mapping = report.to_mapping()
    assert mapping["notice"] == REPORT_NOTICE and "score" not in mapping
    assert mapping["truncated"] is False


NOISE = next(c for c in CASES if c.rule == "noise")


def noise_findings(config: QualityConfig, grid: list[str] = NOISE.defect) -> list[QualityFinding]:
    image = raster(grid)
    size = Dimensions(image.width, image.height)
    report = evaluate_quality(image, canvas=size, palette=PALETTE, config=config)
    return [f for f in report.findings if f.rule_id == "noise"]


def test_noise_min_singletons_is_inclusive() -> None:
    assert len(noise_findings(QualityConfig(min_noise_singletons=8))) == 1  # exactly 8
    assert noise_findings(QualityConfig(min_noise_singletons=9)) == []


def test_noise_permille_threshold_is_exclusive() -> None:
    # SPECKLED: floor(1000 * 8 / 36) = 222 singletons per thousand opaque pixels.
    assert noise_findings(QualityConfig(max_singleton_permille=222)) == []
    assert len(noise_findings(QualityConfig(max_singleton_permille=221))) == 1


def test_noise_is_relative_to_the_opaque_area() -> None:
    # The same eight singletons over 14 x 14 = 196 pixels: floor(8000 / 196) = 40.
    field = NOISE.fixed
    report = evaluate_quality(
        raster(field), canvas=Dimensions(14, 14), palette=PALETTE, config=QualityConfig()
    )
    assert report.metrics is not None
    assert (report.metrics.singletons, report.metrics.opaque_area) == (8, 196)
    assert report.metrics.singleton_permille == 40
    assert noise_findings(QualityConfig(), field) == []
    assert len(noise_findings(QualityConfig(max_singleton_permille=39), field)) == 1


def test_diagonal_line_is_one_cluster_by_default() -> None:
    line = ["k.....", ".k....", "..k...", "...k..", "....k.", ".....k"]
    report = evaluate_quality(raster(line), canvas=CANVAS, palette=PALETTE)
    assert report.metrics is not None
    assert (report.metrics.clusters, report.metrics.singletons) == (1, 0)
    assert report.metrics.components == 6  # the silhouette keeps connectivity 4
    assert report.findings == ()
    four = QualityConfig(cluster_connectivity=4)
    split = evaluate_quality(raster(line), canvas=CANVAS, palette=PALETTE, config=four)
    assert [f.bbox for f in split.findings] == [Box(i, i, i + 1, i + 1) for i in range(6)]
    assert {f.rule_id for f in split.findings} == {"singleton"}


def test_singletons_are_grouped_per_colour_above_the_listing_limit() -> None:
    # SPECKLED has 8 light singletons: listed one per pixel up to 8, grouped above.
    config = QualityConfig(max_listed_singletons=8)
    image = raster(NOISE.defect)
    report = evaluate_quality(image, canvas=CANVAS, palette=PALETTE, config=config)
    pixels = [f.bbox for f in report.findings if f.rule_id == "singleton"]
    assert pixels == [
        Box(x, y, x + 1, y + 1)
        for y, xs in ((0, (0, 2, 4)), (2, (0, 2, 4)), (4, (0, 2)))
        for x in xs
    ]
    config = QualityConfig(max_listed_singletons=7)
    report = evaluate_quality(image, canvas=CANVAS, palette=PALETTE, config=config)
    (grouped,) = [f for f in report.findings if f.rule_id == "singleton"]
    assert grouped.bbox == Box(0, 0, 5, 5)
    assert dict(grouped.evidence) == {
        "color": "#96D278FF",
        "first_x": 0,
        "first_y": 0,
        "pixels": 8,
    }
    assert report.warning_count == 2  # the grouped singleton and noise


def test_grouped_singletons_keep_one_finding_per_colour() -> None:
    grid = ["l.x...", "......", "..l.x.", "......", "......", "......"]
    config = QualityConfig(max_listed_singletons=3, rules=("singleton",))
    report = evaluate_quality(raster(grid), canvas=CANVAS, palette=PALETTE, config=config)
    assert [(f.bbox, dict(f.evidence)) for f in report.findings] == [
        (Box(0, 0, 3, 3), {"color": "#96D278FF", "first_x": 0, "first_y": 0, "pixels": 2}),
        (Box(2, 0, 5, 3), {"color": "#FF00FFFF", "first_x": 2, "first_y": 0, "pixels": 2}),
    ]


def test_one_by_one_images() -> None:
    one = Dimensions(1, 1)
    transparent = evaluate_quality(raster(["."]), canvas=one, palette=PALETTE)
    assert transparent.findings == () and transparent.metrics is not None
    assert transparent.metrics.opaque_area == 0
    ink = evaluate_quality(raster(["k"]), canvas=one, palette=PALETTE)
    assert [f.rule_id for f in ink.findings] == ["singleton"]
    assert ink.passed_hard_checks and ink.metrics is not None
    assert (ink.metrics.singletons, ink.metrics.singleton_permille) == (1, 1000)
    off = evaluate_quality(raster(["x"]), canvas=one, palette=PALETTE)
    assert [(f.rule_id, f.bbox) for f in off.findings] == [
        ("palette_strict", Box(0, 0, 1, 1)),
        ("singleton", Box(0, 0, 1, 1)),
    ]
    assert not off.passed_hard_checks


def test_alpha_check_ignores_normalised_transparency() -> None:
    assert COLORS["."] == (0, 0, 0, 0)
    report = evaluate_quality(raster(["......"] * 6), canvas=CANVAS, palette=PALETTE)
    assert report.findings == ()
