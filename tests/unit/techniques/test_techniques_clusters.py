"""T1/T2/AC2 (MOANA-014): cluster analysis of RGBA images (MOANA.md sections 8 and 19).

Images are drawn from character grids written by hand (``.`` is transparent); the
expected counts, boxes and areas are counted by hand, and the property test compares
with a breadth-first search over Python sets.
"""

from __future__ import annotations

import itertools
import tracemalloc
from collections.abc import Iterable, Sequence

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.core.budget import Deadline
from moana.core.coordinates import Box, Dimensions, Point
from moana.core.errors import BudgetExceeded, ReferenceError, ValidationError
from moana.core.limits import MAX_CLUSTER_EXCEPTIONS, MAX_CLUSTER_RUNS
from moana.geometry import Mask, MaskCover, cover_bytes, rasterize_line
from moana.geometry.mask import _restore
from moana.techniques import (
    CLUSTER_FIXED_BYTES,
    CLUSTER_RULES,
    CLUSTER_RUN_BYTES,
    ClusterException,
    analyze_clusters,
    check_cluster_settings,
    cluster_bytes,
)

RGBA = tuple[int, int, int, int]
PALETTE: dict[str, RGBA] = {
    ".": (0, 0, 0, 0),
    "r": (200, 0, 0, 255),
    "g": (0, 160, 0, 255),
    "w": (255, 255, 255, 255),
    "h": (200, 0, 0, 128),  # same RGB as r, other alpha: another colour
}


def mask_of(pixels: Iterable[tuple[int, int]]) -> Mask:
    """A mask holding exactly ``pixels`` over their bounding box, built from raw bits."""
    points = sorted(pixels)
    if not points:
        return Mask.empty()
    x0, y0 = min(x for x, _ in points), min(y for _, y in points)
    x1, y1 = max(x for x, _ in points) + 1, max(y for _, y in points) + 1
    bits = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    for x, y in points:
        bits[y - y0, x - x0] = 1
    return _restore(Box(x0, y0, x1, y1), (y1 - y0, x1 - x0), bits.tobytes())


def image(rows: list[str]) -> tuple[bytes, Dimensions]:
    data = b"".join(bytes(PALETTE[c]) for row in rows for c in row)
    return data, Dimensions(len(rows[0]), len(rows))


def summary(rows: list[str], connectivity: int) -> list[tuple[str, Box, int, Point]]:
    data, dims = image(rows)
    report = analyze_clusters(data, dims, connectivity=connectivity)  # type: ignore[arg-type]  # 4 or 8
    return [(c.color, c.box, c.area, c.seed) for c in report.clusters]


RED, GREEN, WHITE = "#C80000FF", "#00A000FF", "#FFFFFFFF"


# --- T2: known components ---------------------------------------------------------------


def test_t2_known_components_with_counts_boxes_and_areas() -> None:
    rows = [
        "rr..g",
        "r...g",
        "..ggg",
        "w....",
    ]
    assert summary(rows, 4) == [
        (RED, Box(0, 0, 2, 2), 3, Point(0, 0)),
        (GREEN, Box(2, 0, 5, 3), 5, Point(4, 0)),
        (WHITE, Box(0, 3, 1, 4), 1, Point(0, 3)),
    ]


def test_t1_corner_contact_is_two_clusters_with_4_and_one_with_8() -> None:
    rows = [
        "r...",
        ".r..",
        "..r.",
        "...r",
    ]
    assert [area for _, _, area, _ in summary(rows, 4)] == [1, 1, 1, 1]
    assert summary(rows, 8) == [(RED, Box(0, 0, 4, 4), 4, Point(0, 0))]


def test_t1_hole_does_not_split_a_ring_and_the_hole_colour_is_its_own_cluster() -> None:
    rows = [
        "rrrr",
        "rgwr",
        "rrrr",
    ]
    assert summary(rows, 4) == [
        (RED, Box(0, 0, 4, 3), 10, Point(0, 0)),
        (GREEN, Box(1, 1, 2, 2), 1, Point(1, 1)),
        (WHITE, Box(2, 1, 3, 2), 1, Point(2, 1)),
    ]


def test_t1_canvas_edges_never_wrap() -> None:
    rows = [
        "r..r",
        "....",
        "r..r",
    ]
    assert len(summary(rows, 8)) == 4  # opposite edges are not neighbours


def test_colours_differ_by_alpha_and_transparent_is_background() -> None:
    rows = ["rh..", "...."]
    assert [color for color, _, _, _ in summary(rows, 4)] == [RED, "#C8000080"]
    assert summary(["...."], 4) == []


def test_u_shape_joins_late_and_keeps_the_first_seed() -> None:
    rows = [
        "r.r",
        "r.r",
        "rrr",
    ]
    assert summary(rows, 4) == [(RED, Box(0, 0, 3, 3), 7, Point(0, 0))]


# --- singleton and stair warnings -------------------------------------------------------


def test_singleton_warning_with_bbox_and_evidence() -> None:
    data, dims = image(["rrr..", "rrr.w", "rrr.."])
    report = analyze_clusters(data, dims, connectivity=4)
    (finding,) = report.warnings
    assert finding.rule_id == "singleton" and finding.severity == "warning"
    assert finding.box == Box(4, 1, 5, 2) and finding.color == WHITE
    assert finding.cluster == 1 and finding.region_id is None
    assert finding.evidence == (("area", 1),)  # the pixel is the box
    assert report.singletons == 1 and report.suppressed == ()


def test_irregular_horizontal_stair_warns_on_interior_steps_only() -> None:
    rows = [
        "rr.........",
        "..r........",
        "...rrrr....",
        ".......r...",
        "........rr.",
    ]  # steps 2, 1, 4, 1, 2: interior pairs (1, 4) and (4, 1) jump by 3
    data, dims = image(rows)
    report = analyze_clusters(data, dims, connectivity=8)
    stairs = [f for f in report.warnings if f.rule_id == "irregular_steps"]
    assert [f.box for f in stairs] == [Box(2, 1, 7, 3), Box(3, 2, 8, 4)]
    assert dict(stairs[0].evidence) == {
        "first_length": 1,
        "second_length": 4,
        "step": 1,
        "steps": 5,
    }
    assert analyze_clusters(data, dims, connectivity=4).warnings[0].rule_id == "singleton"


def test_regular_stairs_and_partial_ends_do_not_warn() -> None:
    for rows in (
        # steps 4, 1, 2, 1, 2, 5: the ends jump by 3 but are partial; the interior
        # steps (1, 2, 1, 2) differ by one pixel at most
        [
            "rrrr...........",
            "....r..........",
            ".....rr........",
            ".......r.......",
            "........rr.....",
            "..........rrrrr",
        ],
        ["rrrr.......", "....rr.....", "......rr...", "........rrr"],  # end 4 ignored
    ):
        data, dims = image(rows)
        assert analyze_clusters(data, dims, connectivity=8).warnings == ()


def test_irregular_vertical_stair_and_left_going_stair() -> None:
    vertical = ["r..", "r..", ".r.", ".r.", ".r.", ".r.", "..r", "...", "..."]
    vertical = [row + "." for row in vertical]
    vertical[7], vertical[8] = "...r", "...r"  # columns: 2, 4, 1, 2 -> (4, 1) warns
    data, dims = image(vertical)
    (finding,) = analyze_clusters(data, dims, connectivity=8).warnings
    assert finding.box == Box(1, 2, 3, 7)
    assert dict(finding.evidence)["first_length"] == 4
    left = ["......rr", ".....r..", "..rrr...", ".r......", "r......."]  # 2,1,3,1,1
    data, dims = image(left)
    report = analyze_clusters(data, dims, connectivity=8)
    assert [f.box for f in report.warnings] == [Box(2, 1, 6, 3), Box(1, 2, 5, 4)]


def test_shapes_that_are_not_stairs_never_warn() -> None:
    for rows in (
        ["rrrr", "r..r", "rrrr", "...."],  # two runs in a row
        ["r...", "rrrr", "...r", "..rr", "..r."],  # zigzag columns
        ["r..", ".r.", "r..", ".r.", "r.."],  # one-pixel zigzag
        ["r...", "r...", "r...", "r..."],  # vertical bar: one step
        ["rr..", "rrr.", "..rr", "...r"],  # overlapping runs
    ):
        data, dims = image(rows)
        assert analyze_clusters(data, dims, connectivity=8).warnings == (), rows


@settings(max_examples=200, deadline=None)
@given(
    x0=st.integers(-4, 30),
    y0=st.integers(-4, 30),
    x1=st.integers(-4, 30),
    y1=st.integers(-4, 30),
)
def test_bresenham_lines_never_have_irregular_steps(x0: int, y0: int, x1: int, y1: int) -> None:
    dims = Dimensions(27, 27)
    line = rasterize_line(Point(x0, y0), Point(x1, y1), dims)
    buffer = bytearray(4 * dims.area)
    for point in line.points():
        offset = 4 * (point.y * dims.width + point.x)
        buffer[offset : offset + 4] = bytes(PALETTE["r"])
    report = analyze_clusters(bytes(buffer), dims, connectivity=8)
    assert all(f.rule_id != "irregular_steps" for f in report.warnings)


# --- AC2: exceptions by region ------------------------------------------------------------


GLINT = ["rrrrr", "rrrrr", "rrwrr", "rrrrr", "....g"]


def test_ac2_region_exception_suppresses_and_keeps_the_finding_visible() -> None:
    data, dims = image(GLINT)
    plain = analyze_clusters(data, dims)
    assert [(f.rule_id, f.box) for f in plain.warnings] == [
        ("singleton", Box(2, 2, 3, 3)),
        ("singleton", Box(4, 4, 5, 5)),
    ]
    regions = {"eye_glint": mask_of({(2, 2), (3, 2)})}
    report = analyze_clusters(
        data,
        dims,
        exceptions=[ClusterException("eye_glint", ("singleton",))],
        regions=regions,
    )
    assert [f.box for f in report.warnings] == [Box(4, 4, 5, 5)]
    (kept,) = report.suppressed
    assert (kept.rule_id, kept.box, kept.region_id) == ("singleton", Box(2, 2, 3, 3), "eye_glint")
    assert report.clusters == plain.clusters  # nothing is cleaned up


def test_exception_needs_the_rule_and_every_pixel_in_the_region() -> None:
    data, dims = image(GLINT)
    other_rule = analyze_clusters(
        data,
        dims,
        exceptions=[ClusterException("eye", ("irregular_steps",))],
        regions={"eye": mask_of({(2, 2)})},
    )
    assert len(other_rule.warnings) == 2
    elsewhere = analyze_clusters(
        data,
        dims,
        exceptions=[ClusterException("eye", ("singleton",))],
        regions={"eye": mask_of({(0, 0)})},
    )
    assert len(elsewhere.warnings) == 2 and elsewhere.suppressed == ()


def test_stair_exception_covers_both_steps() -> None:
    rows = ["rr.........", "..r........", "...rrrr....", ".......r...", "........rr."]
    data, dims = image(rows)
    first_only = {(x, y) for x in range(2, 7) for y in range(1, 3)}
    report = analyze_clusters(
        data,
        dims,
        connectivity=8,
        exceptions=[ClusterException("hair", CLUSTER_RULES)],
        regions={"hair": mask_of(first_only)},
    )
    assert [f.box for f in report.suppressed] == [Box(2, 1, 7, 3)]
    assert [f.box for f in report.warnings] == [Box(3, 2, 8, 4)]


# --- negatives ------------------------------------------------------------------------


@pytest.mark.parametrize("connectivity", [6, 0, True, 4.0, "8"])
def test_connectivity_must_be_4_or_8(connectivity: object) -> None:
    data, dims = image(["r"])
    with pytest.raises(ValidationError) as raised:
        analyze_clusters(data, dims, connectivity=connectivity)  # type: ignore[arg-type]  # invalid on purpose
    assert raised.value.context == {
        "field": "connectivity",
        "reason": "unsupported_connectivity",
    }


def test_rgba_size_and_types() -> None:
    with pytest.raises(ValidationError) as raised:
        analyze_clusters(b"\x00" * 7, Dimensions(2, 1))
    assert raised.value.context["reason"] == "size_mismatch"
    with pytest.raises(TypeError, match="bytes"):
        analyze_clusters(bytearray(4), Dimensions(1, 1))  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError, match="Dimensions"):
        analyze_clusters(b"\x00" * 4, (1, 1))  # type: ignore[arg-type]  # invalid on purpose


def test_exception_validation() -> None:
    with pytest.raises(ValidationError) as raised:
        ClusterException("Bad Id", ("singleton",))
    assert raised.value.context["reason"] == "invalid_id"
    for rules, reason in (
        ((), "empty"),
        (["singleton"], "empty"),
        (("blur",), "unknown_rule"),
        ((1,), "unknown_rule"),
        (("singleton", "singleton"), "duplicate_reference"),
    ):
        with pytest.raises(ValidationError) as raised:
            ClusterException("eye", rules)  # type: ignore[arg-type]  # invalid on purpose
        assert raised.value.context["reason"] == reason


def test_exception_references_and_container_types() -> None:
    data, dims = image(GLINT)
    exception = ClusterException("eye", ("singleton",))
    with pytest.raises(ReferenceError) as missing:
        analyze_clusters(data, dims, exceptions=[exception])
    assert missing.value.context == {"field": "region_id", "reason": "unknown_region"}
    with pytest.raises(ValidationError) as twice:
        analyze_clusters(
            data, dims, exceptions=[exception, exception], regions={"eye": Mask.empty()}
        )
    assert twice.value.context["reason"] == "duplicate_reference"
    for bad in ("eye", 3, ["eye"]):
        with pytest.raises(TypeError):
            analyze_clusters(data, dims, exceptions=bad)  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError):
        analyze_clusters(data, dims, exceptions=[exception], regions=[("eye", None)])  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError):
        analyze_clusters(data, dims, exceptions=[exception], regions={"eye": "mask"})  # type: ignore[dict-item]  # invalid on purpose


def test_noisy_image_is_rejected_before_labelling() -> None:
    side = 1024  # 512 x 1024 alternating pixels per row exceed the run limit
    row = (bytes(PALETTE["r"]) + bytes(PALETTE["g"])) * (side // 2)
    with pytest.raises(BudgetExceeded) as raised:
        analyze_clusters(row * side, Dimensions(side, side))
    context = raised.value.context
    assert context["resource"] == "cluster_runs" and context["limit"] == MAX_CLUSTER_RUNS
    estimated = context["estimated"]
    assert isinstance(estimated, int) and estimated > MAX_CLUSTER_RUNS


# --- property: components against breadth-first search -------------------------------------


def bfs_clusters(
    grid: dict[tuple[int, int], str], width: int, height: int, connectivity: int
) -> list[tuple[int, tuple[int, int]]]:
    steps = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if connectivity == 8:
        steps += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    seen: set[tuple[int, int]] = set()
    found = []
    for y in range(height):
        for x in range(width):
            if (x, y) in seen or grid[(x, y)] == ".":
                continue
            seen.add((x, y))
            frontier, area = [(x, y)], 0
            while frontier:
                px, py = frontier.pop()
                area += 1
                for dx, dy in steps:
                    q = (px + dx, py + dy)
                    if q in grid and q not in seen and grid[q] == grid[(px, py)]:
                        seen.add(q)
                        frontier.append(q)
            found.append((area, (x, y)))
    return found


@settings(max_examples=150, deadline=None)
@given(data=st.data(), width=st.integers(1, 9), height=st.integers(1, 9))
def test_components_match_breadth_first_search(
    data: st.DataObject, width: int, height: int
) -> None:
    cells = data.draw(
        st.lists(st.sampled_from(".rgh"), min_size=width * height, max_size=width * height)
    )
    rows = ["".join(cells[y * width : (y + 1) * width]) for y in range(height)]
    grid = {(x, y): rows[y][x] for x in range(width) for y in range(height)}
    for connectivity in (4, 8):
        got = [(area, (seed.x, seed.y)) for _, _, area, seed in summary(rows, connectivity)]
        assert got == bfs_clusters(grid, width, height, connectivity)


# --- scale: run limit, many exceptions, memory and deadline ---------------------------------


def checkerboard(width: int, height: int) -> bytes:
    """Two opaque colours alternating per pixel: every pixel is a 4-connected singleton."""
    yy, xx = np.mgrid[0:height, 0:width]
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    pixels[(yy + xx) % 2 == 0] = PALETTE["r"]
    pixels[(yy + xx) % 2 == 1] = PALETTE["g"]
    return pixels.tobytes()


def full_mask(width: int, height: int, hole: tuple[int, int] | None = None) -> Mask:
    bits = np.ones((height, width), dtype=np.uint8)
    if hole is not None:
        bits[hole[1], hole[0]] = 0
    return _restore(Box(0, 0, width, height), (height, width), bits.tobytes())


@pytest.mark.slow
def test_run_limit_is_exact_at_a_512_checkerboard() -> None:
    report = analyze_clusters(checkerboard(512, 512), Dimensions(512, 512))
    assert len(report.clusters) == MAX_CLUSTER_RUNS == 512 * 512
    with pytest.raises(BudgetExceeded) as raised:
        analyze_clusters(checkerboard(512, 513), Dimensions(512, 513))
    assert raised.value.context["estimated"] == MAX_CLUSTER_RUNS + 512


def test_many_exceptions_cost_one_cover_query_per_finding(monkeypatch: pytest.MonkeyPatch) -> None:
    """64 full regions with one hole each: the first region holding the pixel wins."""
    side = 64
    dims = Dimensions(side, side)
    holes = [(i, 0) for i in range(MAX_CLUSTER_EXCEPTIONS)]
    regions = {f"r{i}": full_mask(side, side, hole) for i, hole in enumerate(holes)}
    exceptions = [ClusterException(f"r{i}", ("singleton",)) for i in range(len(holes))]
    calls: list[object] = []
    original = MaskCover.common

    def counted(self: MaskCover, boxes: Sequence[Box]) -> int:
        calls.append(boxes)
        return original(self, boxes)

    monkeypatch.setattr(MaskCover, "common", counted)
    report = analyze_clusters(
        checkerboard(side, side), dims, exceptions=exceptions, regions=regions
    )
    assert report.warnings == () and len(report.suppressed) == side * side
    assert len(calls) == side * side  # one vectorised query per finding, not per region
    by_box = {f.box: f.region_id for f in report.suppressed}
    assert by_box[Box(0, 0, 1, 1)] == "r1"  # r0 misses its hole, r1 holds it
    assert by_box[Box(1, 0, 2, 1)] == "r0"
    assert by_box[Box(5, 5, 6, 6)] == "r0"


@pytest.mark.parametrize("connectivity", [4, 8])
@pytest.mark.parametrize("kind", ["checkerboard", "stairs"])
def test_peak_memory_stays_within_cluster_bytes(connectivity: int, kind: str) -> None:
    side = 128
    dims = Dimensions(side, side)
    if kind == "checkerboard":
        data = checkerboard(side, side)
    else:  # blocks of 16 x 8 holding a stair of runs 1, 3, 1, 3, ...
        pixels = np.zeros((side, side, 4), dtype=np.uint8)
        for by, bx in itertools.product(range(side // 8), range(side // 16)):
            x = bx * 16
            for row in range(8):
                length = 1 + 2 * (row % 2)
                pixels[by * 8 + row, x : x + length] = PALETTE["rg"[(bx + by) % 2]]
                x += length
        data = pixels.tobytes()
    regions = {"all": full_mask(side, side)}
    exceptions = [ClusterException("all", CLUSTER_RULES)]
    tracemalloc.start()
    try:
        report = analyze_clusters(
            data,
            dims,
            connectivity=8 if connectivity == 8 else 4,
            exceptions=exceptions,
            regions=regions,
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert report.suppressed or connectivity == 8  # a checkerboard joins with 8
    assert peak <= cluster_bytes(dims) + cover_bytes(dims)


def test_cluster_bytes_formula() -> None:
    assert cluster_bytes(Dimensions(8, 4)) == CLUSTER_RUN_BYTES * 32 + CLUSTER_FIXED_BYTES
    big = Dimensions(2048, 2048)  # capped by the run limit plus one row
    assert cluster_bytes(big) == CLUSTER_RUN_BYTES * (MAX_CLUSTER_RUNS + 2048) + CLUSTER_FIXED_BYTES
    with pytest.raises(TypeError):
        cluster_bytes((8, 4))  # type: ignore[arg-type]  # invalid on purpose


def counting_deadline(expiring_call: int) -> Deadline:
    """A deadline whose fake clock passes it on the ``expiring_call``-th check."""
    ticks = itertools.count()
    return Deadline(1000 * expiring_call, clock=lambda: float(next(ticks)))


def test_deadline_is_checked_in_every_stage() -> None:
    side = 8
    dims = Dimensions(side, side)
    data = checkerboard(side, side)
    regions = {"all": full_mask(side, side)}
    exceptions = [ClusterException("all", ("singleton",))]
    stages = []
    for call in itertools.count(1):
        try:
            analyze_clusters(
                data, dims, exceptions=exceptions, regions=regions, deadline=counting_deadline(call)
            )
        except BudgetExceeded as raised:
            assert raised.context["resource"] == "time"
            stages.append(raised.context["stage"])
            continue
        break
    assert list(dict.fromkeys(stages)) == [
        "mask_cover",
        "cluster_runs",
        "cluster_labels",
        "cluster_tally",
        "cluster_findings",
    ]
    with pytest.raises(TypeError, match="Deadline"):
        analyze_clusters(data, dims, deadline=5)  # type: ignore[arg-type]  # invalid on purpose


def test_settings_are_checked_before_anything_else() -> None:
    too_many = [
        ClusterException(f"r{i}", ("singleton",)) for i in range(MAX_CLUSTER_EXCEPTIONS + 1)
    ]
    with pytest.raises(ValidationError) as raised:
        check_cluster_settings(4, too_many)
    assert raised.value.context["reason"] == "too_many_exceptions"
    assert check_cluster_settings(8, []) == (8, ())
    with pytest.raises(ValidationError) as bad:
        analyze_clusters(b"", Dimensions(1, 1), connectivity=6)  # type: ignore[arg-type]  # invalid on purpose
    assert bad.value.context["reason"] == "size_mismatch"  # the input itself comes first
