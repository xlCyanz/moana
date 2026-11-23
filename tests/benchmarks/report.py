"""Benchmark report: environment, fresh-process runs, targets, privacy and summary.

The report (``moanart-benchmark/1``) is canonical JSON (sorted keys, two-space indent,
UTF-8, final newline). It records where it was produced (CPU, OS, Python, library
versions, lock digest, commit) without hostname, user name, absolute paths or
timestamps, and states every MOANART.md section 22 target as met (``true``), missed
(``false``) or unknown (``null``). Targets are informational until there is a stable
runner; nothing here is a gate. The Markdown summary is a pure function of the
canonical JSON, so it can be regenerated from a committed report.
"""

from __future__ import annotations

import contextlib
import getpass
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any, Final

from .adversarial import budget_cases
from .corpus import ANIMATION, ROOT, STATIC, Json, case_names, corpus_digest
from .measure import DEFAULT_SAMPLES, DEFAULT_WARMUPS, P95_METHOD, require_count

REPORT_FORMAT: Final = "moanart-benchmark/1"
LOCK_PATH: Final = ROOT / "uv.lock"
MIB: Final = 1024 * 1024
TARGETS: Final = {
    "static_render_median_ms": 100,
    "animation_16_frames_median_ms": 2000,
    "process_peak_rss_mib": 256,
}
NOTE: Final = (
    "Informational targets of MOANART.md section 22: not a gate until a stable runner exists. "
    "Safety budgets of section 20 apply regardless of these results."
)
WORKER_BASE_TIMEOUT_S: Final = 60
WORKER_TIMEOUT_PER_ITERATION_S: Final = 30
TOOL_TIMEOUT_S: Final = 10


class BenchmarkError(RuntimeError):
    """A worker failed or timed out, or a report would leak private data."""


# --- Environment --------------------------------------------------------------------


def _run_text(command: Sequence[str]) -> str | None:
    """Stripped stdout of a short tool, or ``None`` if it is missing, fails or hangs."""
    try:
        completed = subprocess.run(
            list(command),
            cwd=ROOT,
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            encoding="utf-8",
            errors="replace",
            timeout=TOOL_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def parse_cpuinfo(text: str) -> str | None:
    """CPU name from Linux ``/proc/cpuinfo``: ``model name``, then ARM ``Hardware``/``CPU part``."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and value.strip():
            fields.setdefault(key.strip(), value.strip())
    for key in ("model name", "Hardware"):
        if key in fields:
            return fields[key]
    if "CPU part" in fields:
        implementer = fields.get("CPU implementer")
        prefix = f"CPU implementer {implementer} " if implementer else ""
        return f"{prefix}CPU part {fields['CPU part']}"
    return None


def cpu_model() -> str | None:
    """CPU brand string from the operating system, or ``None`` when unavailable."""
    system = platform.system()
    if system == "Darwin":
        return _run_text(["sysctl", "-n", "machdep.cpu.brand_string"])
    if system == "Linux":
        with contextlib.suppress(OSError):
            found = parse_cpuinfo(Path("/proc/cpuinfo").read_text(encoding="utf-8"))
            if found:
                return found
    return platform.processor() or None


def _version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def git_state() -> Json:
    """Commit and dirty flag of the checkout (``None`` outside a Git checkout)."""
    commit = _run_text(["git", "rev-parse", "HEAD"])
    status = _run_text(["git", "status", "--porcelain"])
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def environment() -> Json:
    """Facts that identify the measuring machine and build; no paths, names or times."""
    import moanart
    from moanart.render import ESTIMATOR_VERSION, RENDERER_BACKEND, RENDERER_VERSION

    lock = hashlib.sha256(LOCK_PATH.read_bytes()).hexdigest() if LOCK_PATH.is_file() else None
    return {
        "cpu_model": cpu_model(),
        "cpu_count": os.cpu_count(),
        "machine": platform.machine(),
        "os": platform.system(),
        "os_release": platform.release(),
        "macos_version": platform.mac_ver()[0] or None,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "moanart": moanart.__version__,
        "numpy": _version("numpy"),
        "pillow": _version("pillow"),
        "aggdraw": _version("aggdraw"),
        "pydantic": _version("pydantic"),
        "lock_sha256": lock,
        "git": git_state(),
        "renderer_version": RENDERER_VERSION,
        "renderer_backend": RENDERER_BACKEND,
        "estimator_version": ESTIMATOR_VERSION,
    }


# --- Running ------------------------------------------------------------------------


def worker_timeout(warmups: int, samples: int) -> int:
    """Seconds allowed to one worker: proportional to its iterations."""
    return WORKER_BASE_TIMEOUT_S + (warmups + samples) * WORKER_TIMEOUT_PER_ITERATION_S


def run_worker(name: str, warmups: int, samples: int) -> Json:
    """Measure one case in a fresh interpreter and return its JSON result."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"}
    command = [sys.executable, "-m", "tests.benchmarks", "worker", name, str(warmups)]
    try:
        completed = subprocess.run(
            [*command, str(samples)],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            encoding="utf-8",
            errors="replace",
            timeout=worker_timeout(warmups, samples),
        )
    except subprocess.TimeoutExpired:
        raise BenchmarkError(f"worker for {name} timed out") from None
    if completed.returncode != 0:
        tail = completed.stderr.strip().splitlines()[-1:] or ["no output"]
        raise BenchmarkError(f"worker for {name} failed: {tail[0]}")
    value: Json = json.loads(completed.stdout)
    return value


def _median_ms(case: Mapping[str, Any]) -> float:
    return float(case["phases"]["render"]["stats"]["median_ns"]) / 1e6


def evaluate_targets(cases: Mapping[str, Mapping[str, Any]]) -> Json:
    """Each section 22 target with its measured value and ``met`` true/false/null."""
    static = cases.get(STATIC)
    animation = cases.get(ANIMATION)
    rss = [cases[name]["memory"]["peak_rss_bytes"] for name in (STATIC, ANIMATION) if name in cases]
    measured: dict[str, float | None] = {
        "static_render_median_ms": None if static is None else _median_ms(static),
        "animation_16_frames_median_ms": None if animation is None else _median_ms(animation),
        "process_peak_rss_mib": None
        if not rss or any(value is None for value in rss)
        else max(rss) / MIB,
    }
    targets: Json = {}
    for key, limit in TARGETS.items():
        value = measured[key]
        targets[key] = {
            "limit": limit,
            "measured": value,
            "met": None if value is None else value <= limit,
        }
    return targets


def build_report(
    cases: Sequence[Json], env: Json, warmups: int, samples: int, budgets: Json
) -> Json:
    """Assemble the ``moanart-benchmark/1`` report from measured cases and context."""
    names = tuple(case["case"] for case in cases)
    by_name = {case["case"]: case for case in cases}
    return {
        "format": REPORT_FORMAT,
        "note": NOTE,
        "method": {
            "warmups": warmups,
            "samples": samples,
            "clock": "time.perf_counter_ns",
            "p95": P95_METHOD,
            "median": "statistics.median (mean of the two middle values for even n)",
            "process": "one fresh interpreter per case (PYTHONHASHSEED=0)",
            "render_section": "in memory; no file I/O; JSON parsing timed as phase parse",
            "gc": "gc.collect() before every timed sample; gc stays enabled inside it",
            "peak_rss": "process peak in bytes: VmHWM on Linux, ru_maxrss elsewhere",
            "tracemalloc": "Python heap only (NumPy buffers traced, native heaps not), one render",
        },
        "corpus_digest": corpus_digest(names),
        "environment": env,
        "cases": by_name,
        "targets": evaluate_targets(by_name),
        "budget_cases": budgets,
    }


def run_benchmark(
    names: Sequence[str] | None = None,
    *,
    warmups: int = DEFAULT_WARMUPS,
    samples: int = DEFAULT_SAMPLES,
) -> Json:
    """Run every case (or ``names``) in fresh processes and build the report."""
    require_count(warmups, "warmups", 0)
    require_count(samples, "samples", 1)
    chosen = tuple(case_names() if names is None else names)
    if len(set(chosen)) != len(chosen):
        raise ValueError("a case is named more than once")
    cases = [run_worker(name, warmups, samples) for name in chosen]
    return build_report(cases, environment(), warmups, samples, budget_cases())


# --- Privacy ------------------------------------------------------------------------

_ABSOLUTE = re.compile(r"(?:^|[\s=:(\"'])(?:/[^\s/]|[A-Za-z]:[\\/]|\\\\|~[\\/])")


def _values(value: Any) -> Iterator[str]:
    """Every string value (not key) nested in ``value``."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _values(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _values(item)


def _strings(value: Any) -> Iterator[str]:
    """Every string nested in ``value``, keys included."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    else:
        yield from _values(value)


def _slashes(text: str) -> str:
    return text.replace("\\", "/")


def private_markers() -> dict[str, str]:
    """Values of this machine that must never appear in a report."""
    markers = {
        "hostname": socket.gethostname(),
        "home": str(Path.home()),
        "home_resolved": str(Path.home().resolve()),
        "root": str(ROOT),
        "root_resolved": str(ROOT.resolve()),
    }
    with contextlib.suppress(OSError, KeyError):  # no user database
        markers["user"] = getpass.getuser()
    return {kind: value for kind, value in markers.items() if len(value) >= 3}


def _names_in(text: str, value: str) -> bool:
    """Case-sensitive whole-word match (POSIX user and host names are case-sensitive)."""
    pattern = rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])"
    return re.search(pattern, text) is not None


def privacy_findings(report: Any, markers: Mapping[str, str] | None = None) -> list[str]:
    """Kinds of private data found in ``report`` (empty: clean).

    Absolute paths and the home/repository paths are searched in every string, keys
    included. User and host names are searched only in the values of the
    ``environment`` section, the one part of a report that comes from the machine:
    the fixed vocabulary (note, method, case and phase names) may legitimately
    contain words such as ``runner`` or ``static``.
    """
    markers = private_markers() if markers is None else markers
    findings: set[str] = set()
    raw = list(_strings(report))
    every = [_slashes(text) for text in raw]
    machine = list(_values(report.get("environment", {}))) if isinstance(report, Mapping) else []
    if any(_ABSOLUTE.search(text) for text in raw):
        findings.add("absolute_path")
    for kind, value in markers.items():
        if kind in {"user", "hostname"}:
            if any(_names_in(text, value) for text in machine):
                findings.add(kind)
        elif any(_slashes(value) in text for text in every):
            findings.add(kind.removesuffix("_resolved"))
    return sorted(findings)


# --- Summary ------------------------------------------------------------------------


def canonical_report(report: Json) -> str:
    """The canonical text of a report: sorted keys, two-space indent, final newline."""
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _ms(value: Any) -> str:
    return "—" if value is None else f"{float(value) / 1e6:.2f}"


def _mib(value: Any) -> str:
    return "—" if value is None else f"{value / MIB:.1f}"


def _met(value: Any) -> str:
    return {True: "sí", False: "no", None: "desconocido"}[value]


def ordered_cases(report: Mapping[str, Any]) -> list[str]:
    """Case names of ``report`` in corpus order, unknown names sorted after them."""
    present = set(report["cases"])
    known = [name for name in case_names() if name in present]
    return known + sorted(present - set(known))


def _header(report: Mapping[str, Any]) -> list[str]:
    env, method = report["environment"], report["method"]
    macos = f" (macOS {env['macos_version']})" if env.get("macos_version") else ""
    return [
        "# Benchmark de MoanArt (informativo)",
        "",
        f"Formato `{report['format']}`; corpus `{report['corpus_digest']}`.",
        f"{method['warmups']} warmups y {method['samples']} muestras por fase; p95 por rango "
        "más cercano; un proceso nuevo por caso.",
        "",
        "Objetivos de MOANART.md §22: informativos hasta disponer de un runner estable. "
        "Los presupuestos de seguridad (§20) siguen vigentes aunque no se cumplan.",
        "",
        "## Máquina",
        "",
        f"- CPU: {env['cpu_model']} ({env['cpu_count']} núcleos lógicos, {env['machine']})",
        f"- SO: {env['os']} {env['os_release']}{macos}",
        f"- Python: {env['python_implementation']} {env['python_version']}; numpy "
        f"{env['numpy']}, Pillow {env['pillow']}, aggdraw {env['aggdraw']}, "
        f"pydantic {env['pydantic']}",
        f"- MoanArt {env['moanart']}, {env['renderer_version']} ({env['renderer_backend']}), "
        f"{env['estimator_version']}; commit `{env['git']['commit']}` "
        f"(dirty: {env['git']['dirty']}); uv.lock `{env['lock_sha256']}`",
    ]


def _targets_table(report: Mapping[str, Any]) -> list[str]:
    lines = ["", "## Objetivos", "", "| Objetivo | Límite | Medido | ¿Cumple? |"]
    lines.append("| --- | ---: | ---: | --- |")
    for key in TARGETS:
        target = report["targets"][key]
        measured = target["measured"]
        shown = "—" if measured is None else f"{measured:.2f}"
        lines.append(f"| {key} | {target['limit']} | {shown} | {_met(target['met'])} |")
    return lines


def _phases_table(report: Mapping[str, Any]) -> list[str]:
    lines = ["", "## Fases (ms)", "", "| Caso | Fase | min | mediana | p95 | max | media |"]
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for name in ordered_cases(report):
        phases = report["cases"][name]["phases"]
        for phase in sorted(phases):
            stats = phases[phase]["stats"]
            row = [stats[k] for k in ("min_ns", "median_ns", "p95_ns", "max_ns", "mean_ns")]
            lines.append(f"| {name} | {phase} | " + " | ".join(_ms(v) for v in row) + " |")
    return lines


def _memory_table(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "",
        "## Memoria (MiB)",
        "",
        "| Caso | Pico RSS del proceso | Fuente | Pico RSS antes del caso | "
        "Pico tracemalloc (sólo Python) |",
        "| --- | ---: | --- | ---: | ---: |",
    ]
    for name in ordered_cases(report):
        memory = report["cases"][name]["memory"]
        lines.append(
            f"| {name} | {_mib(memory['peak_rss_bytes'])} | {memory['peak_rss_source']} | "
            f"{_mib(memory['peak_rss_before_case_bytes'])} | "
            f"{_mib(memory['tracemalloc_render_peak_bytes'])} |"
        )
    return lines


def _budgets_table(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "",
        "## Casos adversos (presupuestos de §20)",
        "",
        "| Caso | ¿Rechazado? | Recursos excedidos | Llamadas al rasterizador | "
        "Pico tracemalloc (KiB) |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for name in sorted(report["budget_cases"]):
        case = report["budget_cases"][name]
        if not isinstance(case, Mapping):
            continue
        resources = ", ".join(case.get("resources", [])) or "—"
        peak = case.get("tracemalloc_peak_bytes")
        shown = "—" if peak is None else f"{peak / 1024:.0f}"
        lines.append(
            f"| {name} | {_met(case['rejected'])} | {resources} | "
            f"{case['rasterize_calls']} | {shown} |"
        )
    return lines


def summary_markdown(report: Mapping[str, Any]) -> str:
    """Short Spanish summary of a report (milliseconds and MiB), in a fixed order."""
    lines = [
        *_header(report),
        *_targets_table(report),
        *_phases_table(report),
        *_memory_table(report),
        *_budgets_table(report),
    ]
    return "\n".join(lines) + "\n"


def write_report(report: Json, output: Path) -> tuple[Path, Path]:
    """Write ``<output>.json`` and ``<output>.md`` after the privacy check.

    The summary is generated from the canonical JSON text, never from the in-memory
    report, so it can always be regenerated from the committed file.
    """
    findings = privacy_findings(report)
    if findings:
        raise BenchmarkError(f"report would leak private data: {', '.join(findings)}")
    canonical = canonical_report(report)
    json_path, md_path = output.with_suffix(".json"), output.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(canonical, encoding="utf-8", newline="\n")
    md_path.write_text(summary_markdown(json.loads(canonical)), encoding="utf-8", newline="\n")
    return json_path, md_path
