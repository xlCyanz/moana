"""MOANA-026: quality reports over every example document (outcomes recorded in ADR-036).

Examples are valid documents, so no hard check may fail. Warnings are recorded, not
forbidden: they are artistic heuristics, and some are intentional (the slime eyes,
the stone highlights). The table of outcomes lives in ADR-036 (section «Resultados
registrados»); ``PINNED`` holds the SHA-256 of each canonical report of the default
configuration. A different digest is a contract change: the pull request must show
the expected and actual reports, their diff and the reason, and update ADR-036.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from moanart.api import evaluate_quality, load_document

EXAMPLES = Path(__file__).resolve().parents[2] / "examples/specs"
NAMES = sorted(path.name for path in EXAMPLES.glob("*.moanart.json"))
# Keyed by the document name without the ``.moanart.json`` suffix.
PINNED: dict[str, str] = {
    "bouncing-slime": "7c77e49df25117ef246103584cadc019f8abe1a7521252ab8a47e32804499c1c",
    "dither-dusk": "696743caaf789723bb7b6ab8948ed94ab6c066b240cf22a212e4ffd76c679dc9",
    "masked-eyes": "edf54809f18ab1f3e4865d2eca1723e894736290153018ae4ceaf681a1b77042",
    "material-cloth": "8884fb47565528be236c8407591f3bd48a3b9528f318fc518197b6876ccec3d9",
    "material-metal": "de0baa84690889f90ef5dac3ee5859e235505a796d59341aee5ce95b339a7f3f",
    "material-skin": "f6d35ab3fbbd19b31e35931cc80ad1f565eb81277beb44cd6f2cc7d3b8da3e44",
    "material-stone": "8fa1974addbd38ccb65eaf683a0d611e95ccfb9a09ce31a45d45538746cf8712",
    "material-wood": "535fb3b40f2f9ed9fdf1402df66845304088517157c518d88295f9e582a4250f",
    "minimal": "e30dd8f0f49b87f7a303eb0d12d33775c87417340394168cd1918f3ae0b98760",
    "outlined-slime": "c16f860917496c2917f4452d02ed7583d1841e3a650b2a76c990fc6fbb72eb27",
    "path-sail": "784e5cd801c2a39b8541819670e4660ad6bf42a34edc3129daf654d28e8f3a92",
    "shaded-orb": "6326c3ca4be386f52605948f896cd25805f611946f6e79ae885d7ee9f9cd6615",
}
# Expected warnings of the default configuration (also in ADR-036).
WARNINGS: dict[str, dict[str, int]] = {
    "bouncing-slime.moanart.json": {"singleton": 2},  # the two eyes
    "material-stone.moanart.json": {"singleton": 2},  # two highlight pixels
    "outlined-slime.moanart.json": {"singleton": 2},  # the two eye glints
}


def canonical(name: str) -> tuple[str, dict[str, int], bool]:
    report = evaluate_quality(load_document(EXAMPLES / name))
    text = json.dumps(report.to_mapping(), sort_keys=True, separators=(",", ":"))
    warnings = dict(Counter[str](f.rule_id for f in report.warnings))
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), warnings, report.passed_hard_checks


def test_every_example_is_pinned() -> None:
    assert sorted(f"{stem}.moanart.json" for stem in PINNED) == NAMES


@pytest.mark.parametrize("name", NAMES)
def test_example_report_matches_its_pinned_digest(name: str) -> None:
    digest, warnings, passed = canonical(name)
    assert passed
    assert warnings == WARNINGS.get(name, {})
    assert digest == PINNED[name.removesuffix(".moanart.json")]


def test_animated_examples_pass_the_hard_checks_on_every_frame() -> None:
    animated = 0
    for name in NAMES:
        document = load_document(EXAMPLES / name)
        for animation in document.animations:
            animated += 1
            report = evaluate_quality(document, animation_id=animation.id)
            assert report.passed_hard_checks
            assert len(report.frame_metrics) == len(animation.frames)
    assert animated >= 1
