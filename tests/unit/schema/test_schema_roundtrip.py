"""T2: model-JSON-model roundtrip, bounded depth fuzz and the golden JSON Schema."""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from moana.core import errors
from moana.schema import (
    Document,
    ParseLimits,
    canonical_json,
    document_json_schema,
    normalize_document,
    snapshot_digest,
    validate_document,
)
from scripts.generate_schema import SCHEMA_PATH, main, render_schema

COORD = st.integers(-1_048_576, 1_048_576)
POINT = st.tuples(COORD, COORD).map(list)
ALPHA = st.sampled_from(["00", "FF", "ff"])


@st.composite
def boxes(draw: st.DrawFn) -> list[int]:
    x0, y0 = draw(COORD), draw(COORD)
    width = draw(st.integers(1, 1_048_577 - x0))
    height = draw(st.integers(1, 1_048_577 - y0))
    return [x0, y0, x0 + width, y0 + height]


@st.composite
def documents(draw: st.DrawFn) -> dict[str, Any]:
    """Valid strict-profile documents; IDs are made unique by construction."""
    counter = iter(range(10_000))

    def new_id(prefix: str) -> str:
        return f"{prefix}{next(counter)}"

    colors = [
        {
            "id": new_id("c"),
            "rgba": "#"
            + draw(st.text("0123456789abcdefABCDEF", min_size=6, max_size=6))
            + draw(ALPHA),
        }
        for _ in range(draw(st.integers(1, 4)))
    ]
    color_ids = [color["id"] for color in colors]
    color = st.sampled_from(color_ids)
    operation = st.one_of(
        st.fixed_dictionaries({"type": st.just("pixel"), "at": POINT, "color": color}),
        st.fixed_dictionaries(
            {"type": st.just("line"), "start": POINT, "end": POINT, "color": color}
        ),
        st.fixed_dictionaries(
            {"type": st.sampled_from(["rect", "ellipse"]), "box": boxes(), "color": color}
        ),
        st.fixed_dictionaries(
            {
                "type": st.just("polygon"),
                "points": st.lists(POINT, min_size=3, max_size=6),
                "color": color,
            }
        ),
    )
    layers = []
    for _ in range(draw(st.integers(0, 3))):
        operations = [{"id": new_id("o"), **item} for item in draw(st.lists(operation, max_size=4))]
        layer: dict[str, Any] = {
            "id": new_id("l"),
            "name": draw(st.text(max_size=8)),
            "operations": operations,
        }
        if draw(st.booleans()):
            layer.update(visible=draw(st.booleans()), locked=draw(st.booleans()))
        layers.append(layer)
    document: dict[str, Any] = {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": draw(st.integers(1, 2048)), "height": draw(st.integers(1, 2048))},
        "palette": {"id": "pal", "colors": colors},
        "layers": layers,
    }
    if draw(st.booleans()):
        document["seed"] = draw(st.integers(0, 2**64 - 1))
    if len(color_ids) >= 2 and draw(st.booleans()):
        document["palette"]["ramps"] = [{"id": "ramp", "colors": color_ids[:2]}]
    if draw(st.booleans()):
        document["metadata"] = {
            "title": draw(st.text(max_size=10)),
            "tags": draw(st.lists(st.text(max_size=5), max_size=3)),
        }
    return document


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(documents())
def test_roundtrip_model_json_model_is_stable(source: dict[str, Any]) -> None:
    document = validate_document(source)
    encoded = canonical_json(document)
    reparsed = validate_document(encoded)
    assert reparsed == document
    assert canonical_json(reparsed) == encoded
    assert normalize_document(validate_document(normalize_document(document))) == json.loads(
        encoded
    )
    assert snapshot_digest(reparsed) == snapshot_digest(document)


def json_values(depth: int) -> st.SearchStrategy[object]:
    scalars = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=3))
    return st.recursive(
        scalars,
        lambda children: st.one_of(
            st.lists(children, max_size=3),
            st.dictionaries(st.text(max_size=3), children, max_size=3),
        ),
        max_leaves=depth,
    )


def depth_of(value: object) -> int:
    if isinstance(value, dict):
        return 1 + max((depth_of(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((depth_of(item) for item in value), default=0)
    return 0


@pytest.mark.security
@settings(max_examples=200)
@given(json_values(60), st.integers(1, 12))
def test_depth_fuzz_fails_only_with_moana_errors(value: object, max_depth: int) -> None:
    """Arbitrary JSON either validates or raises a Moana error; depth is never exceeded."""
    limits = ParseLimits(max_depth=max_depth)
    root = {"schema_version": "1.0", "payload": value}
    data = json.dumps(root).encode()
    for source in (root, data):
        with pytest.raises(errors.MoanaError) as raised:
            validate_document(source, limits=limits)
        too_deep = raised.value.context.get("reason") == "too_deep"
        assert too_deep == (1 + depth_of(value) > max_depth)


def test_generated_schema_matches_reviewed_golden() -> None:
    """Golden: a change here is a contract change that needs a compatibility review."""
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render_schema(), (
        "Generated JSON Schema differs from schemas/: review compatibility, bump "
        "SCHEMA_VERSION for breaking changes, then run scripts/generate_schema.py"
    )
    assert main(["--check"]) == 0


def test_schema_is_reproducible_and_versioned() -> None:
    first, second = document_json_schema(), document_json_schema()
    assert first == second
    assert first["$id"] == "moana-document-1.0.schema.json"
    assert first["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    properties = first["properties"]
    assert isinstance(properties, dict)
    assert properties["schema_version"] == {
        "const": "1.0",
        "title": "Schema Version",
        "type": "string",
    }
    assert first["additionalProperties"] is False
    assert "null" not in json.dumps(first)


def test_schema_compatibility_with_minimal_example() -> None:
    """Every member the minimal example uses is declared by the published schema."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    assert set(Document.model_fields) == set(schema["properties"])
    assert {"width", "height", "profile"} == set(definitions["Canvas"]["properties"])
    rect = definitions["RectOperation"]
    assert set(rect["required"]) == {"id", "type", "box", "color"}
    assert rect["properties"]["box"]["prefixItems"][2]["maximum"] == 1_048_577


def test_check_mode_detects_stale_schema(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.generate_schema as generator

    target = tmp_path / "schemas" / "doc.schema.json"
    monkeypatch.setattr(generator, "SCHEMA_PATH", target)
    monkeypatch.setattr(generator, "ROOT", tmp_path)
    assert generator.main(["--check"]) == 1
    assert generator.main([]) == 0
    assert generator.main(["--check"]) == 0
    target.write_text("{}\n", encoding="utf-8")
    assert generator.main(["--check"]) == 1
