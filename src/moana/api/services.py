"""Render and export entry points of the public facade (MOANA.md section 13, ADR-020).

They compose :func:`moana.render.render` and :func:`moana.export.export_png` without
reimplementing them: ``render`` writes nothing and leaves the document untouched;
``export_png`` writes the master or scaled RGBA PNG of a :class:`RenderResult`
atomically to a caller-authorised path. Indexed PNG stays available through
``moana.export`` directly, since it needs a resolved palette.
"""

from __future__ import annotations

import os

from moana.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moana.export import ExportManifest
from moana.export import export_png as _export_png
from moana.render import RenderResult
from moana.render import render as _render
from moana.schema import Document

__all__ = ["export_png", "render"]


def render(
    document: Document,
    *,
    frame_id: str | None = None,
    limits: RenderLimits | None = None,
    deadline: Deadline | None = None,
) -> RenderResult:
    """Render one frame into an immutable :class:`RenderResult` (no files written).

    Raises ``ValidationError``, ``ReferenceError`` (a ``frame_id``: schema 1.0 has no
    frames), ``UnsupportedOperation`` or ``BudgetExceeded``; see ADR-018.
    """
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
        raise TypeError("result must be a moana.render.RenderResult")
    return _export_png(
        result,
        path,
        scale=scale,
        overwrite=overwrite,
        limits=DEFAULT_RENDER_LIMITS if limits is None else limits,
    )
