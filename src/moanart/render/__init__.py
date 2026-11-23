"""Rendering of validated documents (MOANART.md sections 3, 13, 14 and 20).

:func:`render` is the deterministic orchestrator (MOANA-010, ADR-018): validation,
resolution, budget (:mod:`moanart.render.budget`, MOANA-003), plan, raster and
composition into an immutable :class:`RenderResult`. Per-cell randomness lives in
:mod:`moanart.core.procedural` so that techniques can use it. There is no concurrency
and no cache unless the caller passes an opt-in, byte-bounded :class:`RenderCache` of
finished layer buffers (MOANA-032, ADR-038), which never changes a result.
:func:`render_with_regions` validates once, admits the render plus the
masks of named regions against one budget and returns those masks lazily, for the
region exceptions of a cluster analysis (ADR-027). :func:`plan_frame`,
:func:`admit_sequence` and :func:`render_admitted` admit a finite sequence of frame
documents against one budget before drawing any of them, in two streaming passes
that hold one frame document at a time; :func:`render_sequence` runs them over
pairs the caller holds (for :mod:`moanart.animation`, ADR-032).
"""

from moanart.render.budget import (
    ESTIMATOR_VERSION,
    MAX_FRAMES,
    CostEstimate,
    OperationCost,
    estimate_cost,
    plan_budget,
)
from moanart.render.cache import (
    CACHE_KEY_FORMAT,
    ENTRY_OVERHEAD_BYTES,
    MAX_CACHE_BYTES,
    CacheStats,
    RenderCache,
)
from moanart.render.pipeline import RENDERABLE_OPERATION_TYPES, render
from moanart.render.regions import render_with_regions
from moanart.render.result import (
    RENDERER_BACKEND,
    RENDERER_VERSION,
    Provenance,
    RenderResult,
    RenderWarning,
)
from moanart.render.sequence import (
    RESULT_OVERHEAD_BYTES,
    SequenceBudget,
    admit_sequence,
    plan_frame,
    render_admitted,
    render_sequence,
)

__all__ = [
    "CACHE_KEY_FORMAT",
    "ENTRY_OVERHEAD_BYTES",
    "ESTIMATOR_VERSION",
    "MAX_CACHE_BYTES",
    "MAX_FRAMES",
    "RENDERABLE_OPERATION_TYPES",
    "RENDERER_BACKEND",
    "RENDERER_VERSION",
    "RESULT_OVERHEAD_BYTES",
    "CacheStats",
    "CostEstimate",
    "OperationCost",
    "Provenance",
    "RenderCache",
    "RenderResult",
    "RenderWarning",
    "SequenceBudget",
    "admit_sequence",
    "estimate_cost",
    "plan_budget",
    "plan_frame",
    "render",
    "render_admitted",
    "render_sequence",
    "render_with_regions",
]
