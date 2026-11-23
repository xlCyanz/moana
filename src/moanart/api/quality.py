"""Quality report of a rendered document (MOANART.md section 19, ADR-036).

:func:`evaluate_quality` composes services and adds no algorithm. The whole request
is admitted against **one** budget before the first pixel buffer exists:

1. the configuration is a checked :class:`~moanart.quality.QualityConfig` value, and
   ``animation_id`` a ``str`` or ``None``, before anything is validated or rendered;
2. with ``animation_id``, :func:`moanart.animation.evaluate_animation` resolves the
   animation (``unknown_animation`` before any render) and evaluates every frame;
   each frame is estimated with :func:`moanart.render.plan_frame` and the estimates
   are summed by :func:`moanart.render.admit_sequence`;
3. :func:`moanart.render.render_with_regions` validates the document once, resolves
   every region the configuration names (``unknown_region`` before rendering) and
   admits the base render, the region masks, the animation frames (their visits and
   retained bytes) and the analysis (:func:`moanart.quality.quality_cost`) together
   against ``limits``; the frame pixels of the base render and of the animation are
   admitted together against ``max_frame_pixels``;
4. :func:`moanart.animation.render_animation` renders the admitted frames and
   :func:`moanart.quality.evaluate_quality` evaluates the base render (and the
   frames, with the loop seam when ``loop_count`` is not ``1``) with the document
   canvas and palette.

The configuration is evaluation data, never part of the document; neither the
document nor its snapshot digest changes. There is no CLI command (diagnostics
belong to MOANA-033).
"""

from __future__ import annotations

from moanart.animation import evaluate_animation, find_animation, render_animation
from moanart.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moanart.core.errors import BudgetExceeded
from moanart.palette import Palette
from moanart.quality import QualityConfig, QualityReport, quality_cost
from moanart.quality import evaluate_quality as _evaluate
from moanart.render import SequenceBudget, admit_sequence, plan_frame, render_with_regions
from moanart.schema import Document

__all__ = ["evaluate_quality"]


def _sequence(
    document: Document,
    animation_id: str,
    limits: RenderLimits,
    deadline: Deadline | None,
) -> tuple[SequenceBudget, bool]:
    """Admitted totals of every frame of the animation and whether it loops."""
    evaluations = evaluate_animation(document, animation_id, deadline=deadline)
    _, animation = find_animation(document, animation_id)
    estimates = [
        plan_frame(item.document, limits=limits, deadline=deadline, frame_index=index)
        for index, item in enumerate(evaluations)
    ]
    del evaluations
    return admit_sequence(estimates, limits=limits), animation.loop_count != 1


def _admit_frame_pixels(base: int, sequence: SequenceBudget, limits: RenderLimits) -> None:
    total = base + sequence.frame_pixels
    if total > limits.max_frame_pixels:
        raise BudgetExceeded(
            "quality report exceeds the frame pixel budget",
            context={
                "resource": "frame_pixels",
                "limit": limits.max_frame_pixels,
                "estimated": total,
            },
        )


def evaluate_quality(
    document: Document,
    *,
    config: QualityConfig | None = None,
    animation_id: str | None = None,
    limits: RenderLimits | None = None,
    deadline: Deadline | None = None,
) -> QualityReport:
    """Hard checks, artistic warnings and metrics of the render of ``document``.

    With ``animation_id`` the frames of that animation are also checked (hard rules
    and metrics per frame, ``temporal_flicker`` and, when enabled,
    ``temporal_change`` between frames; with ``loop_count`` other than ``1`` also
    across the seam from the last frame to the first). Raises ``TypeError`` for
    arguments of the wrong type, ``ReferenceError`` (``unknown_animation``,
    ``unknown_region``) and ``BudgetExceeded`` for the whole request before
    anything is rendered, then the errors of the render and of
    :func:`moanart.quality.evaluate_quality`.
    """
    if not isinstance(document, Document):
        raise TypeError("document must be a moanart.schema.Document")
    config = QualityConfig() if config is None else config
    if not isinstance(config, QualityConfig):
        raise TypeError("config must be a QualityConfig")
    if animation_id is not None and type(animation_id) is not str:
        raise TypeError("animation_id must be a str or None")
    request_limits = DEFAULT_RENDER_LIMITS if limits is None else limits
    if not isinstance(request_limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    canvas = document.canvas.dimensions
    sequence = SequenceBudget(frames=0, pixel_visits=0, buffer_bytes=0, frame_pixels=0)
    loop = False
    if animation_id is not None:
        sequence, loop = _sequence(document, animation_id, request_limits, deadline)
        _admit_frame_pixels(canvas.area, sequence, request_limits)
    visits, held = quality_cost(canvas, config, sequence.frames)
    result, regions = render_with_regions(
        document,
        config.region_ids,
        limits=request_limits,
        deadline=deadline,
        extra_visits=visits + sequence.pixel_visits,
        extra_bytes=held + sequence.buffer_bytes,
    )
    frames = (
        ()
        if animation_id is None
        else render_animation(
            document, animation_id, limits=request_limits, deadline=deadline
        ).frames
    )
    palette = Palette.from_mapping(
        document.palette.model_dump(mode="json"), profile=document.canvas.profile
    )
    return _evaluate(
        result,
        canvas=canvas,
        palette=palette,
        config=config,
        regions=regions,
        frames=frames,
        loop=loop,
        limits=request_limits,
        deadline=deadline,
    )
