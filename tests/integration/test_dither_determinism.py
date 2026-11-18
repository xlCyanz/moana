"""Dithering without flicker across processes and hash seeds (MOANA-016, T2).

The example ``examples/specs/dither-dusk.moana.json`` renders to identical RGBA bytes
and digest in fresh interpreters with different ``PYTHONHASHSEED`` values and in
repeated renders; its sky rows match the literal Bayer 4 x 4 matrix of MOANA.md
section 10 and its dune pixels the Bayer 2 x 2 phase of origin (0, -1), computed
here by hand.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from moana.render import render
from moana.schema import validate_document

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "specs" / "dither-dusk.moana.json"
BAYER_2 = [[0, 2], [3, 1]]
BAYER_4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
NIGHT, DUSK = (0x1B, 0x1A, 0x3A, 255), (0x5A, 0x2F, 0x5E, 255)
EMBER, GLOW = (0xB8, 0x54, 0x5E, 255), (0xE8, 0x9A, 0x5C, 255)
SAND, SHADOW = (0xA9, 0x81, 0x4F, 255), (0x6A, 0x4E, 0x3A, 255)
# (first row, last row + 1, colour A, colour B, coverage): one 4-row period each,
# anchored at (0, 0)
BANDS = [(4, 8, NIGHT, DUSK, 6), (8, 12, DUSK, EMBER, 8), (12, 16, EMBER, GLOW, 10)]

PROBE = """
import hashlib, json, sys
from moana.render import render
from moana.schema import validate_document
result = render(validate_document(sys.stdin.buffer.read()))
print(json.dumps({
    "digest": result.digest,
    "rgba": hashlib.sha256(result.rgba).hexdigest(),
}))
"""


def _in_process(source: bytes) -> dict[str, Any]:
    result = render(validate_document(source))
    return {"digest": result.digest, "rgba": hashlib.sha256(result.rgba).hexdigest()}


def _subprocess(source: bytes, hash_seed: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-c", PROBE],
        input=source,
        capture_output=True,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        check=True,
    )
    return dict(json.loads(completed.stdout.decode("utf-8")))


def test_example_sky_matches_the_hand_computed_bayer_bands() -> None:
    result = render(validate_document(EXAMPLE.read_bytes()))
    for y in range(4):
        assert {result.pixel(x, y) for x in range(32)} == {NIGHT}
    for top, bottom, color_a, color_b, coverage in BANDS:
        for y in range(top, bottom):
            for x in range(32):
                chosen = color_b if BAYER_4[y % 4][x % 4] < coverage else color_a
                assert result.pixel(x, y) == chosen, (x, y)
    for y in (16, 17):
        assert {result.pixel(x, y) for x in range(32)} == {GLOW}


def test_example_dune_matches_hand_computed_pixels() -> None:
    """Dune pixels by hand (MOANA.md sections 6 and 10).

    ``dune_dither`` is Bayer 2 x 2, coverage 2, origin (0, -1): B (shadow) where
    ``[[0, 2], [3, 1]][(y + 1) mod 2][x mod 2] < 2``, i.e. where ``x + y`` is odd.
    With origin (0, 0) it would be where ``x + y`` is even, so every shoulder pixel
    below would flip. Mask membership comes from the ellipse inequality of section 6:
    (16, 23), (15, 23), (2, 24) and (3, 24) are inside ``dune_inner``
    ``[-10, 21, 42, 53)`` (e.g. (16, 23): A = 1, B = -27, 1*32^2 + 729*52^2 =
    1 972 240 <= 52^2*32^2 = 2 768 896) and above ``dune_core`` (rows >= 25).
    """
    result = render(validate_document(EXAMPLE.read_bytes()))
    shoulder = {(16, 23): SHADOW, (15, 23): SAND, (2, 24): SAND, (3, 24): SHADOW}
    for (x, y), color in shoulder.items():
        assert result.pixel(x, y) == color, (x, y)
        with_origin_zero = SHADOW if BAYER_2[y % 2][x % 2] < 2 else SAND
        assert with_origin_zero != color, (x, y)  # the negative anchor is visible
    assert result.pixel(16, 30) == SHADOW  # solid core: A = 1, B = -21 inside [-8, 25, 40, 57)
    assert result.pixel(16, 19) == SAND  # lit rim: inside [-12, 18, 44, 50), above dune_inner
    assert result.pixel(0, 18) == GLOW  # 961*32^2 + 961*56^2 > 56^2*32^2: outside the dune


@pytest.mark.slow
@pytest.mark.parametrize("hash_seed", ["0", "1", "4242", "random"])
def test_t2_fresh_processes_with_any_hash_seed_agree(hash_seed: str) -> None:
    source = EXAMPLE.read_bytes()
    assert _subprocess(source, hash_seed) == _in_process(source)


def test_t2_repeated_renders_in_one_process_agree() -> None:
    source = EXAMPLE.read_bytes()
    first = _in_process(source)
    assert all(_in_process(source) == first for _ in range(3))
