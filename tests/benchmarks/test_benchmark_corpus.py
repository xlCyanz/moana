"""T1: shape of the section 22 benchmark corpus, counted on the JSON tree (MOANA-031).

The oracle is the generated JSON itself (layers, operations, frames counted here),
never an engine output.
"""

from __future__ import annotations

from typing import Any

import pytest

from moana import api
from moana.animation import evaluate_animation
from moana.schema import validate_document

from . import corpus

pytestmark = pytest.mark.benchmark


def _operations(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [op for layer in document["layers"] for op in layer["operations"]]


def test_t1_static_case_has_32_layers_and_500_rects() -> None:
    document: dict[str, Any] = corpus.static_document()
    operations = _operations(document)
    assert document["canvas"] == {"width": 128, "height": 128, "profile": "strict"}
    assert len(document["layers"]) == 32
    assert len(operations) == 500
    assert {op["type"] for op in operations} == {"rect"}
    assert sorted({len(layer["operations"]) for layer in document["layers"]}) == [15, 16]
    ids = [op["id"] for op in operations] + [layer["id"] for layer in document["layers"]]
    assert len(ids) == len(set(ids))


def test_t1_rects_stay_inside_the_margin_so_no_frame_clips_one() -> None:
    for op in _operations(corpus.static_document()):
        x0, y0, x1, y1 = op["box"]
        assert 4 <= x0 < x1 <= 124 and 4 <= y0 < y1 <= 124
        assert 4 <= x1 - x0 <= 31 and 4 <= y1 - y0 <= 31


def test_t1_palette_is_strict_and_opaque() -> None:
    document: dict[str, Any] = corpus.static_document()
    colours = document["palette"]["colors"]
    assert len(colours) == 16
    assert all(colour["rgba"].endswith("FF") for colour in colours)
    assert len({colour["rgba"] for colour in colours}) == 16


def test_t1_animation_has_16_frames_of_equal_complexity() -> None:
    document: dict[str, Any] = corpus.animation_document()
    (animation,) = document["animations"]
    frames = animation["frames"]
    assert len(frames) == 16
    kinds = [sorted(o["type"] for o in frame["overrides"]) for frame in frames]
    assert all(k == ["set_color"] * 8 + ["translate"] * 32 for k in kinds)
    assert len({str(frame["overrides"]) for frame in frames}) == 16
    assert len(_operations(document)) == 500 and len(document["layers"]) == 32


def test_t1_every_case_validates_and_every_frame_is_a_different_render() -> None:
    for name in corpus.case_names():
        validate_document(corpus.canonical_bytes(corpus.case_document(name)))
    document = validate_document(corpus.canonical_bytes(corpus.animation_document()))
    frames = evaluate_animation(document, corpus.ANIMATION_ID)
    digests = {api.render(frame.document).digest for frame in frames}
    assert len(digests) == 16
    assert api.render(document).digest not in digests


def test_corpus_names_digest_and_unknown_case() -> None:
    assert corpus.case_names()[:2] == ("static", "animation")
    assert corpus.case_animation("static") is None
    assert corpus.case_animation("corpus/adventurer-walk") == "walk"
    assert corpus.corpus_digest() == corpus.corpus_digest()
    assert corpus.corpus_digest(("static",)) != corpus.corpus_digest(("animation",))
    for bad in ("nope", "corpus/missing", "adventurer"):
        with pytest.raises(ValueError, match="unknown benchmark case"):
            corpus.case_document(bad)


def test_recolour_changes_one_rect_only() -> None:
    base, changed = (
        _operations(corpus.static_document()),
        _operations(corpus.static_document(recolour=7)),
    )
    assert [a == b for a, b in zip(base, changed, strict=True)].count(False) == 1
    assert base[7]["color"] != changed[7]["color"]
