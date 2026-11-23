"""T2: comparability of reports and the informational >20 % regression flag."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from . import compare
from .__main__ import main
from .corpus import Json

pytestmark = pytest.mark.benchmark


def _report(median_ns: float = 100.0, rss: int | None = 1000) -> Json:
    return {
        "format": "moanart-benchmark/1",
        "corpus_digest": "sha256:" + "0" * 64,
        "method": {"warmups": 5, "samples": 30},
        "environment": {
            "renderer_version": "render-v1",
            "renderer_backend": "integer",
            "estimator_version": "budget-v8",
            "cpu_model": "Apple M4",
            "python_version": "3.12.16",
            "pydantic": "2.14.3",
        },
        "cases": {
            "static": {
                "phases": {
                    "render": {"stats": {"median_ns": median_ns}},
                    "parse": {"stats": {"median_ns": 100.0}},
                },
                "memory": {"peak_rss_bytes": rss},
            },
        },
    }


def _with_render(value: Json, median_ns: float) -> Json:
    changed = copy.deepcopy(value)
    changed["cases"]["static"]["phases"]["render"]["stats"]["median_ns"] = median_ns
    return changed


def _rows(before: Json, after: Json) -> dict[str, Json]:
    result = compare.compare_reports(before, after)
    assert result["comparable"], result["reasons"]
    return {row["metric"]: row for row in result["rows"]}


def test_t2_a_rise_over_20_percent_is_flagged() -> None:
    base = _report()
    rows = _rows(base, _with_render(base, 121.0))
    assert {k: r["verdict"] for k, r in rows.items()} == {
        "parse": "ok",
        "render": "investigate",
        "peak_rss": "ok",
    }
    assert rows["render"] == {
        "case": "static",
        "metric": "render",
        "unit": "ns",
        "before": 100.0,
        "after": 121.0,
        "change_pct": pytest.approx(21.0),
        "verdict": "investigate",
    }


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (3.0, 3.6, "ok"),  # exactly +20 %, although 3.6 * 100 > 360 in binary floats
        (7.0, 8.4, "ok"),
        (100.0, 120.0, "ok"),
        (100.0, 120.0001, "investigate"),
        (100.0, 50.0, "ok"),
        (0.0, 1.0, "investigate"),
        (0.0, 0.0, "investigate"),
        (-1.0, 1.0, "investigate"),
    ],
)
def test_t2_the_20_percent_boundary_is_exact(before: float, after: float, expected: str) -> None:
    assert compare.verdict(before, after) == expected
    rows = _rows(_report(before), _report(after))
    assert rows["render"]["verdict"] == expected


def test_t2_peak_rss_rise_is_flagged_and_missing_rss_is_unknown() -> None:
    assert _rows(_report(rss=1000), _report(rss=1201))["peak_rss"]["verdict"] == "investigate"
    assert _rows(_report(rss=1000), _report(rss=1200))["peak_rss"]["verdict"] == "ok"
    unknown = _rows(_report(rss=1000), _report(rss=None))["peak_rss"]
    assert unknown["verdict"] == "unknown" and unknown["change_pct"] is None


def _set(report: Json, path: tuple[str, ...], value: object) -> None:
    target = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("corpus_digest",), "sha256:" + "1" * 64, "corpus digest differs"),
        (("environment", "renderer_version"), "render-v2", "renderer_version differs"),
        (("environment", "renderer_backend"), "other", "renderer_backend differs"),
        (("environment", "estimator_version"), "budget-v9", "estimator_version differs"),
        (("method", "warmups"), 1, "warmups differ"),
        (("method", "samples"), 3, "samples differ"),
        (("cases",), {}, "case sets differ"),
        (("format",), "moanart-benchmark/2", "report format differs"),
    ],
)
def test_t2_non_comparable_reports_are_refused(
    path: tuple[str, ...], value: object, reason: str
) -> None:
    before, after = _report(), _report()
    _set(after, path, value)
    result = compare.compare_reports(before, after)
    assert result["comparable"] is False and result["rows"] == []
    assert any(reason in text for text in result["reasons"])
    assert "NOT COMPARABLE" in compare.comparison_text(result)


def test_t2_a_phase_missing_after_is_not_comparable() -> None:
    after = _report()
    del after["cases"]["static"]["phases"]["parse"]
    result = compare.compare_reports(_report(), after)
    assert result["reasons"] == ["phase sets differ in case static"]


@pytest.mark.parametrize(
    "bad",
    [
        [],
        None,
        "text",
        {},
        {"method": {}, "environment": {}, "cases": {}},
        {**_report(), "cases": {"static": {"phases": {}}}},
        {**_report(), "cases": {"static": {"phases": {"render": {}}, "memory": {}}}},
        {
            **_report(),
            "cases": {
                "static": {"phases": {"render": {"stats": {"median_ns": "1"}}}, "memory": {}}
            },
        },
        {**_report(), "cases": {"static": {"phases": {}, "memory": {"peak_rss_bytes": "x"}}}},
        {**_report(), "cases": {"static": "nope"}},
    ],
)
def test_t2_malformed_reports_are_refused(bad: Any) -> None:
    for before, after in ((bad, _report()), (_report(), bad)):
        result = compare.compare_reports(before, after)
        assert result["comparable"] is False
        assert all(reason.startswith("malformed") for reason in result["reasons"])


def test_t2_a_different_machine_is_a_warning_not_a_refusal() -> None:
    before, after = _report(), _report(130.0)
    after["environment"]["cpu_model"] = "Other CPU"
    after["environment"]["pydantic"] = "2.15.0"
    result = compare.compare_reports(before, after)
    assert result["comparable"] and result["environment_differences"] == ["cpu_model", "pydantic"]
    text = compare.comparison_text(result)
    assert "WARNING: different environment (cpu_model, pydantic)" in text
    assert "static\trender\t0.000 ms\t0.000 ms\t+30.0\tinvestigate" in text
    assert "static\tpeak_rss\t0.0 MiB\t0.0 MiB\t+0.0\tok" in text


def test_compare_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {
        "a": json.dumps(_report()),
        "b": json.dumps(_report(150.0)),
        "c": json.dumps({**_report(), "corpus_digest": "x"}),
        "list": "[]",
        "broken": "{not json",
    }
    for name, text in files.items():
        (tmp_path / f"{name}.json").write_text(text, encoding="utf-8")

    def run(before: str, after: str) -> int:
        return main(["compare", str(tmp_path / f"{before}.json"), str(tmp_path / f"{after}.json")])

    assert run("a", "b") == 0
    assert "investigate" in capsys.readouterr().out
    assert run("a", "c") == 2
    assert "corpus digest differs" in capsys.readouterr().out
    for bad in ("list", "broken", "missing"):
        assert run("a", bad) == 2
        captured = capsys.readouterr()
        assert "malformed" in captured.out and "Traceback" not in captured.err


def test_run_cli_rejects_bad_counts_and_repeated_cases(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["run", "--samples", "0"])
    assert "--samples" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["run", "--case", "static", "--case", "static"])
    assert "more than once" in capsys.readouterr().err
