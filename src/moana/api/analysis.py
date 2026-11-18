"""Read-only cluster analysis of a rendered document (MOANA.md sections 8 and 19, ADR-027).

:func:`analyze_clusters` composes services and adds no algorithm:

1. the settings are checked first (:func:`moana.techniques.check_cluster_settings`:
   connectivity, duplicated regions, rule IDs, at most
   :data:`~moana.core.limits.MAX_CLUSTER_EXCEPTIONS` exceptions), before anything is
   validated or rendered;
2. :func:`moana.render.render_with_regions` validates the document once, resolves
   every exception's region (``unknown_region`` before rendering) and admits the
   whole request against one budget: the render, each region mask read once, the
   cover of the region masks (:func:`moana.geometry.cover_bytes`, only with
   exceptions) and the analysis itself (:func:`moana.techniques.cluster_bytes`, plus
   two visits per pixel for the scan and the labelling);
3. :func:`moana.techniques.analyze_clusters` folds the region masks into the cover
   one at a time and analyses the RGBA bytes, with the same ``deadline``.

The exceptions are evaluation configuration (section 19): they never enter the
document, and neither the document nor its snapshot digest changes. There is no
automatic cleanup.
"""

from __future__ import annotations

from collections.abc import Sequence

from moana.core.budget import Deadline, RenderLimits
from moana.geometry import cover_bytes
from moana.render import render_with_regions
from moana.schema import Document
from moana.techniques import (
    ClusterException,
    ClusterReport,
    Connectivity,
    check_cluster_settings,
    cluster_bytes,
)
from moana.techniques import analyze_clusters as _analyze

__all__ = ["ANALYSIS_VISITS_PER_PIXEL", "analyze_clusters"]

ANALYSIS_VISITS_PER_PIXEL = 2
"""Visits one cluster analysis adds per canvas pixel: the run scan and the labelling."""


def analyze_clusters(
    document: Document,
    *,
    connectivity: Connectivity = 4,
    exceptions: Sequence[ClusterException] = (),
    limits: RenderLimits | None = None,
    deadline: Deadline | None = None,
) -> ClusterReport:
    """Clusters and artistic warnings of the render of ``document``.

    ``connectivity`` is ``4`` (the default analysis of section 8) or ``8``. Each
    exception silences its ``rules`` for findings lying entirely in its region.
    Raises ``ValidationError`` (``unsupported_connectivity``, ``duplicate_reference``,
    ``too_many_exceptions``) before rendering, ``ReferenceError``
    (``unknown_region``) before rendering, the errors of :func:`moana.render.render`
    and ``BudgetExceeded`` (the whole request, ``cluster_runs`` or ``time``).
    """
    if not isinstance(document, Document):
        raise TypeError("document must be a moana.schema.Document")
    checked, rules = check_cluster_settings(connectivity, exceptions)
    dimensions = document.canvas.dimensions
    held = cluster_bytes(dimensions) + (cover_bytes(dimensions) if rules else 0)
    result, regions = render_with_regions(
        document,
        [exception.region_id for exception in rules],
        limits=limits,
        deadline=deadline,
        extra_visits=ANALYSIS_VISITS_PER_PIXEL * dimensions.area,
        extra_bytes=held,
    )
    return _analyze(
        result.rgba,
        dimensions,
        connectivity=checked,
        exceptions=rules,
        regions=regions,
        deadline=deadline,
    )
