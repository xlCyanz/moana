"""Timelines and frame evaluation of MoanArt documents (MOANART.md section 17, ADR-032).

An animation of schema 1.0 has an ID, ordered frames, ``loop_count`` (``0``:
infinite playback) and a common integer pivot; each frame has an ID, a whole
``duration_ms`` (1..60 000) and typed overrides of base IDs (visibility, geometry by
``translate``, colour reference). :func:`evaluate_frame` and
:func:`evaluate_animation` evaluate frames always against the base document, with
the editor's rules and without creating a revision; :func:`render_animation` and
:func:`render_frame` evaluate every frame of the animation, admit the requested
frames against one accumulated budget and only then render each one. No tweening,
no rigging, no implicit temporal variation: the frame never enters the seed.

``animation`` depends on ``core``, ``schema``, ``editing`` and ``render`` (MOANART.md
section 3). It writes no files: GIF and spritesheet export are separate issues.
"""

from moanart.animation.frames import AnimationRender, FrameRender, render_animation, render_frame
from moanart.animation.timeline import (
    FrameEvaluation,
    evaluate_animation,
    evaluate_frame,
    find_animation,
    find_frame,
)

__all__ = [
    "AnimationRender",
    "FrameEvaluation",
    "FrameRender",
    "evaluate_animation",
    "evaluate_frame",
    "find_animation",
    "find_frame",
    "render_animation",
    "render_frame",
]
