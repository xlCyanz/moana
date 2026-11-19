"""Grid spritesheets and reversible manifests (MOANA-023, ADR-033).

Rects, sheet sizes and atlas pixels are written by hand from the grid formula; the
atlas is decoded with Pillow directly, independent of the exporter's own checks.
"""

from __future__ import annotations

import ast
import io
import json
import os
import sys
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PIL import Image

from moana.core.budget import RenderLimits
from moana.core.coordinates import Point
from moana.core.digest import visual_digest
from moana.core.errors import (
    BudgetExceeded,
    ErrorDetail,
    ExportError,
    ReadError,
    UnsupportedVersion,
    ValidationError,
)
from moana.core.limits import GeometryLimits
from moana.export import (
    MAX_SPRITESHEET_IMAGE_BYTES,
    MAX_SPRITESHEET_MANIFEST_BYTES,
    FramePixels,
    SheetAnimation,
    SheetFrame,
    encode_spritesheet,
    export_spritesheet,
    load_spritesheet,
    parse_spritesheet_manifest,
    slice_spritesheet,
    spritesheet_layout,
)
from moana.export import spritesheet as sheet_module
from moana.export.atomic import commit_bytes

RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    rgba: bytes


@dataclass(frozen=True)
class Frame:
    frame_id: str
    duration_ms: int
    pivot: Point
    result: Raster


def pixel(index: int, x: int, y: int) -> RGBA:
    """Distinct opaque colour per frame and position."""
    return (10 * index + 1, x + 1, y + 1, 255)


def make_frame(index: int, width: int, height: int, *, duration: int = 100) -> Frame:
    data = bytes(c for y in range(height) for x in range(width) for c in pixel(index, x, y))
    return Frame(
        f"f{index}", duration, Point(index % (width + 1), height), Raster(width, height, data)
    )


def frames(count: int, width: int, height: int) -> list[Frame]:
    return [make_frame(index, width, height, duration=100 + index) for index in range(count)]


def decode(data: bytes) -> tuple[str, int, int, list[RGBA]]:
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        mode, (width, height) = image.mode, image.size
        rgba = image.tobytes()
    return mode, width, height, [tuple(rgba[i : i + 4]) for i in range(0, len(rgba), 4)]  # type: ignore[misc]  # 4-tuples by slicing


# --- T1: layout by hand ------------------------------------------------------------

# (count, columns, margin, padding, w, h, sheet size, rect origins)
CASES = [
    pytest.param(3, 1, 0, 0, 3, 2, (3, 6), [(0, 0), (0, 2), (0, 4)], id="one-column"),
    pytest.param(3, 3, 0, 0, 3, 2, (9, 2), [(0, 0), (3, 0), (6, 0)], id="one-row"),
    pytest.param(
        5, 2, 1, 2, 3, 2, (10, 12), [(1, 1), (6, 1), (1, 5), (6, 5), (1, 9)], id="incomplete-row"
    ),
    pytest.param(4, 3, 2, 0, 2, 3, (10, 10), [(2, 2), (4, 2), (6, 2), (2, 5)], id="margin-only"),
    pytest.param(4, 2, 0, 1, 3, 2, (7, 5), [(0, 0), (4, 0), (0, 3), (4, 3)], id="padding-only"),
    pytest.param(1, 1, 3, 5, 2, 1, (8, 7), [(3, 3)], id="single-frame"),
]


@pytest.mark.parametrize(
    ("count", "columns", "margin", "padding", "w", "h", "size", "origins"), CASES
)
def test_layout_matches_hand_computed_grid(
    count: int,
    columns: int,
    margin: int,
    padding: int,
    w: int,
    h: int,
    size: tuple[int, int],
    origins: list[tuple[int, int]],
) -> None:
    layout = spritesheet_layout(count, w, h, columns=columns, margin=margin, padding=padding)
    assert (layout.width, layout.height) == size
    assert layout.rects == tuple((x, y, w, h) for x, y in origins)


@pytest.mark.parametrize(
    ("count", "columns", "margin", "padding", "w", "h", "size", "origins"), CASES
)
def test_atlas_pixels_are_placed_by_hand_and_gaps_are_transparent(
    count: int,
    columns: int,
    margin: int,
    padding: int,
    w: int,
    h: int,
    size: tuple[int, int],
    origins: list[tuple[int, int]],
) -> None:
    encoded = encode_spritesheet(
        frames(count, w, h), columns=columns, margin=margin, padding=padding
    )
    expected = [[CLEAR] * size[0] for _ in range(size[1])]
    for index, (x0, y0) in enumerate(origins):
        for y in range(h):
            for x in range(w):
                expected[y0 + y][x0 + x] = pixel(index, x, y)
    mode, width, height, pixels = decode(encoded.image)
    assert (mode, width, height) == ("RGBA", *size)
    assert pixels == [p for row in expected for p in row]
    manifest = json.loads(encoded.manifest_json)
    assert [entry["rect"] for entry in manifest["frames"]] == [[x, y, w, h] for x, y in origins]
    assert manifest["image"]["width"] == size[0] and manifest["image"]["height"] == size[1]


def test_manifest_records_every_frame_value() -> None:
    source = frames(2, 3, 2)
    encoded = encode_spritesheet(source, columns=2, padding=1, image_name="hero.png")
    manifest = json.loads(encoded.manifest_json)
    assert manifest["format"] == "moana-spritesheet" and manifest["version"] == 1
    assert manifest["image"]["name"] == "hero.png"
    assert manifest["image"]["media_type"] == "image/png"
    assert manifest["layout"] == {
        "columns": 2,
        "frame_count": 2,
        "frame_height": 2,
        "frame_width": 3,
        "margin": 0,
        "padding": 1,
        "rows": 1,
    }
    assert manifest["frames"][1] == {
        "digest": visual_digest(3, 2, source[1].result.rgba),
        "duration_ms": 101,
        "frame_id": "f1",
        "pivot": [1, 2],
        "rect": [4, 0, 3, 2],
        "source_size": [3, 2],
        "trim_offset": [0, 0],
    }
    assert encoded.manifest_json.endswith(b"}\n")
    assert parse_spritesheet_manifest(encoded.manifest_json) == encoded.manifest


def test_animation_block_roundtrips_and_is_optional() -> None:
    playback = SheetAnimation("walk", 3)
    encoded = encode_spritesheet(frames(2, 2, 2), columns=2, animation=playback)
    assert json.loads(encoded.manifest_json)["animation"] == {"id": "walk", "loop_count": 3}
    assert parse_spritesheet_manifest(encoded.manifest_json).animation == playback
    plain = encode_spritesheet(frames(2, 2, 2), columns=2)
    assert "animation" not in json.loads(plain.manifest_json)
    assert plain.image == encoded.image
    for bad, error in (
        (SheetAnimation("Walk", 0), ValidationError),
        (SheetAnimation("walk", -1), ValidationError),
        (SheetAnimation("walk", 65_536), ValidationError),
        (SheetAnimation("walk", cast(Any, True)), ValidationError),
        (cast(Any, {"id": "walk"}), TypeError),
    ):
        with pytest.raises(error):
            encode_spritesheet(frames(1, 1, 1), columns=1, animation=bad)


def test_rect_index_is_checked() -> None:
    layout = spritesheet_layout(2, 1, 1, columns=1)
    with pytest.raises(ValidationError):
        layout.rect(2)


# --- AC2: determinism and layout properties -------------------------------------------


def test_export_is_byte_identical_across_directories(tmp_path: Path) -> None:
    source = frames(5, 3, 2)
    reports = []
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        reports.append(
            export_spritesheet(
                source,
                tmp_path / name / "sheet.png",
                tmp_path / name / "sheet.json",
                columns=2,
                margin=1,
                padding=2,
            )
        )
    for file in ("sheet.png", "sheet.json"):
        assert (tmp_path / "a" / file).read_bytes() == (tmp_path / "b" / file).read_bytes()
    first, second = (report.to_mapping() for report in reports)
    assert {k: v for k, v in first.items() if not k.endswith("_path")} == {
        k: v for k, v in second.items() if not k.endswith("_path")
    }
    assert first["frames"] == 5 and first["rows"] == 3


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    count=st.integers(1, 12),
    data=st.data(),
    margin=st.integers(0, 3),
    padding=st.integers(0, 3),
    w=st.integers(1, 5),
    h=st.integers(1, 5),
)
def test_rects_are_disjoint_inside_and_roundtrip(
    count: int, data: st.DataObject, margin: int, padding: int, w: int, h: int
) -> None:
    columns = data.draw(st.integers(1, count))
    layout = spritesheet_layout(count, w, h, columns=columns, margin=margin, padding=padding)
    cover = np.zeros((layout.height, layout.width), dtype=np.int32)
    for x, y, rw, rh in layout.rects:
        assert (rw, rh) == (w, h)
        assert margin <= x and x + w <= layout.width - margin
        assert margin <= y and y + h <= layout.height - margin
        cover[y : y + h, x : x + w] += 1
    assert int(cover.max()) == 1 and int(cover.sum()) == count * w * h  # disjoint
    for x, y, _, _ in layout.rects:  # padding: every other cell is at least `padding` away
        for ox, oy, _, _ in layout.rects:
            if (ox, oy) != (x, y):
                assert abs(ox - x) >= w + padding or abs(oy - y) >= h + padding
    source = frames(count, w, h)
    encoded = encode_spritesheet(source, columns=columns, margin=margin, padding=padding)
    _, _, _, pixels = decode(encoded.image)
    uncovered = [p for p, c in zip(pixels, cover.reshape(-1).tolist(), strict=True) if c == 0]
    assert set(uncovered) <= {CLEAR}
    sliced = slice_spritesheet(encoded.image, encoded.manifest_json)
    assert [(f.frame_id, f.duration_ms, f.pivot, f.result.rgba) for f in sliced] == [
        (f.frame_id, f.duration_ms, f.pivot, f.result.rgba) for f in source
    ]


# --- AC1 / T2: roundtrip ---------------------------------------------------------------


def test_slice_rebuilds_frames_and_reexports_identically(tmp_path: Path) -> None:
    source = frames(5, 3, 2)
    report = export_spritesheet(
        source, tmp_path / "s.png", tmp_path / "s.json", columns=3, margin=2, padding=1
    )
    sliced = load_spritesheet(tmp_path / "s.png", tmp_path / "s.json")
    assert sliced == tuple(
        SheetFrame(f.frame_id, f.duration_ms, f.pivot, FramePixels(3, 2, f.result.rgba))
        for f in source
    )
    assert sliced[0].result.digest == visual_digest(3, 2, source[0].result.rgba)
    again = encode_spritesheet(sliced, columns=3, margin=2, padding=1, image_name="s.png")
    assert again.image == (tmp_path / "s.png").read_bytes()
    assert again.manifest_json == (tmp_path / "s.json").read_bytes()
    assert report.image_byte_size == len(again.image)
    assert report.warnings == () and report.to_mapping()["warnings"] == []
    assert report.manifest_media_type == "application/json"


def test_translucent_pixels_survive_the_roundtrip() -> None:
    data = bytes([0, 0, 0, 0, 200, 100, 50, 77, 1, 2, 3, 1, 16, 32, 48, 255])
    source = [Frame("glass", 60_000, Point(0, 0), Raster(2, 2, data))]
    encoded = encode_spritesheet(source, columns=1, margin=1)
    (frame,) = slice_spritesheet(encoded.image, encoded.manifest_json)
    assert frame.result.rgba == data and frame.duration_ms == 60_000


# --- T2: budgets before allocation ----------------------------------------------------


def shared_frames(count: int, size: int) -> list[Frame]:
    raster = Raster(size, size, bytes([1, 1, 1, 255]) * (size * size))
    return [Frame(f"f{i}", 1, Point(0, 0), raster) for i in range(count)]


@pytest.mark.parametrize(
    ("count", "size", "columns", "limits", "resource"),
    [
        pytest.param(
            4, 8, 4, RenderLimits(max_frame_pixels=255), "frame_pixels", id="frame-pixels"
        ),
        pytest.param(129, 16, 129, RenderLimits(), "export_dimension", id="dimension"),
        pytest.param(
            4, 8, 2, RenderLimits(geometry=GeometryLimits(max_area=255)), "export_area", id="area"
        ),
        pytest.param(4, 8, 2, RenderLimits(max_buffer_bytes=8191), "buffer_bytes", id="bytes"),
    ],
)
def test_excessive_sheet_is_rejected_before_the_atlas_exists(
    monkeypatch: pytest.MonkeyPatch,
    count: int,
    size: int,
    columns: int,
    limits: RenderLimits,
    resource: str,
) -> None:
    def no_atlas(*_: object, **__: object) -> None:
        raise AssertionError("atlas allocated before the budget check")

    monkeypatch.setattr("moana.export.spritesheet.np.zeros", no_atlas)
    with pytest.raises(BudgetExceeded) as caught:
        encode_spritesheet(shared_frames(count, size), columns=columns, limits=limits)
    assert resource in {detail.context["resource"] for detail in caught.value.details}


def test_exact_budget_is_admitted() -> None:
    # 4 frames of 8x8 on a 2x2 grid: 256 pixels, 32 bytes per pixel = 8192.
    limits = RenderLimits(max_frame_pixels=256, max_buffer_bytes=8192)
    encode_spritesheet(shared_frames(4, 8), columns=2, limits=limits)


def test_rejected_large_sheet_allocates_almost_nothing() -> None:
    source = shared_frames(256, 128)  # 2048 x 2048 sheet, 4 194 304 pixels, one raster
    limits = RenderLimits(max_buffer_bytes=64 * 1024 * 1024)
    tracemalloc.start()
    try:
        with pytest.raises(BudgetExceeded) as caught:
            encode_spritesheet(source, columns=16, limits=limits)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert caught.value.context["resource"] == "buffer_bytes"
    assert caught.value.context["estimated"] == 32 * 2048 * 2048
    assert peak < 1024 * 1024


def test_too_many_frames_is_rejected_before_reading_any_frame() -> None:
    class Untouchable:
        @property
        def result(self) -> Raster:
            raise AssertionError("frame read")

    with pytest.raises(BudgetExceeded) as caught:
        encode_spritesheet(cast(Any, [Untouchable()] * 257), columns=1)
    assert caught.value.context == {"resource": "frames", "limit": 256, "estimated": 257}
    assert [detail.context["resource"] for detail in caught.value.details] == ["frames"]
    with pytest.raises(BudgetExceeded):
        spritesheet_layout(257, 1, 1, columns=1)


def test_unnormalized_frame_is_rejected_before_the_atlas_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_atlas(*_: object, **__: object) -> None:
        raise AssertionError("atlas allocated before the frame check")

    monkeypatch.setattr("moana.export.spritesheet.np.zeros", no_atlas)
    bad = replace(GOOD, frame_id="g", result=Raster(2, 2, bytes([0, 9, 0, 0]) + bytes(12)))
    with pytest.raises(ValidationError) as caught:
        encode_spritesheet([GOOD, bad], columns=1)
    assert caught.value.context["reason"] == "not_normalized"


def test_slicing_checks_its_budget_before_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    encoded = encode_spritesheet(frames(4, 3, 2), columns=2)

    def no_decode(*_: object, **__: object) -> None:
        raise AssertionError("decoded before the budget check")

    monkeypatch.setattr("moana.export.spritesheet.Image.open", no_decode)
    # 12 bytes per atlas pixel (6 x 4 sheet) plus the encoded PNG bytes.
    estimate = len(encoded.image) + 12 * 24
    with pytest.raises(BudgetExceeded) as caught:
        slice_spritesheet(
            encoded.image,
            encoded.manifest_json,
            limits=RenderLimits(max_buffer_bytes=estimate - 1),
        )
    assert caught.value.context == {
        "resource": "buffer_bytes",
        "limit": estimate - 1,
        "estimated": estimate,
    }
    monkeypatch.undo()
    exact = RenderLimits(max_buffer_bytes=estimate)
    assert len(slice_spritesheet(encoded.image, encoded.manifest_json, limits=exact)) == 4
    with pytest.raises(BudgetExceeded) as small:
        slice_spritesheet(
            encoded.image, encoded.manifest_json, limits=RenderLimits(max_buffer_bytes=10)
        )
    assert small.value.context == {
        "resource": "image_bytes",
        "limit": 10,
        "estimated": len(encoded.image),
    }
    with pytest.raises(BudgetExceeded):
        slice_spritesheet(
            encoded.image, encoded.manifest_json, limits=RenderLimits(max_frame_pixels=23)
        )


# --- T1/T2: invalid options and frames --------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "field", "reason"),
    [
        ({"columns": 4}, "columns", "too_many_columns"),
        ({"columns": 0}, "columns", "out_of_range"),
        ({"columns": True}, "columns", "not_integer"),
        ({"columns": 1, "margin": -1}, "margin", "out_of_range"),
        ({"columns": 1, "padding": 1.0}, "padding", "not_integer"),
    ],
)
def test_invalid_layout_options(kwargs: dict[str, Any], field: str, reason: str) -> None:
    with pytest.raises(ValidationError) as caught:
        encode_spritesheet(frames(3, 2, 2), **kwargs)
    assert caught.value.context["field"] == field
    assert caught.value.context["reason"] == reason


def test_empty_frames_and_bad_containers() -> None:
    with pytest.raises(ValidationError) as caught:
        encode_spritesheet([], columns=1)
    assert caught.value.context["reason"] == "empty_frames"
    with pytest.raises(ValidationError):
        spritesheet_layout(0, 1, 1, columns=1)
    for bad in ("ab", b"ab", {make_frame(0, 1, 1)}):
        with pytest.raises(TypeError):
            encode_spritesheet(cast(Any, bad), columns=1)
    with pytest.raises(TypeError):
        spritesheet_layout(1, 1, 1, columns=1, limits=cast(Any, None))


def replace(frame: Frame, **changes: Any) -> Frame:
    values = {**frame.__dict__, **changes}
    return Frame(**values)


GOOD = make_frame(0, 2, 2)
BAD_FRAMES: list[Any] = [
    pytest.param(make_frame(1, 3, 2), "size_mismatch", id="size"),
    pytest.param(replace(GOOD, frame_id="Bad"), "invalid_id", id="id"),
    pytest.param(replace(GOOD, frame_id="f0"), "duplicate_frame", id="duplicate"),
    pytest.param(replace(GOOD, frame_id="g", duration_ms=0), "invalid_duration", id="zero"),
    pytest.param(replace(GOOD, frame_id="g", duration_ms=60_001), "invalid_duration", id="long"),
    pytest.param(replace(GOOD, frame_id="g", duration_ms=True), "invalid_duration", id="bool"),
    pytest.param(replace(GOOD, frame_id="g", pivot=Point(3, 0)), "pivot_out_of_frame", id="pivot"),
    pytest.param(replace(GOOD, frame_id="g", pivot=(0, 0)), "pivot_out_of_frame", id="tuple"),
    pytest.param(
        replace(GOOD, frame_id="g", result=Raster(2, 2, bytes(15))), "wrong_size", id="bytes"
    ),
    pytest.param(
        replace(GOOD, frame_id="g", result=Raster(2, 2, bytes([1, 0, 0, 0]) + bytes(12))),
        "not_normalized",
        id="alpha",
    ),
]


@pytest.mark.parametrize(("bad", "reason"), BAD_FRAMES)
def test_invalid_frames_are_located(bad: Frame, reason: str) -> None:
    with pytest.raises(ValidationError) as caught:
        encode_spritesheet([GOOD, bad], columns=1)
    assert caught.value.context == {"field": "frames", "reason": reason, "index": 1}


def test_frame_types_and_image_names() -> None:
    with pytest.raises(TypeError):
        encode_spritesheet(
            [replace(GOOD, result=Raster(2, 2, cast(Any, bytearray(16))))], columns=1
        )
    with pytest.raises(ValidationError):
        encode_spritesheet([replace(GOOD, result=Raster(0, 2, b""))], columns=1)
    for name in (
        "a/b.png",
        "a\\b.png",
        "x.json",
        "",
        "..",
        ".png",
        "a\x01.png",
        "a\x7f.png",
        "a\x85.png",
        "a\x9f.png",
        "\udcff.png",
        "a" * 252 + ".png",
    ):
        with pytest.raises(ValidationError) as caught:
            encode_spritesheet([GOOD], columns=1, image_name=name)
        assert caught.value.context["reason"] == "invalid_name"
    with pytest.raises(TypeError):
        encode_spritesheet([GOOD], columns=1, image_name=cast(Any, None))


# --- T2: corrupt manifests -----------------------------------------------------------

BASE = encode_spritesheet(frames(3, 3, 2), columns=2, margin=1, padding=1, image_name="s.png")


def mutated(change: Callable[[dict[str, Any]], object]) -> bytes:
    manifest: dict[str, Any] = json.loads(BASE.manifest_json)
    change(manifest)
    return json.dumps(manifest).encode("utf-8")


def setter(path: str, value: object) -> Callable[[dict[str, Any]], None]:
    def change(manifest: dict[str, Any]) -> None:
        *parents, last = path.split("/")
        node: Any = manifest
        for key in parents:
            node = node[int(key)] if isinstance(node, list) else node[key]
        if isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value

    return change


def deleter(path: str) -> Callable[[dict[str, Any]], None]:
    def change(manifest: dict[str, Any]) -> None:
        *parents, last = path.split("/")
        node: Any = manifest
        for key in parents:
            node = node[int(key)] if isinstance(node, list) else node[key]
        del node[last]

    return change


def swap_rects(manifest: dict[str, Any]) -> None:
    first, second = manifest["frames"][0], manifest["frames"][1]
    first["rect"], second["rect"] = second["rect"], first["rect"]


CORRUPT: list[Any] = [
    pytest.param(setter("format", "atlas"), "/format", "wrong_format", id="format"),
    pytest.param(setter("version", "1"), "/version", "wrong_type", id="version-str"),
    pytest.param(setter("version", True), "/version", "wrong_type", id="version-bool"),
    pytest.param(deleter("layout"), "/layout", "missing_member", id="missing-layout"),
    pytest.param(setter("extra", 1), "", "unknown_member", id="unknown-root"),
    pytest.param(lambda m: m.__setitem__("a~/b", 1), "", "unknown_member", id="unknown-escaped"),
    pytest.param(setter("frames/0/extra", 1), "/frames/0", "unknown_member", id="unknown-frame"),
    pytest.param(deleter("format"), "/format", "missing_member", id="missing-format"),
    pytest.param(deleter("version"), "/version", "missing_member", id="missing-version"),
    pytest.param(setter("animation", []), "/animation", "wrong_type", id="animation-array"),
    pytest.param(
        setter("animation", {"id": "a"}), "/animation/loop_count", "missing_member", id="anim-key"
    ),
    pytest.param(
        setter("animation", {"id": "a", "loop_count": 0, "x": 1}),
        "/animation",
        "unknown_member",
        id="anim-extra",
    ),
    pytest.param(
        setter("animation", {"id": "A", "loop_count": 0}), "/animation/id", "invalid_id", id="aid"
    ),
    pytest.param(
        setter("animation", {"id": "a", "loop_count": 65_536}),
        "/animation/loop_count",
        "out_of_range",
        id="loop",
    ),
    pytest.param(
        setter("animation", {"id": "a", "loop_count": True}),
        "/animation/loop_count",
        "wrong_type",
        id="loop-bool",
    ),
    pytest.param(setter("image/name", "\udcff.png"), "/image/name", "invalid_name", id="surr"),
    pytest.param(setter("image/name", ".png"), "/image/name", "invalid_name", id="bare"),
    pytest.param(setter("image/name", "a\x7f.png"), "/image/name", "invalid_name", id="del"),
    pytest.param(deleter("frames/1/pivot"), "/frames/1/pivot", "missing_member", id="no-pivot"),
    pytest.param(setter("layout", []), "/layout", "wrong_type", id="layout-array"),
    pytest.param(setter("layout/columns", True), "/layout/columns", "wrong_type", id="bool-int"),
    pytest.param(setter("layout/columns", 2.0), "/layout/columns", "wrong_type", id="float-int"),
    pytest.param(setter("layout/columns", 4), "/layout/columns", "out_of_range", id="columns"),
    pytest.param(setter("layout/rows", 3), "/layout/rows", "layout_mismatch", id="rows"),
    pytest.param(setter("layout/margin", 0), "/image/width", "layout_mismatch", id="margin"),
    pytest.param(setter("image/height", 9), "/image/height", "layout_mismatch", id="height"),
    pytest.param(setter("image/name", 7), "/image/name", "wrong_type", id="name-type"),
    pytest.param(setter("image/name", "../s.png"), "/image/name", "invalid_name", id="name"),
    pytest.param(
        setter("image/media_type", "image/gif"), "/image/media_type", "wrong_media_type", id="mt"
    ),
    pytest.param(setter("image/sha256", "sha256:AB"), "/image/sha256", "invalid_digest", id="sha"),
    pytest.param(setter("frames", {}), "/frames", "wrong_type", id="frames-object"),
    pytest.param(setter("frames/2", "x"), "/frames/2", "wrong_type", id="frame-string"),
    pytest.param(
        lambda m: m["frames"].pop(), "/frames", "frame_count_mismatch", id="missing-frame"
    ),
    pytest.param(
        setter("frames/1/frame_id", "f0"), "/frames/1/frame_id", "duplicate_frame", id="dup"
    ),
    pytest.param(setter("frames/1/frame_id", "F"), "/frames/1/frame_id", "invalid_id", id="id"),
    pytest.param(swap_rects, "/frames/0/rect", "rect_mismatch", id="swapped-rects"),
    pytest.param(
        setter("frames/1/rect", [1, 1, 3, 2]), "/frames/1/rect", "rect_mismatch", id="overlap"
    ),
    pytest.param(
        setter("frames/0/rect", [0, 0, 3, 2]), "/frames/0/rect", "rect_mismatch", id="in-margin"
    ),
    pytest.param(
        setter("frames/1/rect", [7, 1, 3, 2]), "/frames/1/rect", "rect_out_of_sheet", id="outside"
    ),
    pytest.param(
        setter("frames/1/rect", [5, 1, 0, 2]), "/frames/1/rect", "rect_out_of_sheet", id="empty"
    ),
    pytest.param(setter("frames/1/rect", [5, 1, 3]), "/frames/1/rect", "wrong_type", id="rect-3"),
    pytest.param(
        setter("frames/1/rect", [5, 1, 3, False]), "/frames/1/rect/3", "wrong_type", id="rect-bool"
    ),
    pytest.param(
        setter("frames/1/rect", [5, 1, 3, 2**40]), "/frames/1/rect/3", "out_of_range", id="huge"
    ),
    pytest.param(
        setter("frames/0/duration_ms", 0), "/frames/0/duration_ms", "out_of_range", id="duration"
    ),
    pytest.param(
        setter("frames/0/pivot", [4, 0]), "/frames/0/pivot", "pivot_out_of_frame", id="pivot"
    ),
    pytest.param(
        setter("frames/0/source_size", [4, 2]),
        "/frames/0/source_size",
        "source_size_mismatch",
        id="source-size",
    ),
    pytest.param(
        setter("frames/0/trim_offset", [1, 0]),
        "/frames/0/trim_offset",
        "unsupported_trim",
        id="trim",
    ),
    pytest.param(
        setter("frames/0/digest", "md5:00"), "/frames/0/digest", "invalid_digest", id="digest"
    ),
]


@pytest.mark.parametrize(("change", "pointer", "reason"), CORRUPT)
def test_corrupt_manifest_is_located(
    change: Callable[[dict[str, Any]], object], pointer: str, reason: str
) -> None:
    data = mutated(change)
    with pytest.raises(ValidationError) as caught:
        parse_spritesheet_manifest(data)
    assert (caught.value.json_pointer, caught.value.context["reason"]) == (pointer, reason)
    assert caught.value.context["field"] == "manifest"
    with pytest.raises(ValidationError):
        slice_spritesheet(BASE.image, data)


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        pytest.param(b"\xff\xfe{}", "not_utf8", id="not-utf8"),
        pytest.param(b"{", "invalid_json", id="truncated"),
        pytest.param(b'{"a": NaN}', "invalid_json", id="nan"),
        pytest.param(b"[" * 100_000, "invalid_json", id="deep"),
        pytest.param(b'{"a": 1, "a": 2}', "duplicate_member", id="duplicate-key"),
        pytest.param(b"[]", "wrong_type", id="array"),
        pytest.param(b'{"version": 1}', "missing_member", id="empty"),
        pytest.param(b'{"format": "moana-spritesheet"}', "missing_member", id="no-version"),
    ],
)
def test_unreadable_manifest_bytes(data: bytes, reason: str) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_spritesheet_manifest(data)
    assert caught.value.context["reason"] == reason
    assert "/" not in caught.value.message.replace("image/png", "")


def test_manifest_size_version_and_type() -> None:
    with pytest.raises(BudgetExceeded) as caught:
        parse_spritesheet_manifest(b" " * (MAX_SPRITESHEET_MANIFEST_BYTES + 1))
    assert caught.value.context["resource"] == "manifest_bytes"
    for change in (setter("version", 2), setter("extra", 1), deleter("frames")):

        def future(manifest: dict[str, Any], change: Any = change) -> None:
            manifest["version"] = 2
            change(manifest)

        with pytest.raises(UnsupportedVersion) as version:
            parse_spritesheet_manifest(mutated(future))
        assert version.value.json_pointer == "/version"
    with pytest.raises(TypeError):
        parse_spritesheet_manifest(cast(Any, BASE.manifest_json.decode("utf-8")))


# --- T2: atlas checks when slicing ---------------------------------------------------


def png(width: int, height: int, mode: str = "RGBA", fill: int = 0) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (width, height), fill).save(buffer, format="PNG")
    return buffer.getvalue()


def test_digest_mismatches_are_located() -> None:
    with pytest.raises(ValidationError) as caught:
        slice_spritesheet(png(9, 7), BASE.manifest_json)
    assert caught.value.json_pointer == "/image/digest"
    assert caught.value.context["reason"] == "digest_mismatch"
    other = BASE.manifest.frames[1].digest
    data = mutated(setter("frames/0/digest", other))
    with pytest.raises(ValidationError) as frame_error:
        slice_spritesheet(BASE.image, data)
    assert frame_error.value.json_pointer == "/frames/0/digest"


def resealed(change: Callable[[np.ndarray[Any, Any]], None]) -> tuple[bytes, bytes]:
    """BASE with edited atlas pixels, re-encoded, and its digests recomputed."""
    with Image.open(io.BytesIO(BASE.image)) as image:
        atlas = np.array(image)
    change(atlas)
    buffer = io.BytesIO()
    Image.fromarray(atlas, "RGBA").save(buffer, format="PNG")
    manifest: dict[str, Any] = json.loads(BASE.manifest_json)
    height, width = atlas.shape[:2]
    manifest["image"]["digest"] = visual_digest(width, height, atlas.tobytes())
    for entry in manifest["frames"]:
        x, y, w, h = entry["rect"]
        entry["digest"] = visual_digest(w, h, atlas[y : y + h, x : x + w].tobytes())
    return buffer.getvalue(), json.dumps(manifest).encode("utf-8")


def set_pixel(x: int, y: int, value: RGBA) -> Callable[[np.ndarray[Any, Any]], None]:
    def change(atlas: np.ndarray[Any, Any]) -> None:
        atlas[y, x] = value

    return change


# BASE: three 3x2 frames, two columns, margin 1, padding 1 -> 9x7 sheet; rects at
# (1,1), (5,1), (1,4); the cell at (5,4) is empty.
@pytest.mark.parametrize(
    ("change", "reason"),
    [
        pytest.param(set_pixel(0, 0, (1, 2, 3, 255)), "dirty_gap", id="margin"),
        pytest.param(set_pixel(4, 1, (0, 0, 0, 1)), "dirty_gap", id="padding"),
        pytest.param(set_pixel(6, 5, (9, 9, 9, 9)), "dirty_gap", id="empty-cell"),
        pytest.param(set_pixel(8, 6, (5, 0, 0, 0)), "not_normalized", id="gap-unnormalized"),
        pytest.param(set_pixel(2, 1, (5, 0, 0, 0)), "not_normalized", id="frame-unnormalized"),
    ],
)
def test_atlas_pixels_are_checked_independently_of_digests(
    change: Callable[[np.ndarray[Any, Any]], None], reason: str
) -> None:
    image, manifest = resealed(change)
    with pytest.raises(ValidationError) as caught:
        slice_spritesheet(image, manifest)
    assert caught.value.context == {"field": "image", "reason": reason}


def test_resealed_clean_atlas_still_slices() -> None:
    image, manifest = resealed(set_pixel(2, 1, (7, 7, 7, 7)))
    assert len(slice_spritesheet(image, manifest)) == 3


def corrupt_idat(data: bytes) -> bytes:
    offset = data.index(b"IDAT") + 6
    return data[:offset] + bytes([data[offset] ^ 0xFF]) + data[offset + 1 :]


def animated() -> bytes:
    buffer = io.BytesIO()
    images = [Image.new("RGBA", (9, 7), (i, 0, 0, 255)) for i in (1, 2)]
    images[0].save(buffer, format="PNG", save_all=True, append_images=images[1:])
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("image", "reason"),
    [
        pytest.param(b"GIF89a" + bytes(40), "not_png", id="gif"),
        pytest.param(BASE.image[:8] + bytes(25), "not_png", id="no-ihdr"),
        pytest.param(png(9, 7, "RGB"), "wrong_mode", id="rgb"),
        pytest.param(png(7, 9), "image_size_mismatch", id="size"),
        pytest.param(BASE.image[:-1], "unreadable_image", id="truncated"),
        pytest.param(corrupt_idat(BASE.image), "unreadable_image", id="zlib"),
        pytest.param(animated(), "multiple_frames", id="apng"),
    ],
)
def test_bad_atlas_images(image: bytes, reason: str) -> None:
    with pytest.raises(ValidationError) as caught:
        slice_spritesheet(image, BASE.manifest_json)
    assert caught.value.context == {"field": "image", "reason": reason}


def test_atlas_byte_limit_and_types() -> None:
    with pytest.raises(BudgetExceeded) as caught:
        slice_spritesheet(bytes(MAX_SPRITESHEET_IMAGE_BYTES + 1), BASE.manifest_json)
    assert caught.value.context["resource"] == "image_bytes"
    with pytest.raises(TypeError):
        slice_spritesheet(cast(Any, bytearray(BASE.image)), BASE.manifest_json)
    with pytest.raises(TypeError):
        slice_spritesheet(BASE.image, BASE.manifest_json, limits=cast(Any, None))


# --- writing: two files, overwrite and failure semantics ------------------------------


def test_existing_files_are_never_replaced_without_overwrite(tmp_path: Path) -> None:
    image, manifest = tmp_path / "s.png", tmp_path / "s.json"
    manifest.write_bytes(b"old")
    with pytest.raises(ExportError) as caught:
        export_spritesheet(frames(2, 2, 2), image, manifest, columns=2)
    assert caught.value.context == {"reason": "exists", "file_name": "s.json"}
    assert not image.exists() and manifest.read_bytes() == b"old"
    manifest.unlink()
    image.write_bytes(b"old")
    with pytest.raises(ExportError):
        export_spritesheet(frames(2, 2, 2), image, manifest, columns=2)
    assert image.read_bytes() == b"old" and not manifest.exists()
    report = export_spritesheet(frames(2, 2, 2), image, manifest, columns=2, overwrite=True)
    assert image.read_bytes() != b"old" and report.manifest_byte_size == manifest.stat().st_size


def test_manifest_failure_reports_the_committed_atlas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    original = commit_bytes

    detail = ErrorDetail("EXPORT_ERROR", "inner", context={"reason": "io_error"})

    def flaky(data: bytes, destination: Path, *, overwrite: bool) -> None:
        calls.append(destination.name)
        if destination.suffix == ".json":
            raise ExportError(
                "boom",
                json_pointer="/x",
                context={"reason": "io_error", "file_name": destination.name},
                details=[detail],
            )
        original(data, destination, overwrite=overwrite)

    monkeypatch.setattr("moana.export.spritesheet.commit_bytes", flaky)
    with pytest.raises(ExportError) as caught:
        export_spritesheet(frames(2, 2, 2), tmp_path / "s.png", tmp_path / "s.json", columns=1)
    assert calls == ["s.png", "s.json"]  # atlas first, manifest last
    assert caught.value.context == {
        "reason": "io_error",
        "file_name": "s.json",
        "committed": "s.png",
    }
    assert caught.value.details == (detail,) and caught.value.json_pointer == "/x"
    assert (tmp_path / "s.png").exists() and not (tmp_path / "s.json").exists()


def test_invalid_destinations(tmp_path: Path) -> None:
    good = frames(1, 1, 1)
    cases: list[tuple[Any, Any, str]] = [
        (tmp_path / "s.gif", tmp_path / "s.json", "wrong_extension"),
        (tmp_path / "s.png", tmp_path / "s.txt", "wrong_extension"),
        (tmp_path / "s\x00.png", tmp_path / "s.json", "invalid_name"),
        (tmp_path / "s.png", tmp_path / "sub" / "s.json", "separate_directories"),
        (tmp_path / ".png", tmp_path / "s.json", "wrong_extension"),
        (tmp_path / "\udcff.png", tmp_path / "s.json", "invalid_name"),
    ]
    for image, manifest, reason in cases:
        with pytest.raises(ValidationError) as caught:
            export_spritesheet(good, image, manifest, columns=1)
        assert caught.value.context["reason"] == reason
    for image, manifest, overwrite in (
        (b"s.png", "s.json", False),
        (1, "s.json", False),
        ("s.png", "s.json", 1),
    ):
        with pytest.raises(TypeError):
            export_spritesheet(
                good, cast(Any, image), manifest, columns=1, overwrite=cast(Any, overwrite)
            )
    assert list(tmp_path.iterdir()) == []


def test_load_reports_file_problems_without_paths(tmp_path: Path) -> None:
    export_spritesheet(frames(1, 1, 1), tmp_path / "s.png", tmp_path / "s.json", columns=1)
    with pytest.raises(ReadError) as missing:
        load_spritesheet(tmp_path / "s.png", tmp_path / "nope.json")
    assert missing.value.context == {
        "field": "manifest",
        "reason": "not_found",
        "file_name": "nope.json",
    }
    with pytest.raises(ReadError) as folder:
        load_spritesheet(tmp_path, tmp_path / "s.json")
    assert folder.value.context["reason"] == "is_directory"
    assert str(tmp_path) not in folder.value.message
    (tmp_path / "big.json").write_bytes(b" " * (MAX_SPRITESHEET_MANIFEST_BYTES + 1))
    with pytest.raises(BudgetExceeded):
        load_spritesheet(tmp_path / "s.png", tmp_path / "big.json")
    for bad in (b"s.json", 3):
        with pytest.raises(TypeError):
            load_spritesheet(tmp_path / "s.png", cast(Any, bad))
    with pytest.raises(TypeError):
        load_spritesheet(tmp_path / "s.png", tmp_path / "s.json", limits=cast(Any, None))
    with pytest.raises(BudgetExceeded) as small:
        load_spritesheet(
            tmp_path / "s.png", tmp_path / "s.json", limits=RenderLimits(max_buffer_bytes=10)
        )
    assert small.value.context["resource"] == "image_bytes"


def test_load_never_blocks_on_a_fifo(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("no FIFOs on Windows")
    else:
        export_spritesheet(frames(1, 1, 1), tmp_path / "s.png", tmp_path / "s.json", columns=1)
        os.mkfifo(tmp_path / "pipe.json")
        with pytest.raises(ReadError) as caught:
            load_spritesheet(tmp_path / "s.png", tmp_path / "pipe.json")
        assert caught.value.context == {
            "field": "manifest",
            "reason": "not_a_file",
            "file_name": "pipe.json",
        }


def test_load_reports_unreadable_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    export_spritesheet(frames(1, 1, 1), tmp_path / "s.png", tmp_path / "s.json", columns=1)
    for error, reason in ((PermissionError, "permission_denied"), (OSError, "io_error")):

        def refuse(*_: object, error: type[OSError] = error) -> int:
            raise error("refused")

        monkeypatch.setattr("moana.export.spritesheet.os.open", refuse)
        with pytest.raises(ReadError) as caught:
            load_spritesheet(tmp_path / "s.png", tmp_path / "s.json")
        assert caught.value.context["reason"] == reason
        monkeypatch.undo()


class BytesPath:
    def __fspath__(self) -> bytes:
        return b"s.png"


def test_bytes_path_likes_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        export_spritesheet(frames(1, 1, 1), cast(Any, BytesPath()), tmp_path / "s.json", columns=1)
    (tmp_path / "s.json").write_bytes(b"{}")
    with pytest.raises(TypeError):
        load_spritesheet(cast(Any, BytesPath()), tmp_path / "s.json")
    with pytest.raises(TypeError):
        load_spritesheet(tmp_path / "s.png", cast(Any, BytesPath()))


# --- architecture ----------------------------------------------------------------------

EXPORT = Path(sheet_module.__file__).parent
FORBIDDEN = ("moana.render", "moana.animation", "moana.editing", "moana.api", "moana.cli")
ALLOWED_ROOTS = {"moana", "numpy", "PIL"}


def test_export_imports_only_core_palette_and_libraries() -> None:
    import sys

    for path in sorted(EXPORT.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            for name in names:
                root = name.split(".")[0]
                assert root in sys.stdlib_module_names or root in ALLOWED_ROOTS, name
                assert not name.startswith(FORBIDDEN), f"{path.name} imports {name}"
                if root == "moana":
                    assert name.startswith(("moana.core", "moana.palette", "moana.export")), name
