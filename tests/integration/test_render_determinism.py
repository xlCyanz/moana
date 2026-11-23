"""Document → validation → budget → render reproducibility across processes (MOANA-010).

AC1/T1: the same document gives identical RGBA bytes and digest in fresh
interpreters with different ``PYTHONHASHSEED`` values, whatever the order of object
keys or the whitespace of its JSON bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from typing import Any

import pytest

from moanart.render import render
from moanart.schema import canonical_json, validate_document

SCENE: dict[str, Any] = {
    "schema_version": "1.0",
    "id": "harbour",
    "revision": 3,
    "seed": 9_007_199_254_740_993,
    "canvas": {"width": 48, "height": 32, "profile": "rgba"},
    "palette": {
        "id": "pal",
        "colors": [
            {"id": "sea", "rgba": "#1E5A8CFF"},
            {"id": "foam", "rgba": "#E8F4FF99"},
            {"id": "hull", "rgba": "#6B3A1FFF"},
            {"id": "sail", "rgba": "#F2E6C880"},
            {"id": "sun", "rgba": "#FFD24AC0"},
        ],
        "ramps": [{"id": "water", "colors": ["sea", "foam"]}],
    },
    "layers": [
        {
            "id": "water_layer",
            "name": "Agua",
            "operations": [
                {"id": "sea_fill", "type": "rect", "box": [0, 18, 48, 32], "color": "sea"},
                {
                    "id": "wave_a",
                    "type": "line",
                    "start": [0, 20],
                    "end": [47, 23],
                    "color": "foam",
                },
                {
                    "id": "wave_b",
                    "type": "line",
                    "start": [47, 26],
                    "end": [-5, 29],
                    "color": "foam",
                },
            ],
        },
        {
            "id": "sky_layer",
            "name": "Cielo",
            "opacity": 200,
            "operations": [
                {"id": "sun_disc", "type": "ellipse", "box": [34, 2, 45, 13], "color": "sun"},
            ],
        },
        {
            "id": "boat",
            "name": "Barco ⛵",
            "opacity": 230,
            "operations": [
                {
                    "id": "hull_shape",
                    "type": "polygon",
                    "points": [[8, 16], [30, 16], [26, 21], [12, 21]],
                    "color": "hull",
                },
                {
                    "id": "sail_shape",
                    "type": "polygon",
                    "points": [[19, 2], [19, 15], [9, 15], [19, 2], [28, 15], [19, 15]],
                    "color": "sail",
                },
                {"id": "mast_top", "type": "pixel", "at": [19, 1], "color": "hull"},
            ],
        },
        {
            "id": "ghost",
            "name": "Oculta",
            "visible": False,
            "operations": [
                {"id": "ghost_box", "type": "rect", "box": [0, 0, 48, 32], "color": "hull"}
            ],
        },
    ],
    "metadata": {"title": "Puerto", "tags": ["escena", "integración"]},
}

PROBE = """
import hashlib, json, sys
from moanart.render import render
from moanart.schema import validate_document
result = render(validate_document(sys.stdin.buffer.read()))
print(json.dumps({
    "digest": result.digest,
    "rgba": hashlib.sha256(result.rgba).hexdigest(),
    "snapshot": result.provenance.snapshot_digest,
    "warnings": [w.json_pointer for w in result.warnings],
}))
"""


def _reordered(node: Any) -> Any:
    """Same JSON value with every object's keys in reverse order (arrays preserved)."""
    if isinstance(node, dict):
        return {key: _reordered(node[key]) for key in reversed(list(node))}
    if isinstance(node, list):
        return [_reordered(item) for item in node]
    return node


def _variants() -> list[bytes]:
    return [
        json.dumps(SCENE, ensure_ascii=False).encode("utf-8"),
        json.dumps(_reordered(SCENE), ensure_ascii=True, indent=3).encode("utf-8"),
        json.dumps(SCENE, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    ]


def _in_process(source: bytes) -> dict[str, Any]:
    result = render(validate_document(source))
    return {
        "digest": result.digest,
        "rgba": hashlib.sha256(result.rgba).hexdigest(),
        "snapshot": result.provenance.snapshot_digest,
        "warnings": [warning.json_pointer for warning in result.warnings],
    }


def _subprocess(source: bytes, hash_seed: str) -> dict[str, Any]:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    completed = subprocess.run(
        [sys.executable, "-c", PROBE],
        input=source,
        capture_output=True,
        env=env,
        check=True,
    )
    return dict(json.loads(completed.stdout.decode("utf-8")))


def test_scene_is_not_trivial() -> None:
    result = render(validate_document(_variants()[0]))
    alphas = set(result.rgba[3::4])
    assert {0, 255} < alphas  # transparent, opaque and partial alpha all present
    assert len({result.rgba[i : i + 4] for i in range(0, len(result.rgba), 4)}) >= 6


def test_t1_key_order_and_whitespace_do_not_change_the_render() -> None:
    variants = _variants()
    documents = [validate_document(source) for source in variants]
    assert len({canonical_json(document) for document in documents}) == 1
    assert len({json.dumps(_in_process(source)) for source in variants}) == 1


@pytest.mark.slow
@pytest.mark.parametrize("hash_seed", ["0", "1", "4242", "random"])
def test_ac1_t1_fresh_processes_with_any_hash_seed_agree(hash_seed: str) -> None:
    expected = _in_process(_variants()[0])
    for source in _variants():
        assert _subprocess(source, hash_seed) == expected


def test_t1_repeated_renders_in_one_process_agree() -> None:
    source = _variants()[1]
    first = _in_process(source)
    assert all(_in_process(source) == first for _ in range(3))
