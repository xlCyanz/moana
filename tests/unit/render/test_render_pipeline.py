"""Render orchestrator: hand scenes, errors, budgets, cancellation (MOANA-010, ADR-018).

Expected pixels are computed by hand from MOANART.md sections 6 and 11; digests are
recomputed here from section 14 with ``hashlib``, never copied from a render.
"""

from __future__ import annotations

import builtins
import hashlib
import io
import os
import pathlib
import tracemalloc
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import moanart
from moanart.core.budget import Deadline, RenderLimits
from moanart.core.errors import (
    BudgetExceeded,
    OutOfBoundsError,
    ReferenceError,
    UnsupportedOperation,
    ValidationError,
)
from moanart.core.limits import GeometryLimits
from moanart.core.procedural import RNG_VERSION
from moanart.render import (
    RENDERABLE_OPERATION_TYPES,
    RENDERER_VERSION,
    Provenance,
    RenderResult,
    RenderWarning,
    plan_budget,
    render,
)
from moanart.render import pipeline as pipeline_module
from moanart.schema import (
    SUPPORTED_OPERATION_TYPES,
    Document,
    canonical_json,
    snapshot_digest,
    validate_document,
)

RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)


def document(
    width: int,
    height: int,
    layers: list[dict[str, Any]],
    *,
    colors: dict[str, str] | None = None,
    profile: str = "rgba",
    seed: int = 0,
) -> Document:
    palette = colors or {"ink": "#000000FF"}
    return validate_document(
        {
            "schema_version": "1.0",
            "id": "doc",
            "seed": seed,
            "canvas": {"width": width, "height": height, "profile": profile},
            "palette": {
                "id": "pal",
                "colors": [{"id": key, "rgba": value} for key, value in palette.items()],
            },
            "layers": layers,
        }
    )


def layer(layer_id: str, operations: list[dict[str, Any]], **fields: Any) -> dict[str, Any]:
    return {"id": layer_id, "name": layer_id.title(), "operations": operations, **fields}


def hand_digest(width: int, height: int, pixels: dict[tuple[int, int], RGBA]) -> str:
    rows = bytearray()
    for y in range(height):
        for x in range(width):
            rows.extend(pixels.get((x, y), CLEAR))
    data = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes(rows)
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --- Hand scenes ---------------------------------------------------------------------


SEMI = document(
    4,
    3,
    [
        layer("under", [{"id": "wash", "type": "rect", "box": [0, 0, 2, 2], "color": "red"}]),
        layer("over", [{"id": "dot", "type": "pixel", "at": [1, 1], "color": "blue"}], opacity=128),
    ],
    colors={"red": "#FF000080", "blue": "#0000FFFF"},
)


def test_semitransparent_scene_matches_hand_computation() -> None:
    result = render(SEMI)
    # Red a=128 over transparent stays (255, 0, 0, 128).
    # Blue at opacity 128: sa=round(255*128/255)=128, D=128*255+128*127=48896,
    # a=round(48896/255)=192, R=round(255*128*127/48896)=85, B=round(255*128*255/48896)=170.
    expected = {(0, 0): (255, 0, 0, 128), (1, 0): (255, 0, 0, 128), (0, 1): (255, 0, 0, 128)}
    expected[(1, 1)] = (85, 0, 170, 192)
    for y in range(3):
        for x in range(4):
            assert result.pixel(x, y) == expected.get((x, y), CLEAR)
    assert result.digest == hand_digest(4, 3, expected)
    assert (result.width, result.height, len(result.rgba)) == (4, 3, 48)


def test_every_primitive_in_a_strict_scene() -> None:
    ink, gold = (16, 32, 48, 255), (250, 200, 0, 255)
    doc = document(
        6,
        5,
        [
            layer(
                "shapes",
                [
                    {"id": "row", "type": "line", "start": [5, 0], "end": [0, 0], "color": "ink"},
                    {"id": "dot", "type": "pixel", "at": [0, 4], "color": "gold"},
                    {"id": "box", "type": "rect", "box": [4, 3, 6, 5], "color": "gold"},
                    {"id": "oval", "type": "ellipse", "box": [1, 1, 4, 4], "color": "ink"},
                    {
                        "id": "tri",
                        "type": "polygon",
                        "points": [[4, 1], [6, 1], [6, 3]],
                        "color": "gold",
                    },
                ],
            )
        ],
        colors={"ink": "#102030FF", "gold": "#FAC800FF"},
        profile="strict",
    )
    expected: dict[tuple[int, int], RGBA] = {(x, 0): ink for x in range(6)}
    expected[(0, 4)] = gold
    expected.update({(x, y): gold for x in (4, 5) for y in (3, 4)})
    # Ellipse box [1,1,4,4): w=h=3, A=2x-4, B=2y-4 in {-2,0,2}; A^2*9+B^2*9 <= 81 holds
    # even at the corners (72 <= 81), so the whole 3x3 block is inside.
    expected.update({(x, y): ink for x in (1, 2, 3) for y in (1, 2, 3)})
    # Triangle (4,1)-(6,1)-(6,3), even-odd by centres: row y=1 (py=1.5) crosses x=6 and
    # x=4.5, so centres 4.5 and 5.5 have one crossing strictly to their right; row y=2
    # (py=2.5) crosses x=6 and x=5.5, so only centre 5.5 does.
    expected.update({(4, 1): gold, (5, 1): gold, (5, 2): gold})
    result = render(doc)
    assert {
        (x, y): result.pixel(x, y) for y in range(5) for x in range(6) if result.pixel(x, y)[3]
    } == expected
    assert result.digest == hand_digest(6, 5, expected)


def test_minimal_example_document() -> None:
    source = pathlib.Path(__file__).resolve().parents[3] / "examples/specs/minimal.moanart.json"
    doc = validate_document(source.read_bytes())
    result = render(doc)
    cloth = (0x36, 0xAF, 0xA5, 0xFF)
    expected = {(x, y): cloth for x in range(40, 88) for y in range(32, 104)}
    assert result.digest == hand_digest(128, 128, expected)
    assert result.provenance == Provenance(
        document_id="sprite_demo",
        revision=0,
        snapshot_digest=snapshot_digest(doc),
        schema_version="1.0",
        seed=42,
        profile="strict",
        frame_id=None,
        renderer_version=RENDERER_VERSION,
        renderer_backend="integer",
        estimator_version="budget-v8",
        rng_version=RNG_VERSION,
    )
    assert result.provenance.moanart_version == moanart.__version__
    assert result.warnings == ()


def test_hidden_layers_and_zero_opacity_draw_nothing() -> None:
    rect = {"type": "rect", "box": [0, 0, 2, 2], "color": "ink"}
    doc = document(
        2,
        2,
        [
            layer("a", [{"id": "r1", **rect}], visible=False),
            layer("b", [{"id": "r2", **rect}], opacity=0),
        ],
    )
    assert render(doc).rgba == bytes(16)


def test_locked_layers_render_like_unlocked_ones() -> None:
    rect = [{"id": "r", "type": "rect", "box": [0, 0, 2, 1], "color": "ink"}]
    locked = render(document(3, 2, [layer("a", rect, locked=True)]))
    assert locked.rgba == render(document(3, 2, [layer("a", rect)])).rgba


# --- AC1 / AC2 in process ------------------------------------------------------------


def test_ac1_repeated_renders_are_identical() -> None:
    first, second = render(SEMI), render(SEMI)
    assert first == second
    assert first.rgba == second.rgba and first.digest == second.digest


def test_ac2_render_does_not_modify_the_document() -> None:
    before = canonical_json(SEMI)
    render(SEMI)
    assert canonical_json(SEMI) == before
    assert SEMI.layers[1].opacity == 128


def test_ac2_render_writes_and_reads_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("render touched the file system")

    for target, name in (
        (builtins, "open"),
        (io, "open"),
        (os, "open"),
        (os, "remove"),
        (os, "replace"),
        (pathlib.Path, "open"),
        (pathlib.Path, "write_bytes"),
        (pathlib.Path, "write_text"),
        (pathlib.Path, "read_bytes"),
    ):
        monkeypatch.setattr(target, name, forbidden)
    assert render(SEMI).pixel(1, 1) == (85, 0, 170, 192)


def test_ac2_adding_an_operation_only_changes_its_own_pixels() -> None:
    base_layers = [layer("a", [{"id": "r", "type": "rect", "box": [0, 0, 5, 5], "color": "ink"}])]
    added = [
        *base_layers,
        layer("b", [{"id": "p", "type": "pixel", "at": [2, 3], "color": "gold"}]),
    ]
    colors = {"ink": "#10203080", "gold": "#FAC800FF"}
    before = render(document(5, 5, base_layers, colors=colors)).rgba
    after = render(document(5, 5, added, colors=colors)).rgba
    changed = {(i // 4 % 5, i // 20) for i in range(len(before)) if before[i] != after[i]}
    assert changed == {(2, 3)}


# --- T2: unsupported inputs, invalid references, cancellation, budgets ---------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limits": "default"},
        {"deadline": 5},
        {"frame_id": 3},
    ],
)
def test_t2_unsupported_arguments_are_type_errors(kwargs: dict[str, Any]) -> None:
    with pytest.raises(TypeError):
        render(SEMI, **kwargs)


def test_t2_only_documents_are_rendered() -> None:
    with pytest.raises(TypeError):
        render(canonical_json(SEMI))  # type: ignore[arg-type]  # bytes are not a Document
    with pytest.raises(TypeError):
        render({"schema_version": "1.0"})  # type: ignore[arg-type]  # nor is a mapping


def test_t2_unknown_frame_is_a_reference_error() -> None:
    with pytest.raises(ReferenceError) as excinfo:
        render(SEMI, frame_id="walk_0")
    assert excinfo.value.json_pointer is None  # a request parameter, not a document member
    assert dict(excinfo.value.context) == {"field": "frame_id", "reason": "unknown_frame"}
    invalid = _unchecked(_tree([{"id": "p", "type": "pixel", "at": [0, 0], "color": "missing"}]))
    with pytest.raises(ReferenceError) as order:  # the document is validated first
        render(invalid, frame_id="walk_0")
    assert order.value.json_pointer == "/layers/0/operations/0/color"


def _unchecked(tree: dict[str, Any]) -> Document:
    """A model built without validate_document: structure only, no semantics."""
    return Document.model_validate(tree)


def _tree(operations: list[dict[str, Any]], **layer_fields: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": 4, "height": 4, "profile": "rgba"},
        "palette": {"id": "pal", "colors": [{"id": "ink", "rgba": "#000000FF"}]},
        "layers": [{"id": "l", "name": "L", "operations": operations, **layer_fields}],
    }


def test_t2_invalid_references_are_rejected_with_pointers() -> None:
    doc = _unchecked(_tree([{"id": "p", "type": "pixel", "at": [0, 0], "color": "missing"}]))
    with pytest.raises(ReferenceError) as excinfo:
        render(doc)
    assert excinfo.value.json_pointer == "/layers/0/operations/0/color"
    duplicate = _unchecked(_tree([{"id": "l", "type": "pixel", "at": [0, 0], "color": "ink"}]))
    with pytest.raises(ValidationError) as invalid:
        render(duplicate)
    assert invalid.value.details[0].context["reason"] == "duplicate_id"
    strict = _tree([], opacity=7)
    strict["canvas"]["profile"] = "strict"
    with pytest.raises(ValidationError):
        render(_unchecked(strict))


def test_t2_operation_without_rasteriser_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    assert set(RENDERABLE_OPERATION_TYPES) == set(SUPPORTED_OPERATION_TYPES)
    monkeypatch.setattr(pipeline_module, "RENDERABLE_OPERATION_TYPES", ("pixel", "rect"))
    doc = document(
        4, 4, [layer("l", [{"id": "e", "type": "ellipse", "box": [0, 0, 2, 2], "color": "ink"}])]
    )
    with pytest.raises(UnsupportedOperation) as excinfo:
        render(doc)
    assert excinfo.value.json_pointer == "/layers/0/operations/0/type"


class _Spy:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[str] = []
        original = pipeline_module._rasterize

        def spy(operation: Any, dimensions: Any) -> Any:
            self.calls.append(operation.id)
            return original(operation, dimensions)

        monkeypatch.setattr(pipeline_module, "_rasterize", spy)


def test_t2_cancellation_between_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _Spy(monkeypatch)
    pixels = [{"id": f"p{i}", "type": "pixel", "at": [i, 0], "color": "ink"} for i in range(4)]
    doc = document(4, 1, [layer("l", pixels)])

    class Countdown(Deadline):
        """Expires at the third composition fill check."""

        def __init__(self) -> None:
            super().__init__(1000)
            self.fills = 0

        def checkpoint(self, stage: str) -> None:
            if stage == "compose_fill":
                self.fills += 1
                if self.fills == 3:
                    raise BudgetExceeded("expired", context={"resource": "time", "stage": stage})

    with pytest.raises(BudgetExceeded) as excinfo:
        render(doc, deadline=Countdown())
    assert excinfo.value.context["stage"] == "compose_fill"
    assert spy.calls == ["p0", "p1"]  # stopped between the second and third operation


def test_t2_expired_deadline_stops_before_any_raster(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _Spy(monkeypatch)
    ticks = iter([0.0] + [5.0] * 100)
    with pytest.raises(BudgetExceeded) as excinfo:
        render(SEMI, deadline=Deadline(1, clock=lambda: next(ticks)))
    assert excinfo.value.context["resource"] == "time"
    assert spy.calls == []


def test_t2_budgets_are_checked_before_any_raster_or_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = _Spy(monkeypatch)

    def no_compose(*args: object, **kwargs: object) -> None:
        raise AssertionError("composition started over budget")

    monkeypatch.setattr(pipeline_module, "compose", no_compose)
    estimate = plan_budget(SEMI)
    for limits in (
        RenderLimits(max_pixel_visits=estimate.pixel_visits - 1),
        RenderLimits(max_buffer_bytes=estimate.buffer_bytes - 1),
        RenderLimits(max_operations=1),
        RenderLimits(max_layers=1),
        RenderLimits(geometry=GeometryLimits(max_dimension=3)),
    ):
        with pytest.raises(BudgetExceeded):
            render(SEMI, limits=limits)
    assert spy.calls == []
    with pytest.raises(AssertionError, match="composition started"):
        render(SEMI, limits=RenderLimits(max_pixel_visits=estimate.pixel_visits))


def test_hidden_layers_are_never_rasterised(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _Spy(monkeypatch)
    rect = {"type": "rect", "box": [0, 0, 2, 2], "color": "ink"}
    doc = document(
        2,
        2,
        [layer("a", [{"id": "hid", **rect}], visible=False), layer("b", [{"id": "vis", **rect}])],
    )
    render(doc)
    assert spy.calls == ["vis"]


def test_masks_are_built_one_at_a_time_within_the_budget() -> None:
    """Peak memory stays under budget-v2 although every line mask is A bytes."""
    lines = [
        {
            "id": f"d{i}",
            "type": "line",
            "start": [0, i % 7],
            "end": [255, 255 - i % 7],
            "color": "ink",
        }
        for i in range(100)
    ]
    doc = document(256, 256, [layer("l", lines)], colors={"ink": "#10203080"})
    estimate = plan_budget(doc)
    tracemalloc.start()
    try:
        result = render(doc)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    retained_masks = 100 * 256 * 256  # what holding every mask at once would cost
    assert peak <= estimate.buffer_bytes < retained_masks
    assert result.pixel(0, 0)[3] > 0


def test_operations_with_empty_clipped_bounds_produce_located_warnings() -> None:
    doc = document(
        4,
        4,
        [
            layer("a", [{"id": "in", "type": "pixel", "at": [1, 1], "color": "ink"}]),
            layer(
                "b",
                [
                    {"id": "far", "type": "rect", "box": [10, 10, 12, 12], "color": "ink"},
                    {
                        "id": "flat",
                        "type": "polygon",
                        "points": [[0, 0], [2, 0], [3, 0]],
                        "color": "ink",
                    },
                ],
                visible=False,
            ),
        ],
    )
    result = render(doc)
    assert result.warnings == (
        RenderWarning(
            "empty_bounds",
            "operation bounds are empty once clipped to the canvas",
            "/layers/1/operations/0",
        ),
        RenderWarning(
            "empty_bounds",
            "operation bounds are empty once clipped to the canvas",
            "/layers/1/operations/1",
        ),
    )


# --- RenderResult --------------------------------------------------------------------


def test_result_is_immutable_and_hands_out_copies() -> None:
    result = render(SEMI)
    with pytest.raises(AttributeError):
        result.width = 9  # type: ignore[misc]  # frozen on purpose
    assert type(result.rgba) is bytes  # immutable buffer, no NumPy object exposed
    assert result.pixel(0, 0) == (255, 0, 0, 128)
    with pytest.raises(OutOfBoundsError):
        result.pixel(4, 0)
    with pytest.raises(OutOfBoundsError):
        result.pixel(0, -1)


def test_result_constructor_rejects_inconsistent_values() -> None:
    good = render(SEMI)
    fields: dict[str, Any] = {
        "width": good.width,
        "height": good.height,
        "rgba": good.rgba,
        "digest": good.digest,
        "warnings": good.warnings,
        "renderer_version": good.renderer_version,
        "provenance": good.provenance,
    }
    assert RenderResult(**fields) == good
    for change, error in (
        ({"rgba": good.rgba[:-4]}, ValueError),
        ({"rgba": bytearray(good.rgba)}, TypeError),
        ({"digest": "sha256:" + "0" * 64}, ValueError),
        ({"warnings": [RenderWarning("c", "m", "/")]}, TypeError),
        ({"provenance": good.provenance.to_mapping()}, TypeError),
        ({"renderer_version": "render-v0"}, ValueError),
        ({"width": 0}, ValidationError),
    ):
        with pytest.raises(error):
            RenderResult(**{**fields, **change})


def test_provenance_manifest_has_sorted_keys_and_no_paths_or_times() -> None:
    manifest = render(SEMI).provenance.to_mapping()
    assert list(manifest) == sorted(manifest)
    assert not any("path" in key or "time" in key for key in manifest)
    assert manifest["snapshot_digest"] == snapshot_digest(SEMI)


def test_seed_and_revision_change_identity_but_not_pixels() -> None:
    first = render(document(3, 3, [], seed=1))
    second = render(document(3, 3, [], seed=2))
    assert first.digest == second.digest == hand_digest(3, 3, {})
    assert first.rgba == bytes(36)
    assert first.provenance.snapshot_digest != second.provenance.snapshot_digest


# --- Edge cases (graphics review) ----------------------------------------------------


def test_one_by_one_canvas() -> None:
    doc = document(1, 1, [layer("l", [{"id": "p", "type": "pixel", "at": [0, 0], "color": "ink"}])])
    result = render(doc)
    assert result.rgba == bytes([0, 0, 0, 255])
    assert result.digest == hand_digest(1, 1, {(0, 0): (0, 0, 0, 255)})


def test_negative_coordinates_are_clipped_by_hand() -> None:
    ink = (1, 2, 3, 255)
    doc = document(
        4,
        3,
        [
            layer(
                "l",
                [
                    {"id": "r", "type": "rect", "box": [-5, -5, 1, 2], "color": "ink"},
                    {"id": "d", "type": "line", "start": [5, -1], "end": [-2, 2], "color": "ink"},
                ],
            )
        ],
        colors={"ink": "#010203FF"},
    )
    # Rect [-5,-5,1,2) clipped to the canvas: (0,0) and (0,1).
    # Line ordered from (-2,2) to (5,-1): dx=7, dy=-3, err=4. Steps (e2 = 2*err):
    # (-2,2) e2=8 x+1 | (-1,2) e2=2 x+1,y-1 | (0,1) e2=10 x+1 | (1,1) e2=4 x+1,y-1 |
    # (2,0) e2=12 x+1 | (3,0) e2=6 x+1,y-1 | (4,-1) | (5,-1). On the 4x3 canvas only
    # (0,1), (1,1), (2,0) and (3,0) remain.
    expected = {(0, 0): ink, (0, 1): ink, (1, 1): ink, (2, 0): ink, (3, 0): ink}
    result = render(doc)
    assert result.digest == hand_digest(4, 3, expected)


@settings(max_examples=40, deadline=None)
@given(
    width=st.integers(1, 6),
    height=st.integers(1, 6),
    box=st.tuples(st.integers(-3, 6), st.integers(-3, 6), st.integers(1, 5), st.integers(1, 5)),
    kind=st.sampled_from(["rect", "ellipse", "line", "pixel", "polygon"]),
)
def test_plan_budget_admission_means_render_succeeds(
    width: int, height: int, box: tuple[int, int, int, int], kind: str
) -> None:
    """With limits exactly at the plan, the compositor's own check never rejects."""
    x, y, w, h = box
    shapes: dict[str, dict[str, Any]] = {
        "rect": {"box": [x, y, x + w, y + h]},
        "ellipse": {"box": [x, y, x + w, y + h]},
        "line": {"start": [x, y], "end": [x + w, y - h]},
        "pixel": {"at": [x, y]},
        "polygon": {"points": [[x, y], [x + w, y], [x, y + h]]},
    }
    operation = {"id": "op", "type": kind, "color": "ink", **shapes[kind]}
    doc = document(width, height, [layer("l", [operation])], colors={"ink": "#10203080"})
    estimate = plan_budget(doc)
    exact = RenderLimits(
        max_pixel_visits=estimate.pixel_visits,
        max_buffer_bytes=estimate.buffer_bytes,
        max_frame_pixels=estimate.frame_pixels,
        max_operations=1,
        max_layers=1,
    )
    assert render(doc, limits=exact).width == width
