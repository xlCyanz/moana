"""Adverse cases: requests over the safety budgets of MOANA.md section 20 (MOANA-031 AC2).

They would miss every latency target if they were drawn; the engine must reject them
with ``BudgetExceeded`` before any raster or pixel buffer. Each check records the
budget error, its resources, the rasteriser calls (must be zero), the Python heap peak
of the rejection (far below one canvas) and how long the rejection took.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final

from moana import api
from moana.animation import render_animation
from moana.core import BudgetExceeded, RenderLimits
from moana.schema import validate_document

from .corpus import RECTS, Json, canonical_bytes, static_document
from .measure import Counters, counting_rasterizer, traced_peak

HUGE: Final = 2048
HUGE_LAYERS: Final = 32
HUGE_RECTS_PER_LAYER: Final = 16
SEQUENCE_FRAMES: Final = 16
RGBA_BYTES: Final = 4


def _huge_base(layers: int, rects_per_layer: int, *, full: bool) -> Json:
    def rect(layer: int, index: int) -> Json:
        box = [0, 0, HUGE, HUGE] if full else [8, 8, 16, 16]
        return {"id": f"h{layer:02d}_{index:02d}", "type": "rect", "box": box, "color": "ink"}

    return {
        "schema_version": "1.0",
        "id": "bench_huge",
        "revision": 0,
        "seed": 0,
        "canvas": {"width": HUGE, "height": HUGE, "profile": "strict"},
        "palette": {"id": "huge_palette", "colors": [{"id": "ink", "rgba": "#102030FF"}]},
        "layers": [
            {
                "id": f"huge{layer:02d}",
                "name": f"Capa {layer}",
                "operations": [rect(layer, index) for index in range(rects_per_layer)],
            }
            for layer in range(layers)
        ],
    }


def oversized_static() -> Json:
    """2048x2048, 32 layers of 16 full-canvas rects: far over the pixel-visit budget."""
    return _huge_base(HUGE_LAYERS, HUGE_RECTS_PER_LAYER, full=True)


def cumulative_animation() -> Json:
    """2048x2048 with one small rect and 16 frames: each frame fits, the sequence does not."""
    document = _huge_base(1, 1, full=False)
    document["animations"] = [
        {
            "id": "huge_loop",
            "loop_count": 0,
            "pivot": [0, 0],
            "frames": [
                {
                    "id": f"hf{frame:02d}",
                    "duration_ms": 100,
                    "overrides": [
                        {"type": "translate", "target_id": "h00_00", "dx": frame, "dy": 0}
                    ],
                }
                for frame in range(SEQUENCE_FRAMES)
            ],
        }
    ]
    return document


def canvas_bytes() -> int:
    """Bytes of one RGBA buffer of the huge canvas: the rejection must stay far below."""
    return RGBA_BYTES * HUGE * HUGE


def rejection(action: Callable[[], object]) -> Json:
    """Run ``action`` expecting ``BudgetExceeded``; describe the rejection and its cost.

    ``tracemalloc_peak_bytes`` is relative to the traced size before the action (an
    outer tracer is left running); ``elapsed_ns`` includes the tracing overhead.
    """
    counters = Counters()
    with traced_peak() as peak:
        start = time.perf_counter_ns()
        error: BudgetExceeded | None = None
        try:
            with counting_rasterizer(counters):
                action()
        except BudgetExceeded as raised:
            error = raised
        elapsed = time.perf_counter_ns() - start
    if error is None:
        return {"rejected": False, "rasterize_calls": counters.rasterize_calls}
    resources = {str(d.context.get("resource")) for d in error.details}
    resources.add(str(error.context["resource"]))
    return {
        "rejected": True,
        "error_code": error.code,
        "resources": sorted(resources),
        "context": {k: v for k, v in error.context.items() if k != "json_pointer"},
        "rasterize_calls": counters.rasterize_calls,
        "tracemalloc_peak_bytes": peak.bytes,
        "elapsed_ns": elapsed,
    }


def budget_cases() -> Json:
    """Run every adverse case and describe how it was rejected (or that it was not)."""
    huge = validate_document(canonical_bytes(oversized_static()))
    sequence = validate_document(canonical_bytes(cumulative_animation()))
    corpus = validate_document(canonical_bytes(static_document()))
    tight = RenderLimits(max_operations=RECTS - 1)
    return {
        "oversized_static": rejection(lambda: api.render(huge)),
        "operations_over_limit": rejection(lambda: api.render(corpus, limits=tight)),
        "cumulative_animation": rejection(lambda: render_animation(sequence, "huge_loop")),
        "canvas_rgba_bytes": canvas_bytes(),
    }
