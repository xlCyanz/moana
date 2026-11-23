"""Animation → spritesheet → slices: the bouncing slime rebuilds exactly (MOANA-023, AC1).

``moanart.animation.FrameRender`` is passed to the exporter as is: it satisfies the
structural ``SpriteFrame`` protocol without ``export`` importing ``animation``.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from moanart.animation import render_animation
from moanart.export import (
    SheetAnimation,
    export_spritesheet,
    load_spritesheet,
    parse_spritesheet_manifest,
)
from moanart.schema import validate_document

ROOT = Path(__file__).resolve().parents[2]
SLIME = ROOT / "examples/specs/bouncing-slime.moanart.json"


@pytest.mark.parametrize(("columns", "margin", "padding"), [(1, 0, 0), (2, 1, 1), (4, 2, 3)])
def test_bouncing_slime_sheet_rebuilds_every_frame(
    tmp_path: Path, columns: int, margin: int, padding: int
) -> None:
    animation = render_animation(validate_document(SLIME.read_bytes()), "bounce")
    count = len(animation.frames)
    report = export_spritesheet(
        animation.frames,
        tmp_path / "slime.png",
        tmp_path / "slime.json",
        columns=columns,
        margin=margin,
        padding=padding,
        animation=SheetAnimation(animation.animation_id, animation.loop_count),
    )
    manifest = parse_spritesheet_manifest((tmp_path / "slime.json").read_bytes())
    assert manifest.animation == SheetAnimation("bounce", 0)
    rows = -(-count // columns)
    assert (report.width, report.height) == (
        2 * margin + columns * 16 + (columns - 1) * padding,
        2 * margin + rows * 16 + (rows - 1) * padding,
    )
    sliced = load_spritesheet(tmp_path / "slime.png", tmp_path / "slime.json")
    assert [frame.frame_id for frame in sliced] == [frame.frame_id for frame in animation.frames]
    for original, rebuilt in zip(animation.frames, sliced, strict=True):
        assert rebuilt.result.rgba == original.result.rgba
        assert rebuilt.result.digest == original.result.digest
        assert (rebuilt.duration_ms, rebuilt.pivot) == (original.duration_ms, original.pivot)
    with Image.open(io.BytesIO((tmp_path / "slime.png").read_bytes())) as atlas:
        assert atlas.mode == "RGBA" and atlas.size == (report.width, report.height)
