"""Deterministic render orchestrator (MOANA.md sections 3, 13, 14 and 20, ADR-018).

``render`` runs the mandatory flow of section 3 on one schema 1.0 document:

1. **Validation**: the canonical tree of the document is validated again with
   :func:`moana.schema.validate_document`, so a model built without that entry point
   still gets ID uniqueness, colour references and profile rules. The frame must be
   ``None`` (schema 1.0 has no animations).
2. **Resolution**: the schema palette becomes a :class:`moana.palette.Palette` and
   every operation colour is resolved to its ``Rgba``; an operation type without a
   registered rasteriser is ``UNSUPPORTED_OPERATION``, and so is a document with a
   ``path`` (operation or mask leaf) when the ``aggdraw-v1`` backend is missing or
   untested (ADR-023), before any budget or raster. Mask and region references
   were already resolved as a DAG by validation: unknown references and cycles fail
   there, before anything is rasterised (ADR-022).
3. **Budget**: :func:`moana.render.budget.plan_budget` rejects the request before any
   pixel buffer exists.
4. **Plan**: a :class:`moana.layers.LayerTree` whose fills are deferred masks with
   their declared boxes; a layer with ``mask_id`` gets the mask expression as
   :class:`moana.layers.MaskShape` leaves (deferred too) and
   :class:`moana.layers.MaskCombination` nodes, one object per document mask, so
   shared masks stay shared. Nothing is rasterised yet.
5. **Raster and composition**: :func:`moana.layers.compose` builds one mask at a time,
   in array order, between deadline checks.

A ``dither`` operation (ADR-025) becomes two deferred fills, colour A then colour B,
both declared over the result box of its mask ``mask_id``. Each one evaluates that
mask with :func:`moana.layers.evaluate_mask` and keeps its part with
:func:`moana.techniques.dither_mask`; the parts are disjoint, so their order never
changes a pixel, and nothing outside the mask is painted.

An ``outline`` operation (ADR-027) becomes one deferred fill declared over the
outline box of its mask (:func:`moana.render.budget.outline_box`): it evaluates the
mask and keeps :func:`moana.techniques.outline_mask` of it.

A ``shade`` operation (ADR-028) becomes one deferred fill per band, in band order,
declared over the box of the band mask and painted with
``ramp[band_index(...)]`` (:func:`moana.techniques.band_index`: the clamped ramp
index of the band facing under the light). Each fill evaluates its band mask and
subtracts every later band mask whose box meets it
(:func:`moana.render.budget.shade_later`, :func:`moana.techniques.last_wins`), so
overlaps take the last listed band and the parts are disjoint. With
``ramp_order: "monotonic"`` every luminance-order finding of the ramp
(:meth:`moana.palette.Palette.ramp_warnings`) becomes a render warning located at
the operation's ``ramp``; ``stylized`` keeps only the transparency findings.

A document with paths records the backend and the AggDraw and Pillow versions in
its :class:`Provenance` (``vector_backend``, ``vector_backend_versions``); others leave
them empty. Order comes only from document arrays: no sets, ``hash()``, clock, locale, global
state or concurrency decide pixels. The document is never modified and nothing is
read from or written to disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Final, assert_never

from moana.core.budget import DEFAULT_RENDER_LIMITS, Deadline, RenderLimits
from moana.core.coordinates import Box, Dimensions, Point, combined_box
from moana.core.errors import ReferenceError, UnsupportedOperation
from moana.core.procedural import RNG_VERSION
from moana.geometry import (
    Mask,
    PathBackend,
    backend_unavailable_error,
    path_backend,
    rasterize_ellipse,
    rasterize_line,
    rasterize_path,
    rasterize_pixel,
    rasterize_polygon,
    rasterize_rect,
)
from moana.layers import (
    DeferredMask,
    Fill,
    Layer,
    LayerTree,
    MaskCombination,
    MaskNode,
    MaskShape,
    compose,
    evaluate_mask,
)
from moana.palette import RAMP_LUMINANCE_NOT_INCREASING, Palette
from moana.render.budget import (
    CostEstimate,
    MaskEstimate,
    mask_box,
    mask_estimates,
    outline_box,
    plan_budget,
    shade_later,
)
from moana.render.result import (
    RENDERER_BACKEND,
    RENDERER_VERSION,
    Provenance,
    RenderResult,
    RenderWarning,
)
from moana.schema import (
    CombinationMask,
    DitherOperation,
    Document,
    EllipseMask,
    EllipseOperation,
    LineMask,
    LineOperation,
    Operation,
    OutlineOperation,
    PathMask,
    PathOperation,
    PixelMask,
    PixelOperation,
    PolygonMask,
    PolygonOperation,
    RectMask,
    RectOperation,
    ShadeOperation,
    ShapeMask,
    ShapeOperation,
    normalize_document,
    snapshot_digest,
    validate_document,
)
from moana.schema import Layer as DocumentLayer
from moana.schema import MaskNode as DocumentMask
from moana.techniques import (
    DitherPart,
    OrderedDither,
    ShadeLight,
    band_index,
    dither_mask,
    last_wins,
    outline_mask,
)

__all__ = ["RENDERABLE_OPERATION_TYPES", "render"]

RENDERABLE_OPERATION_TYPES: Final = (
    "pixel",
    "line",
    "rect",
    "ellipse",
    "polygon",
    "path",
    "dither",
    "outline",
    "shade",
)
"""Operation types with a registered rasteriser, in registration order."""

EMPTY_BOUNDS: Final = "empty_bounds"
"""Warning: the operation's bounds clipped to the canvas are empty (nothing to draw)."""
STYLIZED_RAMP_CODES: Final = frozenset({RAMP_LUMINANCE_NOT_INCREASING})
"""Ramp findings that ``ramp_order: "stylized"`` documents as intended (ADR-028)."""


def _rasterize(operation: ShapeOperation | ShapeMask, dimensions: Dimensions) -> Mask:
    """Mask of one operation or mask leaf clipped to the canvas (the rasteriser registry)."""
    match operation:
        case PixelOperation() | PixelMask():
            return rasterize_pixel(operation.point, dimensions)
        case LineOperation() | LineMask():
            return rasterize_line(Point(*operation.start), Point(*operation.end), dimensions)
        case RectOperation() | RectMask():
            return rasterize_rect(operation.bbox, dimensions)
        case EllipseOperation() | EllipseMask():
            return rasterize_ellipse(operation.bbox, dimensions)
        case PolygonOperation() | PolygonMask():
            return rasterize_polygon([Point(*point) for point in operation.points], dimensions)
        case PathOperation() | PathMask():
            return rasterize_path(operation.path, dimensions)
        case _:  # pragma: no cover - a new operation type must register its rasteriser
            assert_never(operation)


def _dither_part(
    operation: DitherOperation,
    mask: MaskNode,
    dimensions: Dimensions,
    deadline: Deadline | None,
    part: DitherPart,
) -> Mask:
    """Pixels of the clipping mask that ``operation`` paints with colour ``part``."""
    dither = OrderedDither(operation.size, operation.coverage, operation.anchor)
    return dither_mask(evaluate_mask(mask, dimensions, deadline=deadline), dither, part)


def _outline(
    operation: OutlineOperation, mask: MaskNode, dimensions: Dimensions, deadline: Deadline | None
) -> Mask:
    """Pixels of the outline of the mask of ``operation``."""
    evaluated = evaluate_mask(mask, dimensions, deadline=deadline)
    return outline_mask(evaluated, operation.width, operation.side, dimensions)


def _shade_band(
    nodes: tuple[MaskNode, ...], dimensions: Dimensions, deadline: Deadline | None
) -> Mask:
    """Pixels of the first band mask of ``nodes`` that no later one covers."""
    return last_wins(evaluate_mask(node, dimensions, deadline=deadline) for node in nodes)


def _check_frame(frame_id: str | None) -> None:
    if frame_id is None:
        return
    raise ReferenceError(
        "frame does not exist: schema 1.0 documents have no animations",
        context={"field": "frame_id", "reason": "unknown_frame"},
    )


def _first_path(document: Document) -> str | None:
    """Pointer of the first path operation or path mask leaf, in document order."""
    for layer_index, layer in enumerate(document.layers):
        for index, operation in enumerate(layer.operations):
            if isinstance(operation, PathOperation):
                return f"/layers/{layer_index}/operations/{index}"
    for index, mask in enumerate(document.masks):
        if isinstance(mask, PathMask):
            return f"/masks/{index}"
    return None


def _check_renderable(document: Document) -> PathBackend | None:
    """Reject operations without rasteriser and paths without backend; probe it once."""
    for layer_index, layer in enumerate(document.layers):
        for index, operation in enumerate(layer.operations):
            if operation.type not in RENDERABLE_OPERATION_TYPES:
                raise UnsupportedOperation(
                    "operation type has no registered rasteriser",
                    json_pointer=f"/layers/{layer_index}/operations/{index}/type",
                    context={"reason": "no_rasterizer", "type": operation.type},
                )
    pointer = _first_path(document)
    if pointer is None:
        return None
    backend = path_backend()
    if not backend.available:
        raise backend_unavailable_error(backend, json_pointer=f"{pointer}/backend")
    return backend


def _backend_versions(backend: PathBackend | None) -> tuple[str, ...]:
    if backend is None:
        return ()
    versions = [f"aggdraw=={backend.version}"]
    if backend.pillow_version is not None:
        versions.append(f"pillow=={backend.pillow_version}")
    return tuple(versions)


def _used_masks(document: Document) -> list[str]:
    """Mask IDs that layers and ``dither``/``outline``/``shade`` operations reference."""
    used: list[str] = []
    for layer in document.layers:
        if layer.mask_id is not None:
            used.append(layer.mask_id)
        for op in layer.operations:
            if isinstance(op, DitherOperation | OutlineOperation):
                used.append(op.mask_id)
            elif isinstance(op, ShadeOperation):
                used.extend(band.mask_id for band in op.bands)
    return used


def _plan_masks(
    document: Document, dimensions: Dimensions, used: list[str] | None = None
) -> dict[str, MaskNode]:
    """Layer-tree mask nodes of every mask a layer or operation uses, keyed by mask ID.

    Built operands first (post-order over the operand arrays), one node per document
    mask; the document is valid, so the references are acyclic and resolved. ``used``
    replaces the masks to plan (by default those that layers and operations use).
    """
    masks: dict[str, DocumentMask] = {mask.id: mask for mask in document.masks}
    nodes: dict[str, MaskNode] = {}
    for mask_id in _used_masks(document) if used is None else used:
        work: list[tuple[DocumentMask, bool]] = [(masks[mask_id], False)]
        while work:
            mask, ready = work.pop()
            if mask.id in nodes:
                continue
            if not isinstance(mask, CombinationMask):
                deferred = DeferredMask(
                    mask_box(mask, dimensions), partial(_rasterize, mask, dimensions)
                )
                nodes[mask.id] = MaskShape(mask.id, deferred)
            elif ready:
                operands = tuple(nodes[name] for name in mask.masks)
                nodes[mask.id] = MaskCombination(mask.id, mask.type, operands)
            else:
                work.append((mask, True))
                work.extend((masks[name], False) for name in reversed(mask.masks))
    return nodes


@dataclass(frozen=True, slots=True)
class _Plan:
    """What every layer of one render shares while it is planned."""

    palette: Palette
    dimensions: Dimensions
    masks: dict[str, MaskNode]
    estimates: dict[str, MaskEstimate]
    deadline: Deadline | None


def _shade_fills(operation: ShadeOperation, plan: _Plan) -> tuple[Box | None, list[Fill]]:
    """One deferred fill per band, in order, over the band mask box (ADR-028)."""
    ramp = plan.palette.ramp(operation.ramp)
    spec = operation.light
    light = ShadeLight(spec.direction, spec.height, spec.intensity, spec.ambient)
    boxes = [plan.estimates[band.mask_id].box for band in operation.bands]
    fills: list[Fill] = []
    for index, band in enumerate(operation.bands):
        later = shade_later(boxes, index)
        nodes = (band.mask_id, *(operation.bands[j].mask_id for j in later))
        build = partial(
            _shade_band, tuple(plan.masks[name] for name in nodes), plan.dimensions, plan.deadline
        )
        color = ramp[band_index(band.facing, band.offset, light, len(ramp))]
        fills.append(Fill(DeferredMask(boxes[index], build), color))
    return combined_box("union", boxes, plan.dimensions), fills


def _operation_fills(operation: Operation, plan: _Plan) -> tuple[Box | None, list[Fill]]:
    """Declared box and deferred fills of one operation (two for a ``dither``)."""
    if isinstance(operation, ShadeOperation):
        return _shade_fills(operation, plan)
    if isinstance(operation, OutlineOperation):
        estimate = plan.estimates[operation.mask_id]
        box = outline_box(estimate.box, operation.width, operation.side, plan.dimensions)
        node = plan.masks[operation.mask_id]
        build = partial(_outline, operation, node, plan.dimensions, plan.deadline)
        return box, [Fill(DeferredMask(box, build), plan.palette.color(operation.color))]
    if not isinstance(operation, DitherOperation):
        box = mask_box(operation, plan.dimensions)
        mask = DeferredMask(box, partial(_rasterize, operation, plan.dimensions))
        return box, [Fill(mask, plan.palette.color(operation.color))]
    box = plan.estimates[operation.mask_id].box
    node = plan.masks[operation.mask_id]
    fills = []
    parts: tuple[tuple[DitherPart, str], ...] = (
        ("a", operation.color_a),
        ("b", operation.color_b),
    )
    for part, color_id in parts:
        build = partial(_dither_part, operation, node, plan.dimensions, plan.deadline, part)
        fills.append(Fill(DeferredMask(box, build), plan.palette.color(color_id)))
    return box, fills


def _ramp_warnings(
    operation: ShadeOperation, palette: Palette, pointer: str
) -> list[RenderWarning]:
    """Findings of the shade's ramp; ``stylized`` drops the luminance-order ones."""
    stylized = operation.ramp_order == "stylized"
    return [
        RenderWarning(warning.code, f"{warning.message} ({warning.color_id})", pointer)
        for warning in palette.ramp_warnings(operation.ramp)
        if not (stylized and warning.code in STYLIZED_RAMP_CODES)
    ]


def _plan_layer(
    layer: DocumentLayer, layer_index: int, plan: _Plan, warnings: list[RenderWarning]
) -> Layer:
    fills: list[Fill] = []
    for index, operation in enumerate(layer.operations):
        box, operation_fills = _operation_fills(operation, plan)
        if isinstance(operation, ShadeOperation):
            pointer = f"/layers/{layer_index}/operations/{index}/ramp"
            warnings.extend(_ramp_warnings(operation, plan.palette, pointer))
        if box is None:
            warnings.append(
                RenderWarning(
                    EMPTY_BOUNDS,
                    "operation bounds are empty once clipped to the canvas",
                    f"/layers/{layer_index}/operations/{index}",
                )
            )
        fills.extend(operation_fills)
    return Layer(
        layer.id,
        layer.name,
        tuple(fills),
        visible=layer.visible,
        locked=layer.locked,
        opacity=layer.opacity,
        blend=layer.blend,
        mask=None if layer.mask_id is None else plan.masks[layer.mask_id],
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
    limits = _check_request(document, limits, deadline)
    if frame_id is not None and type(frame_id) is not str:
        raise TypeError("frame_id must be a str or None")
    document = validate_document(normalize_document(document))
    _check_frame(frame_id)
    backend = _check_renderable(document)
    estimate = plan_budget(document, limits, deadline=deadline)
    return _render_validated(document, frame_id, limits, deadline, backend, estimate)


def _check_request(document: object, limits: object, deadline: object) -> RenderLimits:
    """Type checks shared by the render entry points; ``None`` limits are the defaults."""
    if not isinstance(document, Document):
        raise TypeError("document must be a moana.schema.Document")
    if limits is None:
        limits = DEFAULT_RENDER_LIMITS
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    if deadline is not None and not isinstance(deadline, Deadline):
        raise TypeError("deadline must be a Deadline or None")
    return limits


def _render_validated(
    document: Document,
    frame_id: str | None,
    limits: RenderLimits,
    deadline: Deadline | None,
    backend: PathBackend | None,
    estimate: CostEstimate,
) -> RenderResult:
    """Plan, compose and describe a validated document already admitted by ``estimate``."""
    profile = document.canvas.profile
    palette = Palette.from_mapping(document.palette.model_dump(mode="json"), profile=profile)
    dimensions = document.canvas.dimensions
    warnings: list[RenderWarning] = []
    layers: list[Layer] = []
    masks = _plan_masks(document, dimensions)
    plan = _Plan(palette, dimensions, masks, mask_estimates(document), deadline)
    for layer_index, layer in enumerate(document.layers):
        if deadline is not None:
            deadline.checkpoint("plan_layer")
        layers.append(_plan_layer(layer, layer_index, plan, warnings))
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
        vector_backend=None if backend is None else backend.name,
        vector_backend_versions=_backend_versions(backend),
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
