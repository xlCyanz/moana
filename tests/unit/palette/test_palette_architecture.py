"""moanart.palette depends only on core and agrees with the document schema (MOANA-005)."""

from __future__ import annotations

import ast
import copy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from moanart.core import errors as core_errors
from moanart.palette import ColorProfile, Palette
from moanart.schema import normalize_document, validate_document

ROOT = Path(__file__).resolve().parents[3]
PALETTE = ROOT / "src/moanart/palette"


def test_palette_imports_only_stdlib_core_and_itself() -> None:
    for path in PALETTE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                assert root in sys.stdlib_module_names or name.startswith(
                    ("moanart.core", "moanart.palette")
                ), f"{path.name} imports {name}"
                assert name not in {"moanart.core.canvas", "moanart.core.pillow_adapter"}


def test_importing_palette_loads_no_heavy_library() -> None:
    probe = (
        "import sys, moanart.palette; "
        "heavy = {'numpy', 'PIL', 'aggdraw', 'pydantic'}; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in heavy))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, encoding="utf-8", check=True
    )
    assert result.stdout.strip() == "[]"


def _document(palette: dict[str, Any], profile: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": 8, "height": 8, "profile": profile},
        "palette": palette,
        "layers": [{"id": "layer", "name": "Layer", "operations": []}],
    }


def _colors(n: int, alpha: str = "FF") -> list[dict[str, str]]:
    return [{"id": f"c{i}", "rgba": f"#{i % 256:02X}0000{alpha}"} for i in range(n)]


GOOD = {
    "id": "pal",
    "colors": [
        {"id": "ink", "rgba": "#000000ff"},
        {"id": "base", "rgba": "#78788CFF"},
        {"id": "clear", "rgba": "#12345600"},
    ],
    "ramps": [{"id": "ramp", "colors": ["ink", "base"]}],
}


@pytest.mark.parametrize("profile", ["strict", "rgba"])
def test_normalized_document_palette_loads_identically(profile: ColorProfile) -> None:
    document = validate_document(_document(copy.deepcopy(GOOD), profile))
    section = normalize_document(document)["palette"]
    palette = Palette.from_mapping(section, profile=document.canvas.profile)
    assert palette.to_mapping() == section


# Semantic cases: same error type, pointers and reasons once prefixed with /palette.
SEMANTIC: dict[str, tuple[dict[str, Any], ColorProfile]] = {
    "partial_alpha_strict": ({"id": "pal", "colors": _colors(2, "80"), "ramps": []}, "strict"),
    "too_many_strict": ({"id": "pal", "colors": _colors(257), "ramps": []}, "strict"),
    "too_long_rgba": ({"id": "pal", "colors": _colors(4097), "ramps": []}, "rgba"),
    "empty": ({"id": "pal", "colors": [], "ramps": []}, "rgba"),
    "ramp_too_short": (
        {"id": "pal", "colors": _colors(2), "ramps": [{"id": "r", "colors": ["c0"]}]},
        "rgba",
    ),
    "unknown_ramp_color": (
        {"id": "pal", "colors": _colors(1), "ramps": [{"id": "r", "colors": ["c0", "ghost"]}]},
        "strict",
    ),
    "duplicate_ramp_color": (
        {"id": "pal", "colors": _colors(1), "ramps": [{"id": "r", "colors": ["c0", "c0"]}]},
        "rgba",
    ),
    "duplicate_color_id": ({"id": "pal", "colors": _colors(1) * 2, "ramps": []}, "strict"),
    "ramp_id_collides_with_color": (
        {"id": "pal", "colors": _colors(2), "ramps": [{"id": "c1", "colors": ["c0", "c1"]}]},
        "rgba",
    ),
    "color_id_collides_with_palette": ({"id": "c0", "colors": _colors(2), "ramps": []}, "rgba"),
}


def _issues(error: core_errors.MoanArtError, prefix: str = "") -> set[tuple[str, str]]:
    return {(prefix + str(d.json_pointer), str(d.context["reason"])) for d in error.details}


@pytest.mark.parametrize("case", sorted(SEMANTIC))
def test_schema_and_palette_report_the_same_semantic_problems(case: str) -> None:
    palette, profile = SEMANTIC[case]
    with pytest.raises(core_errors.MoanArtError) as schema_error:
        validate_document(_document(copy.deepcopy(palette), profile))
    with pytest.raises(core_errors.MoanArtError) as palette_error:
        Palette.from_mapping(copy.deepcopy(palette), profile=profile)
    assert type(schema_error.value) is type(palette_error.value)
    assert _issues(palette_error.value, "/palette") == _issues(schema_error.value)


# Lexical cases: both reject at the same pointer; reasons are each library's own words.
LEXICAL = {
    "id_with_newline": [{"id": "ink\n", "rgba": "#000000FF"}],
    "rrggbb": [{"id": "ink", "rgba": "#000000"}],
    "upper_case_id": [{"id": "Ink", "rgba": "#000000FF"}],
}


@pytest.mark.parametrize("case", sorted(LEXICAL))
def test_schema_and_palette_reject_the_same_lexical_problems(case: str) -> None:
    palette = {"id": "pal", "colors": LEXICAL[case], "ramps": []}
    with pytest.raises(core_errors.ValidationError) as schema_error:
        validate_document(_document(copy.deepcopy(palette), "rgba"))
    with pytest.raises(core_errors.ValidationError) as palette_error:
        Palette.from_mapping(copy.deepcopy(palette), profile="rgba")
    palette_pointers = {pointer for pointer, _ in _issues(palette_error.value, "/palette")}
    assert palette_pointers <= {pointer for pointer, _ in _issues(schema_error.value)}


@pytest.mark.parametrize("profile", ["strict", "rgba"])
def test_partial_alpha_is_accepted_by_both_only_in_rgba(profile: ColorProfile) -> None:
    palette = {"id": "pal", "colors": _colors(2, "80"), "ramps": []}
    if profile == "rgba":
        validate_document(_document(copy.deepcopy(palette), profile))
        assert Palette.from_mapping(palette, profile=profile).color("c0").a == 0x80
    else:
        with pytest.raises(core_errors.ValidationError):
            Palette.from_mapping(palette, profile=profile)
