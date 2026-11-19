"""MOANA-027: the art corpus renders, edits locally, is stable and has an honest record.

* T1: every example renders deterministically to the digests pinned in its record,
  and a localized edit by region (recolouring the adventurer's shirt with
  :func:`moana.api.apply_edit`) changes exactly the visible shirt pixels: the oracle
  is built from the literal boxes of the shirt operations (minus the boxes painted
  over them), and the expected/actual/diff files are written the way the visual
  harness writes them.
* T2: the animation keeps its ground contact, palette and size on every frame and
  has no flicker (also across the loop seam) nor singletons; the audit of
  ``scripts/corpus.py`` passes for every record and reports every tampered field.
* AC1: the five categories are present once each, every hard check passes and the
  recorded warnings equal the real ones (none hidden; no suppression is used).
* AC2: every record satisfies the rubric invariant (a human review is a person's,
  ``professional`` only with the bar met); the validator itself is tested in
  ``tests/unit/quality/test_quality_rubric.py``.
"""

from __future__ import annotations

import copy
import json
import shutil
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from moana.api import apply_edit, evaluate_quality, render, snapshot_digest
from moana.quality import QualityConfig, QualityReport, parse_rubric
from moana.render import render_with_regions
from scripts import corpus
from scripts.corpus import (
    CATEGORIES,
    Entry,
    audit,
    check,
    cluster_labels,
    frames,
    load_entries,
    load_record,
    main,
)
from tests.visual.harness import compare_rgba, write_diagnostics

ENTRIES = {entry.slug: entry for entry in load_entries()}
NOT_A_PERSON = {"fixture", "test", "tests", "agent", "ai_agent", "ai agent", "claude", "codex"}


def _rgba(entry: Entry) -> np.ndarray:
    result = render(entry.document)
    return np.frombuffer(result.rgba, dtype=np.uint8).reshape(result.height, result.width, 4)


def _boxes(shape: tuple[int, int], *boxes: tuple[int, int, int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    for x0, y0, x1, y1 in boxes:
        mask[y0:y1, x0:x1] = True
    return mask


# T1 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("slug", sorted(ENTRIES))
def test_corpus_renders_to_its_pinned_digests(slug: str) -> None:
    entry = ENTRIES[slug]
    first, second = render(entry.document), render(entry.document)
    assert first.rgba == second.rgba
    assert first.digest == entry.record["render"]["digest"]
    pinned = entry.record["render"]["frame_digests"]
    if entry.animation_id is None:
        assert pinned is None
    else:
        report = evaluate_quality(entry.document, animation_id=entry.animation_id)
        assert {m.frame_id: m.digest for m in report.frame_metrics} == pinned


def test_localized_shirt_recolour_stays_inside_the_shirt_region(tmp_path: Path) -> None:
    entry = ENTRIES["adventurer"]
    document = entry.document
    before = _rgba(entry)
    batch = {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": [
            {"type": "set_color", "target_id": target, "color": "pants"}
            for target in ("torso_fill", "sleeve_left")
        ],
    }
    edited = apply_edit(document, batch)
    after = np.frombuffer(render(edited).rgba, dtype=np.uint8).reshape(before.shape)

    # Oracle from the literal boxes of adventurer.moana.json: torso_fill [8,13,16,19)
    # and sleeve_left [5,14,7,17), minus what later operations paint over them
    # (torso_light [8,14,9,18), torso_shade [14,13,16,19), collar [11,13,13,14),
    # sleeve_left_light [5,14,6,16)).
    size = before.shape[:2]
    shirt_ops = _boxes(size, (8, 13, 16, 19), (5, 14, 7, 17))
    covered = _boxes(size, (8, 14, 9, 18), (14, 13, 16, 19), (11, 13, 13, 14), (5, 14, 6, 16))
    expected_changed = shirt_ops & ~covered
    # Hand count: torso 8*6 - light 4 - shade 12 - collar 2; sleeve 2*3 - light 2.
    assert int(expected_changed.sum()) == (48 - 4 - 12 - 2) + (6 - 2)
    changed = (before != after).any(axis=2)

    assert (changed == expected_changed).all()
    assert (before[changed] == [0x3A, 0x71, 0xA8, 0xFF]).all()  # "shirt_mid" (#3A71A8)
    assert (after[changed] == [0x58, 0x52, 0x73, 0xFF]).all()  # "pants" (#585273)
    _, regions = render_with_regions(document, ["shirt"])
    shirt = np.zeros(size, dtype=bool)
    for point in regions["shirt"].points():
        shirt[point.y, point.x] = True
    assert (changed & ~shirt).sum() == 0  # nothing outside the semantic region moved
    assert {c.id: c.rgba for c in edited.palette.colors} == {
        c.id: c.rgba for c in document.palette.colors
    }

    comparison = compare_rgba(before, after)
    assert comparison.changed_pixels == int(expected_changed.sum())
    assert comparison.bbox is not None
    assert comparison.bbox.as_dict() == {"x0": 5, "y0": 13, "x1": 14, "y1": 19}
    manifest = write_diagnostics(
        comparison,
        before,
        after,
        tmp_path / "corpus__adventurer__shirt-recolour",
        golden=tmp_path / "adventurer-1x.png",
        source="examples/corpus/adventurer + set_color(torso_fill, sleeve_left)",
    )
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["changed_pixels"] == comparison.changed_pixels
    assert {"expected.png", "actual.png", "diff.png"} <= {p.name for p in manifest.parent.iterdir()}


# T2 ---------------------------------------------------------------------------------


def test_walk_cycle_is_stable() -> None:
    entry = ENTRIES["adventurer-walk"]
    assert entry.animation_id == "walk"
    config = QualityConfig(rules=(*QualityConfig().rules, "temporal_change"))
    report = evaluate_quality(entry.document, config=config, animation_id="walk")
    assert report.passed_hard_checks
    assert not [f for f in report.findings if f.rule_id.startswith("temporal_")]
    animation = entry.document.animations[0]
    assert animation.loop_count == 0  # the seam last -> first is evaluated too
    assert [f.id for f in animation.frames] == [
        "contact_a",
        "down_a",
        "pass_a",
        "contact_b",
        "down_b",
        "pass_b",
    ]
    assert {f.duration_ms for f in animation.frames} == {120}
    images = frames(entry)
    assert len({image.tobytes() for image in images}) == len(images)  # no repeated pose
    palette = {bytes.fromhex(c.rgba[1:]) for c in entry.document.palette.colors}
    for image in images:
        opaque = image[..., 3] > 0
        rows = np.nonzero(opaque.any(axis=1))[0]
        assert rows.max() == animation.pivot[1]  # one foot always on the ground row
        assert {bytes(p) for p in image[opaque]} <= palette
        # quality-v1 runs the artistic cluster rules on the still image only; the
        # frames are checked here with the same 8-connected definition.
        assert cluster_labels(image)[1].count(1) == 0
    for metrics in report.frame_metrics:
        assert metrics.bbox is not None
        assert metrics.bbox.y1 == animation.pivot[1] + 1


@pytest.mark.parametrize("slug", sorted(ENTRIES))
def test_provenance_audit_passes(slug: str) -> None:
    entry = ENTRIES[slug]
    assert audit(entry) == []
    provenance = entry.record["provenance"]
    assert provenance["authored_by"] == "ai_agent"
    assert provenance["seed"] == entry.document.seed
    assert provenance["third_party_assets"] == []
    assert provenance["licence"].startswith("PENDIENTE")
    assert entry.record["agent_inspection"]["passes"]
    metadata = entry.document.metadata
    assert metadata is not None and metadata.provenance is not None
    assert "PENDIENTE" in metadata.provenance


type Mutation = Callable[[dict[str, Any]], None]


def _set(path: tuple[str, ...], value: object) -> Mutation:
    def mutate(record: dict[str, Any]) -> None:
        node = record
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return mutate


def _delete(key: str) -> Mutation:
    def mutate(record: dict[str, Any]) -> None:
        del record[key]

    return mutate


def _reviewed_with(fingerprint: str) -> Mutation:
    def mutate(record: dict[str, Any]) -> None:
        for item in record["rubric"]["categories"].values():
            item.update(status="reviewed", score=4, justification="fixture")
        record["rubric"]["human_review"] = {
            "reviewer": "fixture",
            "reviewer_kind": "human",
            "date": "2026-11-19",
            "render_fingerprint": fingerprint,
        }

    return mutate


TAMPERED: dict[str, tuple[Mutation, str]] = {
    "renderer_drift": (_set(("provenance", "renderer_version"), "render-v0"), "renderer_version"),
    "estimator_drift": (_set(("provenance", "estimator_version"), "budget-v1"), "estimator"),
    "seed_drift": (_set(("provenance", "seed"), 1), "provenance seed"),
    "missing_render": (_delete("render"), "missing render block"),
    "missing_quality": (_delete("quality"), "missing quality block"),
    "bad_format": (_set(("format",), "moana-corpus-entry/0"), "format must be"),
    "bad_id": (_set(("id",), "toad"), "id the folder name"),
    "bad_category": (_set(("category",), "vehicle"), "unknown category"),
    "brief_keys": (_set(("brief",), {"subject": "frog"}), "brief must have exactly"),
    "brief_size": (_set(("brief", "size"), [16, 16]), "brief size differs"),
    "provenance_keys": (_set(("provenance",), {}), "provenance must have exactly"),
    "blank_licence": (_set(("provenance", "licence"), " "), "licence must be"),
    "third_party": (_set(("provenance", "third_party_assets"), ["pack"]), "third-party"),
    "url": (_set(("brief", "subject"), "see https://example.invalid"), "URLs"),
    "hidden_warning": (_set(("quality", "warnings"), {"singleton": 1}), "quality.warnings"),
    "digest_drift": (_set(("render", "digest"), "sha256:0"), "render.digest"),
    "professional": (_set(("rubric", "professional"), True), "not_professional"),
    "stale_review": (_reviewed_with("sha256:" + "0" * 64), "art changed after the human"),
}


@pytest.mark.parametrize("case", sorted(TAMPERED))
def test_audit_reports_tampered_records(case: str) -> None:
    entry = ENTRIES["frog"]
    mutate, expected = TAMPERED[case]
    tampered = copy.deepcopy(entry.record)
    mutate(tampered)
    errors = audit(Entry(entry.folder, tampered, entry.document))
    assert any(expected in error for error in errors), errors


def test_audit_stops_when_a_still_names_an_animation() -> None:
    entry = ENTRIES["frog"]
    tampered = {**copy.deepcopy(entry.record), "animation_id": "walk"}
    errors = audit(Entry(entry.folder, tampered, entry.document))
    assert errors == ["frog: only the animation category names an animation_id"]


def test_audit_reports_a_real_failing_hard_check(monkeypatch: pytest.MonkeyPatch) -> None:
    # ``outside_mask`` is a hard rule: containing the frog in its eyes region fails.
    def contained(entry: Entry) -> QualityReport:
        return evaluate_quality(entry.document, config=QualityConfig(containment=("eyes",)))

    monkeypatch.setattr(corpus, "report_of", contained)
    errors = audit(ENTRIES["frog"])
    assert "frog: a hard check fails" in errors
    assert any("quality.passed_hard_checks" in error for error in errors)


def test_check_requires_the_five_categories() -> None:
    entries = list(ENTRIES.values())
    assert check(entries) == []
    errors = check([e for e in entries if e.record["category"] != "tile"])
    assert errors and "corpus categories" in errors[0]


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check"]) == 0
    assert "Corpus OK: 5 examples, 5 pending human review" in capsys.readouterr().out
    assert main(["facts"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert sorted(printed) == sorted(ENTRIES)
    shutil.copytree(ENTRIES["frog"].folder, tmp_path / "frog")
    assert main(["check"], root=tmp_path) == 1
    assert "corpus categories" in capsys.readouterr().out


def test_records_reject_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "x.corpus.json"
    path.write_text('{"id": "a", "id": "b"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key 'id'"):
        load_record(path)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_record(path)


# AC1 / AC2 --------------------------------------------------------------------------


def test_five_categories_pass_hard_checks_and_show_every_warning() -> None:
    assert sorted(e.record["category"] for e in ENTRIES.values()) == sorted(CATEGORIES)
    for entry in ENTRIES.values():
        report = evaluate_quality(entry.document, animation_id=entry.animation_id)
        assert report.passed_hard_checks, entry.slug
        assert report.suppressed == ()
        assert entry.record["quality"]["suppressions"] == []
        recorded = entry.record["quality"]["warnings"]
        assert dict(Counter(f.rule_id for f in report.warnings)) == recorded, entry.slug


@pytest.mark.parametrize("slug", sorted(ENTRIES))
def test_real_records_satisfy_the_rubric_invariant(slug: str) -> None:
    entry = ENTRIES[slug]
    report = evaluate_quality(entry.document, animation_id=entry.animation_id)
    rubric = parse_rubric(
        entry.record["rubric"],
        animated=entry.animation_id is not None,
        passed_hard_checks=report.passed_hard_checks,
    )
    if rubric.human_review is not None:
        reviewer = rubric.human_review.reviewer.strip().casefold()
        assert reviewer not in NOT_A_PERSON
        assert rubric.agent_assessment is None or reviewer != (
            rubric.agent_assessment.agent.strip().casefold()
        )
    if rubric.professional:
        assert rubric.meets_professional_bar


def test_real_corpus_is_pending_until_reviewed() -> None:
    # Tripwire for the initial state: no person has reviewed any example yet. When a
    # person records a review (scripts/corpus.py check passes with it), remove that
    # example from ``pending`` in the same change; the invariant test above keeps guarding
    # the rule.
    pending = {"adventurer", "adventurer-walk", "chest", "frog", "stone-tile"}
    for slug in pending:
        rubric = ENTRIES[slug].record["rubric"]
        assert rubric["human_review"] is None
        assert rubric["professional"] is False
        assert {c["status"] for c in rubric["categories"].values()} == {"pending_human_review"}
