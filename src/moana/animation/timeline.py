"""Evaluation of animation frames against the base document (MOANA.md section 17).

A frame is the base document plus that frame's overrides, and nothing else: it never
starts from the previous frame, so evaluating frames in any order, alone or together,
gives the same documents (ADR-032). Evaluation goes through the editor
(:func:`moana.editing.apply_commands`): each override becomes the edit command of the
same name and runs with its rules (type table, target kinds, locked layers, ranges),
then the whole frame document is validated again. No revision is created and the
persistent revision of the document never changes.

An evaluated frame document is *static*: the base with the overrides applied and an
empty ``animations`` collection, the exact document that is rendered. Its ``seed``
and every ID are the base's and the frame never enters the seed, so per-cell
textures (materials, dithering phases) stay anchored to their ``origin`` in canvas
coordinates in every frame. Moving a textured sprite in a frame therefore slides
the texture relative to the sprite: schema 1.0 has no ``origin`` override yet.

The helpers :func:`validated_base`, :func:`static_base` and :func:`frame_document`
let :mod:`moana.animation.frames` evaluate one frame at a time (streaming); they are
not part of the package API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from moana.core.budget import Deadline
from moana.core.coordinates import Point
from moana.core.errors import ReferenceError
from moana.editing import SetColor, SetVisibility, Translate, apply_commands
from moana.schema import (
    DEFAULT_PARSE_LIMITS,
    Animation,
    Document,
    Frame,
    FrameOverride,
    ParseLimits,
    SetColorOverride,
    SetVisibilityOverride,
    TranslateOverride,
    normalize_document,
    validate_document,
)

__all__ = [
    "FrameEvaluation",
    "check_options",
    "evaluate_animation",
    "evaluate_frame",
    "find_animation",
    "find_frame",
    "frame_document",
    "start_times",
    "static_base",
    "validated_base",
]


@dataclass(frozen=True, slots=True)
class FrameEvaluation:
    """One evaluated frame: where it sits in its timeline and its static document.

    ``index`` is the position of the frame in its animation, ``start_ms`` the sum of
    the durations before it and ``duration_ms``/``pivot`` the authored values,
    unchanged. ``document`` is the base with this frame's overrides applied and no
    animations; its revision is the base revision.
    """

    animation_id: str
    frame_id: str
    index: int
    start_ms: int
    duration_ms: int
    pivot: Point
    document: Document


def _check_document(document: object) -> Document:
    if not isinstance(document, Document):
        raise TypeError("document must be a moana.schema.Document")
    return document


def check_options(limits: object, deadline: object) -> ParseLimits:
    """Type checks shared by the evaluation entry points."""
    if not isinstance(limits, ParseLimits):
        raise TypeError("limits must be a ParseLimits value")
    if deadline is not None and not isinstance(deadline, Deadline):
        raise TypeError("deadline must be a Deadline or None")
    return limits


def _checkpoint(deadline: Deadline | None) -> None:
    if deadline is not None:
        deadline.checkpoint("validate_frame")


def find_animation(document: Document, animation_id: str) -> tuple[int, Animation]:
    """Index and model of the animation ``animation_id``.

    ``ReferenceError`` (``field: animation_id``, ``unknown_animation``) if absent.
    """
    _check_document(document)
    if type(animation_id) is str:
        for index, animation in enumerate(document.animations):
            if animation.id == animation_id:
                return index, animation
    raise ReferenceError(
        "animation does not exist",
        context={"field": "animation_id", "reason": "unknown_animation"},
    )


def find_frame(document: Document, frame_id: str) -> tuple[int, Animation, int, Frame]:
    """Animation index, animation, frame index and frame of ``frame_id``.

    Frame IDs are global (MOANA.md section 12), so the frame alone names its
    animation. ``ReferenceError`` (``field: frame_id``, ``unknown_frame``) if absent.
    """
    _check_document(document)
    if type(frame_id) is str:
        for animation_index, animation in enumerate(document.animations):
            for index, frame in enumerate(animation.frames):
                if frame.id == frame_id:
                    return animation_index, animation, index, frame
    raise ReferenceError(
        "frame does not exist", context={"field": "frame_id", "reason": "unknown_frame"}
    )


def _command(override: FrameOverride) -> SetVisibility | Translate | SetColor:
    """The edit command of the same name and members as ``override``."""
    match override:
        case SetVisibilityOverride():
            return SetVisibility(
                type="set_visibility", target_id=override.target_id, visible=override.visible
            )
        case TranslateOverride():
            return Translate(
                type="translate", target_id=override.target_id, dx=override.dx, dy=override.dy
            )
        case SetColorOverride():
            return SetColor(type="set_color", target_id=override.target_id, color=override.color)
        case _:  # pragma: no cover - a new override type must add its command
            assert_never(override)


def validated_base(document: object, limits: ParseLimits, deadline: Deadline | None) -> Document:
    """``document`` validated again (it may come from ``model_construct``)."""
    tree = normalize_document(_check_document(document))
    _checkpoint(deadline)
    return validate_document(tree, limits=limits)


def static_base(base: Document, limits: ParseLimits, deadline: Deadline | None) -> Document:
    """The validated base without animations: what a frame without overrides is."""
    tree = normalize_document(base)
    tree["animations"] = []
    _checkpoint(deadline)
    return validate_document(tree, limits=limits)


def frame_document(
    static: Document,
    animation_index: int,
    animation: Animation,
    index: int,
    limits: ParseLimits,
    deadline: Deadline | None,
) -> Document:
    """Frame ``index`` evaluated against ``static`` (itself when it has no overrides)."""
    frame = animation.frames[index]
    if not frame.overrides:
        return static
    commands = tuple(_command(override) for override in frame.overrides)
    pointer = f"/animations/{animation_index}/frames/{index}/overrides"
    _checkpoint(deadline)
    return apply_commands(static, commands, pointer=pointer, limits=limits)


def start_times(animation: Animation) -> tuple[int, ...]:
    """Start of every frame: the sum of the durations before it, in milliseconds."""
    starts: list[int] = []
    elapsed = 0
    for frame in animation.frames:
        starts.append(elapsed)
        elapsed += frame.duration_ms
    return tuple(starts)


def _evaluation(
    animation: Animation, index: int, start_ms: int, document: Document
) -> FrameEvaluation:
    frame = animation.frames[index]
    return FrameEvaluation(
        animation_id=animation.id,
        frame_id=frame.id,
        index=index,
        start_ms=start_ms,
        duration_ms=frame.duration_ms,
        pivot=animation.pivot_point,
        document=document,
    )


def evaluate_frame(
    document: Document,
    frame_id: str,
    *,
    limits: ParseLimits = DEFAULT_PARSE_LIMITS,
    deadline: Deadline | None = None,
) -> FrameEvaluation:
    """Evaluate one frame against the base ``document`` (never another frame).

    Raises ``ReferenceError`` (``unknown_frame``), and the editor's
    ``ValidationError``/``ReferenceError`` for an override that cannot apply (for
    example ``invalid_target``, ``not_geometric``, ``multiple_colors``,
    ``locked_layer``, ``out_of_range``), located at
    ``/animations/i/frames/j/overrides/k``. ``deadline`` is checked before every
    validation (stage ``validate_frame``).
    """
    limits = check_options(limits, deadline)
    base = validated_base(document, limits, deadline)
    animation_index, animation, index, _ = find_frame(base, frame_id)
    static = static_base(base, limits, deadline)
    evaluated = frame_document(static, animation_index, animation, index, limits, deadline)
    return _evaluation(animation, index, start_times(animation)[index], evaluated)


def evaluate_animation(
    document: Document,
    animation_id: str,
    *,
    limits: ParseLimits = DEFAULT_PARSE_LIMITS,
    deadline: Deadline | None = None,
) -> tuple[FrameEvaluation, ...]:
    """Evaluate every frame of ``animation_id``, in timeline order, before returning.

    Each frame is evaluated against the same base; the first override that cannot
    apply raises (see :func:`evaluate_frame`) and nothing is returned. ``deadline``
    is checked before each frame (``evaluate_frame``) and each validation. The
    result holds one document per frame with overrides: rendering does not use it
    (:mod:`moana.animation.frames` streams one frame at a time).
    """
    limits = check_options(limits, deadline)
    base = validated_base(document, limits, deadline)
    animation_index, animation = find_animation(base, animation_id)
    static = static_base(base, limits, deadline)
    evaluations: list[FrameEvaluation] = []
    for index, start_ms in enumerate(start_times(animation)):
        if deadline is not None:
            deadline.checkpoint("evaluate_frame")
        evaluated = frame_document(static, animation_index, animation, index, limits, deadline)
        evaluations.append(_evaluation(animation, index, start_ms, evaluated))
    return tuple(evaluations)
