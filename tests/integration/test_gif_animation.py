"""Animation → GIF → decode: the bouncing slime keeps every frame and time (MOANA-024, AC1).

``moanart.animation.FrameRender`` is passed to the exporter as is (structural
``SpriteFrame``); the GIF is decoded with Pillow directly, frame by frame.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from moanart.animation import render_animation
from moanart.export import export_gif
from moanart.schema import validate_document

ROOT = Path(__file__).resolve().parents[2]
SLIME = ROOT / "examples/specs/bouncing-slime.moanart.json"


def normalised_rgba(image: Image.Image) -> bytes:
    raw = bytearray(image.convert("RGBA").tobytes())
    for offset in range(0, len(raw), 4):
        if raw[offset + 3] == 0:
            raw[offset : offset + 4] = bytes(4)
    return bytes(raw)


def test_bouncing_slime_gif_decodes_to_the_rendered_timeline(tmp_path: Path) -> None:
    animation = render_animation(validate_document(SLIME.read_bytes()), "bounce")
    report = export_gif(animation.frames, tmp_path / "slime.gif", loop_count=animation.loop_count)
    assert report.durations_ms == (150, 100, 120, 100) and report.duration_ms == 470
    assert report.losses == () and report.warnings == ()
    assert (report.frames, report.encoded_frames, report.loop_count) == (4, 4, 0)
    with Image.open(tmp_path / "slime.gif") as image:
        assert image.size == (16, 16) and getattr(image, "n_frames", 1) == 4
        assert image.info["loop"] == 0
        for index, rendered in enumerate(animation.frames):
            image.seek(index)
            assert normalised_rgba(image) == rendered.result.rgba
            assert image.info["duration"] == rendered.duration_ms
    again = export_gif(animation.frames, tmp_path / "again.gif")
    assert again.file_sha256 == report.file_sha256
    assert (tmp_path / "again.gif").read_bytes() == (tmp_path / "slime.gif").read_bytes()
    with Image.open(io.BytesIO((tmp_path / "slime.gif").read_bytes())) as image:
        assert image.format == "GIF"
