"""asset → Pillow and project integrity: decode bombs and checksum failures (T2, AC2).

A tampered project never loads partially: every stored byte (assets, snapshots,
batches, preserved migration originals, ZIP entries) is hashed before it is used, so
a mismatch raises before Pillow decodes anything and returns no ``Project``. Image
bombs are rejected from the PNG header before Pillow is called, and Pillow's own
decompression-bomb protection is never changed by the engine.
"""

from __future__ import annotations

import io
import json
import zipfile
import zlib
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from PIL import Image

from moana.api import load_document
from moana.core.coordinates import Point
from moana.core.errors import BudgetExceeded, MoanaError, ValidationError
from moana.editing import History
from moana.export import FramePixels, SheetFrame, encode_spritesheet, load_spritesheet
from moana.project import (
    MANIFEST_NAME,
    Asset,
    Project,
    load_project,
    migrate_project,
    save_project,
    save_project_archive,
)
from moana.schema import snapshot_digest
from tests.fixtures.migration.formats import OLDEST, TEST_ONLY_MIGRATIONS

from .corpus import MINIMAL, chunk, png_declaring, tiny_png
from .guards import (
    assert_clean_error,
    bounded_settings,
    forbid_allocation,
    forbid_effects,
    forbid_writes,
    peak_bytes,
    tree_state,
)

pytestmark = pytest.mark.security

PILLOW_LIMIT = 89_478_485
"""Pillow's documented default bomb threshold; the engine never changes it."""


def _project() -> Project:
    document = load_document(MINIMAL)
    batch = {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": [{"type": "set_color", "target_id": "body_fill", "color": "ink"}],
    }
    history = History.start(document).edit(batch)
    assets = (
        Asset.from_png("texture", tiny_png(3, 2)),
        Asset.from_png("noise", tiny_png(4, 4, (99, 20, 30, 255))),
    )
    return Project(history.document, assets, history)


def _saved(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    save_project(_project(), root)
    return root


def _flip_last_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[-1] ^= 0x01
    path.write_bytes(bytes(data))


def _load_tampered(
    root: Path, source: Path | None = None, *, decoded_assets: bool = False
) -> MoanaError:
    """Load a tampered project with no write allowed (nor any decode, unless stated).

    ``decoded_assets`` admits Pillow for files verified before the tampered one:
    assets are verified and decoded before the history is read.
    """
    before = tree_state(root)
    guard = forbid_writes() if decoded_assets else forbid_effects()
    with guard, pytest.raises(MoanaError) as caught:
        load_project(source or root)
    assert tree_state(root) == before  # loading is read-only, even when it fails
    return assert_clean_error(caught.value, root)


# --- checksum failures ----------------------------------------------------------------


# "assets" also proves the hash runs before Pillow: forbid_effects trips PIL.Image.open.
@pytest.mark.parametrize("folder", ["assets", "history/snapshots", "history/batches"])
def test_t2_checksum_failure_of_any_stored_file_loads_nothing(tmp_path: Path, folder: str) -> None:
    root = _saved(tmp_path)
    files = sorted((root / folder).iterdir())
    assert files
    for path in files:  # every file of the folder: the first one checked already fails
        _flip_last_byte(path)
    error = _load_tampered(root, decoded_assets=folder != "assets")
    assert isinstance(error, ValidationError)
    reason = error.context["reason"]
    assert reason == "checksum_mismatch"


def test_t2_preserved_migration_original_is_verified(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy" / OLDEST.name
    legacy.parent.mkdir()
    legacy.write_bytes(OLDEST.read_bytes())
    root = tmp_path / "migrated"
    migrate_project(legacy, root, registry=TEST_ONLY_MIGRATIONS)
    (original,) = (root / "migrations").iterdir()
    _flip_last_byte(original)
    error = _load_tampered(root)
    assert error.context["reason"] == "checksum_mismatch"
    assert error.context["migration"] == 0


def test_t2_tampered_archive_entry_fails_its_crc(tmp_path: Path) -> None:
    source = tmp_path / "project.moana"
    save_project_archive(_project(), source)
    data = bytearray(source.read_bytes())
    with zipfile.ZipFile(io.BytesIO(bytes(data))) as handle:
        info = handle.getinfo(MANIFEST_NAME)
    start = info.header_offset + 30 + len(info.orig_filename.encode("utf-8"))
    data[start + info.compress_size // 2] ^= 0xFF  # inside the manifest's deflate stream
    source.write_bytes(bytes(data))
    error = _load_tampered(tmp_path, source)
    assert isinstance(error, ValidationError)
    assert error.context["reason"] in ("corrupt_archive", "checksum_mismatch")


@pytest.mark.parametrize("frame", [0, 1])
def test_t2_tampered_spritesheet_atlas_fails_its_digests(tmp_path: Path, frame: int) -> None:
    """A re-encoded atlas with one pixel changed is a valid PNG of the right size.

    Only the digests can tell: the atlas digest is checked first, so the error names
    ``/image/digest`` and no frame of the tampered atlas is returned.
    """
    pixels = FramePixels(2, 2, bytes((10, 20, 30, 255)) * 4)
    frames = [SheetFrame(f"f{index}", 100, Point(0, 0), pixels) for index in range(2)]
    encoded = encode_spritesheet(frames, columns=2)
    with Image.open(io.BytesIO(encoded.image)) as atlas:
        changed = atlas.copy()
    changed.putpixel((frame * 2, 1), (11, 20, 30, 255))  # one channel of one pixel
    buffer = io.BytesIO()
    changed.save(buffer, "PNG")
    image, manifest = tmp_path / "sheet.png", tmp_path / "sheet.json"
    image.write_bytes(buffer.getvalue())
    manifest.write_bytes(encoded.manifest_json)
    before = tree_state(tmp_path)
    with forbid_writes(), pytest.raises(ValidationError) as caught:
        load_spritesheet(image, manifest)
    assert_clean_error(caught.value, tmp_path)
    assert (caught.value.json_pointer, caught.value.context["reason"]) == (
        "/image/digest",
        "digest_mismatch",
    )
    assert tree_state(tmp_path) == before


def test_t2_manifest_rewritten_without_its_history_is_rejected(tmp_path: Path) -> None:
    root = _saved(tmp_path)
    manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["document"]["seed"] = 7  # a silent edit outside the history
    (root / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    error = _load_tampered(root, decoded_assets=True)
    assert error.context["reason"] == "invalid_history"


@bounded_settings(40, 10)  # tmp_path_factory is session-scoped
@given(st.data())
def test_t2_property_any_flipped_byte_is_detected_or_harmless(
    tmp_path_factory: pytest.TempPathFactory, data: st.DataObject
) -> None:
    root = _saved(tmp_path_factory.mktemp("flip"))
    files = sorted(path for path in root.rglob("*") if path.is_file())
    target = data.draw(st.sampled_from(files))
    content = bytearray(target.read_bytes())
    index = data.draw(st.integers(0, len(content) - 1))
    content[index] ^= data.draw(st.integers(1, 255))
    target.write_bytes(bytes(content))
    original = _project()
    try:
        loaded = load_project(root)
    except MoanaError as error:
        assert_clean_error(error, root)
        return
    # A flip the checksums cannot see must not have changed any verified byte.
    assert [asset.data for asset in loaded.assets] == [asset.data for asset in original.assets]
    assert loaded.document == original.document
    assert loaded.history is not None
    assert original.history is not None
    assert loaded.history.cursor == original.history.cursor
    assert list(loaded.history.snapshots) == list(original.history.snapshots)
    for digest, snapshot in original.history.snapshots.items():
        twin = loaded.history.snapshots[digest]
        assert (twin.parent, twin.batch, twin.document) == (
            snapshot.parent,
            snapshot.batch,
            snapshot.document,
        )


# --- decompression bombs --------------------------------------------------------------


@pytest.mark.parametrize(("width", "height"), [(65_535, 65_535), (2049, 1), (1, 2**31 - 1)])
def test_t2_bomb_headers_are_rejected_before_pillow(width: int, height: int) -> None:
    with forbid_allocation(), pytest.raises(ValidationError) as caught:
        Asset.from_png("bomb", png_declaring(width, height))
    assert caught.value.context["reason"] == "image_too_large"
    assert Image.MAX_IMAGE_PIXELS == PILLOW_LIMIT


def test_t2_pixel_budget_is_checked_from_the_header() -> None:
    with forbid_allocation(), pytest.raises(BudgetExceeded) as caught:
        Asset.from_png("big", png_declaring(2048, 2048), max_pixels=2048 * 2048 - 1)
    assert caught.value.context["resource"] == "asset_pixels"
    assert caught.value.context["estimated"] == 2048 * 2048


def test_t2_idat_expanding_beyond_the_header_decodes_only_declared_pixels() -> None:
    """Moana does not inflate in Python; Pillow stops at the declared dimensions.

    The guarantee is the decoded size (``len(asset.rgba) == 64``); the traced peak
    is only a sanity check, since Pillow's native buffers are invisible to it.
    """
    real = tiny_png(4, 4)
    end = real.index(b"IEND") - 4
    start = real.index(b"IDAT") - 4
    width_rows = 4 * (1 + 4 * 4)  # filter byte + RGBA per row
    bomb = zlib.compress(b"\0" * (width_rows + 8 * 1024 * 1024), 9)  # 8 MiB of excess
    hostile = real[:start] + chunk(b"IDAT", bomb) + real[end:]
    error, peak = peak_bytes(lambda: Asset.from_png("excess", hostile))
    assert error is None
    asset = Asset.from_png("excess", hostile)
    # Pillow stops at the declared 4 x 4 pixels: 64 bytes of RGBA, whatever the stream.
    assert (asset.width, asset.height, len(asset.rgba)) == (4, 4, 4 * 4 * 4)
    assert peak < 2 * 1024 * 1024


def test_t2_pillow_bomb_protection_stays_active_and_is_mapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Image.MAX_IMAGE_PIXELS == PILLOW_LIMIT  # the engine never disables it
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)  # a host stricter than Moana
    with pytest.raises(ValidationError) as caught:
        Asset.from_png("strict", tiny_png(16, 16))  # 256 > 2 x 10: Pillow's bomb error
    assert caught.value.context["reason"] == "unreadable_image"


def test_t2_loading_projects_never_changes_pillow_limits(tmp_path: Path) -> None:
    before = (Image.MAX_IMAGE_PIXELS, getattr(Image, "WARN_POSSIBLE_FORMATS", None))
    load_project(_saved(tmp_path))
    assert (Image.MAX_IMAGE_PIXELS, getattr(Image, "WARN_POSSIBLE_FORMATS", None)) == before
    assert Image.MAX_IMAGE_PIXELS == PILLOW_LIMIT
