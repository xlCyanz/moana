"""Material textures without flicker across processes and hash seeds (MOANA-017, T2).

Every ``examples/specs/material-*.moanart.json`` renders to identical RGBA bytes and
digest in fresh interpreters with different ``PYTHONHASHSEED`` values and in repeated
renders: the texture depends only on the document seed, the operation ID and the
cell (``cell-sha256-v1``), never on ``hash()``, a global RNG or the clock.
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

from moanart.render import render
from moanart.schema import validate_document

SPECS = Path(__file__).resolve().parents[2] / "examples" / "specs"
EXAMPLES = ["skin", "cloth", "metal", "wood", "stone"]

PROBE = """
import hashlib, json, sys
from moanart.render import render
from moanart.schema import validate_document
result = render(validate_document(sys.stdin.buffer.read()))
print(json.dumps({
    "digest": result.digest,
    "rgba": hashlib.sha256(result.rgba).hexdigest(),
}))
"""


def _source(name: str) -> bytes:
    return (SPECS / f"material-{name}.moanart.json").read_bytes()


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


@pytest.mark.slow
@pytest.mark.parametrize("hash_seed", ["0", "1", "4242", "random"])
@pytest.mark.parametrize("name", EXAMPLES)
def test_t2_fresh_processes_with_any_hash_seed_agree(name: str, hash_seed: str) -> None:
    source = _source(name)
    assert _subprocess(source, hash_seed) == _in_process(source)


@pytest.mark.parametrize("name", EXAMPLES)
def test_t2_repeated_renders_in_one_process_agree(name: str) -> None:
    source = _source(name)
    first = _in_process(source)
    assert all(_in_process(source) == first for _ in range(3))


def test_t2_the_texture_does_not_depend_on_the_order_of_json_keys() -> None:
    """The same document with its keys reversed renders the same bytes."""
    tree = json.loads(_source("stone"))

    def reversed_keys(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: reversed_keys(value[key]) for key in reversed(list(value))}
        if isinstance(value, list):
            return [reversed_keys(item) for item in value]
        return value

    source = json.dumps(reversed_keys(tree)).encode("utf-8")
    assert _in_process(source) == _in_process(_source("stone"))
