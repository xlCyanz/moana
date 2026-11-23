"""Create, preview, recolor by ID and verify the tutorial potion with ``moanart.api``.

Python version of the CLI flow in ``docs/guides/ai-workflows.md`` (MOANA-033). Run it
from the repository root with an output directory of your choice::

    python examples/tutorial/potion_flow.py artifacts/tutorial

It writes the 1x master and 4x nearest-neighbour previews before and after the edit
plus the new revision as ``potion-r1-api.moanart.json``, and prints one JSON summary.
It exits with status 1 if a pixel outside the edited region changed, and with the
CLI exit code of a MoanArt error (printed as ``{"error": CODE, ...}``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from moanart import api
from moanart.core.errors import MoanArtError
from moanart.project import save_document

TUTORIAL = Path(__file__).parent
SOURCE = TUTORIAL / "potion.moanart.json"
REGION_ID = "potion_liquid"


def changed_pixels(before: api.RenderResult, after: api.RenderResult) -> list[tuple[int, int]]:
    """Coordinates ``(x, y)`` whose RGBA differs between two renders of one canvas."""
    if (before.width, before.height) != (after.width, after.height):
        raise ValueError("the renders have different dimensions")
    width = before.width
    return [
        (index % width, index // width)
        for index in range(before.width * before.height)
        if before.rgba[4 * index : 4 * index + 4] != after.rgba[4 * index : 4 * index + 4]
    ]


def region_box(document: api.Document, region_id: str) -> tuple[int, int, int, int]:
    """Half-open box of a region whose mask is a ``rect``, read from the JSON source."""
    mask_id = api.resolve_region(document, region_id).mask_id
    tree = json.loads(SOURCE.read_text(encoding="utf-8"))
    mask = next((mask for mask in tree["masks"] if mask["id"] == mask_id), None)
    if mask is None or mask["type"] != "rect":
        raise ValueError(f"region {region_id} needs a rect mask in the source")
    x0, y0, x1, y1 = (int(value) for value in mask["box"])
    return x0, y0, x1, y1


def run(output: Path) -> int:
    """The tutorial flow; returns 1 if a pixel outside the region changed."""
    output.mkdir(parents=True, exist_ok=True)

    # 1. Load (validates and normalises) and inspect without drawing.
    document = api.load_document(TUTORIAL / "potion.moanart.json")
    report = api.inspect_document(document)

    # 2. Preview: the 1x master and a 4x nearest-neighbour enlargement.
    before = api.render(document)
    api.export_png(before, output / "potion-api-1x.png", overwrite=True)
    api.export_png(before, output / "potion-api-4x.png", scale=4, overwrite=True)

    # 3. Recolor by ID: the batch names revision 0 and its snapshot digest.
    result = api.edit_document(document, TUTORIAL / "potion-recolor.edit.json")
    after = api.render(result.document)
    api.export_png(after, output / "potion-api-r1-4x.png", scale=4, overwrite=True)

    # 4. Keep the editable source: the document is the artefact, the PNG is derived.
    save_document(result.document, output / "potion-r1-api.moanart.json", overwrite=True)

    # 5. Verify that only the region of the edited operation changed.
    x0, y0, x1, y1 = region_box(result.document, REGION_ID)
    changed = changed_pixels(before, after)
    outside = [(x, y) for x, y in changed if not (x0 <= x < x1 and y0 <= y < y1)]
    summary = {
        "affected_ids": list(result.affected_ids),
        "changed_pixels": len(changed),
        "changed_outside_region": len(outside),
        "region_box": [x0, y0, x1, y1],
        "revision": [report.revision, result.revision],
        "snapshot_digest": result.snapshot,
    }
    print(json.dumps(summary, sort_keys=True))
    return 1 if outside else 0


def main(arguments: list[str]) -> int:
    """Run the flow into ``arguments[0]`` (default ``artifacts/tutorial``).

    A MoanArt error is printed as one JSON object and its CLI exit code is returned.
    """
    try:
        return run(Path(arguments[0] if arguments else "artifacts/tutorial"))
    except MoanArtError as error:
        failure = {"error": error.code, "context": dict(error.context), "message": error.message}
        print(json.dumps(failure, sort_keys=True, default=str))
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
