"""Benchmark corpus of MOANA.md section 22, built programmatically (MOANA-031).

* ``static``: a 128x128 strict document with exactly 32 layers and 500 ``rect``
  operations (20 layers of 16 rects and 12 of 15), 16 opaque palette colours.
* ``animation``: the same base plus one animation of 16 frames of equal complexity.
  Every frame carries the same number of overrides (32 ``translate`` and 8
  ``set_color``) with a different shift and colour, so each frame is a real and
  different render of 32 layers and 500 rects.
* ``corpus/<slug>``: the reviewed examples of ``examples/corpus`` (MOANA-027), smaller
  real-art cases that are timed as they are.

The generator is pure integer arithmetic; it never calls the engine. Documents are
returned as JSON trees; the runner validates them through :mod:`moana.schema`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[2]
EXAMPLES: Final = ROOT / "examples" / "corpus"

CANVAS: Final = 128
LAYERS: Final = 32
RECTS: Final = 500
COLORS: Final = 16
FRAMES: Final = 16
FRAME_DURATION_MS: Final = 100
TRANSLATES_PER_FRAME: Final = LAYERS
RECOLOURS_PER_FRAME: Final = 8
MAX_SHIFT: Final = 4
MARGIN: Final = MAX_SHIFT
"""Rects keep this distance from the edges, so no override moves one off the canvas."""
ANIMATION_ID: Final = "bench_loop"

STATIC: Final = "static"
ANIMATION: Final = "animation"
STATIC_EXAMPLES: Final = ("adventurer", "chest", "frog", "stone-tile")
ANIMATED_EXAMPLES: Final = {"adventurer-walk": "walk"}

Json = dict[str, Any]
"""The one JSON-object alias of the benchmark package (reports and documents)."""


def _colour(index: int) -> str:
    """Opaque, distinct colours spread over RGB (strict profile: alpha FF)."""
    red = (index * 53 + 17) % 256
    green = (index * 97 + 41) % 256
    blue = (index * 151 + 89) % 256
    return f"#{red:02X}{green:02X}{blue:02X}FF"


def rects_per_layer() -> list[int]:
    """500 rects over 32 layers: the first 20 layers get 16, the remaining 12 get 15."""
    base, extra = divmod(RECTS, LAYERS)
    return [base + 1 if layer < extra else base for layer in range(LAYERS)]


def _rect(index: int, color: int) -> Json:
    """Rect ``index``: a 4..31 pixel side, ``MARGIN`` pixels away from every edge."""
    width = 4 + (index * 7) % 28
    height = 4 + (index * 11) % 28
    x0 = MARGIN + (index * 37) % (CANVAS - width - 2 * MARGIN)
    y0 = MARGIN + (index * 53) % (CANVAS - height - 2 * MARGIN)
    return {
        "id": f"r{index:03d}",
        "type": "rect",
        "box": [x0, y0, x0 + width, y0 + height],
        "color": f"c{color:02d}",
    }


def static_document(*, recolour: int | None = None) -> Json:
    """The 32-layer/500-rect document; ``recolour`` changes the colour of that rect only."""
    layers: list[Json] = []
    index = 0
    for layer, count in enumerate(rects_per_layer()):
        operations: list[Json] = []
        for _ in range(count):
            color = index % COLORS
            if index == recolour:
                color = (color + 1) % COLORS
            operations.append(_rect(index, color))
            index += 1
        layers.append(
            {"id": f"layer{layer:02d}", "name": f"Capa {layer}", "operations": operations}
        )
    return {
        "schema_version": "1.0",
        "id": "bench_static",
        "revision": 0,
        "seed": 0,
        "canvas": {"width": CANVAS, "height": CANVAS, "profile": "strict"},
        "palette": {
            "id": "bench_palette",
            "colors": [{"id": f"c{i:02d}", "rgba": _colour(i)} for i in range(COLORS)],
        },
        "layers": layers,
    }


def first_rect_ids() -> list[str]:
    """ID of the first rect of every layer (the targets of the ``translate`` overrides)."""
    ids: list[str] = []
    index = 0
    for count in rects_per_layer():
        ids.append(f"r{index:03d}")
        index += count
    return ids


def _frame(frame: int) -> Json:
    shift = frame % MAX_SHIFT + 1
    dx, dy = (shift, 0) if frame % 2 == 0 else (0, -shift)
    overrides: list[Json] = [
        {"type": "translate", "target_id": target, "dx": dx, "dy": dy}
        for target in first_rect_ids()
    ]
    overrides += [
        {
            "type": "set_color",
            "target_id": f"r{(frame * 31 + slot * 61) % RECTS:03d}",
            "color": f"c{(frame + slot * 3) % COLORS:02d}",
        }
        for slot in range(RECOLOURS_PER_FRAME)
    ]
    return {"id": f"f{frame:02d}", "duration_ms": FRAME_DURATION_MS, "overrides": overrides}


def animation_document() -> Json:
    """The static base with one 16-frame animation (``bench_loop``)."""
    document = static_document()
    document["id"] = "bench_animation"
    document["animations"] = [
        {
            "id": ANIMATION_ID,
            "loop_count": 0,
            "pivot": [CANVAS // 2, CANVAS],
            "frames": [_frame(frame) for frame in range(FRAMES)],
        }
    ]
    return document


def example_document(slug: str) -> Json:
    """One reviewed MOANA-027 example as stored in the repository."""
    path = EXAMPLES / slug / f"{slug}.moana.json"
    value: Json = json.loads(path.read_text(encoding="utf-8"))
    return value


def case_names() -> tuple[str, ...]:
    """Every case of the corpus, in report order."""
    examples = (*STATIC_EXAMPLES, *ANIMATED_EXAMPLES)
    return (STATIC, ANIMATION, *(f"corpus/{slug}" for slug in examples))


def case_document(name: str) -> Json:
    """The JSON tree of case ``name``."""
    if name == STATIC:
        return static_document()
    if name == ANIMATION:
        return animation_document()
    slug = name.removeprefix("corpus/")
    if name.startswith("corpus/") and slug in (*STATIC_EXAMPLES, *ANIMATED_EXAMPLES):
        return example_document(slug)
    raise ValueError(f"unknown benchmark case: {name}")


def case_animation(name: str) -> str | None:
    """Animation rendered by case ``name`` (``None``: a static render of the base)."""
    if name == ANIMATION:
        return ANIMATION_ID
    return ANIMATED_EXAMPLES.get(name.removeprefix("corpus/"))


def canonical_bytes(document: Json) -> bytes:
    """Sorted keys, no spaces, UTF-8: the bytes parsed and digested by the benchmark."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def corpus_digest(names: tuple[str, ...] | None = None) -> str:
    """``sha256:`` over the names and canonical bytes of every case, in order."""
    digest = hashlib.sha256()
    for name in case_names() if names is None else names:
        data = canonical_bytes(case_document(name))
        digest.update(f"{name}\n{len(data)}\n".encode())
        digest.update(data)
    return "sha256:" + digest.hexdigest()
