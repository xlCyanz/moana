"""MOANA-027: the reviewed previews of the art corpus are exact goldens (MOANA.md §21).

Every example of ``examples/corpus/`` has its previews under ``previews/``: the
render at 1x (still image or the frames side by side), the same at 4x by
nearest-neighbour, the silhouette (alpha > 0 in black on white) and the cluster
view (8-connected clusters of equal colour, singletons in magenta) at 4x, and for
the tile its 3x3 repetition at 4x. They are built in memory by ``scripts/corpus.py``
and compared through the visual harness: pixels, never PNG bytes. A source change
updates them only with the reviewed local flow of ``tests/visual/README.md``
(``MOANA_UPDATE_GOLDENS=1``; refused in CI).
"""

from __future__ import annotations

import numpy as np
import pytest

from moana.api import evaluate_quality
from scripts.corpus import cluster_labels, load_entries, preview_path, scale, sheet, views

from .harness import assert_matches_golden

pytestmark = pytest.mark.visual

ENTRIES = {entry.slug: entry for entry in load_entries()}
CASES = sorted((slug, view) for slug, entry in ENTRIES.items() for view in views(entry))


@pytest.mark.parametrize(("slug", "view"), CASES)
def test_corpus_preview_matches_its_golden(slug: str, view: str) -> None:
    entry = ENTRIES[slug]
    assert_matches_golden(
        views(entry)[view],
        preview_path(entry, view),
        name=f"corpus__{slug}__{view}",
        source=f"examples/corpus/{slug}/{slug}.moana.json",
    )


def test_scale_is_nearest_neighbour() -> None:
    image = np.arange(2 * 2 * 4, dtype=np.uint8).reshape(2, 2, 4)
    big = scale(image, 3)
    assert big.shape == (6, 6, 4)
    assert (big[0:3, 3:6] == image[0, 1]).all()
    assert (big[3:6, 0:3] == image[1, 0]).all()


def test_cluster_labels_use_eight_connectivity() -> None:
    red = (255, 0, 0, 255)
    image = np.zeros((3, 3, 4), dtype=np.uint8)
    for x, y in ((0, 0), (1, 1), (2, 2)):  # one diagonal cluster
        image[y, x] = red
    image[0, 2] = (0, 0, 255, 255)  # a lone singleton
    labels, areas = cluster_labels(image)
    assert sorted(areas) == [1, 3]
    assert labels[0, 0] == labels[2, 2] != labels[0, 2]
    assert labels[1, 0] == -1


@pytest.mark.parametrize(
    "slug", sorted(slug for slug, e in ENTRIES.items() if e.animation_id is None)
)
def test_cluster_view_singletons_agree_with_quality_metrics(slug: str) -> None:
    entry = ENTRIES[slug]
    _, areas = cluster_labels(sheet(entry))
    report = evaluate_quality(entry.document)
    assert report.metrics is not None
    assert areas.count(1) == report.metrics.singletons
    assert len(areas) == report.metrics.clusters
