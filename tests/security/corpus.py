"""Versioned malicious corpus of MOANA-030: hostile payloads built in memory.

No binary is committed: every payload is generated from this file, so the corpus is
reviewed as text and carries no executable content (strings that look like code are
inert data). Each :class:`HostileCase` names the threat-model boundary it attacks
(the *Frontera* column of ``docs/architecture/SECURITY_MODEL.md``), the entry point
that receives it, and the domain error and ``reason`` the engine must answer with.

The payloads are small; the hostile part is what they *declare* (sizes, counts,
nesting, ratios, names), so every case runs in milliseconds and bounded memory.
"""

from __future__ import annotations

import io
import json
import os
import stat
import struct
import warnings
import zipfile
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from PIL import Image, ImageCms

from moana.core.coordinates import Point
from moana.core.errors import BudgetExceeded, MoanaError, ValidationError
from moana.export import FramePixels, SheetFrame, encode_spritesheet
from moana.project import MANIFEST_NAME

__all__ = [
    "CORPUS",
    "MINIMAL",
    "SECRET",
    "HostileCase",
    "archive",
    "asset_name",
    "chunk",
    "minimal_bytes",
    "minimal_tree",
    "png_declaring",
    "symlink_entry",
    "tiny_png",
    "with_central_size",
]

ROOT: Final = Path(__file__).resolve().parents[2]
MINIMAL: Final = ROOT / "examples/specs/minimal.moana.json"
SECRET: Final = "moana-test-secret-7f3a"
"""A marker planted in hostile names and values; no error may ever echo it."""

type Target = Literal["document", "batch", "project", "asset", "spritesheet"]

_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_CENTRAL: Final = b"PK\x01\x02"
_CENTRAL_USIZE: Final = 24  # offset of the uncompressed size in a central record
# ``zipfile`` turns ``os.sep`` into ``/`` when it reads a name, so on Windows a
# backslash never reaches Moana: ``..\..\x`` arrives as ``../../x`` and ``C:\x`` as
# ``C:/x``. Both are rejected on every platform, with the reason of what arrives.
_BACKSLASH_TRAVERSAL: Final = "invalid_name" if os.sep == "/" else "parent_reference"
_BACKSLASH_ABSOLUTE: Final = "invalid_name" if os.sep == "/" else "absolute_path"


@dataclass(frozen=True, slots=True)
class HostileCase:
    """One hostile payload and the rejection the engine owes it."""

    id: str
    boundary: str
    target: Target
    build: Callable[[], bytes]
    error: type[MoanaError]
    reason: str | None
    key: str = "reason"
    pointer: str | None = None
    companion: Callable[[], bytes] | None = None
    """Second input of a two-file entry point (the atlas PNG of a spritesheet)."""
    header_only: bool = False
    """The mitigation lives in Pillow's header parsing (``Image.open`` is allowed), so
    the test forbids decoding pixels (``Image.Image.load``) instead of opening."""


def minimal_bytes() -> bytes:
    return MINIMAL.read_bytes()


def minimal_tree() -> dict[str, Any]:
    """A fresh JSON tree of ``examples/specs/minimal.moana.json``."""
    tree = json.loads(minimal_bytes().decode("utf-8"))
    assert isinstance(tree, dict)
    return tree


def tiny_png(
    width: int = 2, height: int = 2, color: tuple[int, int, int, int] = (10, 20, 30, 255)
) -> bytes:
    """A valid 8-bit RGBA PNG made by Pillow (setup only, outside any tripwire)."""
    buffer = io.BytesIO()
    Image.new("RGBA", (width, height), color).save(buffer, "PNG")
    return buffer.getvalue()


def _replaced(old: str, new: str) -> Callable[[], bytes]:
    def build() -> bytes:
        text = json.dumps(minimal_tree())
        assert old in text
        return text.replace(old, new, 1).encode("utf-8")

    return build


def _nested(depth: int) -> bytes:
    return ('{"a":' * depth + "0" + "}" * depth).encode("ascii")


def _wide(values: int) -> bytes:
    return ('{"a":[' + ",".join(["0"] * values) + "]}").encode("ascii")


def _tree_with(**members: object) -> Callable[[], bytes]:
    def build() -> bytes:
        tree = minimal_tree()
        tree.update(members)
        return json.dumps(tree).encode("utf-8")

    return build


def _operation_with(**members: object) -> Callable[[], bytes]:
    def build() -> bytes:
        tree = minimal_tree()
        layers = tree["layers"]
        assert isinstance(layers, list)
        layers[0]["operations"][0].update(members)
        return json.dumps(tree).encode("utf-8")

    return build


def _masks(*masks: dict[str, object]) -> Callable[[], bytes]:
    return _tree_with(masks=list(masks))


# --- ZIP -------------------------------------------------------------------------------


def asset_name(fill: str = "0") -> str:
    """A name of the project layout: ``assets/<64 hex>.png``."""
    return f"assets/{fill * 64}.png"


def symlink_entry(name: str) -> zipfile.ZipInfo:
    """A Unix symbolic-link entry (mode ``S_IFLNK``)."""
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info


def archive(
    entries: Sequence[tuple[zipfile.ZipInfo | str, bytes]], *, deflate: bool = False
) -> bytes:
    """A ZIP of ``entries`` in order (names are written as given, even hostile ones)."""
    buffer = io.BytesIO()
    method = zipfile.ZIP_DEFLATED if deflate else zipfile.ZIP_STORED
    with warnings.catch_warnings(), zipfile.ZipFile(buffer, "w", compression=method) as handle:
        warnings.simplefilter("ignore", UserWarning)  # duplicate names are the point
        for entry, data in entries:
            handle.writestr(entry, data)
    return buffer.getvalue()


def with_central_size(data: bytes, index: int, size: int) -> bytes:
    """``data`` whose central record ``index`` declares ``size`` uncompressed bytes."""
    position = -1
    for _ in range(index + 1):
        position = data.index(_CENTRAL, position + 1)
    field = position + _CENTRAL_USIZE
    return data[:field] + struct.pack("<I", size) + data[field + 4 :]


def _named(name: str) -> Callable[[], bytes]:
    return lambda: archive([(MANIFEST_NAME, b"{}"), (name, b"x")])


def _ratio_bomb() -> bytes:
    """One MiB of zeros deflated to about one KiB: a 1000:1 entry (limit 100:1)."""
    return archive([(MANIFEST_NAME, b"{}"), (asset_name(), b"\0" * (1 << 20))], deflate=True)


def _declared_expansion() -> bytes:
    """A two-byte entry whose central directory claims 2 GiB."""
    return with_central_size(archive([(MANIFEST_NAME, b"{}")]), 0, 2**31)


def _lying_size() -> bytes:
    """A manifest whose central directory declares fewer bytes than it holds."""
    manifest = b'{"kind":"' + SECRET.encode("ascii") + b'"}'
    return with_central_size(archive([(MANIFEST_NAME, manifest)]), 0, 2)


def _end_record_only(entries: int) -> bytes:
    """An empty archive whose end record declares ``entries`` entries."""
    return struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, entries, entries, 0, 0, 0)


def _with_comment() -> bytes:
    data = archive([(MANIFEST_NAME, b"{}")])
    return data[:-2] + struct.pack("<H", 4) + b"PK\x05\x06"


# --- PNG -------------------------------------------------------------------------------


def chunk(kind: bytes, payload: bytes) -> bytes:
    """A PNG chunk with its length and CRC."""
    crc = zlib.crc32(kind + payload)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def png_declaring(width: int, height: int, *, color_type: int = 6, end: bool = True) -> bytes:
    """A tiny PNG whose ``IHDR`` declares ``width x height`` (one KiB of real IDAT)."""
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    body = _PNG_SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\0" * 1024))
    return body + (chunk(b"IEND", b"") if end else b"")


def _apng() -> bytes:
    """A two-frame animated PNG (APNG), valid RGBA."""
    buffer = io.BytesIO()
    first = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    second = Image.new("RGBA", (4, 4), (0, 0, 255, 255))
    first.save(buffer, "PNG", save_all=True, append_images=[second], duration=100)
    return buffer.getvalue()


def _icc() -> bytes:
    """A valid RGBA PNG carrying an embedded sRGB ICC profile."""
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    buffer = io.BytesIO()
    Image.new("RGBA", (4, 4), (1, 2, 3, 255)).save(buffer, "PNG", icc_profile=profile)
    return buffer.getvalue()


# --- spritesheets ------------------------------------------------------------------------


def _sheet() -> tuple[dict[str, Any], bytes]:
    """A genuine two-frame sheet: its manifest tree and its atlas PNG."""
    pixels = FramePixels(4, 4, bytes((10, 20, 30, 255)) * 16)
    frames = [SheetFrame(f"f{index}", 100, Point(0, 0), pixels) for index in range(2)]
    encoded = encode_spritesheet(frames, columns=2)
    tree = json.loads(encoded.manifest_json.decode("utf-8"))
    assert isinstance(tree, dict)
    return tree, encoded.image


def _sheet_manifest(change: Callable[[dict[str, Any]], object] | None = None) -> bytes:
    tree, _ = _sheet()
    if change is not None:
        change(tree)
    return json.dumps(tree, indent=2).encode("utf-8")


def _sheet_atlas() -> bytes:
    return _sheet()[1]


def _sheet_duplicate() -> bytes:
    text = _sheet_manifest().decode("utf-8")
    old = '"version": 1'
    assert old in text
    return text.replace(old, old + ", " + old, 1).encode("utf-8")


def _sheet_oversized() -> bytes:
    return _sheet_manifest() + b" " * (1024 * 1024)  # 1 MiB of padding after valid JSON


def _bomb_layout(tree: dict[str, Any]) -> None:
    """256 frames of 2048 x 2048 on 16 columns: a declared 32 768 x 32 768 atlas."""
    side, columns, count = 2048, 16, 256
    tree["layout"].update(
        frame_count=count,
        columns=columns,
        rows=count // columns,
        frame_width=side,
        frame_height=side,
        margin=0,
        padding=0,
    )
    tree["image"].update(width=side * columns, height=side * columns)
    template = tree["frames"][0]
    tree["frames"] = [
        {
            **template,
            "frame_id": f"f{index}",
            "rect": [(index % columns) * side, (index // columns) * side, side, side],
            "source_size": [side, side],
        }
        for index in range(count)
    ]


def _rect_outside(tree: dict[str, Any]) -> None:
    tree["frames"][1]["rect"] = [4, 0, 4_000_000, 4]


# --- the corpus ------------------------------------------------------------------------

_JSON = "JSON → modelo"
_PLAN = "modelo → plan"
_REFS = "resolución → render"
_ASSET = "asset → Pillow"
_ZIP = "ZIP → filesystem"
_BATCH = "batch → documento"
_SHEET = "spritesheet → frames"

_DOCUMENT_CASES: Final = (
    HostileCase(
        "json-duplicate-key",
        _JSON,
        "document",
        _replaced('"seed": 42', '"seed": 42, "seed": 7'),
        ValidationError,
        "duplicate_key",
    ),
    HostileCase(
        "json-nesting-33", _JSON, "document", lambda: _nested(33), ValidationError, "too_deep"
    ),
    HostileCase(
        "json-nesting-100k",
        _JSON,
        "document",
        lambda: _nested(100_000),
        ValidationError,
        "too_deep",
    ),
    HostileCase(
        "json-nodes-20001",
        _JSON,
        "document",
        lambda: _wide(20_001),
        ValidationError,
        "too_many_nodes",
    ),
    HostileCase(
        "json-nan",
        _JSON,
        "document",
        _replaced('"seed": 42', '"seed": NaN'),
        ValidationError,
        "non_finite_number",
    ),
    HostileCase(
        "json-infinity",
        _JSON,
        "document",
        _replaced('"seed": 42', '"seed": -Infinity'),
        ValidationError,
        "non_finite_number",
    ),
    HostileCase(
        "json-overflowing-float",
        _JSON,
        "document",
        _replaced('"seed": 42', '"seed": 1e999'),
        ValidationError,
        None,
        pointer="/seed",
    ),
    HostileCase(
        "json-huge-integer",
        _JSON,
        "document",
        _replaced('"seed": 42', '"seed": ' + "9" * 10_000),
        ValidationError,
        "invalid_json",
    ),
    HostileCase(
        "json-oversized",
        _JSON,
        "document",
        lambda: b'{"a":"' + b"x" * (8 * 1024 * 1024) + b'"}',
        ValidationError,
        "too_large",
    ),
    HostileCase(
        "json-invalid-utf8",
        _JSON,
        "document",
        lambda: b'{"a":"\xff\xfe"}',
        ValidationError,
        "invalid_utf8",
    ),
    HostileCase(
        "json-unknown-member-with-code",
        _JSON,
        "document",
        _operation_with(on_load=f"__import__('os').system('{SECRET}')"),
        ValidationError,
        None,
        pointer="/layers/0/operations/0/on_load",
    ),
    HostileCase(
        "json-unknown-operation",
        _JSON,
        "document",
        _operation_with(type="exec"),
        ValidationError,
        None,
        pointer="/layers/0/operations/0/type",
    ),
    HostileCase(
        "plan-canvas-dimension",
        _PLAN,
        "document",
        _replaced('"width": 128', '"width": 18446744073709551617'),
        ValidationError,
        None,
        pointer="/canvas/width",
    ),
    HostileCase(
        "plan-coordinate-beyond-contract",
        _PLAN,
        "document",
        _operation_with(box=[-(2**40), 0, 2**40, 10]),
        ValidationError,
        None,
        pointer="/layers/0/operations/0/box/0",
    ),
    HostileCase(
        "refs-mask-self-cycle",
        _REFS,
        "document",
        _masks({"id": "loop", "type": "union", "masks": ["loop"]}),
        ValidationError,
        None,
        pointer="/masks/0/masks",
    ),
    HostileCase(
        "refs-mask-two-cycle",
        _REFS,
        "document",
        _masks(
            {"id": "ping", "type": "union", "masks": ["pong"]},
            {"id": "pong", "type": "subtract", "masks": ["ping"]},
        ),
        ValidationError,
        None,
        pointer="/masks/0/masks",
    ),
    HostileCase(
        "refs-duplicate-global-id",
        _REFS,
        "document",
        _masks({"id": "body_fill", "type": "rect", "box": [0, 0, 1, 1]}),
        ValidationError,
        None,
        pointer="/masks/0/id",
    ),
    HostileCase(
        "refs-missing-color",
        _REFS,
        "document",
        _operation_with(color=SECRET.replace("-", "_")),
        MoanaError,
        None,
        pointer="/layers/0/operations/0/color",
    ),
)

_BATCH_CASES: Final = (
    HostileCase(
        "batch-duplicate-key",
        _BATCH,
        "batch",
        lambda: b'{"schema_version":"1.0","schema_version":"1.0","commands":[]}',
        ValidationError,
        "duplicate_key",
    ),
    HostileCase("batch-nesting", _BATCH, "batch", lambda: _nested(64), ValidationError, "too_deep"),
    HostileCase(
        "batch-nan",
        _BATCH,
        "batch",
        lambda: b'{"schema_version":"1.0","base_revision":NaN,"commands":[]}',
        ValidationError,
        "non_finite_number",
    ),
    HostileCase(
        "batch-too-many-commands",
        _BATCH,
        "batch",
        lambda: json.dumps(
            {
                "schema_version": "1.0",
                "base_revision": 0,
                "base_snapshot": "sha256:" + "0" * 64,
                "commands": [{"type": "set_visibility", "target_id": "body", "visible": True}]
                * 1025,
            }
        ).encode("utf-8"),
        ValidationError,
        None,
        pointer="/commands",
    ),
    HostileCase(
        "batch-unknown-command",
        _BATCH,
        "batch",
        lambda: json.dumps(
            {
                "schema_version": "1.0",
                "base_revision": 0,
                "base_snapshot": "sha256:" + "0" * 64,
                "commands": [{"type": "shell", "target_id": "body", "argv": [SECRET]}],
            }
        ).encode("utf-8"),
        ValidationError,
        None,
        pointer="/commands/0/type",
    ),
)

_ARCHIVE_CASES: Final = (
    *(
        HostileCase(
            f"zip-{label}",
            _ZIP,
            "project",
            _named(name),
            ValidationError,
            reason,
            key="entry_reason",
        )
        for label, name, reason in (
            ("parent-traversal", f"../{SECRET}.json", "parent_reference"),
            ("nested-traversal", f"assets/../../{SECRET}.png", "parent_reference"),
            ("absolute-posix", f"/tmp/{SECRET}.json", "absolute_path"),
            ("drive-letter", f"C:/{SECRET}.json", "absolute_path"),
            ("drive-relative", f"c:{SECRET}.json", "absolute_path"),
            ("backslash-traversal", f"..\\..\\{SECRET}.json", _BACKSLASH_TRAVERSAL),
            ("windows-absolute", f"C:\\{SECRET}.json", _BACKSLASH_ABSOLUTE),
            ("dot-segment", f"./{SECRET}.json", "invalid_name"),
            ("empty-segment", f"assets//{SECRET}.png", "invalid_name"),
            ("unexpected-entry", f"{SECRET}.py", "unexpected_entry"),
        )
    ),
    HostileCase(
        "zip-symlink-entry",
        _ZIP,
        "project",
        lambda: archive([(symlink_entry(MANIFEST_NAME), b"/etc/passwd")]),
        ValidationError,
        "symlink",
        key="entry_reason",
    ),
    HostileCase(
        "zip-duplicate-name",
        _ZIP,
        "project",
        lambda: archive([(MANIFEST_NAME, b"{}"), (MANIFEST_NAME, b"{}")]),
        ValidationError,
        "duplicate_name",
        key="entry_reason",
    ),
    HostileCase(
        "zip-case-collision",
        _ZIP,
        "project",
        lambda: archive([(asset_name("a"), b"x"), (asset_name("A"), b"y")]),
        ValidationError,
        "name_collision",
        key="entry_reason",
    ),
    HostileCase(
        "zip-ratio-bomb",
        _ZIP,
        "project",
        _ratio_bomb,
        ValidationError,
        "expansion_ratio",
        key="entry_reason",
    ),
    HostileCase(
        "zip-declared-expansion",
        _ZIP,
        "project",
        _declared_expansion,
        ValidationError,
        "expansion_ratio",
        key="entry_reason",
    ),
    HostileCase(
        "zip-declared-smaller-than-real",
        _ZIP,
        "project",
        _lying_size,
        ValidationError,
        "corrupt_archive",
    ),
    HostileCase(
        "zip-entry-count",
        _ZIP,
        "project",
        lambda: _end_record_only(65_000),
        BudgetExceeded,
        "archive_entries",
        key="resource",
    ),
    HostileCase(
        "zip-hidden-comment",
        _ZIP,
        "project",
        _with_comment,
        ValidationError,
        "corrupt_archive",
    ),
)

_ASSET_CASES: Final = (
    HostileCase(
        "png-bomb-65535",
        _ASSET,
        "asset",
        lambda: png_declaring(65_535, 65_535),
        ValidationError,
        "image_too_large",
    ),
    HostileCase(
        "png-axis-2049",
        _ASSET,
        "asset",
        lambda: png_declaring(2049, 1),
        ValidationError,
        "image_too_large",
    ),
    HostileCase(
        "png-zero-width",
        _ASSET,
        "asset",
        lambda: png_declaring(0, 1),
        ValidationError,
        "image_too_large",
    ),
    HostileCase(
        "png-wrong-mode",
        _ASSET,
        "asset",
        lambda: png_declaring(4, 4, color_type=2),
        ValidationError,
        "wrong_mode",
    ),
    HostileCase(
        "png-truncated",
        _ASSET,
        "asset",
        lambda: png_declaring(4, 4, end=False),
        ValidationError,
        "unreadable_image",
    ),
    HostileCase(
        "png-not-png",
        _ASSET,
        "asset",
        lambda: b"GIF89a" + SECRET.encode("ascii"),
        ValidationError,
        "not_png",
    ),
)

_HEADER_CASES: Final = (
    HostileCase(
        "png-animated-apng",
        _ASSET,
        "asset",
        _apng,
        ValidationError,
        "multiple_frames",
        header_only=True,
    ),
    HostileCase(
        "png-icc-profile",
        _ASSET,
        "asset",
        _icc,
        ValidationError,
        "color_profile",
        header_only=True,
    ),
)

_SHEET_CASES: Final = (
    HostileCase(
        "sheet-duplicate-key",
        _SHEET,
        "spritesheet",
        _sheet_duplicate,
        ValidationError,
        "duplicate_member",
        companion=_sheet_atlas,
    ),
    HostileCase(
        "sheet-oversized-manifest",
        _SHEET,
        "spritesheet",
        _sheet_oversized,
        BudgetExceeded,
        "manifest_bytes",
        key="resource",
        companion=_sheet_atlas,
    ),
    HostileCase(
        "sheet-bomb-ihdr",
        _SHEET,
        "spritesheet",
        lambda: _sheet_manifest(_bomb_layout),
        BudgetExceeded,
        "frame_pixels",  # 256 x 2048² ≫ 16 777 216, the first budget checked
        key="resource",
        companion=lambda: png_declaring(32_768, 32_768),
    ),
    HostileCase(
        "sheet-header-larger-than-manifest",
        _SHEET,
        "spritesheet",
        _sheet_manifest,
        ValidationError,
        "image_size_mismatch",
        companion=lambda: png_declaring(65_535, 65_535),
    ),
    HostileCase(
        "sheet-rect-outside-atlas",
        _SHEET,
        "spritesheet",
        lambda: _sheet_manifest(_rect_outside),
        ValidationError,
        "rect_out_of_sheet",
        pointer="/frames/1/rect",
        companion=_sheet_atlas,
    ),
)

_PROJECT_JSON_CASES: Final = (
    HostileCase(
        "manifest-duplicate-key",
        _JSON,
        "project",
        lambda: b'{"kind":"moana-project","kind":"moana-project"}',
        ValidationError,
        "duplicate_key",
    ),
    HostileCase(
        "manifest-overflowing-float",
        _JSON,
        "project",
        lambda: b'{"kind":"moana-project","x":1e999}',
        ValidationError,
        "non_finite_number",
    ),
    HostileCase(
        "manifest-nesting", _JSON, "project", lambda: _nested(35), ValidationError, "too_deep"
    ),
)

CORPUS: Final[tuple[HostileCase, ...]] = (
    *_DOCUMENT_CASES,
    *_BATCH_CASES,
    *_ARCHIVE_CASES,
    *_ASSET_CASES,
    *_HEADER_CASES,
    *_SHEET_CASES,
    *_PROJECT_JSON_CASES,
)
"""Every hostile case, in a stable order; IDs are unique and never renamed."""
