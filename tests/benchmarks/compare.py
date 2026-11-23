"""Comparison of two benchmark reports (MOANA-031, MOANART.md section 22).

Reports are comparable only with the same format, corpus digest, renderer version,
renderer backend, estimator version, warmups, samples, cases and phases per case.
Otherwise the comparison is refused with every reason; a malformed report (not a
JSON object, missing keys, non-numeric medians) is refused as ``malformed``.

For comparable reports every phase median and every case's peak RSS is listed raw.
A value is flagged ``investigate`` when ``after * 100 > before * 120`` (a rise of
strictly more than 20 %), computed on the decimal text of the numbers so that the
boundary is exact; a non-positive ``before`` is always ``investigate``. A missing
RSS value is ``unknown``. The verdict is informational: a flagged regression is
repeated under controlled conditions before it is attributed to a change.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Final

from .corpus import Json
from .report import REPORT_FORMAT

REGRESSION_THRESHOLD_PCT: Final = 20
VERSION_KEYS: Final = ("renderer_version", "renderer_backend", "estimator_version")
ENVIRONMENT_KEYS: Final = (
    "cpu_model",
    "cpu_count",
    "machine",
    "os",
    "os_release",
    "python_implementation",
    "python_version",
    "numpy",
    "pillow",
    "aggdraw",
    "pydantic",
    "lock_sha256",
)


def _is_number(value: Any) -> bool:
    return type(value) in (int, float)


def malformed(report: Any) -> str | None:
    """Why ``report`` cannot be read as a ``moanart-benchmark`` report (``None``: fine)."""
    if not isinstance(report, Mapping):
        return "malformed: the report is not a JSON object"
    for key, kind in (("method", Mapping), ("environment", Mapping), ("cases", Mapping)):
        if not isinstance(report.get(key), kind):
            return f"malformed: missing or invalid {key}"
    if not isinstance(report.get("corpus_digest"), str):
        return "malformed: missing corpus_digest"
    for name, case in report["cases"].items():
        phases = case.get("phases") if isinstance(case, Mapping) else None
        memory = case.get("memory") if isinstance(case, Mapping) else None
        if not isinstance(phases, Mapping) or not isinstance(memory, Mapping):
            return f"malformed: case {name} has no phases or memory"
        for phase, data in phases.items():
            stats = data.get("stats") if isinstance(data, Mapping) else None
            if not isinstance(stats, Mapping) or not _is_number(stats.get("median_ns")):
                return f"malformed: {name}/{phase} has no numeric median_ns"
        rss = memory.get("peak_rss_bytes")
        if rss is not None and not _is_number(rss):
            return f"malformed: {name} has a non-numeric peak_rss_bytes"
    return None


def _comparability(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    reasons = [r for r in (malformed(before), malformed(after)) if r is not None]
    if reasons:
        return reasons
    if before.get("format") != REPORT_FORMAT or after.get("format") != REPORT_FORMAT:
        return [
            f"report format differs from {REPORT_FORMAT}: "
            f"{before.get('format')} vs {after.get('format')}"
        ]
    if before["corpus_digest"] != after["corpus_digest"]:
        reasons.append("corpus digest differs")
    for key in VERSION_KEYS:
        old, new = before["environment"].get(key), after["environment"].get(key)
        if old != new:
            reasons.append(f"{key} differs: {old} vs {new}")
    for key in ("warmups", "samples"):
        old, new = before["method"].get(key), after["method"].get(key)
        if old != new:
            reasons.append(f"{key} differ: {old} vs {new}")
    if set(before["cases"]) != set(after["cases"]):
        reasons.append("case sets differ")
    else:
        for name in sorted(before["cases"]):
            if set(before["cases"][name]["phases"]) != set(after["cases"][name]["phases"]):
                reasons.append(f"phase sets differ in case {name}")
    return reasons


def verdict(before: float | None, after: float | None) -> str:
    """``investigate`` above +20 % (exact decimal boundary), ``ok`` otherwise."""
    if before is None or after is None:
        return "unknown"
    old, new = Decimal(repr(before)), Decimal(repr(after))
    if old <= 0 or new * 100 > old * (100 + REGRESSION_THRESHOLD_PCT):
        return "investigate"
    return "ok"


def _row(case: str, metric: str, unit: str, before: Any, after: Any) -> Json:
    change = None
    if before is not None and after is not None and before > 0:
        change = (after - before) / before * 100
    return {
        "case": case,
        "metric": metric,
        "unit": unit,
        "before": before,
        "after": after,
        "change_pct": change,
        "verdict": verdict(before, after),
    }


def compare_reports(before: Any, after: Any) -> Json:
    """Median and peak-RSS changes per case; a rise over 20 % is ``investigate``.

    Informational only: the verdict never fails a build, and raw values are always
    shown. Non-comparable or malformed reports are refused with every reason.
    """
    reasons = _comparability(before, after)
    if reasons:
        return {"comparable": False, "reasons": reasons, "rows": [], "environment_differences": []}
    rows: list[Json] = []
    for name in sorted(before["cases"]):
        old_case, new_case = before["cases"][name], after["cases"][name]
        for phase in sorted(old_case["phases"]):
            rows.append(
                _row(
                    name,
                    phase,
                    "ns",
                    old_case["phases"][phase]["stats"]["median_ns"],
                    new_case["phases"][phase]["stats"]["median_ns"],
                )
            )
        rows.append(
            _row(
                name,
                "peak_rss",
                "bytes",
                old_case["memory"].get("peak_rss_bytes"),
                new_case["memory"].get("peak_rss_bytes"),
            )
        )
    differences = [
        key
        for key in ENVIRONMENT_KEYS
        if before["environment"].get(key) != after["environment"].get(key)
    ]
    return {"comparable": True, "reasons": [], "rows": rows, "environment_differences": differences}


def _shown(value: Any, unit: str) -> str:
    if value is None:
        return "—"
    return f"{value / 1e6:.3f} ms" if unit == "ns" else f"{value / (1024 * 1024):.1f} MiB"


def comparison_text(result: Mapping[str, Any]) -> str:
    """Plain-text table of a comparison, or the refusal with its reasons."""
    if not result["comparable"]:
        return "NOT COMPARABLE:\n" + "\n".join(f"- {r}" for r in result["reasons"]) + "\n"
    lines = ["case\tmetric\tbefore\tafter\tchange_%\tverdict"]
    for row in result["rows"]:
        change = "—" if row["change_pct"] is None else f"{row['change_pct']:+.1f}"
        lines.append(
            f"{row['case']}\t{row['metric']}\t{_shown(row['before'], row['unit'])}\t"
            f"{_shown(row['after'], row['unit'])}\t{change}\t{row['verdict']}"
        )
    if result["environment_differences"]:
        lines.append(
            "WARNING: different environment ("
            + ", ".join(result["environment_differences"])
            + "); a change may come from the machine, not the code."
        )
    lines.append(
        f"Informational: a rise over {REGRESSION_THRESHOLD_PCT} % is investigated "
        "with a controlled repeat (MOANART.md section 22); this is not a gate."
    )
    return "\n".join(lines) + "\n"
