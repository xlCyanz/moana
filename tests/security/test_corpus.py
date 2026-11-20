"""Every case of the malicious corpus is rejected before buffers and side effects (AC1, AC2).

Each case is written to ``tmp_path`` (or passed as bytes for an asset) and handed to
its public entry point with both tripwires armed: no NumPy buffer, no Pillow image
and no filesystem write may happen before the rejection. Cases whose mitigation is
Pillow's header parsing (``header_only``) may open the PNG but never decode a pixel.
The rejection is timed and its Python-traced peak measured against
:data:`~tests.security.guards.MAX_REJECTION_SECONDS` and
:data:`~tests.security.guards.MAX_REJECTION_BYTES`. The expected error and ``reason``
come from the threat model and MOANA.md section 20, not from running the engine; the
directory is byte-identical afterwards and the error never echoes the path, the
planted secret or the hostile entry names.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

import pytest
from PIL import Image

from moana.api import load_document, load_edit_batch
from moana.export import load_spritesheet
from moana.project import Asset, load_project

from .corpus import CORPUS, SECRET, HostileCase
from .guards import (
    assert_bounded,
    assert_clean_error,
    forbid,
    forbid_effects,
    forbid_writes,
    measure,
    pointers,
    tree_state,
)

pytestmark = pytest.mark.security

_SUFFIX = {
    "document": ".moana.json",
    "batch": ".edit.json",
    "project": ".moana",
    "asset": ".png",
    "spritesheet": ".sheet.json",
}


@contextmanager
def _guards(case: HostileCase) -> Iterator[None]:
    with ExitStack() as stack:
        if case.header_only:
            stack.enter_context(forbid_writes())
            stack.enter_context(forbid(Image.Image, "load"))
        else:
            stack.enter_context(forbid_effects())
        yield


def _load(case: HostileCase, source: Path, payload: bytes) -> None:
    if case.target == "asset":
        Asset.from_png("hostile", payload)
    elif case.target == "document":
        load_document(source)
    elif case.target == "batch":
        load_edit_batch(source)
    elif case.target == "spritesheet":
        load_spritesheet(source.with_suffix(".png"), source)
    else:
        load_project(source)


@pytest.mark.parametrize("case", CORPUS, ids=[case.id for case in CORPUS])
def test_ac1_t1_corpus_case_is_rejected_before_buffers_and_io(
    case: HostileCase, tmp_path: Path
) -> None:
    payload = case.build()
    source = tmp_path / f"hostile{_SUFFIX[case.target]}"
    if case.target != "asset":
        source.write_bytes(payload)
    if case.companion is not None:
        source.with_suffix(".png").write_bytes(case.companion())
    before = tree_state(tmp_path)
    with _guards(case):
        rejection = measure(lambda: _load(case, source, payload))
    error = assert_clean_error(assert_bounded(rejection), tmp_path, SECRET, "../", "C:")
    assert isinstance(error, case.error)
    if case.reason is not None:
        assert error.context.get(case.key) == case.reason
    if case.pointer is not None:
        assert case.pointer in pointers(error)
    assert tree_state(tmp_path) == before  # nothing written, nothing extracted
    assert not (tmp_path.parent / f"{SECRET}.json").exists()


def test_corpus_is_versioned_with_unique_ids_and_known_boundaries() -> None:
    ids = Counter(case.id for case in CORPUS)
    assert not [name for name, count in ids.items() if count > 1]
    boundaries = {case.boundary for case in CORPUS}
    assert boundaries == {
        "JSON → modelo",
        "modelo → plan",
        "resolución → render",
        "asset → Pillow",
        "ZIP → filesystem",
        "batch → documento",
        "spritesheet → frames",
    }


@pytest.mark.parametrize("case", CORPUS, ids=[case.id for case in CORPUS])
def test_corpus_payload_is_inert_and_small(case: HostileCase) -> None:
    payload = case.build()
    assert payload == case.build()  # deterministic: the corpus is versioned as code
    assert len(payload) <= 8 * 1024 * 1024 + 16
    for marker in (b"#!", b"MZ\x90", b"\x7fELF"):
        assert not payload.startswith(marker)
