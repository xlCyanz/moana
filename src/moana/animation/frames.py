"""Rendering of animation frames under one accumulated budget (ADR-032).

A render request names an animation (or one of its frames). It runs in two
streaming passes that hold **one** frame document at a time besides the base:

1. the document is validated, the animation resolved and **every** frame of it
   evaluated against the base, so a single invalid override rejects the whole
   request before anything is drawn; each requested frame is estimated with
   :func:`moana.render.plan_frame` and only its :class:`~moana.render.CostEstimate`
   is kept. The estimates are then admitted together by
   :func:`moana.render.admit_sequence` (sums of visits and frame pixels, the bytes
   peak of the sequence) before the first pixel buffer exists;
2. each requested frame is evaluated again and rendered with
   :func:`moana.render.render_admitted`; only the admitted results are kept.

A timeline is finite: ``loop_count`` (``0``: infinite playback) is returned as
data and never repeats a render; each frame is rendered once.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from moana.animation.timeline import (
    check_options,
    find_animation,
    find_frame,
    frame_document,
    start_times,
    static_base,
    validated_base,
)
from moana.core.budget import Deadline, RenderLimits
from moana.core.coordinates import Point
from moana.core.errors import ReferenceError, ValidationError
from moana.render import (
    CostEstimate,
    RenderResult,
    admit_sequence,
    plan_frame,
    render_admitted,
)
from moana.schema import DEFAULT_PARSE_LIMITS, Animation, Document, ParseLimits

__all__ = ["AnimationRender", "FrameRender", "render_animation", "render_frame"]


@dataclass(frozen=True, slots=True)
class FrameRender:
    """One rendered frame: its timeline values and its immutable render result."""

    frame_id: str
    index: int
    start_ms: int
    duration_ms: int
    pivot: Point
    result: RenderResult


@dataclass(frozen=True, slots=True)
class AnimationRender:
    """The rendered frames of one animation, in the requested order.

    ``loop_count`` and ``pivot`` are the authored values; ``duration_ms`` is the sum
    of the durations of the rendered frames (one playback of them).
    """

    animation_id: str
    loop_count: int
    pivot: Point
    frames: tuple[FrameRender, ...]

    @property
    def duration_ms(self) -> int:
        """Duration of one playback of the rendered frames."""
        return sum(frame.duration_ms for frame in self.frames)


@dataclass(frozen=True, slots=True)
class _Request:
    """One animation request: what to evaluate and the options of every pass."""

    static: Document
    animation_index: int
    animation: Animation
    limits: RenderLimits | None
    parse_limits: ParseLimits
    deadline: Deadline | None

    def frame(self, index: int) -> Document:
        return frame_document(
            self.static,
            self.animation_index,
            self.animation,
            index,
            self.parse_limits,
            self.deadline,
        )


def _selected(animation: Animation, frame_ids: Sequence[str] | None) -> tuple[int, ...]:
    """Timeline indexes named by ``frame_ids``, in that order (``None``: all)."""
    if frame_ids is None:
        return tuple(range(len(animation.frames)))
    if isinstance(frame_ids, str | bytes) or not isinstance(frame_ids, Sequence):
        raise TypeError("frame_ids must be a sequence of frame IDs or None")
    if not frame_ids:
        raise ValidationError(
            "a request renders at least one frame",
            context={"field": "frame_ids", "reason": "empty_frames"},
        )
    by_id = {frame.id: index for index, frame in enumerate(animation.frames)}
    selected: list[int] = []
    for frame_id in frame_ids:
        if type(frame_id) is not str or frame_id not in by_id:
            raise ReferenceError(
                "frame does not exist in this animation",
                context={"field": "frame_ids", "reason": "unknown_frame"},
            )
        if by_id[frame_id] in selected:
            raise ValidationError(
                "a frame is requested more than once",
                context={"field": "frame_ids", "reason": "duplicate_frame"},
            )
        selected.append(by_id[frame_id])
    return tuple(selected)


def _admitted(request: _Request, wanted: tuple[int, ...]) -> dict[int, CostEstimate]:
    """Pass 1: evaluate every frame, estimate the wanted ones, admit them together."""
    positions = {index: position for position, index in enumerate(wanted)}
    estimates: dict[int, CostEstimate] = {}
    for index in range(len(request.animation.frames)):
        if request.deadline is not None:
            request.deadline.checkpoint("evaluate_frame")
        document = request.frame(index)
        if index in positions:
            estimates[index] = plan_frame(
                document,
                limits=request.limits,
                deadline=request.deadline,
                frame_index=positions[index],
            )
        del document
    admit_sequence([estimates[index] for index in wanted], limits=request.limits)
    return estimates


def _rendered(request: _Request, wanted: tuple[int, ...]) -> tuple[FrameRender, ...]:
    estimates = _admitted(request, wanted)
    starts = start_times(request.animation)
    renders: list[FrameRender] = []
    for index in wanted:  # pass 2: one frame document at a time
        frame = request.animation.frames[index]
        result = render_admitted(
            request.frame(index),
            frame_id=frame.id,
            estimate=estimates[index],
            limits=request.limits,
            deadline=request.deadline,
        )
        renders.append(
            FrameRender(
                frame_id=frame.id,
                index=index,
                start_ms=starts[index],
                duration_ms=frame.duration_ms,
                pivot=request.animation.pivot_point,
                result=result,
            )
        )
    return tuple(renders)


def _request(
    base: Document,
    animation_index: int,
    animation: Animation,
    limits: RenderLimits | None,
    parse_limits: ParseLimits,
    deadline: Deadline | None,
) -> _Request:
    if limits is not None and not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    static = static_base(base, parse_limits, deadline)
    return _Request(static, animation_index, animation, limits, parse_limits, deadline)


def render_animation(
    document: Document,
    animation_id: str,
    *,
    frame_ids: Sequence[str] | None = None,
    limits: RenderLimits | None = None,
    parse_limits: ParseLimits = DEFAULT_PARSE_LIMITS,
    deadline: Deadline | None = None,
) -> AnimationRender:
    """Render the frames of ``animation_id`` (all, or ``frame_ids`` in that order).

    Every frame of the animation is evaluated first and the requested ones are
    admitted together against ``limits`` (see the module docstring), so an invalid
    override or a request over budget renders nothing. Raises ``ReferenceError``
    (``unknown_animation``; ``unknown_frame`` in ``frame_ids``), ``ValidationError``
    (``empty_frames``, ``duplicate_frame`` and the editor's override errors),
    ``UnsupportedOperation`` or ``BudgetExceeded`` (budgets and the ``deadline``).
    """
    parse_limits = check_options(parse_limits, deadline)
    base = validated_base(document, parse_limits, deadline)
    animation_index, animation = find_animation(base, animation_id)
    wanted = _selected(animation, frame_ids)
    request = _request(base, animation_index, animation, limits, parse_limits, deadline)
    del base
    frames = _rendered(request, wanted)
    return AnimationRender(animation.id, animation.loop_count, animation.pivot_point, frames)


def render_frame(
    document: Document,
    frame_id: str,
    *,
    limits: RenderLimits | None = None,
    parse_limits: ParseLimits = DEFAULT_PARSE_LIMITS,
    deadline: Deadline | None = None,
) -> FrameRender:
    """Render one frame, named by its global ID, after evaluating its whole animation.

    The same rules as :func:`render_animation` with ``frame_ids=[frame_id]``; an
    unknown frame is ``ReferenceError`` (``field: frame_id``, ``unknown_frame``).
    """
    parse_limits = check_options(parse_limits, deadline)
    base = validated_base(document, parse_limits, deadline)
    animation_index, animation, index, _ = find_frame(base, frame_id)
    request = _request(base, animation_index, animation, limits, parse_limits, deadline)
    del base
    return _rendered(request, (index,))[0]
