"""AC2/T2 of MOANA-020: malicious archives, paths, checksums and image bombs.

Every malicious fixture is generated in ``tmp_path`` by the test itself. Loading
never writes: each test also checks that nothing appeared outside its inputs.
"""

from __future__ import annotations

import hashlib
import io
import json
import stat
import struct
import warnings
import zipfile
import zlib
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageFile

from moana.core.errors import BudgetExceeded, ReadError, ValidationError
from moana.project import (
    MANIFEST_NAME,
    Asset,
    Project,
    ProjectLimits,
    load_project,
    save_project,
    save_project_archive,
)
from moana.schema import Document

from .conftest import PngFactory

pytestmark = pytest.mark.security


def _raw_info(name: str) -> zipfile.ZipInfo:
    """A ``ZipInfo`` storing ``name`` verbatim on every platform.

    ``ZipInfo(name)`` turns ``os.sep`` into ``/`` (so a backslash on Windows) and cuts
    at a NUL; assigning ``filename`` afterwards keeps the hostile bytes in the archive.
    """
    info = zipfile.ZipInfo("placeholder")
    info.filename = info.orig_filename = name
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _zip(path: Path, entries: list[tuple[zipfile.ZipInfo | str, bytes]]) -> Path:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # zipfile warns about duplicate names
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for info, data in entries:
                archive.writestr(_raw_info(info) if isinstance(info, str) else info, data)
    return path


def _files(root: Path) -> set[Path]:
    return {path for path in root.rglob("*")}


def _symlink_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info


def _unsafe_reason(error: pytest.ExceptionInfo[ValidationError]) -> object:
    assert error.value.context["reason"] == "unsafe_archive"
    return error.value.context["entry_reason"]


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("../escape.json", "parent_reference"),
        ("assets/../../escape.png", "parent_reference"),
        ("/etc/escape.json", "absolute_path"),
        ("C:/escape.json", "absolute_path"),
        ("assets\\escape.png", "invalid_name"),
        ("assets/a\x00.png", "invalid_name"),
        ("assets//x.png", "invalid_name"),
        ("./project.moana.json", "invalid_name"),
        ("notes.txt", "unexpected_entry"),
        ("other/", "unexpected_entry"),
    ],
)
def test_t2_archive_names_are_rejected_before_extraction(
    tmp_path: Path, name: str, reason: str
) -> None:
    archive = _zip(tmp_path / "evil.moana", [(MANIFEST_NAME, b"{}"), (name, b"x")])
    before = _files(tmp_path)
    with pytest.raises(ValidationError) as caught:
        load_project(archive)
    assert _unsafe_reason(caught) == reason
    assert caught.value.context["entry"] == 1
    assert name not in caught.value.message
    assert _files(tmp_path) == before
    assert not (tmp_path.parent / "escape.json").exists()


def test_t2_symlink_entries_are_rejected(tmp_path: Path) -> None:
    archive = _zip(tmp_path / "link.moana", [(_symlink_info(MANIFEST_NAME), b"/etc/passwd")])
    with pytest.raises(ValidationError) as caught:
        load_project(archive)
    assert _unsafe_reason(caught) == "symlink"


def test_t2_duplicate_and_colliding_names_are_rejected(tmp_path: Path) -> None:
    duplicate = _zip(tmp_path / "dup.moana", [(MANIFEST_NAME, b"{}"), (MANIFEST_NAME, b"{}")])
    with pytest.raises(ValidationError) as caught:
        load_project(duplicate)
    assert _unsafe_reason(caught) == "duplicate_name"
    colliding = _zip(
        tmp_path / "case.moana", [(MANIFEST_NAME, b"{}"), ("PROJECT.moana.json", b"{}")]
    )
    with pytest.raises(ValidationError) as caught:
        load_project(colliding)
    assert _unsafe_reason(caught) == "name_collision"
    # NFC and NFD spellings of the same name also collide.
    nfc, nfd = "assets/\u00e9/", "assets/e\u0301/"
    unicode = _zip(tmp_path / "nfc.moana", [(nfc, b""), (nfd, b"")])
    with pytest.raises(ValidationError) as caught:
        load_project(unicode)
    assert _unsafe_reason(caught) == "name_collision"


def test_t2_excessive_expansion_ratio_is_rejected(tmp_path: Path) -> None:
    bomb = _zip(tmp_path / "ratio.moana", [(MANIFEST_NAME, b" " * 200_000)])
    info = zipfile.ZipFile(bomb).infolist()[0]
    assert info.file_size > 100 * info.compress_size  # the fixture really is a bomb
    with pytest.raises(ValidationError) as caught:
        load_project(bomb)
    assert _unsafe_reason(caught) == "expansion_ratio"


def test_t2_archive_budgets_are_checked_from_the_central_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entries: list[tuple[zipfile.ZipInfo | str, bytes]] = [
        (f"assets/{i:064x}.png", bytes(range(256))) for i in range(5)
    ]
    archive = _zip(tmp_path / "many.moana", entries)

    def no_decompression(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("an entry was decompressed before the budget check")

    monkeypatch.setattr(zipfile.ZipFile, "open", no_decompression)
    cases = [
        (ProjectLimits(max_archive_entries=4), "archive_entries"),
        (ProjectLimits(max_archive_bytes=512), "archive_bytes"),
        (ProjectLimits(max_archive_expanded_bytes=1000), "archive_expanded_bytes"),
    ]
    for limits, resource in cases:
        with pytest.raises(BudgetExceeded) as caught:
            load_project(archive, limits=limits)
        assert caught.value.context["resource"] == resource


def _flag_encrypted(path: Path) -> None:
    """Set bit 0 (encrypted) in the local and central headers; zipfile never writes it."""
    data = bytearray(path.read_bytes())
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        position = data.find(signature)
        data[position + offset] |= 0x1
    path.write_bytes(bytes(data))


@pytest.mark.parametrize("kind", ["encrypted", "compression"])
def test_t2_encrypted_or_exotic_entries_are_rejected(tmp_path: Path, kind: str) -> None:
    info = zipfile.ZipInfo(MANIFEST_NAME)
    if kind == "compression":
        info.compress_type = zipfile.ZIP_BZIP2
    archive = _zip(tmp_path / "x.moana", [(info, b"{}")])
    if kind == "encrypted":
        _flag_encrypted(archive)
    with pytest.raises(ValidationError) as caught:
        load_project(archive)
    assert _unsafe_reason(caught) == kind


_EOCD = struct.Struct("<4sHHHHIIH")


def _eocd(data: bytes) -> tuple[Any, ...]:
    """The fields of the end of central directory record in the last 22 bytes."""
    return _EOCD.unpack(data[-_EOCD.size :])


def _end_record(total: int, size: int, offset: int) -> bytes:
    return _EOCD.pack(b"PK\x05\x06", 0, 0, total, total, size, offset, 0)


def _with_zip64_locator(data: bytes) -> bytes:
    """A ZIP64 end locator inserted right before the end record, sizes kept consistent."""
    _, _, _, _, total, size, offset, _ = _eocd(data)
    locator = b"PK\x06\x07" + b"\x00" * 16
    return data[: -_EOCD.size] + locator + _end_record(total, size + len(locator), offset)


def test_t2_corrupt_archives_are_rejected(tmp_path: Path, project: Project) -> None:
    good = tmp_path / "good.moana"
    save_project_archive(project, good)
    data = good.read_bytes()
    cases = {
        "truncated": data[: len(data) // 2],
        "no_directory": b"PK\x03\x04" + b"\x00" * 64,
        "shorter_than_an_end_record": b"PK\x03\x04",
        "multi_disk": data[:-18] + struct.pack("<H", 1) + data[-16:],
        "split_count": data[:-12] + struct.pack("<H", 99) + data[-10:],
        "count_mismatch": data[:-14] + struct.pack("<HH", 99, 99) + data[-10:],
        "zip64": data[:-14] + struct.pack("<HH", 0xFFFF, 0xFFFF) + data[-10:],
        "garbage_directory": data.replace(b"PK\x01\x02", b"XX\x01\x02"),
        "comment": data[:-2] + struct.pack("<H", 4) + b"note",
        "trailing_bytes": data + b"\x00",
        "offset_gap": data[:-6] + struct.pack("<I", _eocd(data)[6] - 1) + data[-2:],
        "size_overlap": data[:-10] + struct.pack("<I", _eocd(data)[5] + 1) + data[-6:],
        "directory_flood": b"PK\x03\x04" + b"\x00" * 996 + _end_record(1, 1000, 0),
        "zip64_sentinel_size": data[:-10] + struct.pack("<I", 0xFFFFFFFF) + data[-6:],
        "zip64_locator": _with_zip64_locator(data),
    }
    for name, payload in cases.items():
        broken = tmp_path / f"{name}.moana"
        broken.write_bytes(payload)
        with pytest.raises(ValidationError) as caught:
            load_project(broken)
        assert caught.value.context["reason"] == "corrupt_archive", name


def test_t2_corrupt_entry_data_fails_its_crc(tmp_path: Path, document: Document) -> None:
    archive = tmp_path / "crc.moana"
    save_project_archive(Project(document), archive)
    data = bytearray(archive.read_bytes())
    start = 30 + len(MANIFEST_NAME)  # first local header, then the manifest's data
    data[start + 5] ^= 0xFF
    archive.write_bytes(bytes(data))
    with pytest.raises(ValidationError) as caught:
        load_project(archive)
    assert caught.value.context["reason"] == "corrupt_archive"


def test_t2_archive_without_manifest_or_declared_file(tmp_path: Path, project: Project) -> None:
    empty = _zip(tmp_path / "empty.moana", [("assets/", b"")])
    with pytest.raises(ValidationError) as caught:
        load_project(empty)
    assert caught.value.context["reason"] == "missing_entry"
    assert caught.value.context["file_name"] == MANIFEST_NAME
    good = tmp_path / "good.moana"
    save_project_archive(project, good)
    with zipfile.ZipFile(good) as source:
        kept = [(info, source.read(info)) for info in source.infolist()]
    missing = [(info, data) for info, data in kept if not info.filename.startswith("assets/")]
    with pytest.raises(ValidationError) as caught:
        load_project(_zip(tmp_path / "missing.moana", list(missing)))
    assert caught.value.context["reason"] == "missing_entry"


def test_t2_dense_entries_are_stored_so_saved_archives_always_load(
    tmp_path: Path, document: Document, png: PngFactory
) -> None:
    flat = png(2048, 512, (0, 0, 0, 0))  # compresses far beyond 100:1 when deflated again
    project = Project(document, (Asset.from_png("flat", flat),))
    raw = zlib.compress(flat, 9)
    assert len(raw) * 1 < len(flat)
    archive = tmp_path / "dense.moana"
    save_project_archive(project, archive, limits=ProjectLimits(max_archive_ratio=2))
    loaded = load_project(archive, limits=ProjectLimits(max_archive_ratio=2))
    assert loaded == project
    stored = {i.filename: i.compress_type for i in zipfile.ZipFile(archive).infolist()}
    assert zipfile.ZIP_STORED in stored.values()
    with pytest.raises(BudgetExceeded) as caught:
        save_project_archive(
            project, tmp_path / "x.moana", limits=ProjectLimits(max_archive_entries=1)
        )
    assert caught.value.context["resource"] == "archive_entries"


# --- directory projects with malicious manifests -------------------------------------


def _manifest(root: Path) -> dict[str, Any]:
    tree: dict[str, Any] = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    return tree


def _write_manifest(root: Path, tree: dict[str, Any]) -> None:
    (root / MANIFEST_NAME).write_text(json.dumps(tree), encoding="utf-8")


@pytest.mark.parametrize(
    "path",
    ["../escape.png", "/tmp/escape.png", "assets/../../escape.png", "assets\\x.png", "C:/x.png"],
)
def test_ac2_asset_path_outside_the_layout_is_rejected(
    tmp_path: Path, project: Project, path: str
) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    tree = _manifest(root)
    tree["assets"][0]["path"] = path
    _write_manifest(root, tree)
    before = _files(tmp_path)
    with pytest.raises(ValidationError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "invalid_manifest"
    assert caught.value.details[0].json_pointer == "/assets/0"
    assert path not in str(caught.value.details)
    assert _files(tmp_path) == before


def test_ac2_wrong_checksum_never_loads_partially(tmp_path: Path, project: Project) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    second = root / project.assets[1].path
    second.write_bytes(second.read_bytes()[:-1] + b"\x00")
    with pytest.raises(ValidationError) as caught:
        load_project(root)
    assert caught.value.context == {"reason": "checksum_mismatch", "index": 1}
    tree = _manifest(root)
    tree["assets"][0]["sha256"] = "0" * 64
    tree["assets"][0]["path"] = f"assets/{'0' * 64}.png"
    _write_manifest(root, tree)
    with pytest.raises(ReadError) as missing:
        load_project(root)
    assert missing.value.context["reason"] == "not_found"


def test_ac2_longer_asset_file_is_a_checksum_mismatch(tmp_path: Path, project: Project) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    first = root / project.assets[0].path
    first.write_bytes(first.read_bytes() + b"tail")
    with pytest.raises(ValidationError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "checksum_mismatch"


def test_ac2_linked_assets_never_leave_the_root(
    tmp_path: Path, project: Project, confinement: bool
) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    outside = tmp_path / "outside"
    outside.mkdir()
    asset = project.assets[0]
    (outside / Path(asset.path).name).write_bytes(asset.data)
    target = root / asset.path
    target.unlink()
    try:
        target.symlink_to(outside / Path(asset.path).name)
    except OSError:  # pragma: no cover - Windows without symlink privilege
        pytest.skip("symbolic links are not available")
    with pytest.raises(ReadError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "not_a_file"
    target.unlink()
    for item in list((root / "assets").iterdir()):
        (outside / item.name).write_bytes(item.read_bytes())
        item.unlink()
    (root / "assets").rmdir()
    (root / "assets").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ReadError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "not_a_file"
    manifest = root / MANIFEST_NAME
    real = tmp_path / "real.json"
    real.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(real)
    with pytest.raises(ReadError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "not_a_file"


def test_ac2_special_files_are_not_read(tmp_path: Path, project: Project) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    target = root / project.assets[0].path
    target.unlink()
    target.mkdir()
    with pytest.raises(ReadError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "is_directory"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"id": "body_fill"}, "id_collision"),
        ({"id": "gradient"}, "duplicate_asset_id"),
    ],
)
def test_ac2_asset_ids_are_unique_and_distinct_from_document_ids(
    tmp_path: Path, project: Project, change: dict[str, str], reason: str
) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    tree = _manifest(root)
    tree["assets"][0].update(change)
    _write_manifest(root, tree)
    with pytest.raises(ValidationError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == reason


def _bomb_png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(kind + payload)
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00" * 1024)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    )


def test_t2_image_bomb_is_rejected_before_decoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document: Document
) -> None:
    root = tmp_path / "p"
    save_project(Project(document), root)
    bomb = _bomb_png(65_535, 65_535)
    digest = hashlib.sha256(bomb).hexdigest()
    (root / "assets").mkdir()
    (root / "assets" / f"{digest}.png").write_bytes(bomb)
    tree = _manifest(root)
    tree["assets"] = [
        {
            "id": "bomb",
            "path": f"assets/{digest}.png",
            "mime": "image/png",
            "byte_length": len(bomb),
            "sha256": digest,
        }
    ]
    _write_manifest(root, tree)

    def no_decode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Pillow was called on a bomb")

    monkeypatch.setattr(Image, "open", no_decode)
    with pytest.raises(ValidationError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "image_too_large"
    assert caught.value.context["maximum"] == 2048


def test_t2_asset_pixel_and_byte_budgets(png: PngFactory) -> None:
    with pytest.raises(BudgetExceeded) as caught:
        Asset.from_png("big", png(64, 64), max_pixels=4095)
    assert caught.value.context["resource"] == "asset_pixels"
    data = png()
    with pytest.raises(BudgetExceeded) as caught:
        Asset.from_png("big", data, max_bytes=len(data) - 1)
    assert caught.value.context["resource"] == "asset_bytes"
    for width, height in ((2049, 1), (2048, 2049)):
        with pytest.raises(ValidationError) as size:
            Asset.from_png("wide", _bomb_png(width, height))
        assert size.value.context["reason"] == "image_too_large"
    # Exactly MAX_DIMENSION on both axes passes the header check and reaches the
    # bounded decode, which then fails on the short pixel data.
    with pytest.raises(ValidationError) as border:
        Asset.from_png("wide", _bomb_png(2048, 2048))
    assert border.value.context["reason"] == "unreadable_image"


def test_t2_project_pixel_budget_across_assets(
    tmp_path: Path, document: Document, png: PngFactory
) -> None:
    assets = (Asset.from_png("a", png(8, 8)), Asset.from_png("b", png(8, 8, (1, 1, 1, 1))))
    root = tmp_path / "p"
    save_project(Project(document, assets), root)
    with pytest.raises(BudgetExceeded) as caught:
        load_project(root, limits=ProjectLimits(max_asset_pixels=100))
    assert caught.value.context["resource"] == "asset_pixels"
    for limits, resource in (
        (ProjectLimits(max_assets=1), "project_assets"),
        (ProjectLimits(max_asset_bytes=50), "asset_bytes"),
    ):
        with pytest.raises(BudgetExceeded) as caught:
            load_project(root, limits=limits)
        assert caught.value.context["resource"] == resource


def _noise_png() -> bytes:
    """An RGBA PNG whose ``IDAT`` is large under every zlib build.

    The pixels are SHA-256 output, hence incompressible: a periodic pattern compressed
    to ~240 bytes with zlib-ng on macOS and below 200 on Linux wheels, so cutting 200
    bytes removed the ``IHDR`` and the case tested ``not_png`` instead of truncation.
    """
    pixels = b"".join(hashlib.sha256(i.to_bytes(2, "big")).digest() for i in range(512))
    image = Image.frombytes("RGBA", (64, 64), pixels)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    data = buffer.getvalue()
    assert len(data) > 4 * 64 * 64  # the truncation below always keeps the IHDR
    return data


def _apng() -> bytes:
    frames = [Image.new("RGBA", (2, 2), (i, 0, 0, 255)) for i in (0, 255)]
    buffer = io.BytesIO()
    frames[0].save(buffer, "PNG", save_all=True, append_images=frames[1:])
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("not_png", "not_png"),
        ("bad_ihdr", "not_png"),
        ("rgb", "wrong_mode"),
        ("rgba16", "wrong_mode"),
        ("apng", "multiple_frames"),
        ("icc", "color_profile"),
        ("truncated", "unreadable_image"),
        ("no_iend", "unreadable_image"),
        ("corrupt_idat", "unreadable_image"),
    ],
)
def test_t2_png_assets_are_checked_before_full_decode(
    png: PngFactory, kind: str, reason: str
) -> None:
    good = png()
    data = {
        "not_png": b"GIF89a" + b"\x00" * 40,
        "bad_ihdr": good[:12] + b"IHDX" + good[16:],
        "rgb": png(mode="RGB"),
        "rgba16": good[:24] + b"\x10" + good[25:],
        "apng": _apng(),
        "icc": png(icc_profile=b"\x00" * 128),
        "truncated": _noise_png()[:-200],
        "no_iend": good[:-12],
        "corrupt_idat": good[:-20] + bytes([good[-20] ^ 0xFF]) + good[-19:],
    }[kind]
    with pytest.raises(ValidationError) as caught:
        Asset.from_png("tex", data)
    assert caught.value.context["reason"] == reason


def test_t2_truncated_png_is_rejected_even_if_pillow_tolerates_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ImageFile, "LOAD_TRUNCATED_IMAGES", True)
    with pytest.raises(ValidationError) as caught:
        Asset.from_png("tex", _noise_png()[:-200])
    assert caught.value.context["reason"] == "unreadable_image"


def test_t2_pillow_decompression_bomb_is_a_domain_error(
    monkeypatch: pytest.MonkeyPatch, png: PngFactory
) -> None:
    data = png(64, 64)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        with pytest.raises(ValidationError) as caught:
            Asset.from_png("tex", data)
    assert caught.value.context["reason"] == "unreadable_image"


def test_t2_asset_values_are_consistent(png: PngFactory) -> None:
    asset = Asset.from_png("tex", png())
    assert Asset(asset.id, asset.data, asset.width, asset.height, asset.rgba) == asset
    with pytest.raises(ValidationError) as caught:
        Asset(asset.id, asset.data, asset.width, asset.height, b"\x00" * len(asset.rgba))
    assert caught.value.context["reason"] == "pixel_mismatch"
    with pytest.raises(ValidationError):
        Asset.from_png("Not An ID", png())
    with pytest.raises(TypeError):
        Asset.from_png("tex", bytearray(png()))  # type: ignore[arg-type]
    assert asset.sha256 == hashlib.sha256(asset.data).hexdigest()
    assert asset.pixels == 12


@pytest.mark.parametrize("band_id", ["band_highlight", "band_body"])
def test_ac2_asset_id_of_a_shade_band_is_an_id_collision(
    tmp_path: Path, shaded: Document, png: PngFactory, band_id: str
) -> None:
    """Band IDs belong to the document namespace (``schema.document_ids``, ADR-028)."""
    with pytest.raises(ValidationError) as caught:
        Project(shaded, (Asset.from_png(band_id, png()),))
    assert caught.value.context["reason"] == "id_collision"
    root = tmp_path / "p"
    save_project(Project(shaded, (Asset.from_png("orb_texture", png()),)), root)
    tree = _manifest(root)
    tree["assets"][0]["id"] = band_id
    _write_manifest(root, tree)
    with pytest.raises(ValidationError) as loaded:
        load_project(root)
    assert loaded.value.context["reason"] == "id_collision"
