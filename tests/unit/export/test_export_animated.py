"""Lossless APNG and WebP export (MOANA-025, ADR-035; AC1, AC2, T1, T2).

Expected pixels, durations, loop values and chunk layouts are written by hand. Every
file is decoded with Pillow directly (``seek`` + ``convert("RGBA")``, alpha 0 normalised
to ``(0, 0, 0, 0)``) and its container fields (``acTL``/``fcTL``, ``ANIM``/``ANMF``) are
parsed here independently of the exporter. Tests that need a codec are skipped only
when the probe says it is missing, and the skip reason carries the build report.
"""

from __future__ import annotations

import ast
import io
import struct
import tracemalloc
import zlib
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
from moana.core.errors import BudgetExceeded, ExportError, UnsupportedOperation, ValidationError
from moana.core.limits import GeometryLimits
from moana.export import (
    APNG_MEDIA_TYPE,
    STILL_IMAGE_WARNING,
    WEBP_MEDIA_TYPE,
    AnimationWarning,
    encode_apng,
    encode_webp,
    export_apng,
    export_capabilities,
    export_webp,
)
from moana.export import _frames as frames_module
from moana.export import animated as animated_module
from moana.export import codecs as codecs_module

RGBA = tuple[int, int, int, int]
WEBP_FIXED = 24 * 1024 * 1024
CLEAR: RGBA = (0, 0, 0, 0)
RED: RGBA = (255, 0, 0, 255)
HALF_RED: RGBA = (255, 0, 0, 128)
BLUE: RGBA = (0, 0, 255, 255)
FAINT: RGBA = (1, 2, 3, 1)

CAPS = export_capabilities()
BUILD = ", ".join(
    f"{entry.format}={'yes' if entry.available else entry.reason} "
    f"({entry.codec} {entry.codec_version})"
    for entry in CAPS.formats
)
BUILD_REPORT = f"Pillow {CAPS.pillow_version}: {BUILD}"
needs_apng = pytest.mark.skipif(
    not CAPS.status("apng").available, reason=f"APNG not proven in this build; {BUILD_REPORT}"
)
needs_webp = pytest.mark.skipif(
    not CAPS.status("webp").available,
    reason=f"lossless animated WebP not proven in this build; {BUILD_REPORT}",
)
KINDS = [
    pytest.param("apng", marks=needs_apng, id="apng"),
    pytest.param("webp", marks=needs_webp, id="webp"),
]
ENCODERS: dict[str, Any] = {"apng": encode_apng, "webp": encode_webp}
EXPORTERS: dict[str, Any] = {"apng": export_apng, "webp": export_webp}
SUFFIXES = {"apng": ".png", "webp": ".webp"}


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


def frame(frame_id: str, pixels: list[list[RGBA]], duration: int = 100) -> Frame:
    raster = Raster(len(pixels[0]), len(pixels), bytes(c for row in pixels for p in row for c in p))
    return Frame(frame_id, duration, Point(0, 0), raster)


def solid(frame_id: str, color: RGBA, size: int = 2, duration: int = 100) -> Frame:
    return frame(frame_id, [[color] * size for _ in range(size)], duration)


GOOD = solid("a", RED)


def decode(data: bytes) -> tuple[list[list[RGBA]], list[float], dict[Any, Any]]:
    """Composited RGBA (normalised) and duration of every frame, plus the file info."""
    pixels: list[list[RGBA]] = []
    durations: list[float] = []
    with Image.open(io.BytesIO(data)) as image:
        info: dict[Any, Any] = dict(image.info)
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            raw = image.convert("RGBA").tobytes()
            values = [cast(RGBA, tuple(raw[i : i + 4])) for i in range(0, len(raw), 4)]
            pixels.append([value if value[3] else CLEAR for value in values])
            durations.append(image.info.get("duration", 0))
    return pixels, durations, info


def flat(pixels: list[list[RGBA]]) -> list[RGBA]:
    return [value for row in pixels for value in row]


def png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Every chunk of a PNG, CRC checked."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    chunks: list[tuple[bytes, bytes]] = []
    offset = 8
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        (crc,) = struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])
        assert crc == zlib.crc32(kind + payload)
        chunks.append((kind, payload))
        offset += 12 + length
    assert offset == len(data)
    return chunks


def riff_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Top-level chunks of a WebP RIFF container."""
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    assert struct.unpack("<I", data[4:8])[0] == len(data) - 8
    chunks: list[tuple[bytes, bytes]] = []
    offset = 12
    while offset < len(data):
        kind = data[offset : offset + 4]
        (length,) = struct.unpack("<I", data[offset + 4 : offset + 8])
        chunks.append((kind, data[offset + 8 : offset + 8 + length]))
        offset += 8 + length + (length & 1)
    return chunks


def webp_loop(data: bytes) -> int:
    (anim,) = [payload for kind, payload in riff_chunks(data) if kind == b"ANIM"]
    return int(struct.unpack("<H", anim[4:6])[0])


def webp_durations(data: bytes) -> list[int]:
    return [
        int.from_bytes(payload[12:15], "little")
        for kind, payload in riff_chunks(data)
        if kind == b"ANMF"
    ]


def apng_controls(data: bytes) -> list[tuple[int, ...]]:
    return [
        struct.unpack(">IIIIIHHBB", payload)
        for kind, payload in png_chunks(data)
        if kind == b"fcTL"
    ]


# --- AC1 / T2: RGBA, partial alpha and timeline roundtrip -----------------------------


PARTIAL_FRAMES = [
    frame("a", [[HALF_RED, CLEAR], [RED, FAINT]], 33),
    frame("b", [[CLEAR, HALF_RED], [FAINT, BLUE]], 1),
    frame("c", [[(10, 20, 30, 254), CLEAR], [CLEAR, CLEAR]], 60_000),
]


@pytest.mark.parametrize("kind", KINDS)
def test_multi_frame_partial_alpha_and_durations_roundtrip_exactly(kind: str) -> None:
    encoded = ENCODERS[kind](PARTIAL_FRAMES, loop_count=3)
    pixels, durations, info = decode(encoded.data)
    assert pixels == [
        [HALF_RED, CLEAR, RED, FAINT],
        [CLEAR, HALF_RED, FAINT, BLUE],
        [(10, 20, 30, 254), CLEAR, CLEAR, CLEAR],
    ]  # a transparent pixel never shows the previous frame; partial alpha never blends
    assert [round(d) for d in durations] == [33, 1, 60_000]
    assert info["loop"] == 3
    assert (encoded.frames, encoded.encoded_frames, encoded.loop_count) == (3, 3, 3)
    assert encoded.durations_ms == (33, 1, 60_000) and encoded.warnings == ()
    assert (encoded.stored_durations_ms, encoded.stored_loop_count) == ((33, 1, 60_000), 3)
    assert encoded.format == kind and encoded.width == encoded.height == 2


@needs_apng
def test_apng_container_is_full_frame_with_exact_delays() -> None:
    data = encode_apng(PARTIAL_FRAMES, loop_count=5).data
    chunks = png_chunks(data)
    assert [kind for kind, _ in chunks] == [
        b"IHDR",
        b"acTL",
        b"fcTL",
        b"IDAT",
        b"fcTL",
        b"fdAT",
        b"fcTL",
        b"fdAT",
        b"IEND",
    ]
    assert chunks[0][1] == struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)  # RGBA 8-bit
    assert chunks[1][1] == struct.pack(">II", 3, 5)  # num_frames, num_plays
    # sequence, w, h, x, y, delay num/den (exact ms / 1000), dispose NONE, blend SOURCE
    assert apng_controls(data) == [
        (0, 2, 2, 0, 0, 33, 1000, 0, 0),
        (1, 2, 2, 0, 0, 1, 1000, 0, 0),
        (3, 2, 2, 0, 0, 60_000, 1000, 0, 0),
    ]
    fdat_sequences = [struct.unpack(">I", p[:4])[0] for k, p in chunks if k == b"fdAT"]
    assert fdat_sequences == [2, 4]


@needs_apng
def test_apng_delays_survive_float_decoding() -> None:
    # Pillow reports 1001/1000 s as 1000.9999999999999 ms: whole milliseconds still verify.
    frames = [solid("a", RED, duration=1001), solid("b", BLUE, duration=59_999)]
    encoded = encode_apng(frames)
    assert [c[5:7] for c in apng_controls(encoded.data)] == [(1001, 1000), (59_999, 1000)]
    _, durations, _ = decode(encoded.data)
    assert durations[0] != 1001 and round(durations[0]) == 1001


@needs_webp
def test_webp_stores_exact_milliseconds_and_the_loop() -> None:
    encoded = encode_webp(PARTIAL_FRAMES, loop_count=7)
    chunks = riff_chunks(encoded.data)
    assert [kind for kind, _ in chunks][:2] == [b"VP8X", b"ANIM"]
    assert webp_loop(encoded.data) == 7
    assert webp_durations(encoded.data) == [33, 1, 60_000]
    assert all(kind != b"VP8 " for kind, _ in chunks)  # never lossy


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("loop_count", [0, 1, 2, 65_535])
def test_loop_count_is_total_plays(kind: str, loop_count: int) -> None:
    encoded = ENCODERS[kind]([solid("a", RED), solid("b", BLUE)], loop_count=loop_count)
    if kind == "apng":
        (actl,) = [payload for name, payload in png_chunks(encoded.data) if name == b"acTL"]
        assert actl == struct.pack(">II", 2, loop_count)
    else:
        assert webp_loop(encoded.data) == loop_count
    assert decode(encoded.data)[2]["loop"] == loop_count == encoded.loop_count


@needs_apng
def test_apng_keeps_duplicated_frames() -> None:
    frames = [solid("a", RED, duration=100), solid("b", RED, duration=200), solid("c", BLUE)]
    encoded = encode_apng(frames)
    assert (encoded.frames, encoded.encoded_frames) == (3, 3)
    pixels, durations, _ = decode(encoded.data)
    assert pixels == [[RED] * 4, [RED] * 4, [BLUE] * 4] and durations == [100, 200, 100]
    assert encoded.frame_digests[0] == encoded.frame_digests[1] != encoded.frame_digests[2]


@needs_webp
def test_webp_merged_duplicates_keep_an_equivalent_timeline() -> None:
    frames = [solid("a", RED, duration=100), solid("b", RED, duration=200), solid("c", BLUE)]
    encoded = encode_webp(frames)
    assert (encoded.frames, encoded.encoded_frames) == (3, 2)  # libwebp merged a and b
    pixels, durations, _ = decode(encoded.data)
    assert pixels == [[RED] * 4, [BLUE] * 4] and durations == [300, 100]
    assert encoded.durations_ms == (100, 200, 100)  # the requested timeline is reported


@needs_apng
def test_a_single_apng_frame_is_still_an_animation() -> None:
    encoded = encode_apng([solid("a", HALF_RED, duration=40)], loop_count=2)
    chunks = png_chunks(encoded.data)
    assert [kind for kind, _ in chunks] == [b"IHDR", b"acTL", b"fcTL", b"IDAT", b"IEND"]
    assert chunks[1][1] == struct.pack(">II", 1, 2) and encoded.warnings == ()


@needs_webp
def test_a_single_webp_frame_is_a_still_image_with_a_warning() -> None:
    encoded = encode_webp([solid("a", HALF_RED, duration=40)], loop_count=2)
    assert [kind for kind, _ in riff_chunks(encoded.data)] == [b"VP8L"]  # lossless, no ANIM
    assert encoded.warnings == (AnimationWarning(STILL_IMAGE_WARNING),)
    assert encoded.warnings[0].to_mapping() == {"frame_id": None, "kind": "still_image"}
    assert (encoded.stored_durations_ms, encoded.stored_loop_count) == (None, None)
    assert decode(encoded.data)[0] == [[HALF_RED] * 4]
    assert (encoded.encoded_frames, encoded.durations_ms, encoded.loop_count) == (1, (40,), 2)


@needs_webp
def test_equal_webp_frames_collapse_to_a_still_image_with_a_warning() -> None:
    # libwebp merges equal neighbours and writes a lone frame as a still image.
    frames = [solid("a", CLEAR, 1, 1), solid("b", CLEAR, 1, 1), solid("c", CLEAR, 1, 1)]
    encoded = encode_webp(frames, loop_count=0)
    assert [kind for kind, _ in riff_chunks(encoded.data)] == [b"VP8L"]
    assert encoded.warnings == (AnimationWarning("still_image"),)
    assert encoded.encoded_frames == 1 and encoded.stored_durations_ms is None
    assert encoded.durations_ms == (1, 1, 1)


@pytest.mark.parametrize("kind", KINDS)
def test_identical_input_gives_identical_bytes_and_codec_versions(kind: str) -> None:
    first = ENCODERS[kind](PARTIAL_FRAMES, loop_count=0)
    second = ENCODERS[kind](list(PARTIAL_FRAMES), loop_count=0)
    assert first.data == second.data
    status = CAPS.status(cast(Any, kind))
    assert (first.codec, first.codec_version, first.pillow_version) == (
        status.codec,
        status.codec_version,
        status.pillow_version,
    )


PALETTE = [CLEAR, RED, HALF_RED, BLUE, FAINT, (0, 255, 0, 200)]


@st.composite
def timelines(draw: st.DrawFn) -> tuple[list[Frame], int]:
    width = draw(st.integers(1, 4))
    height = draw(st.integers(1, 3))
    count = draw(st.integers(1, 5))
    frames = []
    for index in range(count):
        cells = draw(
            st.lists(st.sampled_from(PALETTE), min_size=width * height, max_size=width * height)
        )
        rows = [cells[y * width : (y + 1) * width] for y in range(height)]
        frames.append(frame(f"f{index}", rows, draw(st.sampled_from([1, 10, 33, 100, 60_000]))))
    return frames, draw(st.integers(0, 4))


def merged(timeline: list[tuple[list[RGBA], int]]) -> list[tuple[list[RGBA], int]]:
    result: list[tuple[list[RGBA], int]] = []
    for pixels, duration in timeline:
        if result and result[-1][0] == pixels:
            result[-1] = (pixels, result[-1][1] + duration)
        else:
            result.append((pixels, duration))
    return result


@pytest.mark.parametrize("kind", KINDS)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(case=timelines())
def test_decoded_timeline_equals_the_target(kind: str, case: tuple[list[Frame], int]) -> None:
    frames, loop_count = case
    encoded = ENCODERS[kind](frames, loop_count=loop_count)
    pixels, durations, info = decode(encoded.data)
    expected = [(flat_pixels(f), f.duration_ms) for f in frames]
    if kind == "webp" and len(merged(expected)) == 1:  # one distinct image: a still WebP
        assert pixels == [expected[0][0]]
        assert encoded.warnings == (AnimationWarning("still_image"),)
        return
    assert encoded.warnings == ()
    decoded = list(zip(pixels, [round(d) for d in durations], strict=True))
    assert merged(decoded) == merged(expected)
    assert info["loop"] == loop_count


def flat_pixels(item: Frame) -> list[RGBA]:
    raw = item.result.rgba
    return [cast(RGBA, tuple(raw[i : i + 4])) for i in range(0, len(raw), 4)]


# --- AC2 / T2: absent codec ------------------------------------------------------------


@pytest.mark.parametrize("kind", ["apng", "webp"])
def test_an_absent_codec_is_unsupported_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    if kind == "webp":
        monkeypatch.setattr("moana.export.codecs.features.check_module", lambda name: False)
    else:
        monkeypatch.setattr("moana.export.codecs.features.check_codec", lambda name: False)
    (tmp_path / "keep.txt").write_bytes(b"x")
    before = sorted(path.name for path in tmp_path.iterdir())

    class Untouchable:
        def __getattr__(self, name: str) -> object:
            raise AssertionError("frame read before the codec check")

    for frames in ([GOOD], [Untouchable()]):
        with pytest.raises(UnsupportedOperation) as caught:
            EXPORTERS[kind](frames, tmp_path / f"anim{SUFFIXES[kind]}")
        assert caught.value.context["reason"] == "codec_unavailable"
        assert caught.value.context["format"] == kind
        assert caught.value.context["cause"] == "missing"
        with pytest.raises(UnsupportedOperation):
            ENCODERS[kind](frames)
    assert sorted(path.name for path in tmp_path.iterdir()) == before  # no file, no temp


def test_a_failing_probe_is_unsupported_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    present, _ = codecs_module._PROBES["webp"]
    monkeypatch.setitem(codecs_module._PROBES, "webp", (present, lambda: False))
    with pytest.raises(UnsupportedOperation) as caught:
        export_webp([GOOD], tmp_path / "a.webp")
    assert caught.value.context["cause"] == "roundtrip_failed"
    assert list(tmp_path.iterdir()) == []


# --- budget ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "bytes_limit", "resource_bytes"),
    [
        pytest.param("apng", 48 * 16 + 12 * 5 * 16 - 1, 48 * 16 + 12 * 5 * 16, marks=needs_apng),
        pytest.param(  # 24 MiB fixed + 64·A + 32·n·A
            "webp",
            WEBP_FIXED + 64 * 16 + 32 * 5 * 16 - 1,
            WEBP_FIXED + 64 * 16 + 32 * 5 * 16,
            marks=needs_webp,
        ),
    ],
)
def test_budget_is_checked_before_any_pixel_is_read(
    monkeypatch: pytest.MonkeyPatch, kind: str, bytes_limit: int, resource_bytes: int
) -> None:
    frames = [solid(f"f{i}", RED, 4) for i in range(5)]  # A = 16, n = 5
    ENCODERS[kind](
        frames, limits=RenderLimits(max_frame_pixels=80, max_buffer_bytes=resource_bytes)
    )

    def no_pixels(*_: object, **__: object) -> None:
        raise AssertionError("pixels read before the budget check")

    monkeypatch.setattr("moana.export._frames.np.frombuffer", no_pixels)
    with pytest.raises(BudgetExceeded) as caught:
        ENCODERS[kind](frames, limits=RenderLimits(max_buffer_bytes=bytes_limit))
    assert caught.value.context == {
        "resource": "buffer_bytes",
        "limit": bytes_limit,
        "estimated": resource_bytes,
    }
    limits = RenderLimits(
        max_frame_pixels=1, max_buffer_bytes=1, geometry=GeometryLimits(max_dimension=1, max_area=1)
    )
    with pytest.raises(BudgetExceeded) as every:
        ENCODERS[kind](frames, limits=limits)
    assert [detail.context["resource"] for detail in every.value.details] == [
        "frame_pixels",
        "export_dimension",
        "export_area",
        "buffer_bytes",
    ]


@pytest.mark.parametrize("kind", KINDS)
def test_too_many_frames_is_rejected_before_reading_any_frame(kind: str) -> None:
    class Untouchable:
        @property
        def result(self) -> Raster:
            raise AssertionError("frame read")

    with pytest.raises(BudgetExceeded) as caught:
        ENCODERS[kind](cast(Any, [Untouchable()] * 257))
    assert caught.value.context == {"resource": "frames", "limit": 256, "estimated": 257}


@pytest.mark.parametrize("kind", KINDS)
def test_rejected_large_animation_allocates_almost_nothing(kind: str) -> None:
    shared = Raster(2048, 2048, bytes(2048 * 2048 * 4))
    frames = [Frame(f"f{i}", 100, Point(0, 0), shared) for i in range(4)]
    tracemalloc.start()
    try:
        with pytest.raises(BudgetExceeded) as caught:
            ENCODERS[kind](frames, limits=RenderLimits(max_buffer_bytes=64 * 1024 * 1024))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert caught.value.context["resource"] == "buffer_bytes"
    assert peak < 1024 * 1024


@pytest.mark.parametrize(
    ("kind", "fixed", "frame_bytes", "output_bytes"),
    [
        pytest.param("apng", 0, 48, 12, marks=needs_apng),
        pytest.param("webp", WEBP_FIXED, 64, 32, marks=needs_webp),
    ],
)
def test_admitted_noise_stays_within_its_traced_estimate(
    kind: str, fixed: int, frame_bytes: int, output_bytes: int
) -> None:
    rng = np.random.default_rng(0)
    frames = []
    for index in range(3):
        pixels = rng.integers(0, 256, size=(128, 128, 4), dtype=np.uint8)
        pixels[pixels[:, :, 3] == 0] = 0
        frames.append(Frame(f"f{index}", 100, Point(0, 0), Raster(128, 128, pixels.tobytes())))
    tracemalloc.start()
    try:
        encoded = ENCODERS[kind](frames)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    area = 128 * 128
    assert len(encoded.data) <= 5 * 3 * area  # incompressible noise: about 4 B/px
    assert peak < fixed + frame_bytes * area + output_bytes * 3 * area


# --- options, frames and container errors ---------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_option_and_frame_errors(kind: str) -> None:
    encode = ENCODERS[kind]
    for loop_count in (-1, 65_536, True, 1.0, "1"):
        with pytest.raises((ValidationError, TypeError)):
            encode([GOOD], loop_count=loop_count)
    with pytest.raises(TypeError, match="limits"):
        encode([GOOD], limits=cast(Any, {}))
    with pytest.raises(ValidationError) as caught:
        encode([GOOD, frame("b", [[(1, 0, 0, 0), RED], [RED, RED]])])
    assert caught.value.context == {"field": "frames", "reason": "not_normalized", "index": 1}
    with pytest.raises(ValidationError) as size:
        encode([GOOD, solid("b", RED, 3)])
    assert size.value.context["reason"] == "size_mismatch"
    with pytest.raises(ValidationError) as empty:
        encode([])
    assert empty.value.context["reason"] == "empty_frames"


@pytest.mark.parametrize(
    "single",
    [
        b"GIF89a",
        b"\x89PNG\r\n\x1a\n\x00\x00",  # truncated chunk header
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDRcrc!",  # chunk longer than the data
        b"\x89PNG\r\n\x1a\n",  # no chunks
    ],
)
def test_unexpected_png_layout_is_an_export_error(single: bytes) -> None:
    with pytest.raises(ExportError) as caught:
        animated_module._zlib_stream(single, 1, 1)
    assert caught.value.context == {"reason": "encoder_layout"}


def png(*chunks: tuple[bytes, bytes]) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"".join(animated_module._png_chunk(k, p) for k, p in chunks)


def test_png_layout_is_checked_chunk_by_chunk() -> None:
    header = (b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    end = (b"IEND", b"")
    assert (
        animated_module._zlib_stream(png(header, (b"IDAT", b"ab"), (b"IDAT", b"c"), end), 1, 1)
        == b"abc"
    )
    for bad in (
        png(header, end),  # no data
        png((b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)), (b"IDAT", b"a"), end),  # RGB
        png(header, (b"pHYs", b"x"), (b"IDAT", b"a"), end),  # an extra chunk
        png(header, (b"IDAT", b"a"), (b"IEND", b"x")),
    ):
        with pytest.raises(ExportError):
            animated_module._zlib_stream(bad, 1, 1)


@needs_webp
def test_webp_encoder_failure_is_an_export_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: object, **__: object) -> None:
        raise OSError("cannot write file as WebP")

    probed = CAPS.status("webp")  # the probe would also see the broken save
    monkeypatch.setattr(animated_module, "require_codec", lambda name: probed)

    monkeypatch.setattr("moana.export.animated.Image.Image.save", broken)
    with pytest.raises(ExportError) as caught:
        encode_webp([GOOD, solid("b", BLUE)])
    assert caught.value.context == {"reason": "encoder_failed"}


@pytest.mark.parametrize("kind", KINDS)
def test_verification_failures_never_return_bytes(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    frames = [solid("a", RED), solid("b", BLUE)]
    original = frames_module.decoded_timeline

    def losing_time(*args: Any, **kwargs: Any) -> tuple[Any, object]:
        timeline, loop = original(*args, **kwargs)
        return [(digest, 10) for digest, _ in timeline], loop

    monkeypatch.setattr(animated_module, "decoded_timeline", losing_time)
    with pytest.raises(ExportError) as caught:
        ENCODERS[kind](frames)
    assert caught.value.context == {"reason": "timeline_mismatch"}

    def losing_loop(*args: Any, **kwargs: Any) -> tuple[Any, object]:
        return original(*args, **kwargs)[0], None

    monkeypatch.setattr(animated_module, "decoded_timeline", losing_loop)
    with pytest.raises(ExportError) as loop:
        ENCODERS[kind](frames, loop_count=2)
    assert loop.value.context == {"reason": "loop_mismatch"}
    monkeypatch.setattr(animated_module, "decoded_timeline", original)

    def broken(*_: object, **__: object) -> None:
        raise OSError("truncated")

    probed = CAPS.status(cast(Any, kind))  # the probe would also see the broken decoder
    monkeypatch.setattr(animated_module, "require_codec", lambda name: probed)
    monkeypatch.setattr("moana.export._frames.Image.open", broken)
    with pytest.raises(ExportError) as unreadable:
        ENCODERS[kind](frames)
    assert unreadable.value.context == {"reason": f"unreadable_{kind}"}


@needs_apng
def test_wrong_decoded_size_is_a_timeline_mismatch() -> None:
    data = encode_apng([GOOD]).data
    with pytest.raises(ExportError) as caught:
        frames_module.decoded_timeline(data, "PNG", 3, 2, unreadable="x")
    assert caught.value.context == {"reason": "timeline_mismatch"}


def test_decoded_durations_are_whole_milliseconds() -> None:
    milliseconds = frames_module._milliseconds
    assert milliseconds(33) == 33 and milliseconds(1000.9999999999999) == 1001
    assert milliseconds(33.0) == 33
    for not_milliseconds in (33.4, "33", None, True):
        assert milliseconds(not_milliseconds) is None
    assert frames_module.equivalent_timeline([("x", None), ("x", 5), ("y", None)]) == [
        ("x", None),
        ("y", None),
    ]


# --- writing --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_export_writes_and_reports(tmp_path: Path, kind: str) -> None:
    destination = tmp_path / f"anim{SUFFIXES[kind]}"
    report = EXPORTERS[kind](PARTIAL_FRAMES, destination, loop_count=4)
    data = destination.read_bytes()
    media_type = {"apng": APNG_MEDIA_TYPE, "webp": WEBP_MEDIA_TYPE}[kind]
    assert media_type == {"apng": "image/apng", "webp": "image/webp"}[kind]
    assert report.path == str(destination) and report.media_type == media_type
    assert (report.width, report.height, report.frames, report.encoded_frames) == (2, 2, 3, 3)
    assert (report.durations_ms, report.duration_ms, report.loop_count) == (
        (33, 1, 60_000),
        60_034,
        4,
    )
    assert report.byte_size == len(data) and report.file_sha256.startswith("sha256:")
    status = CAPS.status(cast(Any, kind))
    assert (report.codec, report.codec_version) == (status.codec, status.codec_version)
    assert report.pillow_version == CAPS.pillow_version and report.format == kind
    mapping = report.to_mapping()
    assert list(mapping) == sorted(mapping)
    assert mapping["durations_ms"] == [33, 1, 60_000] and mapping["warnings"] == []
    assert mapping["stored_durations_ms"] == [33, 1, 60_000] and mapping["stored_loop_count"] == 4
    assert isinstance(mapping["frame_digests"], list) and len(mapping["frame_digests"]) == 3


@pytest.mark.parametrize("kind", KINDS)
def test_existing_files_are_never_replaced_without_overwrite(tmp_path: Path, kind: str) -> None:
    destination = tmp_path / f"a{SUFFIXES[kind]}"
    destination.write_bytes(b"old")
    with pytest.raises(ExportError) as caught:
        EXPORTERS[kind]([GOOD], destination)
    assert caught.value.context == {"reason": "exists", "file_name": destination.name}
    assert destination.read_bytes() == b"old"
    EXPORTERS[kind]([GOOD], destination, overwrite=True)
    assert destination.read_bytes()[:4] in (b"\x89PNG", b"RIFF")


@pytest.mark.parametrize("kind", KINDS)
def test_invalid_destinations_and_failed_encodes_write_nothing(tmp_path: Path, kind: str) -> None:
    suffix = SUFFIXES[kind]
    wrong = ".webp" if kind == "apng" else ".png"
    for path, reason in (
        (tmp_path / f"a{wrong}", "wrong_extension"),
        (tmp_path / "a.apng", "wrong_extension"),
        (tmp_path / suffix, "wrong_extension"),
        (tmp_path / f"a\x00{suffix}", "invalid_name"),
    ):
        with pytest.raises(ValidationError) as caught:
            EXPORTERS[kind]([GOOD], path)
        assert caught.value.context == {"field": "path", "reason": reason}
    bad_calls: list[tuple[Any, Any]] = [
        (b"a" + suffix.encode(), False),
        (tmp_path / f"a{suffix}", 1),
    ]
    for bad_path, overwrite in bad_calls:
        with pytest.raises(TypeError):
            EXPORTERS[kind]([GOOD], bad_path, overwrite=overwrite)
    with pytest.raises(ValidationError):
        EXPORTERS[kind]([GOOD, solid("b", RED, 3)], tmp_path / f"a{suffix}")
    assert list(tmp_path.iterdir()) == []


def test_animated_module_imports_only_core_and_export() -> None:
    tree = ast.parse(Path(animated_module.__file__).read_text(encoding="utf-8"))
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    internal = {name for name in modules if name and name.startswith("moana")}
    assert all(
        name.startswith(("moana.core", "moana.palette", "moana.export")) for name in internal
    )


# --- review follow-ups: stored timeline, RIFF walk, durations, read-only pixels -----------


@needs_webp
def test_webp_reports_the_timeline_the_file_stores() -> None:
    frames = [solid("a", RED, duration=100), solid("b", RED, duration=200), solid("c", BLUE)]
    encoded = encode_webp(frames, loop_count=2)
    assert encoded.durations_ms == (100, 200, 100)  # requested
    assert encoded.stored_durations_ms == (300, 100) and encoded.stored_loop_count == 2


@needs_apng
def test_apng_stores_exactly_the_requested_timeline() -> None:
    encoded = encode_apng([solid("a", RED, duration=7), solid("b", RED, duration=9)])
    assert encoded.stored_durations_ms == (7, 9) and encoded.stored_loop_count == 0


def riff(*chunks: tuple[bytes, bytes], size_delta: int = 0, tail: bytes = b"") -> bytes:
    body = b"WEBP" + b"".join(
        kind + struct.pack("<I", len(data)) + data + b"\x00" * (len(data) & 1)
        for kind, data in chunks
    )
    body += tail
    return b"RIFF" + struct.pack("<I", len(body) + size_delta) + body


def test_webp_animation_is_found_by_walking_the_riff_chunks() -> None:
    animated = animated_module._webp_is_animated
    vp8x = (b"VP8X", bytes([0x02 | 0x10]) + bytes(9))  # animation and alpha flags
    assert animated(riff(vp8x, (b"ANIM", bytes(6)), (b"ANMF", b"x")))
    assert not animated(riff((b"VP8L", b"abc")))  # odd length: padded
    assert not animated(riff((b"VP8X", bytes(10)), (b"ANIM", bytes(6))))  # flag unset
    assert not animated(riff(vp8x, (b"VP8L", b"a")))  # flag without ANIM
    assert not animated(riff((b"VP8L", b"a"), vp8x, (b"ANIM", bytes(6))))  # VP8X not first
    for bad in (
        b"RIFF",
        b"JUNK" + bytes(4) + b"WEBP",
        riff((b"VP8L", b"a"), size_delta=1),
        riff((b"VP8L", b"a"), tail=b"XY"),  # truncated chunk header
        riff(tail=b"VP8L" + struct.pack("<I", 9) + b"ab"),  # chunk longer than the data
    ):
        with pytest.raises(ExportError) as caught:
            animated(bad)
        assert caught.value.context == {"reason": "encoder_layout"}


@needs_apng
def test_a_duration_that_is_not_whole_milliseconds_is_a_mismatch() -> None:
    data = encode_apng([GOOD, solid("b", BLUE)]).data
    rebuilt = [b"\x89PNG\r\n\x1a\n"]
    for kind, payload in png_chunks(data):
        if kind == b"fcTL":  # delay 1/3 s: Pillow reports 333.33... ms
            payload = payload[:20] + struct.pack(">HH", 1, 3) + payload[24:]
        rebuilt.append(animated_module._png_chunk(kind, payload))
    with pytest.raises(ExportError) as caught:
        frames_module.decoded_timeline(b"".join(rebuilt), "PNG", 2, 2, unreadable="x")
    assert caught.value.context == {"reason": "timeline_mismatch"}


def test_a_frame_without_a_duration_is_unreadable() -> None:
    still = io.BytesIO()
    Image.new("RGBA", (2, 2), RED).save(still, format="PNG")  # a plain PNG has no time
    with pytest.raises(ExportError) as caught:
        frames_module.decoded_timeline(still.getvalue(), "PNG", 2, 2, unreadable="unreadable_apng")
    assert caught.value.context == {"reason": "unreadable_apng"}


def test_normalized_pixels_are_read_only_even_over_a_writable_buffer() -> None:
    raster = Raster(1, 1, cast(Any, bytearray(RED)))
    pixels = frames_module.normalized_pixels(raster, 0)
    assert not pixels.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        pixels[0, 0, 0] = 1
    assert bytes(cast(Any, raster.rgba)) == bytes(RED)
