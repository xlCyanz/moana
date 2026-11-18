"""Public facade moana.api: loading, render, export and reports (MOANA-012).

Pixel oracles come from the minimal example by hand: ``body_fill`` is the half-open
rect ``[40, 32, 88, 104)`` in ``cloth`` (#36AFA5FF) on a transparent 128 x 128 canvas,
so 48 * 72 = 3456 opaque pixels. PNG files are decoded with Pillow directly.
"""

from __future__ import annotations

import copy
import dataclasses
import errno
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

import numpy as np
import pytest
from PIL import Image

import moana.api
from moana.api import (
    AVAILABLE_FUNCTIONS,
    PLANNED_FUNCTIONS,
    ParseLimits,
    ReadError,
    RenderLimits,
    RenderResult,
    capabilities,
    export_png,
    inspect_document,
    load_document,
    render,
)
from moana.api import inspection as inspection_module
from moana.api.loading import MAX_REPORTED_NAME
from moana.core import errors
from moana.render import RENDERABLE_OPERATION_TYPES
from moana.schema import PLANNED_OPERATION_TYPES, SUPPORTED_OPERATION_TYPES, snapshot_digest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "specs" / "minimal.moana.json"
MINIMAL: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
CLOTH = (0x36, 0xAF, 0xA5, 0xFF)
CLEAR = (0, 0, 0, 0)
RECT = (40, 32, 88, 104)


def minimal() -> dict[str, Any]:
    return copy.deepcopy(MINIMAL)


def over_budget() -> dict[str, Any]:
    """2048 x 2048 with 30 full-canvas rects: about 31 x 4.2M visits > 100M."""
    document = minimal()
    document["canvas"] = {"width": 2048, "height": 2048, "profile": "strict"}
    document["layers"][0]["operations"] = [
        {"id": f"r{index}", "type": "rect", "box": [0, 0, 2048, 2048], "color": "ink"}
        for index in range(30)
    ]
    return document


def expected_pixel(x: int, y: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = RECT
    return CLOTH if x0 <= x < x1 and y0 <= y < y1 else CLEAR


# --- load_document -----------------------------------------------------------------


def test_every_source_kind_gives_the_same_document(tmp_path: Path) -> None:
    path = tmp_path / "a dir with spaces" / "mini sprite ñ.moana.json"
    path.parent.mkdir()
    path.write_bytes(EXAMPLE.read_bytes())
    documents = [
        load_document(str(path)),
        load_document(path),
        load_document(EXAMPLE.read_bytes()),
        load_document(minimal()),
    ]
    digests = {snapshot_digest(document) for document in documents}
    assert len(digests) == 1
    assert documents[0].id == "sprite_demo"
    assert documents[0].revision == 0


def test_missing_file_is_a_read_error_without_the_full_path(tmp_path: Path) -> None:
    missing = tmp_path / "secret parent" / "absent.moana.json"
    with pytest.raises(ReadError) as caught:
        load_document(missing)
    error = caught.value
    assert (error.code, error.exit_code) == ("READ_ERROR", 5)
    assert dict(error.context) == {
        "reason": "not_found",
        "file_name": "absent.moana.json",
        "errno": "ENOENT",
    }
    assert "secret parent" not in repr(error.context) + error.message
    assert isinstance(error, errors.MoanaError)


def test_directory_is_a_read_error(tmp_path: Path) -> None:
    with pytest.raises(ReadError) as caught:
        load_document(tmp_path)
    assert caught.value.context["reason"] == "is_directory"


def failing_open(error: OSError) -> Callable[..., int]:
    def opener(*args: object, **kwargs: object) -> int:
        raise error

    return opener


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (PermissionError(errno.EACCES, "denied"), {"reason": "permission_denied"}),
        (IsADirectoryError(errno.EISDIR, "dir"), {"reason": "is_directory"}),
        (OSError(errno.EIO, "io"), {"reason": "io_error"}),
    ],
)
def test_open_failures_are_read_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raised: OSError, expected: dict[str, str]
) -> None:
    target = tmp_path / "x.moana.json"
    target.write_bytes(b"{}")
    monkeypatch.setattr(os, "open", failing_open(raised))
    with pytest.raises(ReadError) as caught:
        load_document(target)
    name = errno.errorcode[raised.errno or 0]
    assert dict(caught.value.context) == {**expected, "file_name": "x.moana.json", "errno": name}


def test_os_error_without_errno(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "open", failing_open(OSError("no errno")))
    with pytest.raises(ReadError) as caught:
        load_document(tmp_path / "x.moana.json")
    assert dict(caught.value.context) == {"reason": "io_error", "file_name": "x.moana.json"}


def test_permission_error_on_a_directory_reports_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # What Windows reports when opening a directory.
    monkeypatch.setattr(os, "open", failing_open(PermissionError(errno.EACCES, "denied")))
    with pytest.raises(ReadError) as caught:
        load_document(tmp_path)
    assert caught.value.context["reason"] == "is_directory"


def posix_non_root() -> bool:
    """Whether POSIX permission bits are enforced for this process."""
    if sys.platform == "win32":
        return False
    return os.geteuid() != 0


@pytest.mark.skipif(not posix_non_root(), reason="POSIX permissions, non-root")
def test_real_unreadable_file(tmp_path: Path) -> None:
    target = tmp_path / "unreadable.moana.json"
    target.write_bytes(EXAMPLE.read_bytes())
    target.chmod(0)
    try:
        with pytest.raises(ReadError) as caught:
            load_document(target)
    finally:
        target.chmod(0o600)
    assert caught.value.context["reason"] == "permission_denied"


@pytest.mark.skipif(not posix_non_root(), reason="POSIX permissions, non-root")
def test_unsearchable_parent_is_permission_denied(tmp_path: Path) -> None:
    parent = tmp_path / "locked parent"
    parent.mkdir()
    (parent / "doc.moana.json").write_bytes(EXAMPLE.read_bytes())
    parent.chmod(0)
    try:
        with pytest.raises(ReadError) as caught:
            load_document(parent / "doc.moana.json")
    finally:
        parent.chmod(0o700)
    assert dict(caught.value.context) == {
        "reason": "permission_denied",
        "file_name": "doc.moana.json",
        "errno": "EACCES",
    }


def test_fifo_is_rejected_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe.moana.json"
    if sys.platform == "win32":
        pytest.skip("POSIX FIFOs")
    os.mkfifo(fifo)  # no writer: a blocking open would hang here
    with pytest.raises(ReadError) as caught:
        load_document(fifo)
    assert caught.value.context["reason"] == "not_a_file"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX device")
def test_device_is_not_a_file() -> None:
    with pytest.raises(ReadError) as caught:
        load_document("/dev/null")
    assert dict(caught.value.context) == {"reason": "not_a_file", "file_name": "null"}


def test_fstat_failure_is_an_io_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "x.moana.json"
    target.write_bytes(EXAMPLE.read_bytes())

    opened: list[int] = []
    real_open, real_fstat = os.open, os.fstat

    def recording_open(path: Any, flags: int, *args: Any) -> int:
        descriptor = real_open(path, flags, *args)
        opened.append(descriptor)
        return descriptor

    def broken(descriptor: int) -> os.stat_result:
        if descriptor in opened:  # only the document; pytest also calls fstat
            raise OSError(errno.EIO, "io")
        return real_fstat(descriptor)

    monkeypatch.setattr(os, "open", recording_open)
    monkeypatch.setattr(os, "fstat", broken)
    with pytest.raises(ReadError) as caught:
        load_document(target)
    assert caught.value.context["reason"] == "io_error"


class SpyHandle:
    """Records every ``read`` size; optionally fails like a broken disk."""

    def __init__(self, handle: IO[bytes], sizes: list[int], fail: bool) -> None:
        self.handle, self.sizes, self.fail = handle, sizes, fail

    def __enter__(self) -> SpyHandle:
        return self

    def __exit__(self, *exc: object) -> None:
        self.handle.close()

    def read(self, size: int = -1) -> bytes:
        self.sizes.append(size)
        if self.fail:
            raise OSError(errno.EIO, "io")
        return self.handle.read(size)


def spy_fdopen(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> list[int]:
    sizes: list[int] = []
    real = os.fdopen

    def fdopen(descriptor: int, mode: str) -> SpyHandle:
        return SpyHandle(real(descriptor, "rb"), sizes, fail)

    monkeypatch.setattr(os, "fdopen", fdopen)
    return sizes


def test_bounded_read_asks_for_one_byte_over_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "big.moana.json"
    path.write_bytes(b" " * 10_000 + EXAMPLE.read_bytes())
    sizes = spy_fdopen(monkeypatch)
    with pytest.raises(errors.ValidationError) as caught:
        load_document(path, limits=ParseLimits(max_bytes=64))
    assert caught.value.context["reason"] == "too_large"
    assert sizes == [65]  # a whole-file read() would record -1


def test_read_failure_is_an_io_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "x.moana.json"
    target.write_bytes(EXAMPLE.read_bytes())
    spy_fdopen(monkeypatch, fail=True)
    with pytest.raises(ReadError) as caught:
        load_document(target)
    assert dict(caught.value.context) == {
        "reason": "io_error",
        "file_name": "x.moana.json",
        "errno": "EIO",
    }


def test_long_file_names_are_truncated_in_errors(tmp_path: Path) -> None:
    name = "n" * 300 + ".moana.json"
    with pytest.raises(ReadError) as caught:
        load_document(tmp_path / name)
    reported = caught.value.context["file_name"]
    assert isinstance(reported, str)
    assert len(reported) == MAX_REPORTED_NAME == 255
    assert name.startswith(reported)


@pytest.mark.parametrize("text", ['{"schema_version": "1.0"}', "  [1, 2]", "\n{}"])
def test_json_text_is_not_taken_as_a_path(text: str) -> None:
    with pytest.raises(errors.ValidationError, match="pass bytes or a mapping") as caught:
        load_document(text)
    assert caught.value.context["reason"] == "json_text"


@pytest.mark.parametrize("raw", ["", "bad\x00name.moana.json"])
def test_unrepresentable_paths_are_validation_errors(raw: str) -> None:
    with pytest.raises(errors.ValidationError) as caught:
        load_document(raw)
    assert caught.value.context["reason"] == "invalid_name"


def test_unencodable_path_is_a_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def unencodable(name: str) -> bytes:
        raise UnicodeEncodeError("utf-8", name, 0, 1, "surrogates not allowed")

    monkeypatch.setattr(os, "fsencode", unencodable)
    with pytest.raises(errors.ValidationError) as caught:
        load_document("x.moana.json")
    assert caught.value.context["reason"] == "invalid_name"


def test_limits_apply_to_bytes_and_mappings() -> None:
    with pytest.raises(errors.ValidationError):
        load_document(EXAMPLE.read_bytes(), limits=ParseLimits(max_nodes=5))
    with pytest.raises(errors.ValidationError):
        load_document(minimal(), limits=ParseLimits(max_nodes=5))


class BytesPath:
    def __fspath__(self) -> bytes:
        return b"x.moana.json"


@pytest.mark.parametrize(
    ("source", "message"),
    [(42, "source must be"), (BytesPath(), "path must be text")],
)
def test_wrong_source_types(source: Any, message: str) -> None:
    with pytest.raises(TypeError, match=message):
        load_document(source)


def test_wrong_limits_type() -> None:
    with pytest.raises(TypeError, match="limits"):
        load_document(minimal(), limits=RenderLimits())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda d: d.update(schema_version="2.0"), errors.UnsupportedVersion),
        (lambda d: d["layers"][0]["operations"][0].update(color="nope"), errors.ReferenceError),
        (lambda d: d.update(revision=-1), errors.ValidationError),
        (
            lambda d: d["layers"][0]["operations"].append(
                {"id": "fut", "type": sorted(PLANNED_OPERATION_TYPES)[0]}
            ),
            errors.UnsupportedOperation,
        ),
    ],
)
def test_schema_errors_pass_through(mutate: Any, error: type[errors.MoanaError]) -> None:
    document = minimal()
    mutate(document)
    with pytest.raises(error):
        load_document(document)


# --- render ------------------------------------------------------------------------


def test_render_matches_the_hand_oracle_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    document = load_document(EXAMPLE)
    before = snapshot_digest(document)
    result = render(document)
    assert isinstance(result, RenderResult)
    assert (result.width, result.height) == (128, 128)
    assert type(result.rgba) is bytes
    pixels = np.frombuffer(result.rgba, np.uint8).reshape(128, 128, 4)
    assert int((pixels[:, :, 3] == 255).sum()) == 48 * 72
    for x, y in [(40, 32), (87, 103), (39, 32), (88, 103), (40, 31), (40, 104), (0, 0)]:
        assert result.pixel(x, y) == expected_pixel(x, y)
    assert snapshot_digest(document) == before
    assert list(tmp_path.iterdir()) == []


def test_render_errors() -> None:
    document = load_document(minimal())
    with pytest.raises(errors.ReferenceError):
        render(document, frame_id="walk_0")
    with pytest.raises(errors.BudgetExceeded):
        render(document, limits=RenderLimits(max_pixel_visits=1))
    with pytest.raises(errors.BudgetExceeded) as caught:
        render(load_document(over_budget()))
    assert caught.value.exit_code == 3


def test_results_are_frozen_and_free_of_library_objects(tmp_path: Path) -> None:
    document = load_document(minimal())
    result = render(document)
    manifest = export_png(result, tmp_path / "s.png")
    report = inspect_document(document)
    for value in (result, manifest, report, capabilities()):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, dataclasses.fields(value)[0].name, None)
    with pytest.raises(Exception, match="frozen"):
        document.id = "other"

    def walk(value: object) -> None:
        assert not isinstance(value, np.ndarray | Image.Image | bytearray | memoryview)
        if dataclasses.is_dataclass(value):
            for field in dataclasses.fields(value):
                walk(getattr(value, field.name))
        elif isinstance(value, tuple):
            for item in value:
                walk(item)

    for value in (result, manifest, report, capabilities()):
        walk(value)
    assert "PIL" not in type(result.rgba).__module__


# --- export_png --------------------------------------------------------------------


def test_export_writes_a_verified_128_png(tmp_path: Path) -> None:
    result = render(load_document(EXAMPLE))
    target = tmp_path / "out dir" / "sprite final.png"
    target.parent.mkdir()
    manifest = export_png(result, target)
    assert manifest.path == str(target)
    assert (manifest.width, manifest.height, manifest.scale, manifest.master) == (
        128,
        128,
        1,
        True,
    )
    assert manifest.source_digest == result.digest == manifest.pixel_digest
    assert manifest.warnings == ()
    with Image.open(target) as image:
        assert (image.format, image.mode, image.size) == ("PNG", "RGBA", (128, 128))
        assert image.getpixel((40, 32)) == CLOTH
        assert image.getpixel((39, 32)) == CLEAR


def test_export_scale_overwrite_and_limits(tmp_path: Path) -> None:
    result = render(load_document(EXAMPLE))
    target = tmp_path / "s.png"
    preview = export_png(result, target, scale=2)
    assert (preview.width, preview.height, preview.master) == (256, 256, False)
    assert preview.warnings == ("scaled_preview",)
    original = target.read_bytes()
    with pytest.raises(errors.ExportError) as caught:
        export_png(result, target)
    assert caught.value.context["reason"] == "exists"
    assert target.read_bytes() == original
    replaced = export_png(result, target, overwrite=True)
    assert replaced.master
    with pytest.raises(errors.BudgetExceeded):
        export_png(result, tmp_path / "b.png", limits=RenderLimits(max_buffer_bytes=1))
    with pytest.raises(errors.ValidationError):
        export_png(result, tmp_path / "s.jpg")
    with pytest.raises(errors.ValidationError):
        export_png(result, tmp_path / "z.png", scale=0)


def test_export_requires_a_render_result(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="RenderResult"):
        export_png(object(), tmp_path / "x.png")  # type: ignore[arg-type]


# --- inspect_document and capabilities -----------------------------------------------


def test_inspect_reports_structure_and_budget() -> None:
    document = load_document(EXAMPLE)
    report = inspect_document(document)
    assert report.document_id == "sprite_demo"
    assert (report.width, report.height, report.profile, report.seed) == (128, 128, "strict", 42)
    assert report.colors == ("ink", "cloth")
    assert report.ramps == ()
    assert report.snapshot_digest == snapshot_digest(document)
    (layer,) = report.layers
    assert (layer.id, layer.name, layer.visible, layer.opacity) == ("body", "Cuerpo", True, 255)
    assert [(op.id, op.type, op.color) for op in layer.operations] == [
        ("body_fill", "rect", "cloth")
    ]
    assert report.budget.within_limits
    assert report.budget.exceeded == ()
    assert report.budget.frame_pixels == 128 * 128
    mapping = report.to_mapping()
    assert list(mapping) == sorted(mapping)
    assert json.loads(json.dumps(mapping)) == mapping
    assert mapping["layers"] == [
        {
            "blend": "normal",
            "id": "body",
            "locked": False,
            "mask_id": None,
            "name": "Cuerpo",
            "opacity": 255,
            "operations": [{"color": "cloth", "id": "body_fill", "type": "rect"}],
            "visible": True,
        }
    ]


def test_inspect_reports_exceeded_budget_instead_of_raising() -> None:
    report = inspect_document(load_document(over_budget()))
    assert not report.budget.within_limits
    resources = {item.resource: item for item in report.budget.exceeded}
    assert "pixel_visits" in resources
    visits = resources["pixel_visits"]
    assert visits.estimated == report.budget.pixel_visits > visits.limit == 100_000_000
    lowered = inspect_document(load_document(EXAMPLE), limits=RenderLimits(max_pixel_visits=10))
    assert [item.resource for item in lowered.budget.exceeded] == ["pixel_visits"]


def test_inspect_type_checks() -> None:
    with pytest.raises(TypeError, match="Document"):
        inspect_document(minimal())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RenderLimits"):
        inspect_document(load_document(EXAMPLE), limits=ParseLimits())  # type: ignore[arg-type]


def test_capabilities_separate_available_from_planned() -> None:
    listing = capabilities()
    assert listing.operations == (
        "dither",
        "ellipse",
        "line",
        "outline",
        "path",
        "pixel",
        "polygon",
        "rect",
        "shade",
    )
    assert set(listing.operations).isdisjoint(listing.planned_operations)
    assert set(listing.blend_modes).isdisjoint(listing.planned_blend_modes)
    # MOANA-018: apply_edit moved from planned to available (ADR-024).
    assert listing.planned_functions == PLANNED_FUNCTIONS == ()
    assert "apply_edit" in AVAILABLE_FUNCTIONS
    assert listing.edit_commands == (
        "insert_operation",
        "remove",
        "reorder",
        "replace_palette_color",
        "set_color",
        "set_geometry",
        "set_visibility",
        "translate",
    )
    assert listing.functions == AVAILABLE_FUNCTIONS
    for name in AVAILABLE_FUNCTIONS:
        assert callable(getattr(moana.api, name))
    for name in PLANNED_FUNCTIONS:
        assert not hasattr(moana.api, name)
        assert name not in moana.api.__all__
    mapping = listing.to_mapping()
    assert mapping["export_formats"] == ["png"]
    assert list(mapping) == sorted(mapping)


def test_every_schema_operation_has_a_rasteriser() -> None:
    assert frozenset(RENDERABLE_OPERATION_TYPES) >= SUPPORTED_OPERATION_TYPES
    assert set(capabilities().operations) == SUPPORTED_OPERATION_TYPES


def test_schema_only_operations_are_reported_as_planned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inspection_module, "RENDERABLE_OPERATION_TYPES", ("rect",))
    listing = capabilities()
    assert listing.operations == ("rect",)
    assert {"ellipse", "line", "pixel", "polygon"} <= set(listing.planned_operations)
    assert set(listing.operations).isdisjoint(listing.planned_operations)


def test_malformed_budget_detail_is_a_type_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        detail = errors.ErrorDetail("BUDGET_EXCEEDED", "x", context={"resource": "pixel_visits"})
        raise errors.BudgetExceeded("over", details=[detail])

    monkeypatch.setattr(inspection_module, "plan_budget", refuse)
    with pytest.raises(TypeError, match="resource, limit or estimated"):
        inspect_document(load_document(EXAMPLE))


def test_facade_reexports_what_the_cli_needs() -> None:
    assert moana.api.MAX_SCALE == 64
    assert moana.api.snapshot_digest is snapshot_digest
    assert moana.api.ReadError is errors.ReadError
