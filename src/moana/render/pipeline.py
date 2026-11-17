"""Deterministic render orchestrator (MOANA.md sections 3, 13, 14 and 20, ADR-018).

``render`` runs the mandatory flow of section 3 on one schema 1.0 document:

1. **Validation**: the canonical tree of the document is validated again with
   :func:`moana.schema.validate_document`, so a model built without that entry point
   still gets ID uniqueness, colour references and profile rules. The frame must be
   ``None`` (schema 1.0 has no animations).
2. **Resolution**: the schema palette becomes a :class:`moana.palette.Palette` and
   every operation colour is resolved to its ``Rgba``; an operation type without a
   registered rasteriser is ``UNSUPPORTED_OPERATION``.
3. **Budget**: :func:`moana.render.budget.plan_budget` rejects the request before any
   pixel buffer exists.
4. **Plan**: a :class:`moana.layers.LayerTree` whose fills are deferred masks with
   their declared boxes; nothing is rasterised yet.
5. **Raster and composition**: :func:`moana.layers.compose` builds one mask at a time,
   in array order, between deadline checks.

Order comes only from document arrays: no sets, ``hash()``, clock, locale, global
state or concurrency decide pixels. The document is never modified and nothing is
read from or written to disk.
"""

from __future__ import annotations

from functools import partial
from typing import Final, assert_never

from moana.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moana.core.coordinates import Dimensions, Point
from moana.core.errors import ReferenceError, UnsupportedOperation
from moana.core.procedural import RNG_VERSION
from moana.geometry import (
    Mask,
    rasterize_ellipse,
    rasterize_line,
    rasterize_pixel,
    rasterize_polygon,
    rasterize_rect,
)
from moana.layers import DeferredMask, Fill, Layer, LayerTree, compose
from moana.palette import Palette
from moana.render.budget import mask_box, plan_budget
from moana.render.result import (
    RENDERER_BACKEND,
    RENDERER_VERSION,
    Provenance,
    RenderResult,
    RenderWarning,
)
from moana.schema import (
    Document,
    EllipseOperation,
    LineOperation,
    Operation,
    PixelOperation,
    PolygonOperation,
    RectOperation,
    normalize_document,
    snapshot_digest,
    validate_document,
)
from moana.schema import Layer as DocumentLayer

__all__ = ["RENDERABLE_OPERATION_TYPES", "render"]

RENDERABLE_OPERATION_TYPES: Final = ("pixel", "line", "rect", "ellipse", "polygon")
"""Operation types with a registered rasteriser, in registration order."""

EMPTY_BOUNDS: Final = "empty_bounds"
"""Warning: the operation's bounds clipped to the canvas are empty (nothing to draw)."""


def _rasterize(operation: Operation, dimensions: Dimensions) -> Mask:
    """Mask of one operation clipped to the canvas (the explicit rasteriser registry)."""
    match operation:
        case PixelOperation():
            return rasterize_pixel(operation.point, dimensions)
        case LineOperation():
            return rasterize_line(Point(*operation.start), Point(*operation.end), dimensions)
        case RectOperation():
            return rasterize_rect(operation.bbox, dimensions)
        case EllipseOperation():
            return rasterize_ellipse(operation.bbox, dimensions)
        case PolygonOperation():
            return rasterize_polygon([Point(*point) for point in operation.points], dimensions)
        case _:  # pragma: no cover - a new operation type must register its rasteriser
            assert_never(operation)


def _check_frame(frame_id: str | None) -> None:
    if frame_id is None:
        return
    raise ReferenceError(
        "frame does not exist: schema 1.0 documents have no animations",
        context={"field": "frame_id", "reason": "unknown_frame"},
    )


def _check_renderable(document: Document) -> None:
    for layer_index, layer in enumerate(document.layers):
        for index, operation in enumerate(layer.operations):
            if operation.type not in RENDERABLE_OPERATION_TYPES:
                raise UnsupportedOperation(
                    "operation type has no registered rasteriser",
                    json_pointer=f"/layers/{layer_index}/operations/{index}/type",
                    context={"reason": "no_rasterizer", "type": operation.type},
                )


def _plan_layer(
    layer: DocumentLayer,
    layer_index: int,
    palette: Palette,
    dimensions: Dimensions,
    warnings: list[RenderWarning],
) -> Layer:
    fills: list[Fill] = []
    for index, operation in enumerate(layer.operations):
        box = mask_box(operation, dimensions)
        if box is None:
            warnings.append(
                RenderWarning(
                    EMPTY_BOUNDS,
                    "operation bounds are empty once clipped to the canvas",
                    f"/layers/{layer_index}/operations/{index}",
                )
            )
        mask = DeferredMask(box, partial(_rasterize, operation, dimensions))
        fills.append(Fill(mask, palette.color(operation.color)))
    return Layer(
        layer.id,
        layer.name,
        tuple(fills),
        visible=layer.visible,
        locked=layer.locked,
        opacity=layer.opacity,
        blend=layer.blend,
    )


def render(
    document: Document,
    *,
    frame_id: str | None = None,
    limits: RenderLimits | None = None,
    deadline: Deadline | None = None,
) -> RenderResult:
    """Render one frame of ``document`` into an immutable :class:`RenderResult`.

    ``limits`` defaults to the section 20 budgets; only the hosting application may
    raise them. Raises ``ValidationError``, ``ReferenceError`` (also for a
    ``frame_id``, since schema 1.0 has no frames), ``UnsupportedOperation`` or
    ``BudgetExceeded`` (budgets and the cooperative ``deadline``, checked before
    each layer is planned and before each node and operation is drawn).
    """
    if not isinstance(document, Document):
        raise TypeError("document must be a moana.schema.Document")
    if limits is None:
        limits = DEFAULT_RENDER_LIMITS
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    if deadline is not None and not isinstance(deadline, Deadline):
        raise TypeError("deadline must be a Deadline or None")
    if frame_id is not None and type(frame_id) is not str:
        raise TypeError("frame_id must be a str or None")

    document = validate_document(normalize_document(document))
    _check_frame(frame_id)
    _check_renderable(document)
    profile = document.canvas.profile
    palette = Palette.from_mapping(document.palette.model_dump(mode="json"), profile=profile)
    estimate = plan_budget(document, limits, deadline=deadline)

    dimensions = document.canvas.dimensions
    warnings: list[RenderWarning] = []
    layers: list[Layer] = []
    for layer_index, layer in enumerate(document.layers):
        if deadline is not None:
            deadline.checkpoint("plan_layer")
        layers.append(_plan_layer(layer, layer_index, palette, dimensions, warnings))
    tree = LayerTree(dimensions, tuple(layers), profile=profile)

    canvas = compose(tree, limits=limits, deadline=deadline)
    rgba, digest = canvas.to_bytes(), canvas.visual_digest()
    del canvas
    provenance = Provenance(
        document_id=document.id,
        revision=document.revision,
        snapshot_digest=snapshot_digest(document),
        schema_version=document.schema_version,
        seed=document.seed,
        profile=profile,
        frame_id=frame_id,
        renderer_version=RENDERER_VERSION,
        renderer_backend=RENDERER_BACKEND,
        estimator_version=estimate.estimator_version,
        rng_version=RNG_VERSION,
    )
    return RenderResult(
        width=dimensions.width,
        height=dimensions.height,
        rgba=rgba,
        digest=digest,
        warnings=tuple(warnings),
        renderer_version=RENDERER_VERSION,
        provenance=provenance,
    )
