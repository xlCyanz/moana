"""Reproducibility of ``aggdraw-v1`` paths in a fixed environment (MOANA-007, T2).

The backend guarantee is limited (ADR-023): the same document gives the same RGBA
in fresh interpreters with any ``PYTHONHASHSEED`` *on the same platform and tested
AggDraw version*. Across platforms the contract only promises what the oracles of
``tests/unit/geometry/test_geometry_paths.py`` check; here the cross-backend
comparison is limited to integer-aligned rectangles, where ``path`` and ``rect``
must agree on every platform. No path digest is stored as an expected value: the
cross-platform record is the CI report (local macOS run; matrix pending on main).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from typing import Any

import pytest

from moana.render import render
from moana.schema import validate_document

U = 256


def scene(operations: list[dict[str, Any]], masks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "id": "paths",
        "canvas": {"width": 40, "height": 24, "profile": "rgba"},
        "palette": {
            "id": "pal",
            "colors": [
                {"id": "ink", "rgba": "#102030FF"},
                {"id": "gold", "rgba": "#FAC800C0"},
            ],
        },
        "masks": masks,
        "layers": [
            {"id": "shapes", "name": "Formas", "operations": operations},
            {
                "id": "masked",
                "name": "Recorte",
                "mask_id": "blob",
                "opacity": 200,
                "operations": [
                    {"id": "wash", "type": "rect", "box": [0, 0, 40, 24], "color": "gold"}
                ],
            },
        ],
    }


def path(name: str, commands: list[list[Any]]) -> dict[str, Any]:
    return {
        "id": name,
        "type": "path",
        "backend": "aggdraw-v1",
        "color": "ink",
        "commands": commands,
    }


CURVES = scene(
    [
        path("wave", [["M", -2 * U, 20 * U], ["C", 10 * U, 2 * U, 30 * U, 30 * U, 44 * U, 8 * U]]),
        path("lens", [["M", 4 * U + 77, 3 * U], ["Q", 20 * U, -6 * U, 36 * U + 5, 3 * U]]),
        path(
            "star",
            [
                ["M", 20 * U, 2 * U],
                ["L", 25 * U, 18 * U],
                ["L", 12 * U, 8 * U],
                ["L", 28 * U, 8 * U],
                ["L", 15 * U, 18 * U],
                ["Z"],
            ],
        ),
    ],
    [
        {
            "id": "blob",
            "type": "path",
            "backend": "aggdraw-v1",
            "commands": [["M", 22 * U, 4 * U], ["C", 46 * U, 0, 40 * U, 30 * U, 22 * U, 20 * U]],
        }
    ],
)

PROBE = """
import json, platform, sys
from moana.render import render
from moana.schema import validate_document
result = render(validate_document(sys.stdin.buffer.read()))
print(json.dumps({
    "digest": result.digest,
    "versions": list(result.provenance.vector_backend_versions),
    "platform": platform.system(),
}))
"""


def _subprocess(source: bytes, hash_seed: str) -> dict[str, Any]:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    completed = subprocess.run(
        [sys.executable, "-c", PROBE],
        input=source,
        capture_output=True,
        env=env,
        check=True,
        timeout=60,
    )
    return dict(json.loads(completed.stdout.decode("utf-8")))


def test_scene_draws_every_path() -> None:
    result = render(validate_document(CURVES))
    pixels = {result.rgba[i : i + 4] for i in range(0, len(result.rgba), 4)}
    assert bytes.fromhex("102030FF") in pixels
    assert len(pixels) >= 3  # transparent, ink and the masked wash


@pytest.mark.slow
@pytest.mark.parametrize("hash_seed", ["0", "1", "4242", "random"])
def test_t2_fresh_processes_with_any_hash_seed_agree(hash_seed: str) -> None:
    local = render(validate_document(CURVES))
    for source in (
        json.dumps(CURVES).encode("utf-8"),
        json.dumps(CURVES, sort_keys=True, indent=2).encode("utf-8"),
    ):
        probe = _subprocess(source, hash_seed)
        assert probe["digest"] == local.digest
        assert probe["versions"] == list(local.provenance.vector_backend_versions)
        assert probe["platform"] == platform.system()


def test_t2_integer_rectangles_agree_with_the_integer_backend_on_any_platform() -> None:
    """The only cross-backend promise: integer-aligned rectangles (ADR-023)."""
    boxes = [[2, 3, 9, 7], [-4, 10, 6, 30], [30, -2, 44, 5], [12, 12, 13, 13]]
    as_paths = [
        path(
            f"p{i}",
            [
                ["M", x0 * U, y0 * U],
                ["L", x1 * U, y0 * U],
                ["L", x1 * U, y1 * U],
                ["L", x0 * U, y1 * U],
                ["Z"],
            ],
        )
        for i, (x0, y0, x1, y1) in enumerate(boxes)
    ]
    as_rects = [
        {"id": f"r{i}", "type": "rect", "box": box, "color": "ink"} for i, box in enumerate(boxes)
    ]
    mask = {"id": "blob", "type": "rect", "box": [0, 0, 1, 1]}
    with_paths = render(validate_document(scene(as_paths, [mask])))
    with_rects = render(validate_document(scene(as_rects, [mask])))
    assert with_paths.digest == with_rects.digest
    assert with_paths.provenance.vector_backend == "aggdraw-v1"
    assert with_rects.provenance.vector_backend is None
