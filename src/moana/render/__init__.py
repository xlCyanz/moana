"""Rendering of validated documents (MOANA.md sections 3, 13, 14 and 20).

:func:`render` is the deterministic orchestrator (MOANA-010, ADR-018): validation,
resolution, budget (:mod:`moana.render.budget`, MOANA-003), plan, raster and
composition into an immutable :class:`RenderResult`. Per-cell randomness lives in
:mod:`moana.core.procedural` so that techniques can use it. There is no cache and no
concurrency.
"""

from moana.render.budget import (
    ESTIMATOR_VERSION,
    MAX_FRAMES,
    CostEstimate,
    OperationCost,
    estimate_cost,
    plan_budget,
)
from moana.render.pipeline import RENDERABLE_OPERATION_TYPES, render
from moana.render.result import (
    RENDERER_BACKEND,
    RENDERER_VERSION,
    Provenance,
    RenderResult,
    RenderWarning,
)

__all__ = [
    "ESTIMATOR_VERSION",
    "MAX_FRAMES",
    "RENDERABLE_OPERATION_TYPES",
    "RENDERER_BACKEND",
    "RENDERER_VERSION",
    "CostEstimate",
    "OperationCost",
    "Provenance",
    "RenderResult",
    "RenderWarning",
    "estimate_cost",
    "plan_budget",
    "render",
]
