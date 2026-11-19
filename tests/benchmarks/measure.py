"""Measurement of one benchmark case inside one interpreter (MOANA-031).

The runner starts a fresh interpreter per case (``python -m tests.benchmarks worker``)
so that the process peak RSS belongs to that case alone. Inside it, phases are timed
separately with :func:`time.perf_counter_ns`:

* ``parse``: canonical JSON bytes to a validated :class:`moana.schema.Document`;
* ``render``: the in-memory render (``moana.api.render`` for a static case,
  ``moana.animation.render_animation`` for the whole timeline of an animated one); no
  file is read or written in this section;
* ``render_frame``: animated cases only, every frame document (evaluated and admitted
  outside the timed section) rendered alone with ``moana.render.render_admitted``;
* ``encode_png`` and ``write_png``: static cases only, the in-memory PNG encode and the
  atomic file export of the rendered result, timed apart from the render.

Every render sample carries proof that it did real work:

* the calls of the pipeline's rasteriser registry (``moana.render.pipeline._rasterize``),
  counted by a temporary wrapper. That registry rasterises every primitive operation
  and every mask leaf; ``outline``, ``dither``, ``shade`` and ``material`` build
  further derived masks themselves from those leaves, so the count is a lower bound of
  mask work in general and exactly one call per rect for the rect-only section 22
  corpus. The wrapper replaces a module attribute: it is process-global and assumes
  no concurrent render (no threads, no pytest-xdist workers sharing the process);
* the checkpoints of a :class:`moana.core.budget.Deadline` whose clock counts its
  calls and never expires (public API);
* the digest of the output, compared with a reference rendered once with
  ``moana.api.render`` before the warmups.
"""

from __future__ import annotations

import gc
import hashlib
import math
import re
import statistics
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Final

import moana.render.pipeline as pipeline
from moana import api
from moana.animation import evaluate_animation, render_animation
from moana.core.budget import Deadline
from moana.core.coordinates import Dimensions
from moana.export import encode_png
from moana.geometry import Mask
from moana.render import RenderResult, plan_budget, plan_frame, render_admitted
from moana.schema import Document, ShapeMask, ShapeOperation, validate_document

from .corpus import Json, canonical_bytes, case_animation, case_document

DEFAULT_WARMUPS: Final = 5
DEFAULT_SAMPLES: Final = 30
P95_METHOD: Final = "nearest-rank: sorted[ceil(0.95 * n) - 1]"
NEVER_EXPIRES_MS: Final = 10**12
WORKER_USAGE: Final = "usage: python -m tests.benchmarks worker <case> <warmups> <samples>\n"

Rasterizer = Callable[[ShapeOperation | ShapeMask, Dimensions], Mask]


def require_count(value: object, name: str, minimum: int) -> int:
    """``value`` as an ``int`` (never a ``bool``) of at least ``minimum``."""
    if type(value) is not int:
        raise TypeError(f"{name} must be an int")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


# --- Statistics ---------------------------------------------------------------------


def nearest_rank(values: Sequence[int], percentile: int) -> int:
    """Smallest value with at least ``percentile`` % of the values at or below it."""
    if type(percentile) is not int:
        raise TypeError("percentile must be an int")
    if any(type(value) is not int for value in values):
        raise TypeError("values must be ints")
    if not values:
        raise ValueError("no values")
    if not 0 < percentile <= 100:
        raise ValueError("percentile must be in 1..100")
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered) / 100) - 1]


def summarize(samples_ns: Sequence[int]) -> Json:
    """min, median (mean of the middle two for an even count), p95, max and mean in ns.

    ``median_ns`` and ``mean_ns`` are always floats; the others are sample values.
    """
    if not samples_ns:
        raise ValueError("no samples")
    return {
        "count": len(samples_ns),
        "min_ns": min(samples_ns),
        "median_ns": float(statistics.median(samples_ns)),
        "p95_ns": nearest_rank(samples_ns, 95),
        "max_ns": max(samples_ns),
        "mean_ns": statistics.fmean(samples_ns),
    }


# --- Memory -------------------------------------------------------------------------

_VMHWM = re.compile(r"^VmHWM:\s+(\d+)\s+kB\s*$", re.MULTILINE)


def normalize_maxrss(value: int, system: str) -> int:
    """``ru_maxrss`` in bytes: macOS reports bytes, Linux and the BSDs KiB."""
    return value if system == "Darwin" else value * 1024


def parse_vmhwm(status: str) -> int | None:
    """Peak resident set in bytes from the text of Linux ``/proc/self/status``."""
    match = _VMHWM.search(status)
    return None if match is None else int(match.group(1)) * 1024


def _linux_vmhwm() -> int | None:
    try:
        return parse_vmhwm(Path("/proc/self/status").read_text(encoding="utf-8"))
    except OSError:
        return None


def peak_rss() -> Json:
    """Peak resident set of this process so far, or ``null`` with the reason.

    Linux: ``VmHWM`` of the process status file is the primary value, because the
    ``ru_maxrss`` of a forked and exec'd child can start from the parent's high-water
    mark; ``ru_maxrss`` is kept as a secondary field. Elsewhere ``ru_maxrss``
    (``posix_spawn`` on macOS creates a new address space).
    """
    if sys.platform == "win32":  # Windows has no resource module; never fake a value
        return {
            "bytes": None,
            "source": None,
            "ru_maxrss_bytes": None,
            "reason": "resource module unavailable on this platform",
        }
    import platform
    import resource

    system = platform.system()
    ru_maxrss = normalize_maxrss(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, system)
    vmhwm = _linux_vmhwm() if system == "Linux" else None
    if vmhwm is not None:
        return {"bytes": vmhwm, "source": "VmHWM", "ru_maxrss_bytes": ru_maxrss, "reason": None}
    return {"bytes": ru_maxrss, "source": "ru_maxrss", "ru_maxrss_bytes": ru_maxrss, "reason": None}


@dataclass(slots=True)
class TracedPeak:
    """Python-heap peak of a block, relative to the traced size when it started."""

    bytes: int = 0


@contextmanager
def traced_peak() -> Iterator[TracedPeak]:
    """Measure the ``tracemalloc`` peak of the block above its starting traced size.

    Tracing is started and stopped only if it was not already active (for example
    with ``PYTHONTRACEMALLOC=1``), so an outer tracer keeps working.
    """
    result = TracedPeak()
    already = tracemalloc.is_tracing()
    gc.collect()
    if not already:
        tracemalloc.start()
    baseline = tracemalloc.get_traced_memory()[0]
    tracemalloc.reset_peak()
    try:
        yield result
    finally:
        result.bytes = max(0, tracemalloc.get_traced_memory()[1] - baseline)
        if not already:
            tracemalloc.stop()


def tracemalloc_peak(action: Callable[[], object]) -> int:
    """Peak bytes traced by ``tracemalloc`` during one untimed ``action`` (Python only)."""
    with traced_peak() as peak:
        action()
    return peak.bytes


# --- Work counters ------------------------------------------------------------------


@dataclass(slots=True)
class Counters:
    """Work done by one sample: rasteriser calls and deadline checkpoints."""

    rasterize_calls: int = 0
    checkpoints: int = 0
    _clock_calls: list[int] = field(default_factory=lambda: [0])

    def deadline(self) -> Deadline:
        """A deadline that never expires and counts every check of its clock."""
        calls = self._clock_calls

        def clock() -> float:
            calls[0] += 1
            return 0.0

        deadline = Deadline(NEVER_EXPIRES_MS, clock=clock)
        calls[0] = 0  # the constructor reads the clock once
        return deadline

    def close(self) -> None:
        """Copy the clock calls into ``checkpoints``."""
        self.checkpoints = self._clock_calls[0]


@contextmanager
def counting_rasterizer(counters: Counters) -> Iterator[None]:
    """Count calls of the render pipeline's rasteriser registry while active.

    Process-global (a module attribute is replaced): not safe with concurrent renders.
    """
    original: Rasterizer = pipeline._rasterize

    def counted(operation: ShapeOperation | ShapeMask, dimensions: Dimensions) -> Mask:
        counters.rasterize_calls += 1
        return original(operation, dimensions)

    setattr(pipeline, "_rasterize", counted)  # noqa: B010 - private registry, restored below
    try:
        yield
    finally:
        setattr(pipeline, "_rasterize", original)  # noqa: B010


# --- Phases -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Sample:
    """One timed render: elapsed time, work counters and output digest."""

    elapsed_ns: int
    rasterize_calls: int
    checkpoints: int
    digest: str


def _timed(action: Callable[[], object]) -> int:
    gc.collect()
    start = time.perf_counter_ns()
    action()
    return time.perf_counter_ns() - start


def sequence_digest(results: Sequence[RenderResult]) -> str:
    """``sha256:`` of the frame digests in order (one value per animation render)."""
    joined = "\n".join(result.digest for result in results)
    return "sha256:" + hashlib.sha256(joined.encode("ascii")).hexdigest()


def render_once(document: Document, animation: str | None) -> Callable[[Deadline], str]:
    """The render of the timed section; returns the output digest."""
    if animation is None:
        return lambda deadline: api.render(document, deadline=deadline).digest

    def sequence(deadline: Deadline) -> str:
        rendered = render_animation(document, animation, deadline=deadline)
        return sequence_digest([frame.result for frame in rendered.frames])

    return sequence


def reference_digest(document: Document, animation: str | None) -> str:
    """Independent reference: ``moana.api.render`` once (per frame for an animation).

    An animation frame is rendered as the static document its evaluation produces;
    the visual digest depends on pixels only, so it equals the frame's digest.
    """
    if animation is None:
        return api.render(document).digest
    frames = evaluate_animation(document, animation)
    return sequence_digest([api.render(frame.document) for frame in frames])


def sample_render(render: Callable[[Deadline], str]) -> Sample:
    """Time one ``render`` with fresh counters and return its time, counters and digest."""
    counters = Counters()
    digest: list[str] = []
    with counting_rasterizer(counters):
        deadline = counters.deadline()
        elapsed = _timed(lambda: digest.append(render(deadline)))
    counters.close()
    return Sample(elapsed, counters.rasterize_calls, counters.checkpoints, digest[0])


def measure_render(
    document: Document, animation: str | None, warmups: int, samples: int
) -> tuple[list[Sample], str]:
    """Warm up, then take ``samples`` render samples; returns them and the reference."""
    reference = reference_digest(document, animation)
    render = render_once(document, animation)
    for _ in range(warmups):
        render(Counters().deadline())
    return [sample_render(render) for _ in range(samples)], reference


def measure_phase(action: Callable[[], object], warmups: int, samples: int) -> list[int]:
    """Run ``action`` ``warmups`` times untimed, then return ``samples`` times in ns."""
    for _ in range(warmups):
        action()
    return [_timed(action) for _ in range(samples)]


def measure_frames(
    document: Document, animation: str, warmups: int, samples: int
) -> list[list[int]]:
    """Per-frame render times: ``result[frame][sample]`` in ns (render section only)."""
    frames = evaluate_animation(document, animation)
    plans = [(f.frame_id, f.document, plan_frame(f.document)) for f in frames]
    times: list[list[int]] = []
    for frame_id, frame_document, estimate in plans:
        action = partial(render_admitted, frame_document, frame_id=frame_id, estimate=estimate)
        times.append(measure_phase(action, warmups, samples))
    return times


# --- Case ---------------------------------------------------------------------------


def _cost_plan(document: Document, animation: str | None) -> Json:
    """The admitted cost plan (estimated work) of one render request."""
    if animation is None:
        estimates = [plan_budget(document)]
    else:
        estimates = [plan_frame(f.document) for f in evaluate_animation(document, animation)]
    return {
        "frames": len(estimates),
        "fills": sum(e.fills for e in estimates),
        "layers": sum(e.layers for e in estimates),
        "operations": sum(e.operations for e in estimates),
        "pixel_visits": sum(e.pixel_visits for e in estimates),
        "frame_pixels": sum(e.frame_pixels for e in estimates),
        "peak_buffer_bytes": max(e.buffer_bytes for e in estimates),
    }


def _render_phase(samples: list[Sample], reference: str) -> Json:
    return {
        "stats": summarize([s.elapsed_ns for s in samples]),
        "samples_ns": [s.elapsed_ns for s in samples],
        "rasterize_calls": [s.rasterize_calls for s in samples],
        "checkpoints": [s.checkpoints for s in samples],
        "digests": sorted({s.digest for s in samples}),
        "reference_digest": reference,
        "samples_matching_reference": sum(s.digest == reference for s in samples),
    }


def _io_phases(document: Document, warmups: int, samples: int) -> Json:
    result = api.render(document)
    encode = measure_phase(lambda: encode_png(result), warmups, samples)
    with tempfile.TemporaryDirectory(prefix="moana-bench-") as folder:
        target = Path(folder) / "frame.png"
        write = measure_phase(
            lambda: api.export_png(result, target, overwrite=True), warmups, samples
        )
    return {
        "encode_png": {"stats": summarize(encode), "samples_ns": encode},
        "write_png": {"stats": summarize(write), "samples_ns": write},
    }


def _frame_phase(document: Document, animation: str, warmups: int, samples: int) -> Json:
    per_frame = measure_frames(document, animation, warmups, samples)
    return {
        "stats": summarize([t for frame in per_frame for t in frame]),
        "per_frame_median_ns": [float(statistics.median(frame)) for frame in per_frame],
        "per_frame_p95_ns": [nearest_rank(frame, 95) for frame in per_frame],
    }


def run_case(name: str, warmups: int, samples: int) -> Json:
    """Measure case ``name``; the caller decides whether this is a fresh process."""
    require_count(warmups, "warmups", 0)
    require_count(samples, "samples", 1)
    rss_start = peak_rss()
    data = canonical_bytes(case_document(name))
    animation = case_animation(name)
    parse = measure_phase(lambda: validate_document(data), warmups, samples)
    document = validate_document(data)
    render_samples, reference = measure_render(document, animation, warmups, samples)
    phases: Json = {
        "parse": {"stats": summarize(parse), "samples_ns": parse},
        "render": _render_phase(render_samples, reference),
    }
    if animation is None:
        phases.update(_io_phases(document, warmups, samples))
    else:
        phases["render_frame"] = _frame_phase(document, animation, warmups, samples)
    rss_end = peak_rss()
    once = render_once(document, animation)
    traced = tracemalloc_peak(lambda: once(Counters().deadline()))
    return {
        "case": name,
        "kind": "static" if animation is None else "animation",
        "animation_id": animation,
        "input_bytes": len(data),
        "cost_plan": _cost_plan(document, animation),
        "phases": phases,
        "memory": {
            "peak_rss_bytes": rss_end["bytes"],
            "peak_rss_source": rss_end["source"],
            "peak_rss_reason": rss_end["reason"],
            "ru_maxrss_bytes": rss_end["ru_maxrss_bytes"],
            "peak_rss_before_case_bytes": rss_start["bytes"],
            "tracemalloc_render_peak_bytes": traced,
            "tracemalloc_scope": "python-heap-only",
        },
    }


def main(argv: Sequence[str]) -> int:
    """``worker <case> <warmups> <samples>``: print the case measurement as JSON.

    Returns 2 with the usage on stderr when the arguments are malformed.
    """
    import json

    try:
        if len(argv) != 3:
            raise ValueError("expected 3 arguments")
        name, warmups, samples = argv[0], int(argv[1]), int(argv[2])
    except ValueError:
        sys.stderr.write(WORKER_USAGE)
        return 2
    result = run_case(name, warmups, samples)
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0
