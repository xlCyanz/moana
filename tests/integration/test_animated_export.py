"""Animation → APNG / WebP → decode: the slime keeps every pixel and time (MOANA-025, AC1).

``moanart.animation.FrameRender`` is passed to the exporters as is (structural
``SpriteFrame``); each file is decoded with Pillow directly, frame by frame. A format
whose codec this build lacks is skipped with the build report as reason.
"""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from moanart.animation import render_animation
from moanart.export import AnimatedFormat, export_apng, export_capabilities, export_webp
from moanart.export.animated import (
    WEBP_FIXED_BYTES,
    WEBP_FRAME_BYTES_PER_PIXEL,
    WEBP_OUTPUT_BYTES_PER_PIXEL,
)
from moanart.schema import validate_document

ROOT = Path(__file__).resolve().parents[2]
SLIME = ROOT / "examples/specs/bouncing-slime.moanart.json"
CAPS = export_capabilities()
REPORT = f"Pillow {CAPS.pillow_version}: " + ", ".join(
    f"{entry.format} {entry.codec} {entry.codec_version} {entry.reason}" for entry in CAPS.formats
)
KINDS: tuple[AnimatedFormat, ...] = ("apng", "webp")
EXPORTERS = {"apng": (export_apng, "slime.png"), "webp": (export_webp, "slime.webp")}


def normalised_rgba(image: Image.Image) -> bytes:
    raw = bytearray(image.convert("RGBA").tobytes())
    for offset in range(0, len(raw), 4):
        if raw[offset + 3] == 0:
            raw[offset : offset + 4] = bytes(4)
    return bytes(raw)


@pytest.mark.parametrize(
    "kind",
    [
        pytest.param(
            kind,
            marks=pytest.mark.skipif(
                not CAPS.status(kind).available, reason=f"{kind} unavailable; {REPORT}"
            ),
        )
        for kind in KINDS
    ],
)
def test_bouncing_slime_decodes_to_the_rendered_timeline(
    tmp_path: Path, kind: AnimatedFormat
) -> None:
    exporter, name = EXPORTERS[kind]
    animation = render_animation(validate_document(SLIME.read_bytes()), "bounce")
    report = exporter(animation.frames, tmp_path / name, loop_count=animation.loop_count)
    assert report.durations_ms == (150, 100, 120, 100) and report.duration_ms == 470
    assert (report.frames, report.encoded_frames, report.loop_count) == (4, 4, 0)
    assert report.warnings == () and report.codec_version == CAPS.status(kind).codec_version
    with Image.open(io.BytesIO((tmp_path / name).read_bytes())) as image:
        assert image.format == ("PNG" if kind == "apng" else "WEBP")
        assert image.size == (16, 16) and getattr(image, "n_frames", 1) == 4
        assert image.info["loop"] == 0
        for index, rendered in enumerate(animation.frames):
            image.seek(index)
            assert normalised_rgba(image) == rendered.result.rgba
            assert round(image.info["duration"]) == rendered.duration_ms
    again = exporter(animation.frames, tmp_path / f"again-{name}")
    assert again.file_sha256 == report.file_sha256


RSS_PROBE = r"""
import resource, sys
from dataclasses import dataclass
import numpy as np
from moanart.core.coordinates import Point
from moanart.export import encode_webp

count, side = int(sys.argv[1]), int(sys.argv[2])


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


rng = np.random.default_rng(1)
frames = []
for index in range(count):
    pixels = rng.integers(0, 256, (side, side, 4), dtype=np.uint8)
    pixels[pixels[:, :, 3] == 0] = 0
    frames.append(Frame(f"f{index}", 33, Point(0, 0), Raster(side, side, pixels.tobytes())))
    del pixels
warm = [  # load Pillow's plugins and libwebp before measuring
    Frame("w", 10, Point(0, 0), Raster(2, 2, bytes(16))),
    Frame("v", 10, Point(0, 0), Raster(2, 2, bytes([1]) * 16)),
]
encode_webp(warm)


def proc_status(key):
    with open("/proc/self/status", encoding="utf-8") as status:
        for line in status:
            if line.startswith(key + ":"):
                return int(line.split()[1]) * 1024  # kB
    raise LookupError(key)


if sys.platform == "linux":
    # ru_maxrss is useless here: Linux carries the forking parent's peak into the
    # child, and the pytest process is larger than this probe, so the delta was 0.
    # VmHWM belongs to this image; clear_refs "5" resets it to the current RSS.
    before = proc_status("VmRSS")
    try:
        with open("/proc/self/clear_refs", "w", encoding="utf-8") as refs:
            refs.write("5")
    except OSError:
        # Without the reset VmHWM may keep an earlier, larger peak of this process
        # (e.g. while the frames were generated): the measured growth can only be
        # overestimated, so the bound stays conservative (a false failure is possible,
        # a false pass is not).
        pass
    encode_webp(frames)
    print(proc_status("VmHWM") - before)
else:
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # bytes on macOS
    encode_webp(frames)
    print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before)
"""


@pytest.mark.slow
@pytest.mark.skipif(
    importlib.util.find_spec("resource") is None,
    reason="the resource module (ru_maxrss) is not available on this platform (Windows)",
)
@pytest.mark.skipif(not CAPS.status("webp").available, reason=f"webp unavailable; {REPORT}")
def test_webp_budget_covers_the_measured_process_memory() -> None:
    # 16 noise frames of 256 x 256 in a fresh process: native libwebp memory included.
    count, side = 16, 256
    completed = subprocess.run(
        [sys.executable, "-c", RSS_PROBE, str(count), str(side)],
        capture_output=True,
        check=True,
        text=True,
    )
    growth = int(completed.stdout)
    area = side * side
    estimate = (
        WEBP_FIXED_BYTES
        + WEBP_FRAME_BYTES_PER_PIXEL * area
        + WEBP_OUTPUT_BYTES_PER_PIXEL * count * area
    )
    assert 0 < growth <= estimate, (growth, estimate)
