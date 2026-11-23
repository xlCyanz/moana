"""Read-only reports: what a document contains and what this build can do (ADR-020).

:func:`inspect_document` summarises a validated document and its budget estimate
without rendering: a request over budget is reported (``within_limits`` false and the
exceeded resources), not raised, so a caller can see why ``render`` would refuse it.
:func:`capabilities` lists the implemented vocabulary and, separately, what is only
planned, so help and agents never present a future capability as available. ``path``
(operation and mask leaf) is available only when the ``aggdraw-v1`` backend imports
with a tested version; otherwise it is listed as planned and ``backends`` says why
(ADR-023).
Semantic masks and regions (ADR-022) are listed with their references, so an agent can
find "the left eye" by ID; :func:`moanart.schema.resolve_region` resolves one.
``edit_commands`` lists the edit catalogue of section 15 (ADR-024) plus
``set_parameters`` (ADR-030); ``material`` and ``selective_outline`` are available
operations (ADR-030).
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from operator import attrgetter
from typing import TYPE_CHECKING, Final

from moanart.core.budget import DEFAULT_RENDER_LIMITS, RenderLimits
from moanart.core.errors import BudgetExceeded
from moanart.editing import COMMAND_TYPES
from moanart.export import CodecStatus, export_capabilities
from moanart.geometry import TESTED_AGGDRAW_VERSIONS, path_backend
from moanart.render import (
    ESTIMATOR_VERSION,
    RENDERABLE_OPERATION_TYPES,
    RENDERER_VERSION,
    estimate_cost,
    plan_budget,
)
from moanart.schema import (
    OPERATION_MEMBERS,
    PLANNED_BLEND_MODES,
    PLANNED_COLLECTIONS,
    PLANNED_LAYER_FIELDS,
    PLANNED_MASK_TYPES,
    PLANNED_OPERATION_TYPES,
    SUPPORTED_BLEND_MODES,
    SUPPORTED_COLLECTIONS,
    SUPPORTED_MASK_TYPES,
    SUPPORTED_OPERATION_TYPES,
    SUPPORTED_PROFILES,
    SUPPORTED_SCHEMA_VERSIONS,
    CombinationMask,
    Document,
    Operation,
    snapshot_digest,
)

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

__all__ = [
    "AVAILABLE_FUNCTIONS",
    "PLANNED_FUNCTIONS",
    "BackendSummary",
    "BudgetReport",
    "Capabilities",
    "DocumentReport",
    "ExceededResource",
    "LayerSummary",
    "MaskSummary",
    "OperationSummary",
    "RegionSummary",
    "capabilities",
    "inspect_document",
]

AVAILABLE_FUNCTIONS: Final = (
    "analyze_clusters",
    "apply_edit",
    "capabilities",
    "edit_document",
    "evaluate_quality",
    "export_png",
    "inspect_document",
    "load_document",
    "load_edit_batch",
    "render",
    "resolve_region",
)
"""Functions of ``moanart.api`` that work in this build."""
PLANNED_FUNCTIONS: Final[tuple[str, ...]] = ()
"""Functions of MOANART.md section 13 that are specified but not implemented (none
since MOANA-018 added ``apply_edit``, ADR-024)."""
_PATH_CAPABILITIES: Final = frozenset({"path"})
"""Operation and mask types that need the ``aggdraw-v1`` backend (ADR-023)."""


def _json(value: object) -> object:
    """JSON-ready form: dataclasses become sorted mappings and tuples become lists."""
    if isinstance(value, tuple):
        return [_json(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _fields(value)
    return value


def _fields(value: DataclassInstance) -> dict[str, object]:
    ordered = sorted(fields(value), key=attrgetter("name"))
    return {field.name: _json(getattr(value, field.name)) for field in ordered}


@dataclass(frozen=True, slots=True)
class OperationSummary:
    """One operation: its ID, type and colour reference (colour A of a ``dither``).

    ``color`` is ``None`` for an operation without a colour member: a ``shade``
    (ADR-028) takes its colours from a ramp by index.
    """

    id: str
    type: str
    color: str | None


@dataclass(frozen=True, slots=True)
class LayerSummary:
    """One layer and its operations, in document order."""

    id: str
    name: str
    visible: bool
    locked: bool
    opacity: int
    blend: str
    operations: tuple[OperationSummary, ...]
    mask_id: str | None


@dataclass(frozen=True, slots=True)
class MaskSummary:
    """One semantic mask: its ID, type and, for a combination, its operand mask IDs."""

    id: str
    type: str
    masks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegionSummary:
    """One semantic region: its ID, mask and targeted operation IDs."""

    id: str
    mask_id: str
    operation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExceededResource:
    """One budget the request would exceed, located by JSON Pointer when known."""

    resource: str
    limit: int
    estimated: int
    json_pointer: str | None


@dataclass(frozen=True, slots=True)
class BudgetReport:
    """Estimate of one render against the request limits (``budget-v8``, ADR-025 to ADR-030).

    ``operations`` counts the operations of the document and ``fills`` the raster
    fills of the compositor (two per ``dither``). An ``operations`` entry of
    ``exceeded`` compares ``fills`` with the limit: its ``estimated`` is ``fills``.
    """

    estimator_version: str
    pixel_visits: int
    buffer_bytes: int
    frame_pixels: int
    operations: int
    fills: int
    layers: int
    within_limits: bool
    exceeded: tuple[ExceededResource, ...]


@dataclass(frozen=True, slots=True)
class DocumentReport:
    """Summary of a validated document: identity, canvas, palette, layers and budget."""

    document_id: str
    revision: int
    schema_version: str
    snapshot_digest: str
    seed: int
    width: int
    height: int
    profile: str
    palette_id: str
    colors: tuple[str, ...]
    ramps: tuple[str, ...]
    layers: tuple[LayerSummary, ...]
    masks: tuple[MaskSummary, ...]
    regions: tuple[RegionSummary, ...]
    budget: BudgetReport

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready report with sorted keys."""
        return _fields(self)


@dataclass(frozen=True, slots=True)
class BackendSummary:
    """A raster backend of this build: whether it works here and with which versions.

    ``reason`` is ``None`` when available, else ``"missing"`` or ``"untested_version"``.
    """

    name: str
    available: bool
    version: str | None
    pillow_version: str | None
    reason: str | None
    tested_versions: tuple[str, ...]
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Implemented vocabulary of this build, each with its planned counterpart.

    ``export_formats`` are the formats of :func:`moanart.api.export_png` and ``moanart
    export``; ``export_codecs`` is the runtime codec matrix of ``moanart.export`` (PNG,
    GIF, APNG, WebP: availability, codec and Pillow versions), probed on each call
    (ADR-035).
    """

    schema_versions: tuple[str, ...]
    profiles: tuple[str, ...]
    operations: tuple[str, ...]
    planned_operations: tuple[str, ...]
    mask_types: tuple[str, ...]
    planned_mask_types: tuple[str, ...]
    collections: tuple[str, ...]
    blend_modes: tuple[str, ...]
    planned_blend_modes: tuple[str, ...]
    planned_collections: tuple[str, ...]
    planned_layer_fields: tuple[str, ...]
    export_formats: tuple[str, ...]
    export_codecs: tuple[CodecStatus, ...]
    functions: tuple[str, ...]
    planned_functions: tuple[str, ...]
    edit_commands: tuple[str, ...]
    renderer_version: str
    estimator_version: str
    backends: tuple[BackendSummary, ...]

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready listing with sorted keys."""
        return _fields(self)


def capabilities() -> Capabilities:
    """What this build implements and what is only planned (never both).

    An operation is available only when the schema accepts it, the renderer has a
    rasteriser for it *and* its backend works here; otherwise it is reported as
    planned. ``path`` depends on the ``aggdraw-v1`` backend, probed on each call.
    This is a *runtime* capability: the schema accepts ``path`` documents whatever
    the backend, and only rendering (or the adapter) rejects them with
    ``UNSUPPORTED_OPERATION`` when it is missing or untested.
    """
    backend = path_backend()
    missing = frozenset() if backend.available else _PATH_CAPABILITIES
    rasterisers = frozenset(RENDERABLE_OPERATION_TYPES) - missing
    renderable = SUPPORTED_OPERATION_TYPES & rasterisers
    planned = PLANNED_OPERATION_TYPES | (SUPPORTED_OPERATION_TYPES - rasterisers)
    summary = BackendSummary(
        name=backend.name,
        available=backend.available,
        version=backend.version,
        pillow_version=backend.pillow_version,
        reason=backend.reason,
        tested_versions=TESTED_AGGDRAW_VERSIONS,
        capabilities=tuple(sorted(_PATH_CAPABILITIES)),
    )
    return Capabilities(
        schema_versions=tuple(sorted(SUPPORTED_SCHEMA_VERSIONS)),
        profiles=tuple(sorted(SUPPORTED_PROFILES)),
        operations=tuple(sorted(renderable)),
        planned_operations=tuple(sorted(planned)),
        mask_types=tuple(sorted(SUPPORTED_MASK_TYPES - missing)),
        planned_mask_types=tuple(sorted(PLANNED_MASK_TYPES | (SUPPORTED_MASK_TYPES & missing))),
        collections=tuple(sorted(SUPPORTED_COLLECTIONS)),
        blend_modes=tuple(sorted(SUPPORTED_BLEND_MODES)),
        planned_blend_modes=tuple(sorted(PLANNED_BLEND_MODES)),
        planned_collections=tuple(sorted(PLANNED_COLLECTIONS)),
        planned_layer_fields=tuple(sorted(PLANNED_LAYER_FIELDS)),
        export_formats=("png",),
        export_codecs=export_capabilities().formats,
        functions=AVAILABLE_FUNCTIONS,
        planned_functions=PLANNED_FUNCTIONS,
        edit_commands=COMMAND_TYPES,
        renderer_version=RENDERER_VERSION,
        estimator_version=ESTIMATOR_VERSION,
        backends=(summary,),
    )


def _primary_color(operation: Operation) -> str | None:
    """The colour an operation summary names: ``color``, colour A of a ``dither`` or none."""
    colors = OPERATION_MEMBERS[operation.type].colors
    return str(getattr(operation, colors[0])) if colors else None


def _exceeded(error: BudgetExceeded) -> tuple[ExceededResource, ...]:
    """Typed view of the ``resource``/``limit``/``estimated`` context of each detail."""
    resources: list[ExceededResource] = []
    for detail in error.details:
        context = detail.context
        resource, limit, estimated = (
            context.get("resource"),
            context.get("limit"),
            context.get("estimated"),
        )
        if not (
            isinstance(resource, str) and isinstance(limit, int) and isinstance(estimated, int)
        ):
            raise TypeError("budget detail lacks resource, limit or estimated")
        resources.append(ExceededResource(resource, limit, estimated, detail.json_pointer))
    return tuple(resources)


def _budget(document: Document, limits: RenderLimits) -> BudgetReport:
    estimate = estimate_cost(document)
    exceeded: tuple[ExceededResource, ...] = ()
    try:
        plan_budget(document, limits)
    except BudgetExceeded as error:
        exceeded = _exceeded(error)
    return BudgetReport(
        estimator_version=estimate.estimator_version,
        pixel_visits=estimate.pixel_visits,
        buffer_bytes=estimate.buffer_bytes,
        frame_pixels=estimate.frame_pixels,
        operations=estimate.operations,
        fills=estimate.fills,
        layers=estimate.layers,
        within_limits=not exceeded,
        exceeded=exceeded,
    )


def inspect_document(document: Document, *, limits: RenderLimits | None = None) -> DocumentReport:
    """Summarise ``document`` and estimate one render against ``limits``; nothing is drawn."""
    if not isinstance(document, Document):
        raise TypeError("document must be a moanart.schema.Document")
    if limits is None:
        limits = DEFAULT_RENDER_LIMITS
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    layers = tuple(
        LayerSummary(
            id=layer.id,
            name=layer.name,
            visible=layer.visible,
            locked=layer.locked,
            opacity=layer.opacity,
            blend=layer.blend,
            operations=tuple(
                OperationSummary(operation.id, operation.type, _primary_color(operation))
                for operation in layer.operations
            ),
            mask_id=layer.mask_id,
        )
        for layer in document.layers
    )
    masks = tuple(
        MaskSummary(mask.id, mask.type, mask.masks if isinstance(mask, CombinationMask) else ())
        for mask in document.masks
    )
    regions = tuple(
        RegionSummary(region.id, region.mask_id, region.operation_ids)
        for region in document.regions
    )
    palette = document.palette
    return DocumentReport(
        document_id=document.id,
        revision=document.revision,
        schema_version=document.schema_version,
        snapshot_digest=snapshot_digest(document),
        seed=document.seed,
        width=document.canvas.width,
        height=document.canvas.height,
        profile=document.canvas.profile,
        palette_id=palette.id,
        colors=tuple(color.id for color in palette.colors),
        ramps=tuple(ramp.id for ramp in palette.ramps),
        layers=layers,
        masks=masks,
        regions=regions,
        budget=_budget(document, limits),
    )
