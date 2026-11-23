"""Isometric desk example of ``examples/desk``.

The example documents an editing history: ``desk-r0.moanart.json`` plus two edit
batches must reproduce ``desk.moanart.json`` exactly, and the committed 1x preview
must be the render of the final document. Colours are checked against the palette.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from moanart.api import apply_edit, edit_document, load_document, render, snapshot_digest

DESK = Path(__file__).resolve().parents[2] / "examples" / "desk"
BATCHES = ("desk-solid-shadows.edit.json", "desk-deeper-overhang.edit.json")
DITHERED_IDS = {
    "floor_cast_fringe",
    "leg_side_falloff",
    "cabinet_side_falloff",
    "cabinet_side_base",
    "shadow_falloff_left",
    "shadow_falloff_right",
}


def _operation_ids(document_path: Path) -> set[str]:
    document = load_document(document_path)
    return {op.id for layer in document.layers for op in layer.operations}


def test_batches_replay_the_history_to_the_final_document() -> None:
    document = load_document(DESK / "desk-r0.moanart.json")
    assert document.revision == 0
    for revision, name in enumerate(BATCHES, start=1):
        document = apply_edit(document, DESK / name)
        assert document.revision == revision
        expected = "desk-r1.moanart.json" if revision == 1 else "desk.moanart.json"
        assert snapshot_digest(document) == snapshot_digest(load_document(DESK / expected))


def test_shadow_batch_replaces_every_dither_with_solid_bands() -> None:
    base = load_document(DESK / "desk-r0.moanart.json")
    result = edit_document(base, DESK / BATCHES[0])
    assert set(result.affected_ids) >= DITHERED_IDS
    assert _operation_ids(DESK / "desk-r0.moanart.json") >= DITHERED_IDS
    final_ids = _operation_ids(DESK / "desk.moanart.json")
    assert not DITHERED_IDS & final_ids
    final = load_document(DESK / "desk.moanart.json")
    kinds = {op.type for layer in final.layers for op in layer.operations}
    assert "dither" not in kinds


def test_preview_is_the_render_of_the_final_document() -> None:
    document = load_document(DESK / "desk.moanart.json")
    result = render(document)
    assert (result.width, result.height) == (512, 512)
    rendered = np.frombuffer(bytes(result.rgba), dtype=np.uint8).reshape(512, 512, 4)
    with Image.open(DESK / "previews" / "desk-1x.png") as image:
        preview = np.asarray(image.convert("RGBA"))
    np.testing.assert_array_equal(rendered, preview)


def test_render_uses_only_opaque_palette_colours() -> None:
    document = load_document(DESK / "desk.moanart.json")
    palette = {color.rgba for color in document.palette.colors}
    rendered = np.frombuffer(bytes(render(document).rgba), dtype=np.uint8).reshape(-1, 4)
    used = {"#" + "".join(f"{v:02X}" for v in px) for px in np.unique(rendered, axis=0)}
    assert used <= {str(c) for c in palette}
    assert all(px.endswith("FF") for px in used)
