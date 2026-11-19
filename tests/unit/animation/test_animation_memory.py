"""A render request holds one frame document at a time (MOANA-022 T1; ADR-032).

Rendering streams: pass 1 evaluates and estimates every frame, keeping only its
``CostEstimate``; pass 2 evaluates and renders the requested frames one by one. The
traced peak of a request is therefore bounded by what ``admit_sequence`` admits
(pixel buffers and the retained results) plus a documented slack of a few documents
(the validated base, its static copy, one frame document and the transient tree the
editor validates). Without streaming the peak grows with the number of frames.
"""

from __future__ import annotations

import gc
import tracemalloc
from collections.abc import Callable
from typing import Any

import pytest

from moana.animation import AnimationRender, FrameRender, render_animation, render_frame
from moana.core.budget import RenderLimits
from moana.render import admit_sequence, plan_frame
from moana.schema import Document, normalize_document, validate_document

FRAMES = 256
OPERATIONS = 2000
DOCUMENT_SLACK = 6
"""Whole documents a request may hold besides its pixels (see the module docstring)."""
WARM_SLACK = 64 * 1024
"""Bytes left alive after the results are dropped: interpreter caches (interned IDs,
type caches) warmed by the first validation of a document, independent of frames."""

LIMITS = RenderLimits(max_pixel_visits=10**9, max_buffer_bytes=2**31, host_override=True)


def tree(frames: int, operations: int, width: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": width, "height": width},
        "palette": {"id": "pal", "colors": [{"id": "c", "rgba": "#FF0000FF"}]},
        "layers": [
            {
                "id": "body",
                "name": "Body",
                "operations": [
                    {"id": f"o{i}", "type": "pixel", "color": "c", "at": [i % width, 0]}
                    for i in range(operations)
                ],
            }
        ],
        "animations": [
            {
                "id": "run",
                "loop_count": 0,
                "pivot": [0, 0],
                "frames": [
                    {
                        "id": f"f{k}",
                        "duration_ms": 10,
                        "overrides": [
                            {"type": "translate", "target_id": f"o{k}", "dx": 0, "dy": 1}
                        ],
                    }
                    for k in range(frames)
                ],
            }
        ],
    }


def traced(call: Callable[[], object]) -> tuple[int, int, object]:
    """Peak and retained bytes allocated by ``call`` (and its result)."""
    gc.collect()
    tracemalloc.start()
    try:
        before, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        result = call()
        _, peak = tracemalloc.get_traced_memory()
        gc.collect()  # what is still alive, not garbage awaiting the cycle collector
        current, _ = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak - before, current - before, result


def admitted(document: Document, frames: int) -> int:
    """Bytes ``admit_sequence`` admits for ``frames`` frames like the static base."""
    static = normalize_document(document)
    static["animations"] = []
    estimate = plan_frame(validate_document(static), limits=LIMITS)
    return admit_sequence([estimate] * frames, limits=LIMITS).buffer_bytes


def document_bytes(source: dict[str, Any]) -> int:
    size, _, _ = traced(lambda: validate_document(source))
    return size


@pytest.mark.slow
def test_t1_render_frame_holds_one_frame_document() -> None:
    source = tree(FRAMES, OPERATIONS, 8)
    document = validate_document(source)
    size = document_bytes(source)
    peak, retained, result = traced(lambda: render_frame(document, "f3", limits=LIMITS))
    assert isinstance(result, FrameRender)
    assert peak <= admitted(document, 1) + DOCUMENT_SLACK * size
    assert retained <= admitted(document, 1) + WARM_SLACK
    # Keeping every evaluated frame would cost about FRAMES documents.
    assert DOCUMENT_SLACK * size < FRAMES * size // 16


@pytest.mark.slow
def test_t1_selected_frames_do_not_keep_the_unrequested_ones() -> None:
    source = tree(64, OPERATIONS, 8)
    document = validate_document(source)
    wanted = ["f60", "f7", "f3"]
    peak, retained, _ = traced(
        lambda: render_animation(document, "run", frame_ids=wanted, limits=LIMITS)
    )
    assert peak <= admitted(document, len(wanted)) + DOCUMENT_SLACK * document_bytes(source)
    assert retained <= admitted(document, len(wanted)) + WARM_SLACK


def test_t1_rendering_every_frame_stays_within_the_admitted_bytes() -> None:
    # Large frames, small documents: the retained results dominate the peak.
    source = tree(32, 32, 128)
    document = validate_document(source)
    slack = DOCUMENT_SLACK * document_bytes(source)
    peak, retained, result = traced(lambda: render_animation(document, "run", limits=LIMITS))
    assert isinstance(result, AnimationRender)
    assert len(result.frames) == 32
    expected = admitted(document, 32)
    assert peak <= expected + slack
    assert retained <= expected + WARM_SLACK
