"""Timeline evaluation and frame rendering (MOANA-022 AC1, AC2, T1, T2; ADR-032).

The sprite is written by hand and every expected pixel comes from :func:`expected`,
a hand-written oracle of MOANA.md sections 6, 10 and 17 (half-open boxes, Bayer 2x2
``[[0, 2], [3, 1]]`` with colour B where the threshold is below ``coverage``), never
from the renderer's own output.
"""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana import api, editing, layers
from moana.animation import (
    AnimationRender,
    evaluate_animation,
    evaluate_frame,
    find_animation,
    find_frame,
    render_animation,
    render_frame,
)
from moana.animation import timeline as timeline_module
from moana.core import errors
from moana.core.budget import Deadline, RenderLimits
from moana.core.coordinates import Point
from moana.render import RenderResult, render
from moana.render import pipeline as pipeline_module
from moana.schema import (
    Document,
    ParseLimits,
    canonical_json,
    document_ids,
    snapshot_digest,
    validate_document,
)

type Tree = dict[str, Any]
type Rgba = tuple[int, int, int, int]

EXAMPLES = Path(__file__).resolve().parents[3] / "examples/specs"
RED: Rgba = (255, 0, 0, 255)
BLUE: Rgba = (0, 0, 255, 255)
GREEN: Rgba = (0, 255, 0, 255)
CLEAR: Rgba = (0, 0, 0, 0)
FRAMES = ("f0", "f1", "f2", "f3")
DURATIONS = {"f0": 100, "f1": 120, "f2": 80, "f3": 60_000}


def sprite() -> Tree:
    """8x8: a red 2x2 body, a green eye pixel and a dithered patch on top.

    Frames: ``f0`` is the base; ``f1`` moves the body right by 2; ``f2`` turns the
    body blue and hides the eye layer; ``f3`` moves the dither mask by (-2, +2).
    """
    return {
        "schema_version": "1.0",
        "id": "hero",
        "revision": 7,
        "seed": 99,
        "canvas": {"width": 8, "height": 8, "profile": "strict"},
        "palette": {
            "id": "pal",
            "colors": [
                {"id": "red", "rgba": "#FF0000FF"},
                {"id": "blue", "rgba": "#0000FFFF"},
                {"id": "green", "rgba": "#00FF00FF"},
            ],
        },
        "masks": [{"id": "patch", "type": "rect", "box": [4, 0, 8, 4]}],
        "layers": [
            {
                "id": "body",
                "name": "Body",
                "operations": [
                    {"id": "torso", "type": "rect", "color": "red", "box": [1, 1, 3, 3]}
                ],
            },
            {
                "id": "eye",
                "name": "Eye",
                "operations": [{"id": "pupil", "type": "pixel", "color": "green", "at": [6, 6]}],
            },
            {
                "id": "texture",
                "name": "Texture",
                "operations": [
                    {
                        "id": "grain",
                        "type": "dither",
                        "size": 2,
                        "coverage": 2,
                        "origin": [0, 0],
                        "color_a": "red",
                        "color_b": "blue",
                        "mask_id": "patch",
                    }
                ],
            },
            {
                "id": "frozen",
                "name": "Frozen",
                "locked": True,
                "operations": [{"id": "stud", "type": "pixel", "color": "green", "at": [0, 7]}],
            },
        ],
        "animations": [
            {
                "id": "walk",
                "loop_count": 0,
                "pivot": [4, 8],
                "frames": [
                    {"id": "f0", "duration_ms": 100},
                    {
                        "id": "f1",
                        "duration_ms": 120,
                        "overrides": [
                            {"type": "translate", "target_id": "torso", "dx": 2, "dy": 0}
                        ],
                    },
                    {
                        "id": "f2",
                        "duration_ms": 80,
                        "overrides": [
                            {"type": "set_color", "target_id": "torso", "color": "blue"},
                            {"type": "set_visibility", "target_id": "eye", "visible": False},
                        ],
                    },
                    {
                        "id": "f3",
                        "duration_ms": 60_000,
                        "overrides": [
                            {"type": "translate", "target_id": "patch", "dx": -2, "dy": 2}
                        ],
                    },
                ],
            },
            {
                "id": "blink",
                "loop_count": 3,
                "pivot": [0, 0],
                "frames": [
                    {"id": "open", "duration_ms": 1},
                    {
                        "id": "shut",
                        "duration_ms": 2,
                        "overrides": [
                            {"type": "set_visibility", "target_id": "eye", "visible": False}
                        ],
                    },
                ],
            },
        ],
    }


def expected(frame_id: str, x: int, y: int) -> Rgba:
    """Hand oracle: layers bottom to top, each frame from the base only."""
    pixel = CLEAR
    torso_x0 = 3 if frame_id == "f1" else 1
    if torso_x0 <= x < torso_x0 + 2 and 1 <= y < 3:
        pixel = BLUE if frame_id == "f2" else RED
    if (x, y) == (6, 6) and frame_id not in {"f2", "shut"}:
        pixel = GREEN
    x0, y0 = (2, 2) if frame_id == "f3" else (4, 0)
    if x0 <= x < x0 + 4 and y0 <= y < y0 + 4:
        threshold = ((0, 2), (3, 1))[y % 2][x % 2]  # origin (0, 0)
        pixel = BLUE if threshold < 2 else RED
    if (x, y) == (0, 7):
        pixel = GREEN
    return pixel


def expected_bytes(frame_id: str) -> bytes:
    return b"".join(bytes(expected(frame_id, x, y)) for y in range(8) for x in range(8))


@pytest.fixture
def document() -> Document:
    return validate_document(sprite())


@pytest.fixture
def renders(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Frame IDs actually rasterised, in order (spy on the sequence renderer)."""
    calls: list[str] = []
    original = pipeline_module._render_validated

    def spy(document: Document, frame_id: str | None, *args: Any) -> RenderResult:
        calls.append(str(frame_id))
        return original(document, frame_id, *args)

    monkeypatch.setattr("moana.render.sequence._render_validated", spy)
    return calls


@pytest.fixture
def paints(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every call that could paint: the pipeline renderer and layer composition."""
    calls: list[str] = []
    render_validated = pipeline_module._render_validated
    compose = layers.compose

    def spy_render(*args: Any) -> RenderResult:
        calls.append("render")
        return render_validated(*args)

    def spy_compose(*args: Any, **kwargs: Any) -> Any:
        calls.append("compose")
        return compose(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "_render_validated", spy_render)
    monkeypatch.setattr("moana.render.pipeline.compose", spy_compose)
    return calls


# --- AC1: evaluation order never changes a result ------------------------------------


@settings(max_examples=24, deadline=None)
@given(order=st.permutations(FRAMES))
def test_ac1_any_evaluation_order_gives_the_same_bytes_per_frame(order: list[str]) -> None:
    document = validate_document(sprite())
    rendered = render_animation(document, "walk", frame_ids=order)
    assert [frame.frame_id for frame in rendered.frames] == list(order)
    for frame in rendered.frames:
        assert frame.result.rgba == expected_bytes(frame.frame_id)
        assert frame.index == FRAMES.index(frame.frame_id)
    together = evaluate_animation(document, "walk")
    for frame_id in order:  # one at a time, in the drawn order
        alone = evaluate_frame(document, frame_id)
        assert alone == together[FRAMES.index(frame_id)]
        assert render(alone.document).rgba == expected_bytes(frame_id)


def test_ac1_frames_never_inherit_the_previous_frame(document: Document) -> None:
    rendered = render_animation(document, "walk")
    by_id = {frame.frame_id: frame.result for frame in rendered.frames}
    # f2 recolours but does not move: the f1 translate is not inherited; f3 has the
    # base red body and visible eye although f2 changed both.
    assert by_id["f2"].pixel(1, 1) == BLUE
    assert by_id["f2"].pixel(3, 1) == CLEAR
    assert by_id["f3"].pixel(1, 1) == RED
    assert by_id["f3"].pixel(6, 6) == GREEN
    for frame_id in FRAMES:
        assert by_id[frame_id].rgba == expected_bytes(frame_id)


def test_ac1_one_frame_alone_equals_the_same_frame_in_a_sequence(document: Document) -> None:
    together = {frame.frame_id: frame.result for frame in render_animation(document, "walk").frames}
    for frame_id in reversed(FRAMES):
        alone = render_frame(document, frame_id).result
        assert alone.rgba == together[frame_id].rgba
        assert alone.digest == together[frame_id].digest
        assert alone.provenance == together[frame_id].provenance
        assert (
            evaluate_frame(document, frame_id)
            == evaluate_animation(document, "walk")[FRAMES.index(frame_id)]
        )


def test_ac1_evaluating_does_not_touch_the_base(document: Document) -> None:
    before = canonical_json(document)
    render_animation(document, "walk")
    evaluate_animation(document, "blink")
    assert canonical_json(document) == before
    assert render(document).rgba == expected_bytes("f0")


# --- AC2: durations and pivots preserved; invalid override renders nothing -----------


def test_ac2_durations_pivots_and_offsets_are_preserved(document: Document) -> None:
    rendered = render_animation(document, "walk", frame_ids=["f3", "f0", "f2"])
    assert isinstance(rendered, AnimationRender)
    assert (rendered.animation_id, rendered.loop_count, rendered.pivot) == ("walk", 0, Point(4, 8))
    assert [(f.frame_id, f.duration_ms, f.start_ms, f.pivot) for f in rendered.frames] == [
        ("f3", 60_000, 300, Point(4, 8)),
        ("f0", 100, 0, Point(4, 8)),
        ("f2", 80, 220, Point(4, 8)),
    ]
    assert rendered.duration_ms == 60_000 + 100 + 80
    evaluations = evaluate_animation(document, "walk")
    assert [e.duration_ms for e in evaluations] == [DURATIONS[f] for f in FRAMES]
    assert [e.start_ms for e in evaluations] == [0, 100, 220, 300]
    assert {e.pivot for e in evaluations} == {Point(4, 8)}


def test_ac2_provenance_names_the_frame_and_keeps_the_revision(document: Document) -> None:
    for frame in render_animation(document, "walk").frames:
        provenance = frame.result.provenance
        assert provenance.frame_id == frame.frame_id
        assert provenance.revision == 7
        assert provenance.seed == 99
        assert provenance.document_id == "hero"


INVALID_OVERRIDES = [
    ({"type": "translate", "target_id": "eye", "dx": 1, "dy": 0}, "invalid_target", "target_id"),
    ({"type": "translate", "target_id": "grain", "dx": 1, "dy": 0}, "not_geometric", "target_id"),
    (
        {"type": "set_visibility", "target_id": "torso", "visible": False},
        "invalid_target",
        "target_id",
    ),
    ({"type": "set_color", "target_id": "grain", "color": "red"}, "multiple_colors", "target_id"),
    ({"type": "set_color", "target_id": "body", "color": "red"}, "invalid_target", "target_id"),
    ({"type": "translate", "target_id": "stud", "dx": 1, "dy": 0}, "locked_layer", None),
    ({"type": "translate", "target_id": "torso", "dx": 2_097_153, "dy": 0}, "out_of_range", None),
]


@pytest.mark.parametrize(("override", "reason", "member"), INVALID_OVERRIDES)
def test_ac2_an_invalid_override_in_any_frame_renders_nothing(
    override: Tree, reason: str, member: str | None, renders: list[str], paints: list[str]
) -> None:
    tree = sprite()
    tree["animations"][0]["frames"][3]["overrides"].append(override)
    document = validate_document(tree)  # structurally valid: kind is checked on evaluation
    pointer = "/animations/0/frames/3/overrides/1" + (f"/{member}" if member else "")
    for request in (
        lambda: render_animation(document, "walk"),
        lambda: render_animation(document, "walk", frame_ids=["f0"]),  # f3 not requested
        lambda: render_frame(document, "f0"),
        lambda: api.render(document, frame_id="f1"),
        lambda: evaluate_animation(document, "walk"),
    ):
        with pytest.raises(errors.MoanaError) as raised:
            request()
        assert raised.value.context["reason"] == reason
        assert raised.value.json_pointer == pointer
    assert renders == []
    assert paints == []
    assert render_animation(document, "blink").frames[0].frame_id == "open"  # other timeline
    assert renders == ["open", "shut"]


def test_ac2_an_override_whose_result_is_invalid_renders_nothing(
    renders: list[str], paints: list[str]
) -> None:
    tree = sprite()
    # Off-canvas is fine (clipping), but a box beyond +-1 048 576 leaves the format: the
    # editor's range check rejects it before the frame document exists.
    tree["animations"][0]["frames"][1]["overrides"][0]["dx"] = -1_048_578
    document = validate_document(tree)
    with pytest.raises(errors.ValidationError) as raised:
        render_animation(document, "walk")
    assert raised.value.json_pointer == "/animations/0/frames/1/overrides/0"
    assert raised.value.context["reason"] == "out_of_range"
    assert renders == paints == []


def test_ac2_budget_of_the_whole_request_is_checked_before_any_frame(
    document: Document, renders: list[str], paints: list[str]
) -> None:
    with pytest.raises(errors.BudgetExceeded) as raised:
        render_animation(document, "walk", limits=RenderLimits(max_frame_pixels=4 * 64 - 1))
    assert raised.value.context["resource"] == "frame_pixels"
    assert raised.value.context["estimated"] == 4 * 64
    assert raised.value.context["frames"] == 4
    assert renders == paints == []


# --- T1: single frame, 256 frames, duration/area limits and loops --------------------


def test_t1_single_frame_animation(renders: list[str]) -> None:
    tree = sprite()
    tree["animations"] = [
        {
            "id": "still",
            "loop_count": 1,
            "pivot": [0, 8],
            "frames": [{"id": "only", "duration_ms": 1}],
        }
    ]
    document = validate_document(tree)
    rendered = render_animation(document, "still")
    assert [(f.frame_id, f.index, f.start_ms, f.duration_ms) for f in rendered.frames] == [
        ("only", 0, 0, 1)
    ]
    assert rendered.frames[0].result.rgba == expected_bytes("f0")
    assert rendered.duration_ms == 1
    assert renders == ["only"]


def many_frames(count: int, width: int = 8) -> Document:
    tree = sprite()
    tree["canvas"]["width"] = tree["canvas"]["height"] = width
    tree["animations"] = [
        {
            "id": "long",
            "loop_count": 0,
            "pivot": [0, 0],
            "frames": [
                {
                    "id": f"t{i}",
                    "duration_ms": 60_000,
                    "overrides": [
                        {"type": "translate", "target_id": "pupil", "dx": -(i % 7), "dy": 0}
                    ],
                }
                for i in range(count)
            ],
        }
    ]
    return validate_document(tree)


def test_t1_256_frames_render_each_frame_once() -> None:
    document = many_frames(256)
    started = time.perf_counter()
    rendered = render_animation(document, "long")
    elapsed = time.perf_counter() - started
    assert len(rendered.frames) == 256
    assert rendered.duration_ms == 256 * 60_000
    for i, frame in enumerate(rendered.frames):
        assert frame.start_ms == i * 60_000
        assert frame.result.pixel(6 - i % 7, 6) == GREEN
        assert frame.result.pixel(6, 6) == (GREEN if i % 7 == 0 else CLEAR)
    assert elapsed < 30, f"256 frames took {elapsed:.2f} s"


def test_t1_accumulated_frame_pixels_limit_is_inclusive(renders: list[str]) -> None:
    document = many_frames(4)
    at_limit = RenderLimits(max_frame_pixels=4 * 64)
    assert len(render_animation(document, "long", limits=at_limit).frames) == 4
    assert len(renders) == 4
    renders.clear()
    with pytest.raises(errors.BudgetExceeded) as raised:
        render_animation(document, "long", limits=RenderLimits(max_frame_pixels=4 * 64 - 1))
    assert dict(raised.value.context) == {
        "resource": "frame_pixels",
        "limit": 255,
        "estimated": 256,
        "frames": 4,
    }
    assert renders == []
    # Three of the four frames fit the lowered budget: only the request is counted.
    subset = render_animation(
        document, "long", frame_ids=["t3", "t0", "t1"], limits=RenderLimits(max_frame_pixels=192)
    )
    assert [frame.frame_id for frame in subset.frames] == ["t3", "t0", "t1"]


def test_t1_default_budget_rejects_a_sequence_over_16777216_frame_pixels(
    renders: list[str],
) -> None:
    # 2048 x 2048 = 4 194 304 pixels: four frames are exactly the section 17 budget,
    # five exceed it. Both are rejected or admitted before any pixel buffer exists.
    document = many_frames(5, width=2048)
    with pytest.raises(errors.BudgetExceeded) as raised:
        render_animation(document, "long")
    exceeded = {d.context["resource"]: d.context["estimated"] for d in raised.value.details}
    assert exceeded["frame_pixels"] == 5 * 2048 * 2048
    assert renders == []


@pytest.mark.slow
def test_t1_256_frames_at_exactly_16777216_accumulated_pixels() -> None:
    document = many_frames(256, width=256)  # 256 x 65 536 = 16 777 216
    limits = RenderLimits(max_pixel_visits=10**9, max_buffer_bytes=2**31, host_override=True)
    started = time.perf_counter()
    rendered = render_animation(document, "long", limits=limits)
    assert len(rendered.frames) == 256
    assert sum(f.result.width * f.result.height for f in rendered.frames) == 16_777_216
    assert time.perf_counter() - started < 120


def test_t1_loop_count_never_multiplies_the_render(document: Document, renders: list[str]) -> None:
    blink = render_animation(document, "blink")
    assert (blink.loop_count, blink.pivot) == (3, Point(0, 0))
    assert renders == ["open", "shut"]
    assert blink.duration_ms == 3  # one playback; loops are playback data
    walk = render_animation(document, "walk")  # loop_count 0 = infinite playback
    assert walk.loop_count == 0
    assert len(walk.frames) == 4
    assert renders == ["open", "shut", *FRAMES]
    assert blink.frames[1].result.pixel(6, 6) == CLEAR
    assert blink.frames[0].result.rgba == expected_bytes("f0")


def test_t1_frame_selection_errors(document: Document, renders: list[str]) -> None:
    cases: list[tuple[object, type[errors.MoanaError] | type[TypeError], str | None]] = [
        ([], errors.ValidationError, "empty_frames"),
        (["f0", "f0"], errors.ValidationError, "duplicate_frame"),
        (["open"], errors.ReferenceError, "unknown_frame"),  # another animation's frame
        (["nope"], errors.ReferenceError, "unknown_frame"),
        ([1], errors.ReferenceError, "unknown_frame"),
        ("f0", TypeError, None),
        (b"f0", TypeError, None),
        (5, TypeError, None),
    ]
    for frame_ids, kind, reason in cases:
        with pytest.raises(kind) as raised:
            render_animation(document, "walk", frame_ids=frame_ids)  # type: ignore[arg-type]
        if reason is not None:
            assert isinstance(raised.value, errors.MoanaError)
            assert dict(raised.value.context) == {"field": "frame_ids", "reason": reason}
    assert renders == []


def test_t1_unknown_animation_and_frame(document: Document) -> None:
    animation_calls: list[Callable[[], object]] = [
        lambda: render_animation(document, "run"),
        lambda: evaluate_animation(document, "run"),
        lambda: find_animation(document, 3),  # type: ignore[arg-type]
    ]
    for call in animation_calls:
        with pytest.raises(errors.ReferenceError) as raised:
            call()
        assert dict(raised.value.context) == {
            "field": "animation_id",
            "reason": "unknown_animation",
        }
    frame_calls: list[Callable[[], object]] = [
        lambda: render_frame(document, "walk"),  # an animation is not a frame
        lambda: evaluate_frame(document, "zz"),
        lambda: api.render(document, frame_id="zz"),
        lambda: find_frame(document, None),  # type: ignore[arg-type]
    ]
    for call in frame_calls:
        with pytest.raises(errors.ReferenceError) as raised:
            call()
        assert dict(raised.value.context) == {"field": "frame_id", "reason": "unknown_frame"}
    assert find_animation(document, "blink")[0] == 1
    index, animation, frame_index, frame = find_frame(document, "shut")
    assert (index, animation.id, frame_index, frame.duration_ms) == (1, "blink", 1, 2)


def test_t1_render_without_animation_draws_only_the_base(document: Document) -> None:
    with pytest.raises(errors.ReferenceError) as raised:
        render(document, frame_id="f1")
    assert dict(raised.value.context) == {"field": "frame_id", "reason": "frame_not_evaluated"}
    with pytest.raises(errors.ReferenceError) as raised:
        render(document, frame_id="zz")
    assert dict(raised.value.context) == {"field": "frame_id", "reason": "unknown_frame"}
    facade = api.render(document, frame_id="f1")
    assert facade.rgba == expected_bytes("f1")
    assert facade.provenance.frame_id == "f1"
    assert api.render(document).rgba == expected_bytes("f0")


def test_t1_argument_types_are_checked(document: Document) -> None:
    calls: list[Callable[[], object]] = [
        lambda: render_animation(document, "walk", parse_limits=None),  # type: ignore[arg-type]
        lambda: render_animation(document, "walk", deadline=5),  # type: ignore[arg-type]
        lambda: render_animation({}, "walk"),  # type: ignore[arg-type]
        lambda: render_frame(document, "f0", parse_limits=None),  # type: ignore[arg-type]
        lambda: evaluate_frame(document, "f0", limits=None),  # type: ignore[arg-type]
        lambda: evaluate_frame({}, "f0"),  # type: ignore[arg-type]
        lambda: evaluate_animation(document, "walk", limits=None),  # type: ignore[arg-type]
        lambda: evaluate_animation(document, "walk", deadline=1),  # type: ignore[arg-type]
        lambda: find_animation({}, "walk"),  # type: ignore[arg-type]
        lambda: api.render({}, frame_id="f0"),  # type: ignore[arg-type]
    ]
    for call in calls:
        with pytest.raises(TypeError):
            call()


@pytest.mark.parametrize(
    "options",
    [
        {"frame_id": 5},
        {"frame_id": True},
        {"frame_id": b"f0"},
        {"frame_id": "f0", "limits": 5},
        {"frame_id": "f0", "deadline": 5},
    ],
)
def test_t1_api_render_checks_frame_arguments_before_evaluating(
    document: Document, options: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluated: list[object] = []
    monkeypatch.setattr(timeline_module, "validate_document", evaluated.append)
    with pytest.raises(TypeError):
        api.render(document, **options)
    assert evaluated == []


class Clock:
    """A deadline clock that records the stages checked before it expires."""

    def __init__(self, expire_after: int) -> None:
        self.reads = 0
        self.expire_after = expire_after

    def __call__(self) -> float:
        self.reads += 1
        return 0.0 if self.reads <= self.expire_after else 10.0


def stage_after(call: Callable[[Deadline], object], checks: int) -> str:
    clock = Clock(checks + 1)  # the first read starts the deadline
    with pytest.raises(errors.BudgetExceeded) as raised:
        call(Deadline(1, clock=clock))
    return str(raised.value.context["stage"])


def test_t1_deadline_is_checked_before_every_validation_and_frame(document: Document) -> None:
    def evaluate(deadline: Deadline) -> object:
        return evaluate_animation(document, "walk", deadline=deadline)

    # base, static base, then per frame evaluate_frame, plus validate_frame for a
    # frame with overrides (f0 has none: it is the static base itself).
    stages = [stage_after(evaluate, checks) for checks in range(7)]
    assert stages == [
        "validate_frame",
        "validate_frame",
        "evaluate_frame",
        "evaluate_frame",
        "validate_frame",
        "evaluate_frame",
        "validate_frame",
    ]

    def frame(deadline: Deadline) -> object:
        return render_frame(document, "f2", deadline=deadline)

    assert stage_after(frame, 0) == "validate_frame"
    assert stage_after(frame, 2) == "evaluate_frame"


def test_t1_a_short_deadline_fails_near_its_limit() -> None:
    tree = sprite()
    frames = tree["animations"][0]["frames"]
    tree["animations"][0]["frames"] = [
        {**copy.deepcopy(frames[k % 4]), "id": f"g{k}"} for k in range(256)
    ]
    document = validate_document(tree)
    started = time.perf_counter()
    unbounded = render_animation(document, "walk")
    whole = time.perf_counter() - started
    assert len(unbounded.frames) == 256
    milliseconds = max(1, int(whole * 1000) // 20)
    started = time.perf_counter()
    with pytest.raises(errors.BudgetExceeded) as raised:
        render_animation(document, "walk", deadline=Deadline(milliseconds))
    elapsed = time.perf_counter() - started
    assert raised.value.context["resource"] == "time"
    # It stops at the next checkpoint: well before the whole request.
    assert elapsed < milliseconds / 1000 + whole / 4


def test_t1_parse_limits_bound_each_frame_document(document: Document) -> None:
    with pytest.raises(errors.ValidationError):
        render_animation(document, "walk", parse_limits=ParseLimits(max_nodes=50))


# --- T2: geometry/colour/visibility overrides, stable IDs and textures --------------


def test_t2_a_frame_without_overrides_does_not_call_the_editor(
    document: Document, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    original = editing.apply_commands

    def spy(*args: Any, **kwargs: Any) -> Document:
        calls.append(kwargs["pointer"])
        return original(*args, **kwargs)

    monkeypatch.setattr("moana.animation.timeline.apply_commands", spy)
    opened, shut = evaluate_animation(document, "blink")
    assert calls == ["/animations/1/frames/1/overrides"]
    static = json.loads(canonical_json(document))
    static["animations"] = []
    assert canonical_json(opened.document) == canonical_json(validate_document(static))
    assert render_frame(document, "open").result.rgba == render(opened.document).rgba
    assert shut.document.layers != opened.document.layers


def test_t2_evaluated_frames_are_static_documents_with_stable_ids(document: Document) -> None:
    base_ids = document_ids(document) - {"walk", "blink", *FRAMES, "open", "shut"}
    for evaluation in evaluate_animation(document, "walk"):
        frame_document = evaluation.document
        assert frame_document.animations == ()
        assert document_ids(frame_document) == base_ids
        assert frame_document.revision == document.revision
        assert frame_document.seed == document.seed
        layers = [layer.id for layer in frame_document.layers]
        assert layers == ["body", "eye", "texture", "frozen"]
    first = evaluate_frame(document, "f0").document
    assert snapshot_digest(first) != snapshot_digest(document)  # animations removed
    assert render(first).rgba == render(document).rgba


def test_t2_each_override_changes_only_its_target(document: Document) -> None:
    frames = {e.frame_id: e.document for e in evaluate_animation(document, "walk")}
    base = json.loads(canonical_json(frames["f0"]))

    def changed(frame_id: str) -> Tree:
        tree: Tree = json.loads(canonical_json(frames[frame_id]))
        return tree

    moved = copy.deepcopy(base)
    moved["layers"][0]["operations"][0]["box"] = [3, 1, 5, 3]
    assert changed("f1") == moved
    recoloured = copy.deepcopy(base)
    recoloured["layers"][0]["operations"][0]["color"] = "blue"
    recoloured["layers"][1]["visible"] = False
    assert changed("f2") == recoloured
    shifted = copy.deepcopy(base)
    shifted["masks"][0]["box"] = [2, 2, 6, 6]
    assert changed("f3") == shifted


def test_t2_dither_phase_is_anchored_and_stable_between_frames(document: Document) -> None:
    rendered = {f.frame_id: f.result for f in render_animation(document, "walk").frames}
    for frame_id in FRAMES:
        for y in range(8):
            for x in range(8):
                assert rendered[frame_id].pixel(x, y) == expected(frame_id, x, y), (frame_id, x, y)
    # Where the moved patch overlaps the base patch, the dithered colour is the same.
    for x, y in [(4, 2), (5, 2), (4, 3), (5, 3)]:
        assert rendered["f3"].pixel(x, y) == rendered["f0"].pixel(x, y)


def test_t2_material_texture_is_identical_in_every_frame() -> None:
    tree = json.loads((EXAMPLES / "material-skin.moana.json").read_text(encoding="utf-8"))
    tree["palette"]["colors"].append({"id": "spark_color", "rgba": "#FFFFFFFF"})
    tree["layers"].append(
        {
            "id": "spark",
            "name": "Spark",
            "operations": [
                {"id": "spark_dot", "type": "pixel", "color": "spark_color", "at": [0, 0]}
            ],
        }
    )
    tree["animations"] = [
        {
            "id": "twinkle",
            "loop_count": 0,
            "pivot": [16, 32],
            "frames": [
                {"id": "a", "duration_ms": 50},
                {
                    "id": "b",
                    "duration_ms": 50,
                    "overrides": [
                        {"type": "translate", "target_id": "spark_dot", "dx": 31, "dy": 0}
                    ],
                },
                {
                    "id": "c",
                    "duration_ms": 50,
                    "overrides": [
                        {"type": "set_visibility", "target_id": "spark", "visible": False}
                    ],
                },
            ],
        }
    ]
    document = validate_document(tree)
    base = render(document)
    frames = render_animation(document, "twinkle", frame_ids=["c", "b", "a"]).frames
    sparks = {(0, 0), (31, 0)}
    for frame in frames:
        for y in range(32):
            for x in range(32):
                if (x, y) not in sparks:
                    assert frame.result.pixel(x, y) == base.pixel(x, y), (frame.frame_id, x, y)
    by_id = {frame.frame_id: frame.result for frame in frames}
    assert by_id["a"].pixel(0, 0) == (255, 255, 255, 255)
    assert by_id["b"].pixel(31, 0) == (255, 255, 255, 255)
    assert by_id["b"].pixel(0, 0) == by_id["c"].pixel(0, 0) == CLEAR  # outside the body


def test_t2_editing_cannot_remove_an_animated_target(document: Document) -> None:
    batch = {
        "schema_version": "1.0",
        "base_revision": 7,
        "base_snapshot": snapshot_digest(document),
        "commands": [
            {"type": "remove", "target_id": "pupil"},
            {"type": "remove", "target_id": "eye"},
        ],
    }
    tree = sprite()
    tree["animations"][0]["frames"][2]["overrides"].pop()  # nothing animates the eye
    tree["animations"].pop()
    free = validate_document(tree)
    edited = api.apply_edit(free, {**batch, "base_snapshot": snapshot_digest(free)})
    assert [layer.id for layer in edited.layers] == ["body", "texture", "frozen"]
    with pytest.raises(errors.ReferenceError) as raised:
        api.apply_edit(document, batch)
    assert raised.value.context["reason"] == "live_reference"
    assert [d.json_pointer for d in raised.value.details] == [
        "/animations/0/frames/2/overrides/1/target_id",
        "/animations/1/frames/1/overrides/0/target_id",
    ]


def test_t2_moving_a_textured_sprite_slides_its_texture() -> None:
    tree = json.loads((EXAMPLES / "material-stone.moana.json").read_text(encoding="utf-8"))
    material = next(
        op for layer in tree["layers"] for op in layer["operations"] if op["type"] == "material"
    )
    masks = [mask["id"] for mask in tree["masks"] if mask["type"] == "polygon"]
    overrides = [{"type": "translate", "target_id": i, "dx": 1, "dy": 0} for i in masks]
    tree["animations"] = [
        {
            "id": "slide",
            "loop_count": 0,
            "pivot": [16, 32],
            "frames": [
                {"id": "still", "duration_ms": 1},
                {"id": "moved", "duration_ms": 1, "overrides": overrides},
            ],
        }
    ]
    document = validate_document(tree)
    still, moved = (f.result for f in render_animation(document, "slide").frames)
    # The texture stays anchored to its origin: the frame is not the base shifted.
    shifted = [
        (x, y)
        for y in range(still.height)
        for x in range(still.width - 1)
        if still.pixel(x, y)[3] and still.pixel(x, y) != moved.pixel(x + 1, y)
    ]
    assert shifted
    # It is the base with its masks moved and the material origin intact.
    static = copy.deepcopy(tree)
    static["animations"] = []
    for mask in static["masks"]:
        if mask["id"] in masks:
            mask["points"] = [[x + 1, y] for x, y in mask["points"]]
    by_id = {op["id"]: op for layer in static["layers"] for op in layer["operations"]}
    assert by_id[material["id"]]["origin"] == material["origin"]
    assert moved.rgba == render(validate_document(static)).rgba
