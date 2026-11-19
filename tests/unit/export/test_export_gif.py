"""Animated GIF export with explicit losses (MOANA-024, ADR-034).

Expected pixels, palettes, durations and header bytes are written by hand; every GIF
is decoded with Pillow directly (``seek`` + ``convert("RGBA")``, alpha 0 normalised to
``(0, 0, 0, 0)``), independently of the exporter's own verification.
"""

from __future__ import annotations

import ast
import io
import struct
import tracemalloc
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PIL import Image

from moana.core.budget import RenderLimits
from moana.core.coordinates import Point
from moana.core.errors import BudgetExceeded, ExportError, ValidationError
from moana.core.limits import GeometryLimits
from moana.export import (
    GIF_MEDIA_TYPE,
    GifLoss,
    GifWarning,
    encode_gif,
    encode_spritesheet,
    export_gif,
)
from moana.export import gif as gif_module
from moana.export._frames import equivalent_timeline
from moana.palette import Palette, PaletteColor, Rgba

RGBA = tuple[int, int, int, int]
CLEAR: RGBA = (0, 0, 0, 0)
RED: RGBA = (255, 0, 0, 255)
GREEN: RGBA = (0, 255, 0, 255)
BLUE: RGBA = (0, 0, 255, 255)


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


def raster(pixels: list[list[RGBA]]) -> Raster:
    return Raster(len(pixels[0]), len(pixels), bytes(c for row in pixels for p in row for c in p))


def frame(frame_id: str, pixels: list[list[RGBA]], duration: int = 100) -> Frame:
    return Frame(frame_id, duration, Point(0, 0), raster(pixels))


def solid(frame_id: str, color: RGBA, size: int = 2, duration: int = 100) -> Frame:
    return frame(frame_id, [[color] * size for _ in range(size)], duration)


def decode(data: bytes) -> tuple[list[list[RGBA]], list[int], dict[Any, Any]]:
    """Composited RGBA (normalised) and duration of every frame, plus the file info."""
    pixels: list[list[RGBA]] = []
    durations: list[int] = []
    with Image.open(io.BytesIO(data)) as image:
        info: dict[Any, Any] = dict(image.info)
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            raw = image.convert("RGBA").tobytes()
            values = [cast(RGBA, tuple(raw[i : i + 4])) for i in range(0, len(raw), 4)]
            pixels.append([value if value[3] else CLEAR for value in values])
            durations.append(image.info["duration"])
    return pixels, durations, info


def flat(pixels: list[list[RGBA]]) -> list[RGBA]:
    return [value for row in pixels for value in row]


def global_palette(data: bytes) -> list[tuple[int, int, int]]:
    size = 2 << (data[10] & 7)
    table = data[13 : 13 + 3 * size]
    return [cast(tuple[int, int, int], tuple(table[i : i + 3])) for i in range(0, len(table), 3)]


def skip_sub_blocks(data: bytes, position: int) -> int:
    while (length := data[position]) != 0:
        position += 1 + length
    return position + 1


def blocks(data: bytes) -> list[tuple[str, bytes]]:
    """Walk a GIF: header, screen and table, then extensions and images until ``;``.

    Returns ``(kind, bytes)`` with ``kind`` ``ext:<label>`` (the whole extension) or
    ``image`` (the 10-byte descriptor); fails on anything else.
    """
    assert data[:6] == b"GIF89a"
    flags = data[10]
    position = 13 + (3 << ((flags & 7) + 1) if flags & 0x80 else 0)
    found: list[tuple[str, bytes]] = []
    while data[position] != 0x3B:
        if data[position] == 0x21:
            end = skip_sub_blocks(data, position + 2)
            found.append((f"ext:{data[position + 1]:02x}", data[position:end]))
            position = end
        else:
            assert data[position] == 0x2C and not data[position + 9] & 0x80  # no local table
            found.append(("image", data[position : position + 10]))
            position = skip_sub_blocks(data, position + 11)
    assert position == len(data) - 1
    return found


def controls(data: bytes) -> list[bytes]:
    """Every graphic control extension (8 bytes), found by walking the blocks."""
    return [block for kind, block in blocks(data) if kind == "ext:f9"]


def netscape(data: bytes) -> list[bytes]:
    return [block for kind, block in blocks(data) if kind == "ext:ff"]


def distinct(count: int, *, offset: int = 0) -> list[RGBA]:
    return [((i + offset) % 256, (i + offset) // 256, 7, 255) for i in range(count)]


def grid(colors: list[RGBA], width: int = 16) -> list[list[RGBA]]:
    return [colors[y * width : (y + 1) * width] for y in range(len(colors) // width)]


# --- T1: palette, transparency, alpha and disposal ------------------------------------


def test_full_palette_of_256_opaque_colours() -> None:
    colors = distinct(256)[::-1]  # written in reverse: the palette is sorted by (r, g, b)
    encoded = encode_gif([frame("a", grid(colors))])
    assert (encoded.palette_size, encoded.transparent_index) == (256, None)
    assert global_palette(encoded.data) == [(i, 0, 7) for i in range(256)]
    assert controls(encoded.data) == [b"!\xf9\x04\x08\x0a\x00\x00\x00"]  # disposal 2, no tRNS
    pixels, _, info = decode(encoded.data)
    assert pixels[0] == colors and "transparency" not in info


def test_255_opaque_colours_plus_transparency() -> None:
    colors = [CLEAR, *distinct(255)]
    encoded = encode_gif([frame("a", grid(colors))])
    assert (encoded.palette_size, encoded.transparent_index) == (256, 0)
    assert global_palette(encoded.data) == [(0, 0, 0)] + [(i, 0, 7) for i in range(255)]
    assert controls(encoded.data) == [b"!\xf9\x04\x09\x0a\x00\x00\x00"]  # disposal 2 + tRNS 0
    pixels, _, info = decode(encoded.data)
    assert pixels[0] == colors and info["transparency"] == 0


def test_256_opaque_colours_plus_transparency_is_rejected() -> None:
    frames = [frame("a", grid(distinct(256))), solid("b", CLEAR, 16)]
    with pytest.raises(ValidationError) as caught:
        encode_gif(frames)
    assert caught.value.context == {
        "field": "palette",
        "reason": "too_many_colors",
        "maximum": 256,
        "count": 257,
    }


def test_more_than_256_colours_across_frames_is_rejected_early() -> None:
    frames = [frame("a", grid(distinct(256))), frame("b", grid(distinct(256, offset=256)))]
    with pytest.raises(ValidationError) as caught:
        encode_gif(frames)
    assert caught.value.context["reason"] == "too_many_colors"
    assert caught.value.context["count"] == 512


def test_palette_is_shared_and_sorted_by_rgb() -> None:
    encoded = encode_gif([solid("a", BLUE), solid("b", RED), solid("c", GREEN)])
    # Sorted ascending by (r, g, b): blue (0,0,255) < green (0,255,0) < red (255,0,0).
    assert global_palette(encoded.data)[:3] == [(0, 0, 255), (0, 255, 0), (255, 0, 0)]
    assert encoded.palette_size == 3 and len(global_palette(encoded.data)) == 4
    assert encoded.data.count(b",\x00\x00\x00\x00\x02\x00\x02\x00\x00") == 3  # no local tables


def test_partial_alpha_is_rejected_without_background() -> None:
    pixels = [[RED, (200, 100, 0, 128)], [CLEAR, RED]]
    with pytest.raises(ValidationError) as caught:
        encode_gif([solid("a", RED), frame("b", pixels)])
    assert caught.value.context == {
        "field": "frames",
        "reason": "partial_alpha",
        "index": 1,
        "x": 1,
        "y": 0,
        "pixels": 1,
    }


def test_partial_alpha_is_flattened_exactly_with_background() -> None:
    pixels = [[(200, 100, 0, 128), (255, 255, 255, 1)], [CLEAR, (10, 20, 30, 254)]]
    encoded = encode_gif([frame("a", pixels)], background=Rgba(0, 0, 255, 255))
    # (c·a + b·(255 - a) + 127) // 255, by hand:
    # r: (200·128 + 127) // 255 = 100; g: (100·128 + 127) // 255 = 50;
    # b: (255·127 + 127) // 255 = 127. White at alpha 1 over blue: (255 + 127) // 255 = 1
    # for r and g, (255 + 255·254 + 127) // 255 = 255 for b. (10, 20, 30, 254):
    # (2540 + 127) // 255 = 10, (5080 + 127) // 255 = 20, (7620 + 255 + 127) // 255 = 31.
    expected = [(100, 50, 127, 255), (1, 1, 255, 255), CLEAR, (10, 20, 31, 255)]
    decoded, _, _ = decode(encoded.data)
    assert decoded[0] == expected
    assert encoded.losses == (GifLoss("alpha_flattened", "a", 3, 0),)
    assert encoded.transparent_index == 0  # alpha 0 stays transparent


def test_background_must_be_opaque_and_typed() -> None:
    with pytest.raises(ValidationError) as caught:
        encode_gif([solid("a", RED)], background=Rgba(0, 0, 0, 254))
    assert caught.value.context == {"field": "background", "reason": "not_opaque"}
    with pytest.raises(TypeError):
        encode_gif([solid("a", RED)], background=cast(Any, (0, 0, 0)))


def test_background_disposal_never_shows_an_older_frame_through_a_hole() -> None:
    hole = [[CLEAR, RED], [RED, RED]]
    encoded = encode_gif([solid("a", GREEN), frame("b", hole), solid("c", CLEAR)])
    decoded, _, _ = decode(encoded.data)
    assert decoded[0] == [GREEN] * 4
    assert decoded[1] == [CLEAR, RED, RED, RED]  # not GREEN at (0, 0)
    assert decoded[2] == [CLEAR] * 4  # a fully transparent frame stays empty
    assert [block[3] >> 2 & 7 for block in controls(encoded.data)] == [2, 2, 2]
    assert encoded.data.count(b"GIF89a") == 1  # one header (Pillow's writer adds a second)


def test_none_disposal_rejects_frames_that_reveal_the_previous_one() -> None:
    hole = [[CLEAR, RED], [RED, RED]]
    with pytest.raises(ValidationError) as caught:
        encode_gif([solid("a", GREEN), frame("b", hole)], disposal="none")
    assert caught.value.context == {
        "field": "disposal",
        "reason": "disposal_reveals_previous",
        "index": 1,
    }
    encoded = encode_gif([frame("a", hole), solid("b", GREEN)], disposal="none", loop_count=1)
    assert [block[3] >> 2 & 7 for block in controls(encoded.data)] == [1, 1]
    decoded, _, _ = decode(encoded.data)
    assert decoded[1] == [GREEN] * 4


def test_a_file_whose_disposal_shows_older_frames_never_verifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Disposal 1 written while "background" is requested: Pillow composes GREEN through
    # the hole, so the decoded timeline differs and nothing is returned.
    monkeypatch.setattr(gif_module, "_DISPOSAL_CODES", {"background": 1, "none": 1})
    with pytest.raises(ExportError) as caught:
        encode_gif([solid("a", GREEN), frame("b", [[CLEAR, RED], [RED, RED]])])
    assert caught.value.context == {"reason": "timeline_mismatch"}


def palette(*values: RGBA, profile: Any = "strict") -> Palette:
    return Palette(
        "p",
        profile,
        tuple(PaletteColor(f"c{index}", Rgba(*value)) for index, value in enumerate(values)),
    )


def test_declared_palette_keeps_its_order_and_appends_transparency() -> None:
    encoded = encode_gif(
        [frame("a", [[CLEAR, RED], [GREEN, RED]])], palette=palette(GREEN, RED, BLUE)
    )
    assert global_palette(encoded.data) == [(0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 0, 0)]
    assert (encoded.palette_size, encoded.transparent_index) == (4, 3)
    with Image.open(io.BytesIO(encoded.data)) as image:
        assert image.mode == "P" and list(image.tobytes()) == [3, 1, 0, 1]
    declared = encode_gif([frame("a", [[CLEAR, RED]])], palette=palette(RED, CLEAR, GREEN))
    assert (declared.palette_size, declared.transparent_index) == (3, 1)
    opaque = encode_gif([solid("a", RED)], palette=palette(RED, CLEAR))
    assert opaque.transparent_index == 1  # a declared transparent entry is kept


def test_declared_palette_limits_and_misses() -> None:
    full = palette(*distinct(256), profile="rgba")
    assert encode_gif([solid("a", (5, 0, 7, 255))], palette=full).palette_size == 256
    with pytest.raises(ValidationError) as caught:
        encode_gif([solid("a", CLEAR)], palette=full)
    assert caught.value.context["reason"] == "too_many_colors"
    with pytest.raises(ValidationError) as too_long:
        encode_gif([solid("a", (5, 0, 7, 255))], palette=palette(*distinct(257), profile="rgba"))
    assert too_long.value.context["count"] == 257
    with pytest.raises(ValidationError) as missing:
        encode_gif([solid("a", RED), solid("b", BLUE)], palette=palette(RED))
    assert missing.value.context == {
        "field": "palette",
        "reason": "color_not_in_palette",
        "x": 0,
        "y": 0,
        "pixels": 4,
        "index": 1,
    }


def test_declared_palette_partial_alpha_entries() -> None:
    translucent = palette(RED, (200, 100, 0, 128), profile="rgba")
    with pytest.raises(ValidationError) as caught:
        encode_gif([solid("a", RED)], palette=translucent)
    assert caught.value.context == {"field": "palette", "reason": "partial_alpha", "index": 1}
    encoded = encode_gif(
        [frame("a", [[(200, 100, 0, 128), RED]])],
        palette=translucent,
        background=Rgba(0, 0, 255, 255),
    )
    assert global_palette(encoded.data)[:2] == [(255, 0, 0), (100, 50, 127)]


# --- T2: duplicates, loop, short durations, accumulated decode ------------------------


def test_duplicated_frames_keep_an_equivalent_timeline() -> None:
    frames = [
        solid("a", RED, duration=100),
        solid("b", RED, duration=200),
        solid("c", BLUE, duration=300),
    ]
    encoded = encode_gif(frames)
    assert (encoded.frames, encoded.encoded_frames) == (3, 3)
    decoded, durations, _ = decode(encoded.data)
    assert durations == [100, 200, 300] and sum(durations) == 600
    assert decoded == [[RED] * 4, [RED] * 4, [BLUE] * 4]
    assert encoded.frame_digests[0] == encoded.frame_digests[1] != encoded.frame_digests[2]


def test_equivalent_timeline_merges_equal_neighbours() -> None:
    timeline = [("x", 100), ("x", 200), ("y", 300), ("x", 10)]
    assert equivalent_timeline(timeline) == [("x", 300), ("y", 300), ("x", 10)]
    assert equivalent_timeline([]) == []


def test_verification_accepts_a_decoder_that_merges_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = gif_module._decoded

    def merging(data: bytes, width: int, height: int) -> tuple[Any, object]:
        timeline, loop = original(data, width, height)
        return equivalent_timeline(timeline), loop

    monkeypatch.setattr(gif_module, "_decoded", merging)
    frames = [solid("a", RED, duration=100), solid("b", RED, duration=200)]
    assert encode_gif(frames).encoded_frames == 1  # time and image preserved, count not

    def losing_time(data: bytes, width: int, height: int) -> tuple[Any, object]:
        timeline, loop = original(data, width, height)
        return [(digest, 10) for digest, _ in timeline], loop

    monkeypatch.setattr(gif_module, "_decoded", losing_time)
    with pytest.raises(ExportError) as caught:
        encode_gif(frames)
    assert caught.value.context == {"reason": "timeline_mismatch"}


APP = b"!\xff\x0bNETSCAPE2.0\x03\x01"


@pytest.mark.parametrize(
    ("loop_count", "blocks_written", "pillow_loop"),
    [
        # Moana counts plays (0: infinite); NETSCAPE counts repeats after the first.
        (0, [APP + b"\x00\x00\x00"], 0),
        (1, [], None),  # a single play: no block at all
        (2, [APP + b"\x01\x00\x00"], 1),
        (7, [APP + b"\x06\x00\x00"], 6),
        (65_535, [APP + b"\xfe\xff\x00"], 65_534),
    ],
)
def test_loop_count_roundtrips(
    loop_count: int, blocks_written: list[bytes], pillow_loop: int | None
) -> None:
    encoded = encode_gif([solid("a", RED), solid("b", BLUE)], loop_count=loop_count)
    assert netscape(encoded.data) == blocks_written
    _, _, info = decode(encoded.data)
    assert info.get("loop") == pillow_loop and encoded.loop_count == loop_count


def test_loop_mismatch_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    original = gif_module._decoded
    monkeypatch.setattr(
        gif_module, "_decoded", lambda *args: (original(*args)[0], None)
    )  # a decoder that loses the NETSCAPE block
    with pytest.raises(ExportError) as caught:
        encode_gif([solid("a", RED)], loop_count=2)
    assert caught.value.context == {"reason": "loop_mismatch"}


def test_short_durations_and_rounding_policy() -> None:
    ok = encode_gif([solid("a", RED, duration=10), solid("b", BLUE, duration=20)])
    assert ok.durations_ms == (10, 20) and ok.warnings == (GifWarning("short_delay", "a"),)
    many = encode_gif([solid("a", RED, duration=10), solid("b", BLUE, duration=10)])
    assert [warning.frame_id for warning in many.warnings] == ["a", "b"]
    assert ok.warnings[0].to_mapping() == {"frame_id": "a", "kind": "short_delay"}
    assert encode_gif([solid("a", RED, duration=20)]).warnings == ()
    for requested in (5, 15, 1, 59_999):
        with pytest.raises(ValidationError) as caught:
            encode_gif([solid("a", RED), solid("b", BLUE, duration=requested)])
        assert caught.value.context == {
            "field": "frames",
            "reason": "duration_not_representable",
            "index": 1,
            "duration_ms": requested,
        }
    asked = [5, 15, 1, 14, 25, 60_000, 59_995]
    frames = [solid(f"f{i}", (i, 0, 0, 255), duration=d) for i, d in enumerate(asked)]
    encoded = encode_gif(frames, duration_policy="round")
    # max(10, 10·⌊(d + 5) / 10⌋): ties round up, never below 10 ms.
    assert encoded.durations_ms == (10, 20, 10, 10, 30, 60_000, 60_000)
    assert encoded.losses == (
        GifLoss("duration_rounded", "f0", 5, 10),
        GifLoss("duration_rounded", "f1", 15, 20),
        GifLoss("duration_rounded", "f2", 1, 10),
        GifLoss("duration_rounded", "f3", 14, 10),
        GifLoss("duration_rounded", "f4", 25, 30),
        GifLoss("duration_rounded", "f6", 59_995, 60_000),
    )
    _, durations, _ = decode(encoded.data)
    assert durations == [10, 20, 10, 10, 30, 60_000, 60_000]
    assert [struct.unpack("<H", block[4:6])[0] for block in controls(encoded.data)] == [
        1, 2, 1, 1, 3, 6000, 6000,
    ]  # fmt: skip


def test_accumulated_decode_equals_every_target_frame() -> None:
    targets = [
        [[RED, CLEAR, CLEAR], [CLEAR, CLEAR, CLEAR]],
        [[RED, GREEN, CLEAR], [CLEAR, CLEAR, BLUE]],
        [[CLEAR, CLEAR, CLEAR], [BLUE, BLUE, BLUE]],
        [[GREEN, GREEN, GREEN], [GREEN, GREEN, GREEN]],
        [[CLEAR, RED, CLEAR], [CLEAR, CLEAR, CLEAR]],
    ]
    encoded = encode_gif([frame(f"f{i}", target, 10 * (i + 1)) for i, target in enumerate(targets)])
    decoded, durations, _ = decode(encoded.data)
    assert decoded == [flat(t) for t in targets] and durations == [10, 20, 30, 40, 50]


# --- AC2: unrepresentable colours and times ------------------------------------------


@pytest.mark.parametrize(
    ("frames", "accept", "reason", "kind"),
    [
        ([solid("a", (1, 2, 3, 77))], {"background": Rgba(0, 0, 0, 255)}, "partial_alpha", "alpha"),
        ([solid("a", RED, duration=33)], {"duration_policy": "round"}, "duration", "duration"),
    ],
)
def test_losses_need_explicit_acceptance(
    frames: list[Frame], accept: dict[str, Any], reason: str, kind: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        encode_gif(frames)
    assert str(caught.value.context["reason"]).startswith(reason)
    encoded = encode_gif(frames, **accept)
    assert len(encoded.losses) == 1 and encoded.losses[0].kind.startswith(kind)


def test_colours_beyond_the_table_are_never_quantised() -> None:
    frames = [frame("a", grid(distinct(256))), frame("b", grid(distinct(256, offset=300)))]
    for options in ({}, {"background": Rgba(0, 0, 0, 255)}, {"duration_policy": "round"}):
        with pytest.raises(ValidationError) as caught:
            encode_gif(frames, **cast(Any, options))
        assert caught.value.context["reason"] == "too_many_colors"


# --- determinism ----------------------------------------------------------------------


def test_identical_input_gives_identical_bytes_and_a_known_header() -> None:
    frames = [solid("a", RED, 1), solid("b", CLEAR, 1)]
    first, second = encode_gif(frames).data, encode_gif(list(frames)).data
    assert first == second
    # 1x1, GCT of 2 entries (flags 0xF0): transparent (0,0,0) then red.
    assert first.startswith(b"GIF89a\x01\x00\x01\x00\xf0\x00\x00" + bytes(3) + b"\xff\x00\x00")
    assert first.endswith(b";")


COLORS = st.sampled_from([CLEAR, RED, GREEN, BLUE, (9, 9, 9, 255), (255, 255, 255, 255)])


@st.composite
def timelines(draw: st.DrawFn) -> list[Frame]:
    width = draw(st.integers(1, 4))
    height = draw(st.integers(1, 4))
    count = draw(st.integers(1, 6))
    return [
        frame(
            f"f{index}",
            [[draw(COLORS) for _ in range(width)] for _ in range(height)],
            10 * draw(st.integers(1, 30)),
        )
        for index in range(count)
    ]


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(timelines(), st.integers(0, 3))
def test_decoded_timeline_equals_the_target(frames: list[Frame], loop_count: int) -> None:
    encoded = encode_gif(frames, loop_count=loop_count)
    decoded, durations, info = decode(encoded.data)
    expected = [
        [[cast(RGBA, tuple(f.result.rgba[i : i + 4])) for i in range(0, len(f.result.rgba), 4)]]
        for f in frames
    ]
    assert decoded == [row[0] for row in expected]
    assert durations == [f.duration_ms for f in frames]
    assert info.get("loop") == {0: 0, 1: None}.get(loop_count, loop_count - 1)
    assert encoded.data == encode_gif(frames, loop_count=loop_count).data


OPAQUE = st.sampled_from([RED, GREEN, BLUE, (9, 9, 9, 255)])


@st.composite
def unrevealing(draw: st.DrawFn) -> tuple[list[Frame], int]:
    """Timelines valid for disposal none: transparency only shrinks frame to frame.

    With a single play (``loop_count == 1``) frame 0 may have more holes than the last
    frame; when the animation wraps, every frame keeps the same holes.
    """
    width, height = draw(st.integers(1, 4)), draw(st.integers(1, 4))
    loop_count = draw(st.sampled_from([0, 1, 3]))
    count = draw(st.integers(1, 6))
    clear = [[draw(st.booleans()) for _ in range(width)] for _ in range(height)]
    frames: list[Frame] = []
    for index in range(count):
        rows = []
        for y in range(height):
            row: list[RGBA] = []
            for x in range(width):
                hole = clear[y][x] and (loop_count != 1 or draw(st.booleans()))
                clear[y][x] = hole
                row.append(CLEAR if hole else draw(OPAQUE))
            rows.append(row)
        frames.append(frame(f"f{index}", rows, 10 * draw(st.integers(1, 30))))
    return frames, loop_count


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(unrevealing())
def test_none_disposal_timeline_equals_the_target(case: tuple[list[Frame], int]) -> None:
    frames, loop_count = case
    encoded = encode_gif(frames, loop_count=loop_count, disposal="none")
    decoded, durations, _ = decode(encoded.data)
    assert decoded == [
        [cast(RGBA, tuple(f.result.rgba[i : i + 4])) for i in range(0, len(f.result.rgba), 4)]
        for f in frames
    ]
    assert durations == [f.duration_ms for f in frames]
    assert [block[3] >> 2 & 7 for block in controls(encoded.data)] == [1] * len(frames)


# --- frames, options and budget -------------------------------------------------------


GOOD = solid("a", RED)


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        (solid("b", RED, size=3), "size_mismatch"),
        (replace(GOOD, frame_id="Bad"), "invalid_id"),
        (GOOD, "duplicate_frame"),
        (replace(GOOD, frame_id="b", duration_ms=0), "invalid_duration"),
        (replace(GOOD, frame_id="b", duration_ms=60_001), "invalid_duration"),
        (replace(GOOD, frame_id="b", duration_ms=cast(Any, True)), "invalid_duration"),
        (replace(GOOD, frame_id="b", result=Raster(2, 2, bytes(15))), "wrong_size"),
        (
            replace(GOOD, frame_id="b", result=Raster(2, 2, bytes([0, 9, 0, 0]) + bytes(12))),
            "not_normalized",
        ),
    ],
)
def test_invalid_frames_are_located(bad: Frame, reason: str) -> None:
    with pytest.raises(ValidationError) as caught:
        encode_gif([GOOD, bad])
    assert caught.value.context["reason"] == reason and caught.value.context["index"] == 1


def test_option_and_container_errors() -> None:
    with pytest.raises(ValidationError) as empty:
        encode_gif([])
    assert empty.value.context == {"field": "frames", "reason": "empty_frames"}
    for value in ("ab", b"ab", 3):
        with pytest.raises(TypeError):
            encode_gif(cast(Any, value))
    for item in (object(), Frame("a", 100, Point(0, 0), cast(Any, object()))):
        with pytest.raises(TypeError, match="sprite frame"):
            encode_gif(cast(Any, [GOOD, item]))
    with pytest.raises(TypeError):
        encode_gif([replace(GOOD, result=Raster(2, 2, cast(Any, bytearray(16))))])
    cases: list[tuple[dict[str, Any], str, str]] = [
        ({"loop_count": -1}, "loop_count", "out_of_range"),
        ({"loop_count": 65_536}, "loop_count", "out_of_range"),
        ({"loop_count": True}, "loop_count", "not_integer"),
        ({"duration_policy": "floor"}, "duration_policy", "unknown_duration_policy"),
        ({"duration_policy": ["exact"]}, "duration_policy", "unknown_duration_policy"),
        ({"duration_policy": np.str_("exact")}, "duration_policy", "unknown_duration_policy"),
        ({"disposal": "previous"}, "disposal", "unknown_disposal"),
        ({"disposal": {"none": 1}}, "disposal", "unknown_disposal"),
        ({"disposal": np.str_("none")}, "disposal", "unknown_disposal"),
    ]
    for options, field, reason in cases:
        with pytest.raises(ValidationError) as caught:
            encode_gif([GOOD], **options)
        assert (caught.value.context["field"], caught.value.context["reason"]) == (field, reason)
    for options in ({"palette": "p"}, {"limits": None}):
        with pytest.raises(TypeError):
            encode_gif([GOOD], **cast(Any, options))


@pytest.mark.parametrize(
    ("count", "size", "limits", "resource"),
    [
        pytest.param(5, 4, RenderLimits(max_frame_pixels=79), "frame_pixels", id="pixels"),
        pytest.param(
            1, 9, RenderLimits(geometry=GeometryLimits(max_dimension=8)), "export_dimension",
            id="dimension",
        ),
        pytest.param(
            1, 9, RenderLimits(geometry=GeometryLimits(max_area=80)), "export_area", id="area"
        ),
        # 48·16 + 4·5·16 = 1088 bytes.
        pytest.param(5, 4, RenderLimits(max_buffer_bytes=1087), "buffer_bytes", id="bytes"),
    ],
)  # fmt: skip
def test_budget_is_checked_before_any_pixel_is_read(
    monkeypatch: pytest.MonkeyPatch, count: int, size: int, limits: RenderLimits, resource: str
) -> None:
    def no_pixels(*_: object, **__: object) -> None:
        raise AssertionError("pixels read before the budget check")

    monkeypatch.setattr("moana.export.gif.np.frombuffer", no_pixels)
    frames = [solid(f"f{i}", RED, size) for i in range(count)]
    with pytest.raises(BudgetExceeded) as caught:
        encode_gif(frames, limits=limits)
    assert [detail.context["resource"] for detail in caught.value.details] == [resource]


def test_exact_budget_is_admitted_and_every_resource_reported() -> None:
    frames = [solid(f"f{i}", RED, 4) for i in range(5)]
    encode_gif(frames, limits=RenderLimits(max_frame_pixels=80, max_buffer_bytes=1088))
    limits = RenderLimits(
        max_frame_pixels=1, max_buffer_bytes=1, geometry=GeometryLimits(max_dimension=1, max_area=1)
    )
    with pytest.raises(BudgetExceeded) as caught:
        encode_gif(frames, limits=limits)
    assert [detail.context["resource"] for detail in caught.value.details] == [
        "frame_pixels",
        "export_dimension",
        "export_area",
        "buffer_bytes",
    ]
    assert caught.value.context == {"resource": "frame_pixels", "limit": 1, "estimated": 80}


def test_too_many_frames_is_rejected_before_reading_any_frame() -> None:
    class Untouchable:
        @property
        def result(self) -> Raster:
            raise AssertionError("frame read")

    with pytest.raises(BudgetExceeded) as caught:
        encode_gif(cast(Any, [Untouchable()] * 257))
    assert caught.value.context == {"resource": "frames", "limit": 256, "estimated": 257}
    assert len(caught.value.details) == 1


def test_rejected_large_gif_allocates_almost_nothing() -> None:
    shared = Raster(2048, 2048, bytes(2048 * 2048 * 4))
    frames = [Frame(f"f{i}", 100, Point(0, 0), shared) for i in range(4)]
    tracemalloc.start()
    try:
        with pytest.raises(BudgetExceeded) as caught:
            encode_gif(frames, limits=RenderLimits(max_buffer_bytes=64 * 1024 * 1024))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    area = 2048 * 2048
    assert caught.value.context["resource"] == "buffer_bytes"
    assert caught.value.context["estimated"] == 48 * area + 4 * 4 * area
    assert peak < 1024 * 1024


def test_admitted_gif_stays_within_its_traced_estimate() -> None:
    rng = np.random.default_rng(0)
    indices = rng.integers(0, 255, size=(256, 256))
    colors = np.array(distinct(255), dtype=np.uint8)
    frames = [
        Frame(f"f{i}", 100, Point(0, 0), Raster(256, 256, colors[np.roll(indices, i)].tobytes()))
        for i in range(3)
    ]
    tracemalloc.start()
    try:
        encoded = encode_gif(frames)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    area = 256 * 256
    assert len(encoded.data) <= 4 * 3 * area  # worst-case LZW bound of the output term
    assert peak < 48 * area + 4 * 3 * area


# --- LZW extraction and decoding failures --------------------------------------------

DESCRIPTOR = b"," + struct.pack("<HHHHB", 0, 0, 1, 1, 0)


@pytest.mark.parametrize(
    "single",
    [
        b"GIF89a",
        b"PNG89a" + bytes(7) + DESCRIPTOR + b"\x08\x01\x00\x00;",
        b"GIF89a" + bytes(7) + b"!\xfe\x03ab",  # extension without its terminator
        b"GIF89a" + bytes(7) + b"!\xfe\x00" + b"\x2c" + bytes(9) + b"\x08\x00;",  # wrong size
        b"GIF89a" + bytes(7) + DESCRIPTOR + b"\x08\x05\x00",
        b"GIF89a" + bytes(7) + DESCRIPTOR + b"\x08\x00;junk",
        b"GIF89a" + bytes(7) + DESCRIPTOR + b"\x09\x00;",
    ],
)
def test_unexpected_encoder_output_is_an_export_error(single: bytes) -> None:
    with pytest.raises(ExportError) as caught:
        gif_module._image_data(single, 1, 1)
    assert caught.value.context == {"reason": "encoder_layout"}


def test_encoder_output_with_a_colour_table_is_parsed() -> None:
    single = b"GIF87a" + b"\x01\x00\x01\x00\x80\x00\x00" + bytes(6) + DESCRIPTOR + b"\x08\x00;"
    assert gif_module._image_data(single, 1, 1) == b"\x08\x00"
    # Well-formed extensions before the descriptor (a comment, a control block) are skipped.
    extensions = b"!\xfe\x02hi\x00" + b"!\xf9\x04\x00\x00\x00\x00\x00"
    single = b"GIF89a" + bytes(7) + extensions + DESCRIPTOR + b"\x08\x02\x01\x02\x00;"
    assert gif_module._image_data(single, 1, 1) == b"\x08\x02\x01\x02\x00"


def test_a_gif_frame_without_a_duration_is_unreadable() -> None:
    # No graphic control extension: Pillow reports no duration (ADR-035 kept this reason).
    buffer = io.BytesIO()
    Image.new("P", (2, 2), 0).save(buffer, format="GIF")
    with pytest.raises(ExportError) as caught:
        gif_module._decoded(buffer.getvalue(), 2, 2)
    assert caught.value.context == {"reason": "unreadable_gif"}


def test_decoding_failures_never_return_a_gif(monkeypatch: pytest.MonkeyPatch) -> None:
    data = encode_gif([GOOD]).data
    with pytest.raises(ExportError) as size:
        gif_module._decoded(data, 3, 2)
    assert size.value.context == {"reason": "timeline_mismatch"}

    def broken(*_: object, **__: object) -> None:
        raise OSError("truncated")

    monkeypatch.setattr("moana.export.gif.Image.open", broken)
    with pytest.raises(ExportError) as caught:
        encode_gif([GOOD])
    assert caught.value.context == {"reason": "unreadable_gif"}


# --- writing --------------------------------------------------------------------------


def test_export_writes_and_reports(tmp_path: Path) -> None:
    destination = tmp_path / "anim.gif"
    report = export_gif(
        [solid("a", RED, duration=15), solid("b", CLEAR)],
        destination,
        loop_count=3,
        duration_policy="round",
    )
    data = destination.read_bytes()
    assert report.path == str(destination) and report.media_type == GIF_MEDIA_TYPE == "image/gif"
    assert (report.width, report.height, report.frames, report.encoded_frames) == (2, 2, 2, 2)
    assert (report.durations_ms, report.duration_ms, report.loop_count) == ((20, 100), 120, 3)
    assert (report.palette_size, report.transparent_index, report.disposal) == (2, 0, "background")
    assert report.byte_size == len(data) and report.file_sha256.startswith("sha256:")
    mapping = report.to_mapping()
    assert list(mapping) == sorted(mapping)
    assert mapping["losses"] == [
        {"kind": "duration_rounded", "frame_id": "a", "requested": 15, "effective": 20}
    ]
    assert mapping["durations_ms"] == [20, 100] and mapping["warnings"] == []
    assert mapping["background"] is None and report.background is None
    assert isinstance(mapping["frame_digests"], list) and len(mapping["frame_digests"]) == 2


def test_existing_files_are_never_replaced_without_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "a.gif"
    destination.write_bytes(b"old")
    with pytest.raises(ExportError) as caught:
        export_gif([GOOD], destination)
    assert caught.value.context == {"reason": "exists", "file_name": "a.gif"}
    assert destination.read_bytes() == b"old"
    export_gif([GOOD], destination, overwrite=True)
    assert destination.read_bytes().startswith(b"GIF89a")


def test_invalid_destinations_and_failed_encodes_write_nothing(tmp_path: Path) -> None:
    for path, reason in (
        (tmp_path / "a.png", "wrong_extension"),
        (tmp_path / ".gif", "wrong_extension"),
        (tmp_path / "a\x00.gif", "invalid_name"),
    ):
        with pytest.raises(ValidationError) as caught:
            export_gif([GOOD], path)
        assert caught.value.context == {"field": "path", "reason": reason}
    bad_calls: list[tuple[Any, Any]] = [(b"a.gif", False), (tmp_path / "a.gif", 1)]
    for bad_path, overwrite in bad_calls:
        with pytest.raises(TypeError):
            export_gif([GOOD], bad_path, overwrite=overwrite)
    with pytest.raises(ValidationError):
        export_gif([solid("a", RED, duration=15)], tmp_path / "a.gif")
    assert list(tmp_path.iterdir()) == []


# --- review follow-ups -----------------------------------------------------------------


def test_screen_background_index_is_the_transparent_index() -> None:
    encoded = encode_gif([frame("a", [[CLEAR, RED]])], palette=palette(GREEN, RED, BLUE))
    assert encoded.transparent_index == 3
    # Screen descriptor: width 2, height 1, GCT flags (4 entries: 0xF1), background 3.
    assert encoded.data[6:13] == b"\x02\x00\x01\x00\xf1\x03\x00"
    opaque = encode_gif([solid("a", RED)])
    assert opaque.transparent_index is None and opaque.data[11] == 0


def test_none_disposal_checks_the_loop_seam() -> None:
    hole = [[CLEAR, RED], [RED, RED]]
    frames = [frame("a", hole), solid("b", GREEN)]  # frame 0 after b would show GREEN
    for loop_count in (0, 2):
        with pytest.raises(ValidationError) as caught:
            encode_gif(frames, disposal="none", loop_count=loop_count)
        assert caught.value.context == {
            "field": "disposal",
            "reason": "disposal_reveals_previous",
            "index": 0,
        }
    assert encode_gif(frames, disposal="none", loop_count=1).encoded_frames == 2
    assert encode_gif([frame("a", hole)], disposal="none").encoded_frames == 1


def test_loss_mapping_keys_are_sorted() -> None:
    mapping = GifLoss("duration_rounded", "a", 15, 20).to_mapping()
    assert list(mapping) == ["effective", "frame_id", "kind", "requested"]


def test_flatten_background_is_reported_for_reproduction(tmp_path: Path) -> None:
    report = export_gif(
        [solid("a", (200, 100, 0, 128))], tmp_path / "a.gif", background=Rgba(0, 0, 255, 255)
    )
    assert report.background == (0, 0, 255, 255)
    assert report.to_mapping()["background"] == [0, 0, 255, 255]
    assert report.to_mapping()["losses"] == [
        {"effective": 0, "frame_id": "a", "kind": "alpha_flattened", "requested": 4}
    ]


def test_items_that_are_not_sprite_frames_are_type_errors() -> None:
    for item in ("frame", Frame("b", 100, Point(0, 0), cast(Any, (2, 2)))):
        with pytest.raises(TypeError, match="sprite frame"):
            encode_gif(cast(Any, [GOOD, item]))
        with pytest.raises(TypeError, match="sprite frame"):
            encode_spritesheet(cast(Any, [GOOD, item]), columns=1)


def test_gif_module_imports_only_core_palette_and_libraries() -> None:
    tree = ast.parse(Path(gif_module.__file__).read_text(encoding="utf-8"))
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    internal = {name for name in modules if name and name.startswith("moana")}
    assert all(
        name.startswith(("moana.core", "moana.palette", "moana.export")) for name in internal
    )
