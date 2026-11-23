"""Admit and render a finite sequence of frame documents under one budget (ADR-032).

Animations (:mod:`moanart.animation`) evaluate each frame into a static document, but
``render`` must not depend on the evaluator (MOANART.md section 3) and must not keep
every frame document alive at once. The sequence API is therefore split in three
steps that a caller runs in **two streaming passes**, holding one frame document at
a time:

1. :func:`plan_frame` checks and estimates one frame document (backend, operation
   types, :func:`~moanart.render.budget.plan_budget`) and returns its
   :class:`~moanart.render.CostEstimate`; the caller keeps only that estimate;
2. :func:`admit_sequence` compares the estimates with one
   :class:`~moanart.core.budget.RenderLimits` before any pixel buffer exists:

   * visits: the sum of every frame estimate;
   * frame pixels: the sum of every frame area (MOANART.md section 17: at most
     16 777 216 accumulated pixels by default);
   * bytes: the largest working peak of one frame plus, for every frame, its RGBA
     (``4·area``) and :data:`RESULT_OVERHEAD_BYTES` for the result object, since
     frames are rendered one after another and every result is kept;

3. :func:`render_admitted` validates one frame document again, checks that it is
   the document that was admitted (same estimate) and renders it.

:func:`render_sequence` runs those steps over ``(frame_id, document)`` pairs the
caller already holds; it keeps no validated copy between passes. A render never
depends on another frame, so the order of the sequence never changes a result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from moanart.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moanart.core.errors import BudgetExceeded, ErrorDetail
from moanart.core.ids import is_id
from moanart.render.budget import MAX_FRAMES, CostEstimate, plan_budget
from moanart.render.cache import RenderCache
from moanart.render.pipeline import (
    _check_cache,
    _check_renderable,
    _check_request,
    _render_validated,
)
from moanart.render.result import RenderResult
from moanart.schema import Document, normalize_document, validate_document

__all__ = [
    "RESULT_OVERHEAD_BYTES",
    "SequenceBudget",
    "admit_sequence",
    "plan_frame",
    "render_admitted",
    "render_sequence",
]

RGBA_BYTES: Final = 4
RESULT_OVERHEAD_BYTES: Final = 2048
"""Bytes kept per rendered frame besides its RGBA: the ``RenderResult``, its digest,
warnings and ``Provenance``, plus the timeline record of an animation frame
(measured with ``tracemalloc`` on CPython 3.12 between about 0.6 KiB per result in a
long sequence and 1.9 KiB for a single-frame animation render; rounded up)."""


@dataclass(frozen=True, slots=True)
class SequenceBudget:
    """What :func:`admit_sequence` admitted for the whole sequence."""

    frames: int
    pixel_visits: int
    buffer_bytes: int
    frame_pixels: int


def _with_frame_index(error: BudgetExceeded, index: int) -> BudgetExceeded:
    return BudgetExceeded(
        error.message,
        json_pointer=error.json_pointer,
        context={**error.context, "frame_index": index},
        details=error.details,
    )


def plan_frame(
    document: Document,
    *,
    limits: RenderLimits | None = None,
    deadline: Deadline | None = None,
    frame_index: int | None = None,
) -> CostEstimate:
    """Check and estimate one frame document alone, without rasterising it.

    Raises ``UnsupportedOperation`` (operation type or path backend) or
    ``BudgetExceeded`` (this frame alone over ``limits``). The document is not
    validated again here (the estimate is pure arithmetic that rejects broken
    references instead of looping); :func:`render_admitted` validates it before
    drawing. ``frame_index`` (the frame's position in its request), when given, is
    added to the context of a ``BudgetExceeded``.
    """
    request_limits = _check_request(document, limits, deadline)
    if frame_index is not None and type(frame_index) is not int:
        raise TypeError("frame_index must be an int or None")
    _check_renderable(document)
    try:
        return plan_budget(document, request_limits, deadline=deadline)
    except BudgetExceeded as error:
        if frame_index is None:
            raise
        raise _with_frame_index(error, frame_index) from None


def admit_sequence(
    estimates: Sequence[CostEstimate], *, limits: RenderLimits | None = None
) -> SequenceBudget:
    """Admit 1..``MAX_FRAMES`` frame estimates together against ``limits``.

    Raises ``BudgetExceeded`` listing every exceeded total (``resource``, ``limit``,
    ``estimated`` and ``frames`` in each detail); a total exactly at its limit is
    admitted.
    """
    if isinstance(estimates, str | bytes) or not isinstance(estimates, Sequence):
        raise TypeError("estimates must be a sequence of CostEstimate values")
    if not all(isinstance(estimate, CostEstimate) for estimate in estimates):
        raise TypeError("estimates must be a sequence of CostEstimate values")
    if not 1 <= len(estimates) <= MAX_FRAMES:
        raise ValueError(f"a sequence has 1..{MAX_FRAMES} frames")
    request_limits = _check_request_limits(limits)
    retained = sum(RGBA_BYTES * e.frame_pixels + RESULT_OVERHEAD_BYTES for e in estimates)
    peak = max(e.buffer_bytes - RGBA_BYTES * e.frame_pixels for e in estimates)
    budget = SequenceBudget(
        frames=len(estimates),
        pixel_visits=sum(e.pixel_visits for e in estimates),
        buffer_bytes=peak + retained,
        frame_pixels=sum(e.frame_pixels for e in estimates),
    )
    totals = (
        ("pixel_visits", request_limits.max_pixel_visits, budget.pixel_visits),
        ("buffer_bytes", request_limits.max_buffer_bytes, budget.buffer_bytes),
        ("frame_pixels", request_limits.max_frame_pixels, budget.frame_pixels),
    )
    details = [
        ErrorDetail(
            BudgetExceeded.code,
            f"estimated {resource} of the sequence exceed the request budget",
            context={
                "resource": resource,
                "limit": limit,
                "estimated": estimated,
                "frames": budget.frames,
            },
        )
        for resource, limit, estimated in totals
        if estimated > limit
    ]
    if details:
        raise BudgetExceeded(
            f"sequence exceeds {len(details)} budget{'s' if len(details) != 1 else ''}",
            context=dict(details[0].context),
            details=details,
        )
    return budget


def _check_request_limits(limits: object) -> RenderLimits:
    if limits is None:
        return DEFAULT_RENDER_LIMITS
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    return limits


def render_admitted(
    document: Document,
    *,
    frame_id: str,
    estimate: CostEstimate,
    limits: RenderLimits | None = None,
    deadline: Deadline | None = None,
    cache: RenderCache | None = None,
) -> RenderResult:
    """Validate and render one frame document admitted with ``estimate``.

    ``frame_id`` (an ID) is recorded in the provenance. The document is validated
    again (checking the cooperative ``deadline`` first, stage ``validate_frame``)
    and planned again; an estimate different from the admitted one is a programming
    error (``ValueError``): the caller rendered another document than it admitted.
    ``cache`` (optional, ADR-038) reuses finished layer buffers, also between frames.
    """
    request_limits = _check_request(document, limits, deadline)
    cache = _check_cache(cache)
    if type(frame_id) is not str or not is_id(frame_id):
        raise TypeError("frame_id must be an ID str")
    if not isinstance(estimate, CostEstimate):
        raise TypeError("estimate must be a CostEstimate")
    if deadline is not None:
        deadline.checkpoint("validate_frame")
    validated = validate_document(normalize_document(document))
    backend = _check_renderable(validated)
    if plan_budget(validated, request_limits, deadline=deadline) != estimate:
        raise ValueError("the document is not the one admitted with this estimate")
    return _render_validated(
        validated, frame_id, request_limits, deadline, backend, estimate, cache
    )


def _pairs(frames: object) -> tuple[tuple[str, Document], ...]:
    if isinstance(frames, str | bytes) or not isinstance(frames, Sequence):
        raise TypeError("frames must be a sequence of (frame_id, Document) pairs")
    if not 1 <= len(frames) <= MAX_FRAMES:
        raise ValueError(f"a sequence has 1..{MAX_FRAMES} frames")
    pairs: list[tuple[str, Document]] = []
    for pair in frames:
        if not (isinstance(pair, tuple) and len(pair) == 2):
            raise TypeError("each frame must be a (frame_id, Document) pair")
        frame_id, document = pair
        if type(frame_id) is not str or not is_id(frame_id):
            raise TypeError("frame_id must be an ID str")
        if not isinstance(document, Document):
            raise TypeError("document must be a moanart.schema.Document")
        pairs.append((frame_id, document))
    if len({frame_id for frame_id, _ in pairs}) != len(pairs):
        raise ValueError("frame IDs of a sequence must be unique")
    return tuple(pairs)


def render_sequence(
    frames: Sequence[tuple[str, Document]],
    *,
    limits: RenderLimits | None = None,
    deadline: Deadline | None = None,
    cache: RenderCache | None = None,
) -> tuple[RenderResult, ...]:
    """Render ``(frame_id, document)`` pairs, admitted together, in the given order.

    1..``MAX_FRAMES`` pairs with unique ID frame IDs. Each document is validated and
    estimated (a frame over budget alone carries ``frame_index``), the sequence is
    admitted with :func:`admit_sequence` and only then is each frame validated again
    and rendered; no validated copy is kept between the passes. Raises
    ``ValidationError``, ``ReferenceError``, ``UnsupportedOperation`` or
    ``BudgetExceeded``. ``cache`` (optional, ADR-038) is passed to every frame.
    """
    pairs = _pairs(frames)
    cache = _check_cache(cache)
    estimates: list[CostEstimate] = []
    for index, (_, document) in enumerate(pairs):
        _check_request(document, limits, deadline)
        if deadline is not None:
            deadline.checkpoint("validate_frame")
        validated = validate_document(normalize_document(document))
        estimates.append(plan_frame(validated, limits=limits, deadline=deadline, frame_index=index))
        del validated
    admit_sequence(estimates, limits=limits)
    return tuple(
        render_admitted(
            document,
            frame_id=frame_id,
            estimate=estimate,
            limits=limits,
            deadline=deadline,
            cache=cache,
        )
        for (frame_id, document), estimate in zip(pairs, estimates, strict=True)
    )
