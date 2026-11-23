"""PNG export: round-trip, indexed order, scale, atomic writes and races (MOANA-011).

Expected pixels are built by hand here; decoding uses Pillow directly, independent of
the exporter's own verification.
"""

from __future__ import annotations

import ast
import errno
import hashlib
import io
import os
import struct
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from moanart.core.budget import RenderLimits
from moanart.core.digest import visual_digest
from moanart.core.errors import BudgetExceeded, ExportError, ValidationError
from moanart.core.limits import GeometryLimits
from moanart.export import ExportManifest, encode_png, export_png
from moanart.export import png as png_module
from moanart.palette import Palette, PaletteColor, Rgba

RGBA = tuple[int, int, int, int]


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    rgba: bytes


def frame(rows: list[list[RGBA]]) -> Frame:
    data = bytes(channel for row in rows for pixel in row for channel in pixel)
    return Frame(len(rows[0]), len(rows), data)


CLEAR: RGBA = (0, 0, 0, 0)
INK: RGBA = (16, 32, 48, 255)
GLASS: RGBA = (200, 100, 50, 77)
ROWS: list[list[RGBA]] = [[INK, GLASS, CLEAR], [CLEAR, INK, (1, 2, 3, 1)]]
SAMPLE = frame(ROWS)


def decode(path_or_bytes: Path | bytes) -> tuple[str, int, int, list[RGBA]]:
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else path_or_bytes.read_bytes()
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        mode, (width, height) = image.mode, image.size
        rgba = image.convert("RGBA").tobytes()
    pixels = [tuple(rgba[i : i + 4]) for i in range(0, len(rgba), 4)]
    return mode, width, height, pixels  # type: ignore[return-value]  # 4-tuples by slicing


def scaled_by_hand(rows: list[list[RGBA]], k: int) -> list[RGBA]:
    return [pixel for row in rows for _ in range(k) for pixel in row for _ in range(k)]


def chunk_types(data: bytes) -> list[bytes]:
    types, offset = [], 8
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        types.append(data[offset + 4 : offset + 8])
        offset += 12 + length
    return types


def chunk(data: bytes, kind: bytes) -> bytes:
    offset = 8
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        if data[offset + 4 : offset + 8] == kind:
            return data[offset + 8 : offset + 8 + length]
        offset += 12 + length
    raise AssertionError(f"no {kind!r} chunk")


def palette(values: list[RGBA], profile: str = "rgba") -> Palette:
    colors = tuple(PaletteColor(f"c{i}", Rgba(*value)) for i, value in enumerate(values))
    return Palette("pal", profile, colors)  # type: ignore[arg-type]  # literal profile


# --- AC1 / T1: round-trip -------------------------------------------------------------


def test_ac1_rgba_png_decodes_exactly_to_the_frame(tmp_path: Path) -> None:
    manifest = export_png(SAMPLE, tmp_path / "sprite.png")
    mode, width, height, pixels = decode(tmp_path / "sprite.png")
    assert (mode, width, height) == ("RGBA", 3, 2)
    assert pixels == [pixel for row in ROWS for pixel in row]
    assert manifest.source_digest == manifest.pixel_digest == visual_digest(3, 2, SAMPLE.rgba)
    assert manifest.master and manifest.warnings == ()


def test_ac1_rendered_document_round_trips(tmp_path: Path) -> None:
    from moanart.render import render
    from moanart.schema import validate_document

    root = Path(__file__).resolve().parents[3]
    result = render(validate_document((root / "examples/specs/minimal.moanart.json").read_bytes()))
    manifest = export_png(result, tmp_path / "minimal.png")
    _, width, height, pixels = decode(tmp_path / "minimal.png")
    assert bytes(c for p in pixels for c in p) == result.rgba
    assert (width, height) == (128, 128)
    assert manifest.source_digest == result.digest


@pytest.mark.parametrize("k", [1, 2, 4])
def test_t1_nearest_scale_replicates_blocks(tmp_path: Path, k: int) -> None:
    manifest = export_png(SAMPLE, tmp_path / f"x{k}.png", scale=k)
    _, width, height, pixels = decode(tmp_path / f"x{k}.png")
    assert (width, height) == (3 * k, 2 * k)
    assert pixels == scaled_by_hand(ROWS, k)
    assert (manifest.width, manifest.height, manifest.scale) == (3 * k, 2 * k, k)
    assert manifest.master is (k == 1)
    assert manifest.warnings == (() if k == 1 else ("scaled_preview",))
    assert manifest.source_digest == visual_digest(3, 2, SAMPLE.rgba)


@pytest.mark.parametrize("k", [1, 2, 4])
def test_t1_indexed_round_trip_keeps_declared_order_and_transparency(
    tmp_path: Path, k: int
) -> None:
    # Index = declaration position; the duplicate (5) of INK never wins; the unused
    # entry (3) is still written; #FF000000 is transparent and normalised to zero.
    values = [GLASS, INK, (255, 0, 0, 0), (9, 9, 9, 255), (1, 2, 3, 1), INK]
    export_png(SAMPLE, tmp_path / "i.png", mode="indexed", palette=palette(values), scale=k)
    mode, _, _, pixels = decode(tmp_path / "i.png")
    assert mode == "P"
    assert pixels == scaled_by_hand(ROWS, k)
    with Image.open(tmp_path / "i.png") as image:
        raw_palette = image.getpalette()
        assert raw_palette is not None
        assert raw_palette[: 6 * 3] == [
            200, 100, 50, 16, 32, 48, 0, 0, 0, 9, 9, 9, 1, 2, 3, 16, 32, 48,
        ]  # fmt: skip
        assert image.info["transparency"][:6] == bytes([77, 255, 0, 255, 1, 255])
        assert list(image.tobytes())[: 3 * k : k] == [1, 0, 2]  # INK, GLASS, CLEAR
    data = (tmp_path / "i.png").read_bytes()
    assert chunk(data, b"PLTE") == bytes(
        [200, 100, 50, 16, 32, 48, 0, 0, 0, 9, 9, 9, 1, 2, 3, 16, 32, 48]
    )  # exactly the six declared entries, no padding
    assert chunk(data, b"tRNS") == bytes([77, 255, 0, 255, 1, 255])


def test_maximum_scale_on_a_single_indexed_pixel(tmp_path: Path) -> None:
    single = frame([[INK]])
    manifest = export_png(
        single, tmp_path / "p.png", scale=64, mode="indexed", palette=palette([GLASS, INK])
    )
    mode, width, height, pixels = decode(tmp_path / "p.png")
    assert (mode, width, height, manifest.scale) == ("P", 64, 64, 64)
    assert pixels == [INK] * 64 * 64


def test_palette_chunks_are_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    real = png_module._encode_image

    def truncated_alpha(image: Any, *, transparency: bytes | None = None) -> bytes:
        return real(image, transparency=None if transparency is None else transparency[:-1])

    monkeypatch.setattr(png_module, "_encode_image", truncated_alpha)
    with pytest.raises(ExportError) as excinfo:
        encode_png(SAMPLE, mode="indexed", palette=palette([GLASS, INK, CLEAR, ROWS[1][2]]))
    assert excinfo.value.context["reason"] == "palette_mismatch"


def test_t1_transparent_frame_round_trips_in_both_modes(tmp_path: Path) -> None:
    empty = frame([[CLEAR, CLEAR]])
    export_png(empty, tmp_path / "a.png")
    export_png(empty, tmp_path / "b.png", mode="indexed", palette=palette([CLEAR]))
    assert decode(tmp_path / "a.png")[3] == decode(tmp_path / "b.png")[3] == [CLEAR, CLEAR]


def test_encoding_is_stable_and_has_no_volatile_chunks() -> None:
    first, second = encode_png(SAMPLE), encode_png(SAMPLE)
    assert first.data == second.data
    assert set(chunk_types(first.data)) <= {b"IHDR", b"IDAT", b"IEND"}
    assert png_module._chunk(first.data, b"PLTE") is None  # RGBA master has no palette
    indexed = encode_png(SAMPLE, mode="indexed", palette=palette([INK, GLASS, CLEAR, ROWS[1][2]]))
    assert set(chunk_types(indexed.data)) <= {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"}


_ENCODE_IN_CHILD = """
import hashlib
from dataclasses import dataclass
from moanart.export import encode_png
from moanart.palette import Palette, PaletteColor, Rgba

@dataclass(frozen=True)
class F:
    width: int
    height: int
    rgba: bytes

f = F(3, 2, bytes([16, 32, 48, 255, 200, 100, 50, 77, 0, 0, 0, 0] * 2))
p = Palette("pal", "rgba", tuple(PaletteColor(f"c{i}", Rgba(*v)) for i, v in enumerate(
    [(200, 100, 50, 77), (16, 32, 48, 255), (0, 0, 0, 0)])))
for data in (encode_png(f, scale=2).data, encode_png(f, mode="indexed", palette=p).data):
    print(hashlib.sha256(data).hexdigest())
"""


@pytest.mark.slow
def test_encoded_bytes_agree_across_fresh_processes_and_hash_seeds() -> None:
    outputs = {
        subprocess.run(
            [sys.executable, "-c", _ENCODE_IN_CHILD],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("0", "1", "4242")
    }
    assert len(outputs) == 1


# --- T2: palettes and options ---------------------------------------------------------


def test_t2_palette_of_256_is_accepted_and_257_rejected() -> None:
    values: list[RGBA] = [(i, 0, 0, 255) for i in range(255)] + [CLEAR]
    pixels = frame([[(254, 0, 0, 255), CLEAR, (0, 0, 0, 255)]])
    encoded = encode_png(pixels, mode="indexed", palette=palette(values))
    assert decode(encoded.data)[3] == [(254, 0, 0, 255), CLEAR, (0, 0, 0, 255)]
    with pytest.raises(ValidationError) as excinfo:
        encode_png(pixels, mode="indexed", palette=palette([*values, (1, 1, 1, 255)]))
    assert excinfo.value.context["reason"] == "too_many_colors"
    assert excinfo.value.context["count"] == 257


def test_indexed_export_never_quantises() -> None:
    near = frame([[INK, (16, 32, 49, 255)]])
    with pytest.raises(ValidationError) as excinfo:
        encode_png(near, mode="indexed", palette=palette([INK]))
    assert dict(excinfo.value.context) == {
        "field": "palette",
        "reason": "color_not_in_palette",
        "x": 1,
        "y": 0,
        "pixels": 1,
    }


@pytest.mark.parametrize(
    ("kwargs", "error", "reason"),
    [
        ({"scale": 0}, ValidationError, "out_of_range"),
        ({"scale": 65}, ValidationError, "out_of_range"),
        ({"scale": True}, ValidationError, "not_integer"),
        ({"mode": "gif"}, ValidationError, "unknown_mode"),
        ({"mode": "indexed"}, ValidationError, "missing_palette"),
        ({"palette": "p"}, ValidationError, "unexpected_palette"),
        ({"limits": None}, TypeError, None),
    ],
)
def test_options_are_validated(kwargs: dict[str, Any], error: type[Exception], reason: str) -> None:
    with pytest.raises(error) as excinfo:
        encode_png(SAMPLE, **kwargs)
    if reason is not None:
        assert excinfo.value.context["reason"] == reason  # type: ignore[attr-defined]  # MoanArtError


@pytest.mark.parametrize(
    ("bad", "error"),
    [
        (Frame(3, 2, SAMPLE.rgba[:-1]), ValidationError),
        (Frame(3, 2, bytearray(SAMPLE.rgba)), TypeError),  # type: ignore[arg-type]  # misuse
        (Frame(0, 2, b""), ValidationError),
        (frame([[(5, 0, 0, 0)]]), ValidationError),  # colour under zero alpha
    ],
)
def test_frames_are_validated(bad: Frame, error: type[Exception]) -> None:
    with pytest.raises(error):
        encode_png(bad)


def test_palette_must_be_a_palette_value() -> None:
    with pytest.raises(TypeError):
        encode_png(SAMPLE, mode="indexed", palette=[INK])  # type: ignore[arg-type]  # list


def test_budget_is_checked_before_scaling(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_allocation(*args: object, **kwargs: object) -> None:
        raise AssertionError("allocated before the budget check")

    monkeypatch.setattr(np, "repeat", no_allocation)
    big = Frame(1024, 1, bytes(4096))
    with pytest.raises(BudgetExceeded) as excinfo:
        encode_png(big, scale=3)
    assert excinfo.value.context["resource"] == "export_dimension"
    with pytest.raises(BudgetExceeded) as excinfo:
        encode_png(SAMPLE, scale=2, limits=RenderLimits(max_buffer_bytes=100))
    assert excinfo.value.context["resource"] == "buffer_bytes"
    small = RenderLimits(geometry=GeometryLimits(max_area=20))
    with pytest.raises(BudgetExceeded) as excinfo:
        encode_png(SAMPLE, scale=2, limits=small)
    assert excinfo.value.context["resource"] == "export_area"


def test_roundtrip_mismatch_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = png_module._decode_rgba

    def corrupt(data: bytes) -> Any:
        pixels = real(data).copy()
        pixels[0, 0, 0] ^= 1
        return pixels

    monkeypatch.setattr(png_module, "_decode_rgba", corrupt)
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / "x.png")
    assert excinfo.value.context["reason"] == "roundtrip_mismatch"
    assert list(tmp_path.iterdir()) == []


# --- T2 / AC2: destinations and failures ----------------------------------------------


def test_t2_existing_destination_is_kept_unless_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "sprite.png"
    target.write_bytes(b"previous")
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, target)
    assert dict(excinfo.value.context) == {"reason": "exists", "file_name": "sprite.png"}
    assert target.read_bytes() == b"previous"
    manifest = export_png(SAMPLE, target, overwrite=True)
    assert manifest.file_sha256 == "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    assert manifest.byte_size == target.stat().st_size
    assert sorted(p.name for p in tmp_path.iterdir()) == ["sprite.png"]


def _posix_non_root() -> bool:
    if sys.platform == "win32":
        return False
    return os.geteuid() != 0


@pytest.mark.skipif(not _posix_non_root(), reason="POSIX permissions as non-root")
def test_t2_permission_denied_leaves_nothing(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "old.png").write_bytes(b"previous")
    locked.chmod(0o500)
    try:
        for overwrite in (False, True):
            with pytest.raises(ExportError) as excinfo:
                export_png(SAMPLE, locked / "old.png", overwrite=overwrite)
            assert excinfo.value.context["reason"] == "permission_denied"
        assert (locked / "old.png").read_bytes() == b"previous"
        assert [p.name for p in locked.iterdir()] == ["old.png"]
    finally:
        locked.chmod(0o700)


@pytest.mark.parametrize("stage", ["write", "fsync", "link", "replace"])
@pytest.mark.parametrize("overwrite", [False, True])
def test_ac2_t2_failure_during_write_keeps_previous_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, overwrite: bool
) -> None:
    target = tmp_path / "sprite.png"
    if overwrite:
        target.write_bytes(b"previous")
    calls = {"write": 0}
    real_write = os.write

    def failing_write(descriptor: int, data: Any) -> int:
        calls["write"] += 1
        if calls["write"] == 1:  # half the bytes land, then the disk fails
            return real_write(descriptor, bytes(data)[: len(data) // 2])
        raise OSError(errno.ENOSPC, "no space")

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError(errno.EIO, "simulated I/O error")

    if stage == "write":
        monkeypatch.setattr(os, "write", failing_write)
    else:
        monkeypatch.setattr(os, stage, fail)
    commits = {"link": not overwrite, "replace": overwrite}
    if stage in commits and not commits[stage]:
        export_png(SAMPLE, target, overwrite=overwrite)  # this path does not use it
        return
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, target, overwrite=overwrite)
    assert excinfo.value.context["reason"] == "io_error"
    assert "errno" in excinfo.value.context
    if overwrite:
        assert target.read_bytes() == b"previous"
    else:
        assert not target.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == (["sprite.png"] if overwrite else [])


def test_filesystem_without_links_fails_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_links(*args: object, **kwargs: object) -> None:
        raise OSError(errno.EPERM, "hard links not supported")

    monkeypatch.setattr(os, "link", no_links)
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / "x.png")
    assert excinfo.value.context["reason"] == "no_replace_unavailable"
    assert list(tmp_path.iterdir()) == []


def test_destination_checks(tmp_path: Path) -> None:
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / "missing" / "x.png")
    assert excinfo.value.context["reason"] == "missing_directory"
    (tmp_path / "dir.png").mkdir()
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / "dir.png", overwrite=True)
    assert excinfo.value.context["reason"] == "is_directory"
    with pytest.raises(ValidationError):
        export_png(SAMPLE, tmp_path / "x.jpg")
    with pytest.raises(TypeError):
        export_png(SAMPLE, 3)  # type: ignore[arg-type]  # not a path
    with pytest.raises(TypeError):
        export_png(SAMPLE, tmp_path / "x.png", overwrite=1)  # type: ignore[arg-type]
    assert not (tmp_path / "x.png").exists()


@pytest.mark.parametrize("name", ["a\x00b.png", "a\ud800.png"])
def test_unrepresentable_names_are_rejected_before_writing(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        export_png(SAMPLE, tmp_path / name)
    assert excinfo.value.context["reason"] == "invalid_name"
    with pytest.raises(TypeError):
        export_png(SAMPLE, _BytesPath())  # type: ignore[arg-type]  # bytes path
    assert list(tmp_path.iterdir()) == []


def test_atomic_commit_rejects_unrepresentable_names(tmp_path: Path) -> None:
    from moanart.export.atomic import commit_bytes

    with pytest.raises(ExportError) as excinfo:
        commit_bytes(b"x", tmp_path / "a\x00b.png", overwrite=False)
    assert excinfo.value.context["reason"] == "invalid_name"
    assert list(tmp_path.iterdir()) == []


def test_long_valid_names_still_commit(tmp_path: Path) -> None:
    name = "n" * 240 + ".png"  # 244 bytes: valid, but too long with a naive temp suffix
    export_png(SAMPLE, tmp_path / name)
    assert [p.name for p in tmp_path.iterdir()] == [name]


def test_inspection_errors_are_wrapped_without_paths(tmp_path: Path) -> None:
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / ("n" * 300 + ".png"))  # beyond NAME_MAX
    assert excinfo.value.context["reason"] == "io_error"
    assert str(tmp_path) not in str(excinfo.value)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not _posix_non_root(), reason="POSIX permissions as non-root")
def test_unsearchable_parent_is_permission_denied(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    (locked / "sub").mkdir(parents=True)
    locked.chmod(0o000)
    try:
        with pytest.raises(ExportError) as excinfo:
            export_png(SAMPLE, locked / "sub" / "x.png")
        assert excinfo.value.context["reason"] == "permission_denied"
        assert str(tmp_path) not in str(excinfo.value)
    finally:
        locked.chmod(0o700)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symbolic link loop (ELOOP)")
@pytest.mark.parametrize("overwrite", [False, True])
@pytest.mark.parametrize("where", ["destination", "parent"])
def test_link_loops_fail_closed_as_io_error(tmp_path: Path, where: str, overwrite: bool) -> None:
    """ADR-039: an ``ELOOP`` while inspecting is ``io_error``, never "missing" or "absent"."""
    loop = tmp_path / ("x.png" if where == "destination" else "loop")
    loop.symlink_to(loop)
    target = loop if where == "destination" else loop / "x.png"
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, target, overwrite=overwrite)
    assert excinfo.value.context["reason"] == "io_error"
    assert excinfo.value.context["errno"] == "ELOOP"
    assert str(tmp_path) not in str(excinfo.value)
    assert [p.name for p in tmp_path.iterdir()] == [loop.name]
    assert loop.is_symlink() and os.readlink(loop) == str(loop)


def test_stat_is_directory_never_raises(tmp_path: Path) -> None:
    from moanart.export.atomic import stat_is_directory

    (tmp_path / "file").write_bytes(b"")
    assert stat_is_directory(tmp_path)
    assert not stat_is_directory(tmp_path / "file")
    assert not stat_is_directory(tmp_path / "missing")
    assert not stat_is_directory(str(tmp_path / "a\x00b"))


class _BytesPath:
    def __fspath__(self) -> bytes:
        return b"x.png"


def test_errors_do_not_echo_full_paths(tmp_path: Path) -> None:
    (tmp_path / "x.png").write_bytes(b"")
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / "x.png")
    assert str(tmp_path) not in str(excinfo.value)
    assert str(tmp_path) not in repr(dict(excinfo.value.context))


def test_manifest_contents(tmp_path: Path) -> None:
    manifest = export_png(SAMPLE, str(tmp_path / "m.png"), scale=2)
    assert isinstance(manifest, ExportManifest)
    mapping = manifest.to_mapping()
    assert list(mapping) == sorted(mapping)
    assert mapping["path"] == str(tmp_path / "m.png")
    assert (mapping["media_type"], mapping["frames"], mapping["mode"]) == ("image/png", 1, "rgba")
    assert (mapping["source_width"], mapping["source_height"]) == (3, 2)
    assert mapping["pixel_digest"] == visual_digest(
        6, 4, bytes(c for p in scaled_by_hand(ROWS, 2) for c in p)
    )
    assert mapping["warnings"] == ["scaled_preview"]


# --- T3: concurrent writers -----------------------------------------------------------


def test_t3_competitor_created_between_checks_and_commit_is_never_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic race: another writer creates the name right before our commit.

    A check-then-replace implementation would overwrite the competitor here.
    """
    target = tmp_path / "x.png"
    real_link = os.link

    def competing_link(source: Any, destination: Any, **kwargs: Any) -> None:
        Path(destination).write_bytes(b"competitor")
        real_link(source, destination, **kwargs)

    monkeypatch.setattr(os, "link", competing_link)
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, target)
    assert excinfo.value.context["reason"] == "exists"
    assert target.read_bytes() == b"competitor"
    assert [p.name for p in tmp_path.iterdir()] == ["x.png"]


def test_link_reported_as_existing_but_done_by_us_is_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link

    def link_then_lost_reply(source: Any, destination: Any, **kwargs: Any) -> None:
        real_link(source, destination, **kwargs)
        raise FileExistsError(errno.EEXIST, "retried")

    monkeypatch.setattr(os, "link", link_then_lost_reply)
    manifest = export_png(SAMPLE, tmp_path / "x.png")
    assert manifest.byte_size == (tmp_path / "x.png").stat().st_size
    assert [p.name for p in tmp_path.iterdir()] == ["x.png"]


def test_link_existing_destination_that_vanished_is_still_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def exists_without_file(*args: object, **kwargs: object) -> None:
        raise FileExistsError(errno.EEXIST, "exists")

    monkeypatch.setattr(os, "link", exists_without_file)
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / "x.png")
    assert excinfo.value.context["reason"] == "exists"
    assert list(tmp_path.iterdir()) == []


class _WindowsNoLinks(OSError):
    winerror = 1  # ERROR_INVALID_FUNCTION, as FAT/exFAT report it


def test_windows_filesystems_without_links_fail_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_links(*args: object, **kwargs: object) -> None:
        raise _WindowsNoLinks(errno.EINVAL, "invalid function")

    monkeypatch.setattr(os, "link", no_links)
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / "x.png")
    assert excinfo.value.context["reason"] == "no_replace_unavailable"
    assert list(tmp_path.iterdir()) == []


def test_t3_two_threads_one_wins_the_other_fails_without_replacing(tmp_path: Path) -> None:
    other = frame([[INK, INK, INK], [INK, INK, INK]])
    for attempt in range(25):
        target = tmp_path / f"race{attempt}.png"
        barrier = threading.Barrier(2)
        outcomes: dict[str, object] = {}

        def write(
            name: str,
            source: Frame,
            target: Path = target,
            barrier: threading.Barrier = barrier,
            outcomes: dict[str, object] = outcomes,
        ) -> None:
            barrier.wait()
            try:
                outcomes[name] = export_png(source, target)
            except ExportError as exc:
                outcomes[name] = exc

        threads = [
            threading.Thread(target=write, args=("a", SAMPLE)),
            threading.Thread(target=write, args=("b", other)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        winners = [name for name, value in outcomes.items() if isinstance(value, ExportManifest)]
        losers = [value for value in outcomes.values() if isinstance(value, ExportError)]
        assert len(winners) == 1 and len(losers) == 1
        assert losers[0].context["reason"] == "exists"
        winner = outcomes[winners[0]]
        assert isinstance(winner, ExportManifest)
        assert winner.file_sha256 == "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    assert all(not name.endswith(".tmp") for name in os.listdir(tmp_path))


RACER = """
import sys, time
from dataclasses import dataclass
from moanart.core.errors import ExportError
from moanart.export import export_png

@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    rgba: bytes

value = int(sys.argv[2])
start = float(sys.argv[3])
while time.time() < start:
    pass
try:
    export_png(Frame(1, 1, bytes([value, value, value, 255])), sys.argv[1])
    print("won")
except ExportError as exc:
    print(exc.context["reason"])
"""


@pytest.mark.slow
def test_t3_two_processes_race_for_the_same_name(tmp_path: Path) -> None:
    import time

    target = tmp_path / "race.png"
    start = str(time.time() + 1.0)
    racers = [
        subprocess.Popen(
            [sys.executable, "-c", RACER, str(target), str(value), start],
            stdout=subprocess.PIPE,
            text=True,
        )
        for value in (10, 20)
    ]
    results = sorted(racer.communicate(timeout=60)[0].strip() for racer in racers)
    assert results == ["exists", "won"]
    pixel = decode(target)[3][0]
    assert pixel in ((10, 10, 10, 255), (20, 20, 20, 255))


# --- Architecture ---------------------------------------------------------------------

EXPORT = Path(__file__).resolve().parents[3] / "src/moanart/export"


def test_export_imports_only_core_palette_numpy_pillow_and_stdlib() -> None:
    paths = sorted(EXPORT.glob("*.py"))
    assert paths
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                assert (
                    root in sys.stdlib_module_names
                    or root in ("numpy", "PIL")
                    or name.startswith(("moanart.core", "moanart.palette", "moanart.export"))
                ), f"{path.name} imports {name}"


def test_temporary_name_collisions_are_retried_then_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import secrets

    names = iter(["aa", "aa", "bb"])
    monkeypatch.setattr(secrets, "token_hex", lambda n: next(names))
    (tmp_path / ".x.png.aa.tmp").write_bytes(b"someone else's")
    export_png(SAMPLE, tmp_path / "x.png")  # "aa" taken, retried with "bb"
    assert (tmp_path / ".x.png.aa.tmp").read_bytes() == b"someone else's"
    monkeypatch.setattr(secrets, "token_hex", lambda n: "aa")
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / "x.png", overwrite=True)
    assert excinfo.value.context["reason"] == "io_error"


def test_temporary_creation_and_replace_errors_are_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_open = os.open

    def broken_open(path: Any, flags: int, mode: int = 0o777) -> int:
        if str(path).endswith(".tmp"):
            raise OSError(errno.EIO, "simulated")
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", broken_open)
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / "x.png")
    assert excinfo.value.context["reason"] == "io_error"
    monkeypatch.setattr(os, "open", real_open)

    def denied(*args: object) -> None:
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(os, "replace", denied)
    with pytest.raises(ExportError) as excinfo:
        export_png(SAMPLE, tmp_path / "x.png", overwrite=True)
    assert excinfo.value.context["reason"] == "permission_denied"
    assert list(tmp_path.iterdir()) == []
