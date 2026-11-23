"""Render and export entry points of the public facade (MOANART.md section 13, ADR-020).

They compose :func:`moanart.render.render`, :func:`moanart.animation.render_frame` (a
``frame_id``, ADR-032) and :func:`moanart.export.export_png` without reimplementing
them: ``render`` writes nothing and leaves the document untouched;
``export_png`` writes the master or scaled RGBA PNG of a :class:`RenderResult`
atomically to a caller-authorised path. Indexed PNG stays available through
``moanart.export`` directly, since it needs a resolved palette.
"""

from __future__ import annotations

import os

from moanart.animation import render_frame
from moanart.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moanart.export import ExportManifest
from moanart.export import export_png as _export_png
from moanart.render import RenderResult
from moanart.render import render as _render
from moanart.schema import Document

__all__ = ["export_png", "render"]


def render(
    document: Document,
    *,
    frame_id: str | None = None,
    limits: RenderLimits | None = None,
    deadline: Deadline | None = None,
) -> RenderResult:
    """Render one frame into an immutable :class:`RenderResult` (no files written).

    ``frame_id=None`` renders the base document (ADR-018). A ``frame_id`` names an
    animation frame by its global ID: every frame of its animation is evaluated
    against the base, then that frame alone is admitted and rendered, with
    ``frame_id`` in the provenance (:func:`moanart.animation.render_frame`, ADR-032).
    Raises ``ValidationError``, ``ReferenceError`` (``unknown_frame``),
    ``UnsupportedOperation`` or ``BudgetExceeded``.
    """
    if frame_id is not None:
        if not isinstance(document, Document):
            raise TypeError("document must be a moanart.schema.Document")
        if type(frame_id) is not str:
            raise TypeError("frame_id must be a str or None")
        if limits is not None and not isinstance(limits, RenderLimits):
            raise TypeError("limits must be a RenderLimits value")
        if deadline is not None and not isinstance(deadline, Deadline):
            raise TypeError("deadline must be a Deadline or None")
        return render_frame(document, frame_id, limits=limits, deadline=deadline).result
    return _render(document, frame_id=frame_id, limits=limits, deadline=deadline)


def export_png(
    result: RenderResult,
    path: str | os.PathLike[str],
    *,
    scale: int = 1,
    overwrite: bool = False,
    limits: RenderLimits | None = None,
) -> ExportManifest:
    """Write ``result`` as an RGBA PNG at ``path`` and return its manifest.

    ``scale`` is an integer ``1..64`` (nearest neighbour; ``scale > 1`` is a preview).
    With ``overwrite=False`` an existing file is never replaced. Raises
    ``ValidationError`` (scale, extension, unrepresentable name), ``BudgetExceeded``
    or ``ExportError``; see ADR-019.
    """
    if not isinstance(result, RenderResult):
        raise TypeError("result must be a moanart.render.RenderResult")
    return _export_png(
        result,
        path,
        scale=scale,
        overwrite=overwrite,
        limits=DEFAULT_RENDER_LIMITS if limits is None else limits,
    )
