"""Render a document together with the masks of some of its regions (ADR-027).

:func:`render_with_regions` serves read-only analyses that need the image and the
pixels of named regions (the cluster exceptions of section 19). It validates the
document **once**, resolves every region before anything is rasterised, and admits
the whole request against one :class:`~moana.core.budget.RenderLimits` before any
buffer exists:

* visits: the render, plus for each region its mask estimate and one pass over the
  mask box (the reader folds it once), plus the caller's ``extra_visits``;
* bytes: ``max(render peak, 4·area + extra_bytes + largest region mask peak)``. The
  render's working buffers are gone when the regions are read; what stays is the
  RGBA (``4·area``), whatever the caller holds (``extra_bytes``) and **one** region
  mask at a time.

The region masks come back as a lazy read-only mapping: each read evaluates the
mask again (same rasterisers and evaluation order as a layer mask of
:func:`moana.render.render`) and nothing is cached, so a caller that folds each mask
once and drops it stays within the admitted peak.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

from moana.core.budget import Deadline, RenderLimits
from moana.core.coordinates import Dimensions
from moana.core.errors import BudgetExceeded, ErrorDetail
from moana.geometry import Mask
from moana.layers import MaskNode, evaluate_mask
from moana.render.budget import mask_estimates, plan_budget
from moana.render.pipeline import (
    _check_renderable,
    _check_request,
    _plan_masks,
    _render_validated,
)
from moana.render.result import RenderResult
from moana.schema import Document, normalize_document, resolve_region, validate_document

__all__ = ["render_with_regions"]

RGBA_BYTES = 4


class _RegionMasks(Mapping[str, Mask]):
    """Region ID → mask, evaluated on every read and never cached."""

    __slots__ = ("_deadline", "_dimensions", "_nodes")

    def __init__(
        self, nodes: dict[str, MaskNode], dimensions: Dimensions, deadline: Deadline | None
    ) -> None:
        self._nodes = nodes
        self._dimensions = dimensions
        self._deadline = deadline

    def __getitem__(self, region_id: str) -> Mask:
        node = self._nodes[region_id]
        return evaluate_mask(node, self._dimensions, deadline=self._deadline)

    def __iter__(self) -> Iterator[str]:
        return iter(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)


def _check_extra(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise TypeError(f"{name} must be a non-negative int")
    return value


def _region_ids(region_ids: object) -> tuple[str, ...]:
    if isinstance(region_ids, str | bytes) or not isinstance(region_ids, Sequence):
        raise TypeError("region_ids must be a sequence of region IDs")
    return tuple(dict.fromkeys(region_ids))


def _admit(totals: tuple[int, int], limits: RenderLimits) -> None:
    """``BudgetExceeded`` listing each of ``(visits, bytes)`` over its limit."""
    checks = (
        ("pixel_visits", limits.max_pixel_visits, totals[0]),
        ("buffer_bytes", limits.max_buffer_bytes, totals[1]),
    )
    details = [
        ErrorDetail(
            BudgetExceeded.code,
            f"estimated {name} of the render and its regions exceed the request budget",
            context={"resource": name, "limit": limit, "estimated": value},
        )
        for name, limit, value in checks
        if value > limit
    ]
    if details:
        plural = "s" if len(details) != 1 else ""
        raise BudgetExceeded(
            f"render with regions exceeds {len(details)} budget{plural}",
            context=dict(details[0].context),
            details=details,
        )


def render_with_regions(
    document: Document,
    region_ids: Sequence[str],
    *,
    limits: RenderLimits | None = None,
    deadline: Deadline | None = None,
    extra_visits: int = 0,
    extra_bytes: int = 0,
) -> tuple[RenderResult, Mapping[str, Mask]]:
    """Render ``document`` and return it with a lazy mapping of its regions' masks.

    Raises the errors of :func:`moana.render.render`, ``ReferenceError``
    (``unknown_region``) for an ID that names no region, before rendering, and
    ``BudgetExceeded`` when the whole request (see the module docstring) is over
    ``limits``. ``extra_visits`` and ``extra_bytes`` are the caller's own work and
    memory held next to the RGBA while the regions are read.
    """
    limits = _check_request(document, limits, deadline)
    ids = _region_ids(region_ids)
    extra_visits = _check_extra(extra_visits, "extra_visits")
    extra_bytes = _check_extra(extra_bytes, "extra_bytes")
    document = validate_document(normalize_document(document))
    backend = _check_renderable(document)
    mask_ids = {region_id: resolve_region(document, region_id).mask_id for region_id in ids}
    estimate = plan_budget(document, limits, deadline=deadline)
    estimates = mask_estimates(document)
    dimensions = document.canvas.dimensions
    regions = [estimates[mask_id] for mask_id in mask_ids.values()]
    visits = estimate.pixel_visits + extra_visits
    visits += sum(e.pixel_visits + (0 if e.box is None else e.box.area) for e in regions)
    held = RGBA_BYTES * dimensions.area + extra_bytes
    held += max((e.buffer_bytes for e in regions), default=0)
    _admit((visits, max(estimate.buffer_bytes, held)), limits)
    result = _render_validated(document, None, limits, deadline, backend, estimate)
    nodes = _plan_masks(document, dimensions, list(dict.fromkeys(mask_ids.values())))
    by_region = {region_id: nodes[mask_id] for region_id, mask_id in mask_ids.items()}
    return result, _RegionMasks(by_region, dimensions, deadline)
