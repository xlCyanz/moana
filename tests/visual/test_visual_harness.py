"""Exact visual regression harness (MOANA-028, MOANA.md section 21).

Oracles are hand-written literals and hand-computed bboxes/counts; the harness is never
its own oracle and no renderer is involved.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, PngImagePlugin

from moana.core import BudgetExceeded, RenderLimits, ValidationError
from moana.core.canvas import Canvas

from .harness import (
    ARTIFACTS_ENV,
    DIFF_ADDED,
    DIFF_CHANGED,
    GOLDENS_DIR,
    MANIFEST_FORMAT,
    UPDATE_ENV,
    BBox,
    VisualMismatch,
    assert_matches_golden,
    ci_active,
    compare_rgba,
    default_name,
    diff_rgba,
    load_png,
    normalize_rgba,
    update_requested,
    visual_digest,
)

pytestmark = pytest.mark.visual


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test states its own CI/update policy; the runner's variables never leak in."""
    for name in ("CI", UPDATE_ENV, ARTIFACTS_ENV):
        monkeypatch.delenv(name, raising=False)


R = (200, 40, 40, 255)
G = (40, 160, 60, 255)
B = (30, 60, 200, 128)
T = (0, 0, 0, 0)

REFERENCE_ROWS = [
    [R, G, B, T],
    [G, B, T, R],
    [B, T, R, G],
]
"""4 x 3 reference fixture; committed as ``goldens/harness-reference-4x3.png``."""


def rgba(rows: list[list[tuple[int, int, int, int]]]) -> np.ndarray:
    return np.array(rows, dtype=np.uint8)


def reference() -> np.ndarray:
    return rgba(REFERENCE_ROWS)


def save(array: np.ndarray, path: Path, **options: object) -> Path:
    """Encode with plain Pillow (independent of the harness writer)."""
    height, width = array.shape[:2]
    Image.frombytes("RGBA", (width, height), array.tobytes()).save(path, "PNG", **options)
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        assert image.mode == "RGBA"
        return np.frombuffer(image.tobytes(), dtype=np.uint8).reshape(image.height, image.width, 4)


# --- Comparator (T1, AC1) ---------------------------------------------------------


def test_identical_buffers_match() -> None:
    result = compare_rgba(reference(), reference())
    assert result.matches
    assert result.differing_pixels == 0
    assert result.bbox is None
    assert result.expected_digest == result.actual_digest


def test_one_changed_pixel_fails_with_hand_computed_bbox_and_count() -> None:
    """AC1 / T1: pixel (x=2, y=1) changed -> count 1, bbox [2,3) x [1,2)."""
    actual = reference()
    actual[1, 2] = (1, 2, 3, 255)
    result = compare_rgba(reference(), actual)
    assert not result.matches
    assert result.dimensions_match
    assert result.differing_pixels == 1
    assert result.bbox == BBox(2, 1, 3, 2)
    assert result.expected_digest != result.actual_digest


def test_single_channel_alpha_change_is_a_difference() -> None:
    actual = reference()
    actual[0, 0, 3] = 254
    result = compare_rgba(reference(), actual)
    assert (result.differing_pixels, result.bbox) == (1, BBox(0, 0, 1, 1))


def test_scattered_differences_bbox_spans_all() -> None:
    actual = reference()
    actual[0, 1] = T
    actual[2, 3] = R
    result = compare_rgba(reference(), actual)
    assert result.differing_pixels == 2
    assert result.bbox == BBox(1, 0, 4, 3)


def test_different_dimensions_fail_over_the_union() -> None:
    """T1: 4x3 vs 4x2 (top-left anchored): the missing row (4 px) differs."""
    result = compare_rgba(reference(), reference()[:2])
    assert not result.dimensions_match
    assert not result.matches
    assert (result.expected_size, result.actual_size) == ((4, 3), (4, 2))
    assert result.differing_pixels == 4
    assert result.bbox == BBox(0, 2, 4, 3)


def test_transposed_dimensions_with_same_pixel_count_fail() -> None:
    """3x4 vs 4x3: same byte length, different dimensions and digests."""
    expected = reference()
    actual = expected.reshape(4, 3, 4)
    result = compare_rgba(expected, actual)
    assert not result.matches
    assert result.expected_digest != result.actual_digest
    # Union 4x4. Only in one image: column x=3 of rows 0..2 (3) + row y=3 of cols 0..2 (3).
    # Common 3x3, by hand: row 0 [R,G,B]=[R,G,B]; row 1 [G,B,T] vs [T,G,B] (3);
    # row 2 [B,T,R] vs [T,R,B] (3). Total 12.
    assert result.differing_pixels == 12
    assert result.bbox == BBox(0, 0, 4, 4)


def test_zero_alpha_with_residual_rgb_is_equal() -> None:
    """T1: transparent pixels compare as (0, 0, 0, 0) whatever their RGB."""
    residual = reference()
    residual[0, 3] = (9, 99, 199, 0)
    residual[1, 2] = (255, 255, 255, 0)
    result = compare_rgba(reference(), residual)
    assert result.matches
    assert result.actual_digest == visual_digest(reference())


def test_inputs_are_not_mutated_and_canvas_is_accepted() -> None:
    residual = reference()
    residual[0, 3] = (9, 99, 199, 0)
    before = residual.copy()
    canvas = Canvas.from_array(reference(), limits=RenderLimits())
    assert compare_rgba(canvas, residual).matches
    assert np.array_equal(residual, before)
    assert normalize_rgba(residual)[0, 3].tolist() == [0, 0, 0, 0]


def test_digest_follows_section_14_and_agrees_with_canvas() -> None:
    """Hand formula: SHA-256(width BE32 || height BE32 || RGBA row-major)."""
    pixels = reference()
    oracle = hashlib.sha256(
        (4).to_bytes(4, "big") + (3).to_bytes(4, "big") + pixels.tobytes()
    ).hexdigest()
    assert visual_digest(pixels) == "sha256:" + oracle
    canvas = Canvas.from_array(pixels, limits=RenderLimits())
    assert visual_digest(pixels) == canvas.visual_digest()


@pytest.mark.parametrize(
    "bad",
    [
        np.zeros((2, 2, 4), dtype=np.int16),
        np.zeros((2, 2, 3), dtype=np.uint8),
        np.zeros((0, 2, 4), dtype=np.uint8),
        [[[0, 0, 0, 0]]],
    ],
)
def test_rejects_non_rgba_buffers(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        compare_rgba(reference(), bad)  # type: ignore[arg-type]  # deliberate bad input


def test_diff_image_marks_changes_and_extra_area() -> None:
    actual = reference()[:2].copy()
    actual[0, 1] = R
    diff = diff_rgba(reference(), actual)
    assert diff.shape == (3, 4, 4)
    assert tuple(diff[0, 1]) == DIFF_CHANGED
    assert all(tuple(diff[2, x]) == DIFF_ADDED for x in range(4))
    unchanged = diff[:2].reshape(-1, 4)
    others = [tuple(p) for i, p in enumerate(unchanged) if i != 1]
    assert all(p[3] == 255 and 16 <= p[0] == p[1] == p[2] <= 96 for p in others)


# --- Golden assertion (AC2, AC1, T2) -----------------------------------------------


def test_same_pixels_pass_with_different_png_bytes(tmp_path: Path) -> None:
    """AC2: two encodings (compression, metadata, residual RGB) of the same pixels."""
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "different metadata")
    residual = reference()
    residual[0, 3] = (12, 34, 56, 0)
    golden = save(residual, tmp_path / "golden.png", compress_level=9, pnginfo=info)
    other = save(reference(), tmp_path / "other.png", compress_level=0)
    assert golden.read_bytes() != other.read_bytes()
    artifacts = tmp_path / "artifacts"
    assert_matches_golden(load_png(other), golden, artifacts=artifacts, update=False)
    assert_matches_golden(reference(), golden, artifacts=artifacts, update=False)
    assert not artifacts.exists()


def test_failure_writes_valid_diagnostics_and_keeps_baseline(tmp_path: Path) -> None:
    """AC1 + T2: one-pixel failure, decodable PNGs, valid manifest, baseline intact."""
    folder = tmp_path / "golden dir with spaces"
    folder.mkdir()
    golden = save(reference(), folder / "sprite golden.png")
    digest_before = sha256(golden)
    actual = reference()
    actual[2, 1] = G
    artifacts = tmp_path / "visual artifacts"

    with pytest.raises(VisualMismatch) as failure:
        assert_matches_golden(actual, golden, artifacts=artifacts, update=False)

    assert sha256(golden) == digest_before
    out = artifacts / "sprite golden"
    assert failure.value.manifest == out / "manifest.json"
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == MANIFEST_FORMAT
    assert manifest["differing_pixels"] == 1
    assert manifest["bbox"] == {"x0": 1, "y0": 2, "x1": 2, "y1": 3}
    assert manifest["dimensions_match"] is True
    assert manifest["expected"]["width"] == 4 and manifest["expected"]["height"] == 3
    assert manifest["expected"]["digest"] == visual_digest(reference())
    assert manifest["actual"]["digest"] == visual_digest(actual)
    assert manifest["files"] == {
        "expected": "expected.png",
        "actual": "actual.png",
        "diff": "diff.png",
    }
    assert {"python", "numpy", "pillow", "platform"} <= manifest["environment"].keys()
    assert np.array_equal(decode(out / manifest["files"]["expected"]), reference())
    assert np.array_equal(decode(out / manifest["files"]["actual"]), actual)
    diff = decode(out / manifest["files"]["diff"])
    assert tuple(diff[2, 1]) == DIFF_CHANGED
    assert int(np.count_nonzero(np.all(diff == DIFF_CHANGED, axis=2))) == 1


def test_dimension_mismatch_diagnostics(tmp_path: Path) -> None:
    golden = save(reference(), tmp_path / "g.png")
    with pytest.raises(VisualMismatch):
        assert_matches_golden(reference()[:, :3], golden, artifacts=tmp_path / "a", update=False)
    manifest = json.loads((tmp_path / "a/g/manifest.json").read_text(encoding="utf-8"))
    assert manifest["dimensions_match"] is False
    assert manifest["differing_pixels"] == 3
    assert (manifest["changed_pixels"], manifest["only_in_one_pixels"]) == (0, 3)
    assert manifest["bbox"] == {"x0": 3, "y0": 0, "x1": 4, "y1": 3}
    assert decode(tmp_path / "a/g/diff.png").shape == (3, 4, 4)


def test_missing_golden_fails_without_creating_it(tmp_path: Path) -> None:
    golden = tmp_path / "missing.png"
    with pytest.raises(VisualMismatch, match="does not exist"):
        assert_matches_golden(reference(), golden, artifacts=tmp_path / "a", update=False)
    assert not golden.exists()
    manifest = json.loads((tmp_path / "a/missing/manifest.json").read_text(encoding="utf-8"))
    assert manifest["baseline_found"] is False
    assert manifest["files"] == {"expected": None, "actual": "actual.png", "diff": None}


def test_explicit_update_rewrites_baseline_and_still_fails(tmp_path: Path) -> None:
    golden = save(reference(), tmp_path / "g.png")
    actual = reference()
    actual[0, 0] = B
    with pytest.raises(VisualMismatch, match="rewritten"):
        assert_matches_golden(actual, golden, artifacts=tmp_path / "a", update=True)
    assert np.array_equal(decode(golden), actual)
    assert (tmp_path / "a/g/expected.png").is_file()
    assert_matches_golden(actual, golden, artifacts=tmp_path / "b", update=False)


def test_explicit_update_creates_missing_baseline(tmp_path: Path) -> None:
    golden = tmp_path / "new golden.png"
    with pytest.raises(VisualMismatch, match="rewritten"):
        assert_matches_golden(reference(), golden, artifacts=tmp_path / "a", update=True)
    assert np.array_equal(decode(golden), reference())


def test_update_does_not_touch_an_equal_baseline(tmp_path: Path) -> None:
    golden = save(reference(), tmp_path / "g.png", compress_level=1)
    before = sha256(golden)
    assert_matches_golden(reference(), golden, artifacts=tmp_path / "a", update=True)
    assert sha256(golden) == before


def test_update_flag_is_explicit_and_refused_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(UPDATE_ENV, raising=False)
    monkeypatch.delenv("CI", raising=False)
    assert update_requested() is False
    monkeypatch.setenv(UPDATE_ENV, "true")
    assert update_requested() is False
    monkeypatch.setenv(UPDATE_ENV, "1")
    assert update_requested() is True
    monkeypatch.setenv("CI", "true")
    with pytest.raises(RuntimeError, match="CI"):
        update_requested()


def test_ci_never_writes_baseline_even_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(UPDATE_ENV, "1")
    monkeypatch.setenv("CI", "true")
    golden = save(reference(), tmp_path / "g.png")
    before = sha256(golden)
    with pytest.raises(RuntimeError):
        assert_matches_golden(reference()[:2], golden, artifacts=tmp_path / "a")
    assert sha256(golden) == before


@pytest.mark.parametrize("name", ["../escape", "a/b", "", ".hidden"])
def test_rejects_unsafe_diagnostic_names(tmp_path: Path, name: str) -> None:
    golden = save(reference(), tmp_path / "g.png")
    with pytest.raises(ValueError, match="unsafe"):
        assert_matches_golden(reference(), golden, artifacts=tmp_path / "a", name=name)


def test_rejects_non_rgba_golden(tmp_path: Path) -> None:
    golden = tmp_path / "rgb.png"
    Image.new("RGB", (2, 2)).save(golden, "PNG")
    with pytest.raises(ValidationError, match="RGBA"):
        load_png(golden)


# --- Committed reference golden ----------------------------------------------------


def test_reference_fixture_matches_committed_golden(tmp_path: Path) -> None:
    """End to end over the real goldens folder; the PNG is also decoded independently."""
    golden = GOLDENS_DIR / "harness-reference-4x3.png"
    assert np.array_equal(decode(golden), reference())
    assert_matches_golden(reference(), golden, artifacts=tmp_path / "a")


# --- QA follow-ups -------------------------------------------------------------------


def test_ci_blocks_explicit_update_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T2: ``update=True`` cannot bypass the CI guard; the baseline stays intact."""
    monkeypatch.setenv("CI", "true")
    golden = save(reference(), tmp_path / "g.png")
    before = sha256(golden)
    actual = reference()
    actual[1, 1] = R
    with pytest.raises(RuntimeError, match="CI"):
        assert_matches_golden(actual, golden, artifacts=tmp_path / "a", update=True)
    assert sha256(golden) == before


@pytest.mark.parametrize(
    ("ci", "refused"),
    [
        ("", False),
        ("0", False),
        ("false", False),
        (" False ", False),
        ("1", True),
        ("yes", True),
        ("true", True),
        ("TRUE", True),
    ],
)
def test_ci_policy(monkeypatch: pytest.MonkeyPatch, ci: str, refused: bool) -> None:
    monkeypatch.setenv("CI", ci)
    monkeypatch.setenv(UPDATE_ENV, "1")
    assert ci_active() is refused
    if refused:
        with pytest.raises(RuntimeError, match="CI"):
            update_requested()
    else:
        assert update_requested() is True


@pytest.mark.parametrize("value", [" 1", "1 ", "01", "yes", "TRUE", ""])
def test_update_needs_exactly_one(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(UPDATE_ENV, value)
    assert update_requested() is False


def test_stale_diagnostics_are_replaced(tmp_path: Path) -> None:
    """T2: a failure with baseline, then one without, leaves no stale expected/diff."""
    golden = save(reference(), tmp_path / "case.png")
    artifacts = tmp_path / "a"
    with pytest.raises(VisualMismatch):
        assert_matches_golden(reference()[:2], golden, artifacts=artifacts, update=False)
    out = artifacts / "case"
    assert (out / "expected.png").is_file() and (out / "diff.png").is_file()
    golden.unlink()
    with pytest.raises(VisualMismatch, match="does not exist"):
        assert_matches_golden(reference(), golden, artifacts=artifacts, update=False)
    assert sorted(path.name for path in out.iterdir()) == ["actual.png", "manifest.json"]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["baseline_found"] is False
    assert manifest["actual"]["height"] == 3
    assert np.array_equal(decode(out / "actual.png"), reference())


def test_passing_comparison_clears_previous_diagnostics(tmp_path: Path) -> None:
    golden = save(reference(), tmp_path / "case.png")
    artifacts = tmp_path / "a"
    with pytest.raises(VisualMismatch):
        assert_matches_golden(reference()[:2], golden, artifacts=artifacts, update=False)
    (artifacts / "case" / "notes.txt").write_text("kept", encoding="utf-8")
    assert_matches_golden(reference(), golden, artifacts=artifacts, update=False)
    assert [path.name for path in (artifacts / "case").iterdir()] == ["notes.txt"]


def test_source_is_recorded_in_manifest(tmp_path: Path) -> None:
    golden = save(reference(), tmp_path / "g.png")
    with pytest.raises(VisualMismatch):
        assert_matches_golden(
            reference()[:2],
            golden,
            artifacts=tmp_path / "a",
            update=False,
            source="tests/visual: REFERENCE_ROWS[:2]",
        )
    manifest = json.loads((tmp_path / "a/g/manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == "tests/visual: REFERENCE_ROWS[:2]"


def test_default_names_do_not_collide_between_golden_subfolders(tmp_path: Path) -> None:
    assert default_name(GOLDENS_DIR / "sprites" / "hero.png") == "sprites__hero"
    assert default_name(GOLDENS_DIR / "tiles" / "hero.png") == "tiles__hero"
    assert default_name(GOLDENS_DIR / "harness-reference-4x3.png") == "harness-reference-4x3"
    assert default_name(tmp_path / "with spaces" / "a b.png") == "a b"
    assert default_name(tmp_path / "ñandú+1.png") == "_and__1"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_written_files_are_world_readable(tmp_path: Path) -> None:
    golden = tmp_path / "new.png"
    with pytest.raises(VisualMismatch):
        assert_matches_golden(reference(), golden, artifacts=tmp_path / "a", update=True)
    for path in (golden, tmp_path / "a/new/actual.png", tmp_path / "a/new/manifest.json"):
        assert stat.S_IMODE(path.stat().st_mode) & 0o044 == 0o044


def test_budget_is_checked_before_copying(tmp_path: Path) -> None:
    """A broadcast view reserves no memory; the harness must reject it before copying."""
    huge = np.broadcast_to(np.zeros((1, 1, 4), dtype=np.uint8), (2049, 1, 4))
    with pytest.raises((ValidationError, BudgetExceeded)):
        compare_rgba(reference(), huge)


def test_diff_outside_both_images_differs_from_unchanged_black() -> None:
    """2x1 vs 1x2 of opaque black: unchanged (0,0) is grey 16, corner (1,1) is black."""
    black = (0, 0, 0, 255)
    diff = diff_rgba(rgba([[black, black]]), rgba([[black], [black]]))
    assert tuple(diff[0, 0]) == (16, 16, 16, 255)
    assert tuple(diff[0, 1]) == DIFF_ADDED
    assert tuple(diff[1, 0]) == DIFF_ADDED
    assert tuple(diff[1, 1]) == (0, 0, 0, 255)
    result = compare_rgba(rgba([[black, black]]), rgba([[black], [black]]))
    assert (result.changed_pixels, result.only_in_one_pixels) == (0, 2)
    assert result.bbox == BBox(0, 0, 2, 2)
