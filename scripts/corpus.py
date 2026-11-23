"""Art corpus tooling: audit records and build review views (MOANA-027, ADR-037).

Each example lives in ``examples/corpus/<slug>/``: the editable source
``<slug>.moanart.json``, the record ``<slug>.corpus.json`` (brief, provenance, pinned
render and quality facts, agent inspection notes and the human rubric) and the
reviewed previews under ``previews/``. Two subcommands:

``check``
    Audit every record: format, category, brief, provenance (licence, seed, renderer
    and estimator versions, vector backend, no third-party assets, no URLs), the
    pinned render digests and quality outcome (hard checks must pass; the recorded
    warnings must equal the real ones, so none is hidden), the previews on disk, the
    rubric (:func:`moanart.quality.parse_rubric`: ``professional`` only with a human
    review scoring every applicable category at least 4) and, when a human review
    exists, that its ``render_fingerprint`` still matches the render (otherwise the
    art changed after the review). Records with a repeated JSON key are rejected.
    Exit code 1 on any error.
``facts``
    Print, as JSON, the facts computed now for each example (digests, warnings,
    versions and the ``render_fingerprint`` a human review records), so a person can
    update a record after a reviewed source change.

Previews are compared and rewritten only through the visual harness
(``tests/visual/test_corpus_previews.py``; ``MOANART_UPDATE_GOLDENS=1`` locally, never
in CI). Nothing here writes a file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

from moanart.api import Document, capabilities, evaluate_quality, load_document, render
from moanart.core.errors import MoanArtError
from moanart.quality import QualityReport, parse_rubric

ROOT: Final = Path(__file__).resolve().parents[1]
CORPUS_DIR: Final = ROOT / "examples" / "corpus"
ENTRY_FORMAT: Final = "moanart-corpus-entry/1"
CATEGORIES: Final = ("character", "creature", "object", "tile", "animation")
PREVIEW_SCALE: Final = 4
BRIEF_KEYS: Final = ("subject", "size", "palette_intent", "light", "constraints")
PROVENANCE_KEYS: Final = (
    "author",
    "authored_by",
    "method",
    "date",
    "licence",
    "third_party_assets",
    "seed",
    "renderer_version",
    "estimator_version",
    "vector_backend",
)
SILHOUETTE_INK: Final = (0, 0, 0, 255)
SILHOUETTE_PAPER: Final = (255, 255, 255, 255)
SINGLETON_COLOUR: Final = (255, 0, 255, 255)
CLUSTER_COLOURS: Final = (
    (230, 159, 0, 255),
    (86, 180, 233, 255),
    (0, 158, 115, 255),
    (240, 228, 66, 255),
    (0, 114, 178, 255),
    (213, 94, 0, 255),
    (204, 121, 167, 255),
    (120, 120, 120, 255),
)
"""Categorical colours of the cluster view; neighbouring clusters never share one
when the table allows it. Magenta is reserved for singletons."""
_URL: Final = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")

type RGBA = npt.NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class Entry:
    """One corpus example: its folder, its record and its validated document."""

    folder: Path
    record: dict[str, Any]
    document: Document

    @property
    def slug(self) -> str:
        return self.folder.name

    @property
    def animation_id(self) -> str | None:
        value = self.record.get("animation_id")
        return value if isinstance(value, str) else None


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"duplicate JSON key {duplicates[0]!r}")
    return dict(pairs)


def load_record(path: Path) -> dict[str, Any]:
    """A record as JSON; a repeated key in any object is ``ValueError``."""
    record = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    if not isinstance(record, dict):
        raise ValueError("a corpus record is a JSON object")
    return record


def load_entries(root: Path = CORPUS_DIR) -> list[Entry]:
    """Every example folder of ``root`` (sorted), with its record and document."""
    entries = []
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        record = load_record(folder / f"{folder.name}.corpus.json")
        document = load_document(folder / f"{folder.name}.moanart.json")
        entries.append(Entry(folder, record, document))
    return entries


def _array(width: int, height: int, rgba: bytes) -> RGBA:
    return np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4).copy()


def frames(entry: Entry) -> list[RGBA]:
    """The rendered still image, or every frame of the example's animation."""
    if entry.animation_id is None:
        result = render(entry.document)
        return [_array(result.width, result.height, result.rgba)]
    animation = next(a for a in entry.document.animations if a.id == entry.animation_id)
    rendered = [render(entry.document, frame_id=frame.id) for frame in animation.frames]
    return [_array(r.width, r.height, r.rgba) for r in rendered]


def sheet(entry: Entry) -> RGBA:
    """The still image, or the frames side by side (a horizontal strip)."""
    return np.concatenate(frames(entry), axis=1)


def scale(image: RGBA, factor: int) -> RGBA:
    """Nearest-neighbour enlargement by an integer factor."""
    return np.repeat(np.repeat(image, factor, axis=0), factor, axis=1)


def silhouette(image: RGBA) -> RGBA:
    """Every pixel with alpha > 0 in solid black on white paper."""
    view = np.empty_like(image)
    view[...] = SILHOUETTE_PAPER
    view[image[..., 3] > 0] = SILHOUETTE_INK
    return view


def _neighbours(x: int, y: int, width: int, height: int) -> Iterator[tuple[int, int]]:
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            nx, ny = x + dx, y + dy
            if (dx or dy) and 0 <= nx < width and 0 <= ny < height:
                yield nx, ny


def cluster_labels(image: RGBA) -> tuple[npt.NDArray[np.int32], list[int]]:
    """8-connected clusters of equal RGBA (labels from 0, -1 transparent) and areas.

    Same definition as the artistic cluster rules of ``moanart.quality``
    (``cluster_connectivity`` 8): the tests compare the singleton count with the
    quality report's ``singletons`` metric.
    """
    height, width = image.shape[:2]
    labels = np.full((height, width), -1, dtype=np.int32)
    areas: list[int] = []
    for y in range(height):
        for x in range(width):
            if image[y, x, 3] == 0 or labels[y, x] >= 0:
                continue
            label, stack, area = len(areas), [(x, y)], 0
            labels[y, x] = label
            while stack:
                cx, cy = stack.pop()
                area += 1
                for nx, ny in _neighbours(cx, cy, width, height):
                    if labels[ny, nx] < 0 and np.array_equal(image[ny, nx], image[cy, cx]):
                        labels[ny, nx] = label
                        stack.append((nx, ny))
            areas.append(area)
    return labels, areas


def cluster_view(image: RGBA) -> RGBA:
    """Clusters in categorical colours, singletons in magenta, transparency white."""
    labels, areas = cluster_labels(image)
    height, width = labels.shape
    touching: list[set[int]] = [set() for _ in areas]
    for y in range(height):
        for x in range(width):
            here = int(labels[y, x])
            for nx, ny in _neighbours(x, y, width, height):
                there = int(labels[ny, nx])
                if here >= 0 and there >= 0 and there != here:
                    touching[here].add(there)
    colour: list[int] = []
    for label in range(len(areas)):
        used = {colour[other] for other in touching[label] if other < label}
        free = [index for index in range(len(CLUSTER_COLOURS)) if index not in used]
        colour.append(free[0] if free else label % len(CLUSTER_COLOURS))
    view = np.empty_like(image)
    view[...] = SILHOUETTE_PAPER
    for y in range(height):
        for x in range(width):
            label = int(labels[y, x])
            if label >= 0:
                singleton = areas[label] == 1
                view[y, x] = SINGLETON_COLOUR if singleton else CLUSTER_COLOURS[colour[label]]
    return view


def views(entry: Entry) -> dict[str, RGBA]:
    """The reviewed previews of an example, keyed by their file suffix."""
    image = sheet(entry)
    result = {
        "1x": image,
        "4x": scale(image, PREVIEW_SCALE),
        "silhouette-4x": scale(silhouette(image), PREVIEW_SCALE),
        "clusters-4x": scale(cluster_view(image), PREVIEW_SCALE),
    }
    if entry.record.get("category") == "tile":
        result["tiled-3x3-4x"] = scale(np.tile(image, (3, 3, 1)), PREVIEW_SCALE)
    return result


def preview_path(entry: Entry, view: str) -> Path:
    return entry.folder / "previews" / f"{entry.slug}-{view}.png"


def report_of(entry: Entry) -> QualityReport:
    """Quality report of the default configuration (with the animation, if any)."""
    return evaluate_quality(entry.document, animation_id=entry.animation_id)


def report_digest(report: QualityReport) -> str:
    text = json.dumps(report.to_mapping(), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_fingerprint(render_facts: dict[str, Any]) -> str:
    """``sha256:`` of the canonical JSON of the ``render`` facts (digest and frames).

    A human review stores it as ``human_review.render_fingerprint``: the audit then
    reports a review whose pixels changed afterwards.
    """
    text = json.dumps(render_facts, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def facts(entry: Entry) -> dict[str, Any]:
    """What the engine computes now for an example (compared with its record)."""
    base = render(entry.document)
    report = report_of(entry)
    frame_digests = None
    if entry.animation_id is not None:
        frame_digests = {item.frame_id: item.digest for item in report.frame_metrics}
    render_facts = {"digest": base.digest, "frame_digests": frame_digests}
    return {
        "render": render_facts,
        "render_fingerprint": render_fingerprint(render_facts),
        "quality": {
            "rule_set": report.rule_set,
            "passed_hard_checks": report.passed_hard_checks,
            "warnings": dict(sorted(Counter(f.rule_id for f in report.warnings).items())),
            "report_digest": report_digest(report),
        },
        "versions": {
            "seed": entry.document.seed,
            "renderer_version": base.renderer_version,
            "estimator_version": capabilities().estimator_version,
            "vector_backend": base.provenance.vector_backend or None,
        },
    }


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _audit_brief(record: dict[str, Any], entry: Entry) -> list[str]:
    brief = record.get("brief")
    if not isinstance(brief, dict) or sorted(brief) != sorted(BRIEF_KEYS):
        return [f"{entry.slug}: brief must have exactly {', '.join(BRIEF_KEYS)}"]
    canvas = entry.document.canvas
    if brief["size"] != [canvas.width, canvas.height]:
        return [f"{entry.slug}: brief size differs from the canvas"]
    return []


def _audit_provenance(record: dict[str, Any], entry: Entry, now: dict[str, Any]) -> list[str]:
    provenance = record.get("provenance")
    if not isinstance(provenance, dict) or sorted(provenance) != sorted(PROVENANCE_KEYS):
        return [f"{entry.slug}: provenance must have exactly {', '.join(PROVENANCE_KEYS)}"]
    errors = []
    for key in ("author", "method", "date", "licence"):
        if not isinstance(provenance[key], str) or not provenance[key].strip():
            errors.append(f"{entry.slug}: provenance {key} must be a non-blank text")
    if provenance["third_party_assets"] != []:
        errors.append(f"{entry.slug}: the corpus admits no third-party assets")
    for key, value in now["versions"].items():
        if provenance[key] != value:
            errors.append(f"{entry.slug}: provenance {key} is {provenance[key]!r}, now {value!r}")
    return errors


def _audit_quality(record: dict[str, Any], entry: Entry, now: dict[str, Any]) -> list[str]:
    errors = []
    if not now["quality"]["passed_hard_checks"]:
        errors.append(f"{entry.slug}: a hard check fails")
    for block in ("render", "quality"):
        recorded = record.get(block)
        if not isinstance(recorded, dict):
            errors.append(f"{entry.slug}: missing {block} block")
            continue
        for key, value in now[block].items():
            if recorded.get(key) != value:
                errors.append(
                    f"{entry.slug}: {block}.{key} is {recorded.get(key)!r}, now {value!r}"
                )
    return errors


def audit(entry: Entry) -> list[str]:
    """Every problem of one example (empty when the record is consistent)."""
    record = entry.record
    errors = []
    if record.get("format") != ENTRY_FORMAT or record.get("id") != entry.slug:
        errors.append(f"{entry.slug}: format must be {ENTRY_FORMAT} and id the folder name")
    if record.get("category") not in CATEGORIES:
        errors.append(f"{entry.slug}: unknown category {record.get('category')!r}")
    animated = record.get("category") == "animation"
    if animated != (entry.animation_id is not None):
        # Nothing else can be computed reliably (the animation may not exist).
        return [*errors, f"{entry.slug}: only the animation category names an animation_id"]
    if any(_URL.search(text) for text in _strings(record)):
        errors.append(f"{entry.slug}: records hold no URLs (no external sources)")
    now = facts(entry)
    errors += _audit_brief(record, entry)
    errors += _audit_provenance(record, entry, now)
    errors += _audit_quality(record, entry, now)
    errors += [
        f"{entry.slug}: missing preview {preview_path(entry, view).name}"
        for view in views(entry)
        if not preview_path(entry, view).is_file()
    ]
    try:
        parse_rubric(
            record.get("rubric"),
            animated=animated,
            passed_hard_checks=bool(now["quality"]["passed_hard_checks"]),
        )
    except MoanArtError as error:
        errors.append(f"{entry.slug}: rubric {dict(error.context)}: {error}")
    review = record.get("rubric", {}).get("human_review")
    if isinstance(review, dict) and review.get("render_fingerprint") != now["render_fingerprint"]:
        errors.append(f"{entry.slug}: the art changed after the human review; review it again")
    return errors


def check(entries: Sequence[Entry]) -> list[str]:
    """Audit the whole corpus: the five categories once each, then every example."""
    errors = []
    categories = sorted(str(entry.record.get("category")) for entry in entries)
    if categories != sorted(CATEGORIES):
        errors.append(f"corpus categories are {categories}, expected {sorted(CATEGORIES)}")
    for entry in entries:
        errors += audit(entry)
    return errors


def main(argv: Sequence[str] | None = None, root: Path = CORPUS_DIR) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("command", choices=("check", "facts"))
    args = parser.parse_args(argv)
    entries = load_entries(root)
    if args.command == "facts":
        print(json.dumps({e.slug: facts(e) for e in entries}, indent=2, sort_keys=True))
        return 0
    errors = check(entries)
    for error in errors:
        print(error)
    if not errors:
        pending = sum(1 for e in entries if e.record["rubric"]["human_review"] is None)
        print(f"Corpus OK: {len(entries)} examples, {pending} pending human review")
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
