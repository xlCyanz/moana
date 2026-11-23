"""Runtime codec capabilities of the export formats (MOANA-025, ADR-035; T1, AC2).

The matrix is checked against ``PIL.features`` directly; missing or failing codecs are
simulated by patching the Pillow feature query or the probe, never by guessing.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, cast

import PIL
import pytest
from PIL import features

from moanart.api import capabilities
from moanart.core.errors import UnsupportedOperation, ValidationError
from moanart.export import (
    EXPORT_FORMATS,
    CodecStatus,
    codec_status,
    export_capabilities,
)
from moanart.export import codecs as codecs_module
from moanart.export.codecs import require_codec


def test_capability_matrix_reports_every_format_of_this_build() -> None:
    matrix = export_capabilities()
    print("export capability matrix:", matrix.to_mapping())  # build report (pytest -s)
    assert EXPORT_FORMATS == ("png", "gif", "apng", "webp")
    assert tuple(entry.format for entry in matrix.formats) == EXPORT_FORMATS
    assert matrix.pillow_version == PIL.__version__
    expected = {
        "png": ("image/png", ".png", "zlib", True),
        "gif": ("image/gif", ".gif", "pillow-lzw", False),
        "apng": ("image/apng", ".png", "zlib", True),
        "webp": ("image/webp", ".webp", "libwebp", True),
    }
    for entry in matrix.formats:
        media_type, extension, codec, lossless = expected[entry.format]
        assert (entry.media_type, entry.extension, entry.codec) == (media_type, extension, codec)
        assert entry.lossless is lossless and entry.pillow_version == PIL.__version__
        assert entry.available is (entry.reason is None)
    # Versions come from Pillow's own feature report, not from the exporter.
    for name in ("png", "apng"):
        assert matrix.status(name).codec_version == features.version_codec("zlib")
    assert matrix.status("gif").codec_version == PIL.__version__
    webp = matrix.status("webp")
    if features.check_module("webp"):
        assert webp.codec_version == features.version_module("webp")
    else:  # pragma: no cover - depends on the Pillow build
        assert (webp.available, webp.reason, webp.codec_version) == (False, "missing", None)
    mapping = matrix.to_mapping()
    assert list(mapping) == ["formats", "pillow_version"]
    for row in cast(list[dict[str, object]], mapping["formats"]):
        assert list(row) == sorted(row)
        assert set(row) == {
            "available",
            "codec",
            "codec_version",
            "extension",
            "format",
            "lossless",
            "media_type",
            "pillow_version",
            "reason",
        }


def test_png_gif_and_apng_are_always_available_with_pillow() -> None:
    # The PNG plugin, zlib and the GIF LZW encoder are part of every Pillow wheel.
    for name in ("png", "gif", "apng"):
        assert codec_status(name).available, name


def test_unknown_formats_are_rejected() -> None:
    for name in ("jpeg", "PNG", 1, None):
        with pytest.raises(ValidationError) as caught:
            codec_status(cast(Any, name))
        assert caught.value.context == {"field": "name", "reason": "unknown_format"}
        assert repr(name) not in caught.value.message
    with pytest.raises(KeyError):
        export_capabilities().status(cast(Any, "jpeg"))


def test_a_missing_webp_module_is_reported_and_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    original = features.check_module
    monkeypatch.setattr(
        "moanart.export.codecs.features.check_module",
        lambda name: False if name == "webp" else original(name),
    )
    status = codec_status("webp")
    assert (status.available, status.reason, status.codec_version) == (False, "missing", None)
    assert export_capabilities().status("png").available
    with pytest.raises(UnsupportedOperation) as caught:
        require_codec("webp")
    assert caught.value.context == {
        "reason": "codec_unavailable",
        "format": "webp",
        "codec": "libwebp",
        "cause": "missing",
        "pillow_version": PIL.__version__,
    }
    assert caught.value.code == "UNSUPPORTED_OPERATION" and caught.value.exit_code == 2


def test_missing_zlib_disables_png_and_apng(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("moanart.export.codecs.features.check_codec", lambda name: False)
    matrix = export_capabilities()
    assert [entry.format for entry in matrix.formats if not entry.available] == ["png", "apng"]
    assert matrix.status("gif").available


@pytest.mark.parametrize("name", EXPORT_FORMATS)
def test_a_codec_that_does_not_roundtrip_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    present, _ = codecs_module._PROBES[name]
    monkeypatch.setitem(codecs_module._PROBES, name, (present, lambda: False))
    status = codec_status(cast(Any, name))
    assert (status.available, status.reason) == (False, "roundtrip_failed")
    assert status.codec_version is not None  # the codec is there, it just failed

    def broken() -> bool:
        raise OSError("encoder not compiled")

    monkeypatch.setitem(codecs_module._PROBES, name, (present, broken))
    assert codec_status(cast(Any, name)).reason == "roundtrip_failed"
    with pytest.raises(UnsupportedOperation) as caught:
        require_codec(cast(Any, name))
    assert caught.value.context["cause"] == "roundtrip_failed"


def test_animation_probe_requires_frames_and_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    assert codecs_module._probe_apng() and codecs_module._probe_webp()
    monkeypatch.setattr(
        codecs_module, "_frames_of", lambda data, kind: ([b"x", b"y"], None)
    )  # a decoder that loses the loop and the pixels
    assert not codecs_module._probe_apng()


def test_status_is_a_frozen_value() -> None:
    status = codec_status("png")
    assert isinstance(status, CodecStatus)
    with pytest.raises(AttributeError):
        cast(Any, status).available = False


def test_codecs_module_imports_only_core_and_libraries() -> None:
    tree = ast.parse(Path(codecs_module.__file__).read_text(encoding="utf-8"))
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    internal = {name for name in modules if name and name.startswith("moanart")}
    assert internal == {"moanart.core.errors"}


@pytest.mark.parametrize("error", [RuntimeError("codec crashed"), TypeError("bad argument")])
def test_a_probe_that_raises_anything_is_a_failed_roundtrip(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def broken() -> bool:
        raise error

    present, _ = codecs_module._PROBES["webp"]
    monkeypatch.setitem(codecs_module._PROBES, "webp", (present, broken))
    assert codec_status("webp").reason == "roundtrip_failed"
    listing = capabilities()  # the public report still returns
    assert {row.format: row.reason for row in listing.export_codecs}["webp"] == "roundtrip_failed"


def test_a_feature_query_that_raises_is_a_missing_codec(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(name: str) -> bool:
        raise ImportError("cannot import _webp")

    monkeypatch.setattr("moanart.export.codecs.features.check_module", broken)
    status = codec_status("webp")
    assert (status.available, status.reason, status.codec_version) == (False, "missing", None)
    assert capabilities().export_codecs[3].reason == "missing"


def test_an_unreadable_codec_version_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(name: str) -> str:
        raise ValueError("unknown feature")

    monkeypatch.setattr("moanart.export.codecs.features.version_codec", broken)
    status = codec_status("png")
    assert status.available and status.codec_version is None


def test_the_webp_probe_uses_the_exporter_options(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, object]] = []
    original = codecs_module._probe_animation

    def spy(kind: str, **options: object) -> bool:
        seen.append(options)
        return original(kind, **options)

    monkeypatch.setattr(codecs_module, "_probe_animation", spy)
    codecs_module._probe_webp()
    assert seen == [codecs_module.WEBP_ENCODER_OPTIONS]
    assert seen[0]["lossless"] is True and (seen[0]["quality"], seen[0]["method"]) == (75, 4)
