"""T1/T2: smoke report, work counters, absence of caching, statistics, memory and privacy.

No test here asserts a latency: timings are only checked for shape (MOANA-031,
docs/standards/testing.md). Oracles: hand-computed statistics, operation counts read
from the corpus JSON and digests rendered independently with ``moana.api.render``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tracemalloc
from pathlib import Path
from typing import Any

import pytest

from moana import api
from moana.animation import evaluate_animation
from moana.schema import Document, validate_document

from . import corpus, measure, report
from .conftest import SMOKE_SAMPLES, SMOKE_WARMUPS
from .corpus import Json

BASELINE = Path(__file__).resolve().parent / "results" / "macos-arm64-py312"

pytestmark = pytest.mark.benchmark

STATS_KEYS = {"count", "min_ns", "median_ns", "p95_ns", "max_ns", "mean_ns"}
ENV_KEYS = {
    "cpu_model",
    "cpu_count",
    "machine",
    "os",
    "os_release",
    "macos_version",
    "python_implementation",
    "python_version",
    "moana",
    "numpy",
    "pillow",
    "aggdraw",
    "pydantic",
    "lock_sha256",
    "git",
    "renderer_version",
    "renderer_backend",
    "estimator_version",
}


def _rect_count(name: str) -> int:
    tree = corpus.case_document(name)
    return sum(len(layer["operations"]) for layer in tree["layers"])


def _document(name: str) -> Document:
    return validate_document(corpus.canonical_bytes(corpus.case_document(name)))


# --- T1: smoke report ---------------------------------------------------------------


def test_t1_smoke_report_is_well_formed(smoke_report: Json) -> None:
    assert smoke_report["format"] == "moana-benchmark/1"
    assert "Informational" in smoke_report["note"]
    method = smoke_report["method"]
    assert (method["warmups"], method["samples"]) == (SMOKE_WARMUPS, SMOKE_SAMPLES)
    assert "nearest-rank" in method["p95"]
    assert set(smoke_report["environment"]) == ENV_KEYS
    assert set(smoke_report["environment"]["git"]) == {"commit", "dirty"}
    assert re.fullmatch(r"[0-9a-f]{64}", smoke_report["environment"]["lock_sha256"])
    assert smoke_report["corpus_digest"] == corpus.corpus_digest(("static", "animation"))
    assert set(smoke_report["cases"]) == {"static", "animation"}
    phases = {name: set(case["phases"]) for name, case in smoke_report["cases"].items()}
    assert phases == {
        "static": {"parse", "render", "encode_png", "write_png"},
        "animation": {"parse", "render", "render_frame"},
    }
    for case in smoke_report["cases"].values():
        for phase in case["phases"].values():
            assert set(phase["stats"]) == STATS_KEYS
            stats = phase["stats"]
            assert stats["min_ns"] <= stats["median_ns"] <= stats["p95_ns"] <= stats["max_ns"]
        assert len(case["phases"]["render"]["samples_ns"]) == SMOKE_SAMPLES
        assert case["memory"]["tracemalloc_scope"] == "python-heap-only"


def test_t1_animation_reports_the_sequence_and_every_frame(smoke_report: Json) -> None:
    animation = smoke_report["cases"]["animation"]
    assert animation["kind"] == "animation" and animation["animation_id"] == "bench_loop"
    frames = animation["phases"]["render_frame"]
    assert len(frames["per_frame_median_ns"]) == len(frames["per_frame_p95_ns"]) == 16
    assert frames["stats"]["count"] == 16 * SMOKE_SAMPLES
    assert animation["cost_plan"]["frames"] == 16
    assert animation["cost_plan"]["operations"] == 16 * 500


def test_t1_targets_are_stated_with_true_false_or_null(smoke_report: Json) -> None:
    targets = smoke_report["targets"]
    assert {key: target["limit"] for key, target in targets.items()} == {
        "static_render_median_ms": 100,
        "animation_16_frames_median_ms": 2000,
        "process_peak_rss_mib": 256,
    }
    for target in targets.values():
        if target["measured"] is None:
            assert target["met"] is None
        else:
            assert target["met"] is (target["measured"] <= target["limit"])


def test_t1_markdown_summary_lists_machine_targets_and_budgets(smoke_output: Path) -> None:
    text = smoke_output.with_suffix(".md").read_text(encoding="utf-8")
    for heading in ("## Máquina", "## Objetivos", "## Fases (ms)", "## Memoria (MiB)"):
        assert heading in text
    assert "## Casos adversos" in text and "informativos" in text


# --- T2: counters and absence of caching --------------------------------------------


@pytest.mark.parametrize(("name", "frames"), [("static", 1), ("animation", 16)])
def test_t2_counters_are_equal_non_zero_and_match_the_json(
    smoke_report: Json, name: str, frames: int
) -> None:
    render = smoke_report["cases"][name]["phases"]["render"]
    expected_calls = frames * _rect_count(name)
    assert render["rasterize_calls"] == [expected_calls] * SMOKE_SAMPLES
    checkpoints = render["checkpoints"]
    assert len(set(checkpoints)) == 1 and checkpoints[0] > expected_calls


def test_t2_every_sample_matches_an_independent_reference(smoke_report: Json) -> None:
    static = smoke_report["cases"]["static"]["phases"]["render"]
    assert static["digests"] == [api.render(_document("static")).digest]
    animation = _document("animation")
    frames = evaluate_animation(animation, corpus.ANIMATION_ID)
    expected = measure.sequence_digest([api.render(frame.document) for frame in frames])
    sequence = smoke_report["cases"]["animation"]["phases"]["render"]
    assert sequence["digests"] == [expected]
    for render in (static, sequence):
        assert render["samples_matching_reference"] == SMOKE_SAMPLES


def test_t2_a_changed_rect_is_drawn_again_with_the_same_work() -> None:
    base = _document("static")
    # The last rect is painted on top of everything: its new colour must show.
    top = corpus.RECTS - 1
    changed = validate_document(corpus.canonical_bytes(corpus.static_document(recolour=top)))
    render_base = measure.render_once(base, None)
    render_changed = measure.render_once(changed, None)
    first = measure.sample_render(render_base)
    other = measure.sample_render(render_changed)
    again = measure.sample_render(render_base)
    assert other.digest != first.digest == again.digest
    assert first.rasterize_calls == other.rasterize_calls == again.rasterize_calls == 500
    assert first.checkpoints == other.checkpoints == again.checkpoints


def test_t2_counting_wrapper_is_removed_after_a_sample() -> None:
    import moana.render.pipeline as pipeline

    original = pipeline._rasterize
    measure.sample_render(measure.render_once(_document("corpus/stone-tile"), None))
    assert pipeline._rasterize is original


def test_t2_the_engine_has_no_memoisation() -> None:
    source = Path(__file__).resolve().parents[2] / "src" / "moana"
    pattern = re.compile(r"lru_cache|functools\.cache\b|@cache\b|cached_property")
    hits = [
        path.relative_to(source).as_posix()
        for path in sorted(source.rglob("*.py"))
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert hits == []


def test_t2_measure_render_returns_samples_and_reference() -> None:
    document = _document("corpus/stone-tile")
    samples, reference = measure.measure_render(document, None, warmups=1, samples=2)
    assert [s.digest for s in samples] == [reference, reference]
    assert samples[0].rasterize_calls == samples[1].rasterize_calls > 0


def test_run_case_in_process_rejects_bad_counts() -> None:
    with pytest.raises(ValueError, match="warmups"):
        measure.run_case("static", -1, 3)
    with pytest.raises(ValueError, match="samples"):
        measure.run_case("static", 0, 0)
    bad: list[tuple[Any, Any]] = [(True, 3), (0, True), (1.0, 3), (0, "3")]
    for warmups, samples in bad:
        with pytest.raises(TypeError):
            measure.run_case("static", warmups, samples)
    with pytest.raises(TypeError):
        report.run_benchmark(["static"], warmups=False)
    with pytest.raises(ValueError, match="more than once"):
        report.run_benchmark(["static", "static"], warmups=0, samples=1)


def test_worker_argv_is_checked(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in ([], ["static"], ["static", "1"], ["static", "x", "3"], ["a", "1", "2", "3"]):
        assert measure.main(argv) == 2
        assert capsys.readouterr().err == measure.WORKER_USAGE


# --- Statistics oracles -------------------------------------------------------------


def test_stats_against_hand_computed_values() -> None:
    odd = measure.summarize([5, 1, 3])
    assert odd == {
        "count": 3,
        "min_ns": 1,
        "median_ns": 3.0,
        "p95_ns": 5,
        "max_ns": 5,
        "mean_ns": 3.0,
    }
    assert type(odd["median_ns"]) is float
    even = measure.summarize([40, 10, 30, 20])
    assert even["median_ns"] == 25.0 and even["mean_ns"] == 25.0 and even["p95_ns"] == 40
    thirty = list(range(1, 31))  # ceil(0.95 * 30) = 29th smallest
    assert measure.nearest_rank(thirty, 95) == 29
    assert measure.nearest_rank(list(range(1, 21)), 95) == 19  # ceil(19.0) = 19
    assert measure.nearest_rank(list(range(100, 0, -1)), 50) == 50
    assert measure.nearest_rank([7], 95) == 7
    assert measure.nearest_rank([3, 9], 100) == 9


def test_stats_reject_empty_input_bad_percentiles_and_non_ints() -> None:
    with pytest.raises(ValueError):
        measure.summarize([])
    with pytest.raises(ValueError):
        measure.nearest_rank([], 50)
    for percentile in (0, 101):
        with pytest.raises(ValueError):
            measure.nearest_rank([1], percentile)
    wrong: list[Any] = [True, 95.0]
    for percentile in wrong:
        with pytest.raises(TypeError):
            measure.nearest_rank([1], percentile)
    values: list[Any] = [[1, True], [1.5]]
    for sample in values:
        with pytest.raises(TypeError):
            measure.nearest_rank(sample, 50)


# --- Memory -------------------------------------------------------------------------

LINUX_STATUS = "Name:\tpython3\nVmPeak:\t  400000 kB\nVmHWM:\t   65432 kB\nVmRSS:\t   60000 kB\n"


def test_rss_units_are_normalised_per_platform() -> None:
    assert measure.normalize_maxrss(1000, "Darwin") == 1000
    assert measure.normalize_maxrss(1000, "Linux") == 1_024_000
    assert measure.normalize_maxrss(1000, "FreeBSD") == 1_024_000


def test_linux_vmhwm_is_parsed_from_the_status_text() -> None:
    assert measure.parse_vmhwm(LINUX_STATUS) == 65432 * 1024
    assert measure.parse_vmhwm("VmRSS:\t 10 kB\n") is None
    assert measure.parse_vmhwm("") is None


def test_peak_rss_is_plausible_on_this_platform() -> None:
    value = measure.peak_rss()
    peak = value["bytes"]
    if peak is None:  # pragma: no cover - Windows only
        assert value["reason"]
    else:
        assert value["reason"] is None
        assert value["source"] == ("VmHWM" if sys.platform.startswith("linux") else "ru_maxrss")
        assert isinstance(peak, int) and 8 * 1024 * 1024 < peak < 64 * 1024**3
        assert isinstance(value["ru_maxrss_bytes"], int)


def test_peak_rss_is_null_with_a_reason_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert measure.peak_rss() == {
        "bytes": None,
        "source": None,
        "ru_maxrss_bytes": None,
        "reason": "resource module unavailable on this platform",
    }


def test_rss_target_is_unknown_when_rss_is_missing() -> None:
    case = {"phases": {"render": {"stats": {"median_ns": 5e7}}}, "memory": {"peak_rss_bytes": None}}
    targets = report.evaluate_targets({"static": case})
    assert targets["static_render_median_ms"] == {"limit": 100, "measured": 50.0, "met": True}
    assert targets["animation_16_frames_median_ms"]["met"] is None
    assert targets["process_peak_rss_mib"] == {"limit": 256, "measured": None, "met": None}


def test_tracemalloc_peak_sees_a_python_allocation() -> None:
    size = 4 * 1024 * 1024
    assert measure.tracemalloc_peak(lambda: bytearray(size)) >= size


def test_tracemalloc_peak_is_relative_and_keeps_an_outer_tracer() -> None:
    size = 2 * 1024 * 1024
    outer = tracemalloc.is_tracing()
    if not outer:
        tracemalloc.start()
    try:
        held = bytearray(8 * size)  # traced before the measured block: not counted
        peak = measure.tracemalloc_peak(lambda: bytearray(size))
        assert size <= peak < 2 * size
        assert tracemalloc.is_tracing()
        del held
    finally:
        if not outer:
            tracemalloc.stop()
    assert tracemalloc.is_tracing() is outer


# --- Environment and subprocesses ---------------------------------------------------


def test_cpuinfo_parser_covers_x86_and_arm() -> None:
    x86 = "processor\t: 0\nmodel name\t: Intel(R) Xeon(R) CPU @ 2.20GHz\nflags\t: fpu\n"
    assert report.parse_cpuinfo(x86) == "Intel(R) Xeon(R) CPU @ 2.20GHz"
    hardware = "processor\t: 0\nHardware\t: BCM2835\nCPU part\t: 0xd08\n"
    assert report.parse_cpuinfo(hardware) == "BCM2835"
    arm = "processor\t: 0\nCPU implementer\t: 0x41\nCPU part\t: 0xd0c\n"
    assert report.parse_cpuinfo(arm) == "CPU implementer 0x41 CPU part 0xd0c"
    assert report.parse_cpuinfo("CPU part\t: 0xd0c\n") == "CPU part 0xd0c"
    assert report.parse_cpuinfo("processor\t: 0\nmodel name\t:\n") is None


@pytest.mark.parametrize(
    "error",
    [OSError("missing"), subprocess.TimeoutExpired("tool", 10), subprocess.SubprocessError("x")],
)
def test_tool_failures_become_null(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def failing(*args: object, **kwargs: object) -> object:
        raise error

    monkeypatch.setattr(subprocess, "run", failing)
    assert report.git_state() == {"commit": None, "dirty": None}


def test_worker_timeout_is_proportional_and_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    assert report.worker_timeout(5, 30) == 60 + 35 * 30
    seen: dict[str, object] = {}

    def hanging(*args: object, **kwargs: object) -> object:
        seen.update(kwargs)
        raise subprocess.TimeoutExpired("worker", 1)

    monkeypatch.setattr(subprocess, "run", hanging)
    with pytest.raises(report.BenchmarkError, match="worker for static timed out"):
        report.run_worker("static", 1, 3)
    assert seen["timeout"] == 60 + 4 * 30 and seen["stdin"] == subprocess.DEVNULL


def test_worker_failure_is_reported() -> None:
    with pytest.raises(report.BenchmarkError, match="worker for nope failed"):
        report.run_worker("nope", 0, 1)


# --- Summary ------------------------------------------------------------------------


def test_committed_baseline_summary_regenerates_from_its_json() -> None:
    text = BASELINE.with_suffix(".json").read_text(encoding="utf-8")
    baseline = json.loads(text)
    assert report.canonical_report(baseline) == text
    expected = BASELINE.with_suffix(".md").read_text(encoding="utf-8")
    assert report.summary_markdown(baseline) == expected
    assert report.ordered_cases(baseline) == list(corpus.case_names())


def test_smoke_summary_regenerates_from_its_json(smoke_output: Path) -> None:
    value = json.loads(smoke_output.with_suffix(".json").read_text(encoding="utf-8"))
    expected = smoke_output.with_suffix(".md").read_text(encoding="utf-8")
    assert report.summary_markdown(value) == expected


def test_unknown_cases_are_summarised_after_the_corpus() -> None:
    assert report.ordered_cases({"cases": {"zeta": {}, "static": {}, "alpha": {}}}) == [
        "static",
        "alpha",
        "zeta",
    ]


# --- Privacy ------------------------------------------------------------------------


def test_privacy_report_has_no_host_user_or_absolute_path(smoke_output: Path) -> None:
    text = smoke_output.with_suffix(".json").read_text(encoding="utf-8")
    markdown = smoke_output.with_suffix(".md").read_text(encoding="utf-8")
    for content in (text, markdown):
        assert str(corpus.ROOT) not in content
        assert str(Path.home()) not in content
        assert str(smoke_output.parent) not in content
    assert report.privacy_findings(json.loads(text)) == []


# Common CI account names and words of the report vocabulary. A name that equals a whole
# word of an environment value ("Apple" in "Apple M4", "render" in "render-v1") cannot be
# told apart from a leak and is reported, by design.
@pytest.mark.parametrize("name", ["runner", "apple", "static", "ubuntu", "admin", "parse"])
def test_privacy_vocabulary_is_not_a_leak(smoke_output: Path, name: str) -> None:
    baseline = json.loads(BASELINE.with_suffix(".json").read_text(encoding="utf-8"))
    smoke = json.loads(smoke_output.with_suffix(".json").read_text(encoding="utf-8"))
    for value in (baseline, smoke):
        assert report.privacy_findings(value, {"user": name, "hostname": name}) == []


def test_privacy_findings_detect_leaks_in_the_environment() -> None:
    markers = {"hostname": "build-box-7", "user": "runner"}
    clean = {"note": "runner", "environment": {"cpu": "Apple M4", "os_release": "6.5.0"}}
    assert report.privacy_findings(clean, markers) == []
    leaks = {"environment": {"os_release": "6.5.0-runner", "cpu": "on build-box-7"}}
    assert report.privacy_findings(leaks, markers) == ["hostname", "user"]
    assert report.privacy_findings({"environment": {"x": "runners"}}, markers) == []
    assert report.privacy_findings(["not", "a", "mapping"], markers) == []


@pytest.mark.parametrize(
    "text",
    [
        "/etc/passwd",
        "built in /private/var/folders/x",
        "path=/tmp/a",
        "C:/Users/x",
        "C:\\Users\\x",
        "see (D:\\data)",
        "~/moana",
        "at ~\\moana",
        "\\\\server\\share",
        "cwd:/srv/x",
    ],
)
def test_absolute_paths_are_found_anywhere(text: str) -> None:
    assert report.privacy_findings({"k": text}, {}) == ["absolute_path"]
    assert report.privacy_findings({text: 1}, {}) == ["absolute_path"]


@pytest.mark.parametrize(
    "text", ["I/O", "sha256:abcd", "nearest-rank: sorted[ceil(0.95 * n) - 1]", "1/2", "a/b"]
)
def test_relative_text_is_not_a_path(text: str) -> None:
    assert report.privacy_findings({"k": text}, {}) == []


def test_home_and_root_markers_match_with_either_separator() -> None:
    markers = {"home": "C:\\Users\\ana"}
    assert report.privacy_findings({"k": "x C:/Users/ana"}, markers) == ["absolute_path", "home"]
    found = report.privacy_findings({"k": "x-/srv/repo"}, {"root_resolved": "/srv/repo"})
    assert found == ["root"]
    assert set(report.private_markers()) >= {"home", "home_resolved", "root", "root_resolved"}


def test_write_report_refuses_a_leaking_report(tmp_path: Path) -> None:
    with pytest.raises(report.BenchmarkError, match="absolute_path"):
        report.write_report({"leak": str(tmp_path)}, tmp_path / "out")
    assert list(tmp_path.iterdir()) == []
