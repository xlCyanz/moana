"""Cross-process and cross-platform determinism evidence (MOANA-029, MOANA.md section 14).

Three subcommands:

``probe``
    Render every case of the fixed corpus (``tests/fixtures/determinism/corpus.json``),
    export it as PNG in memory and through an atomic file write, decode it again with
    Pillow and print one JSON object. Used by ``report`` in fresh interpreters.
``report``
    Run ``probe`` in fresh subprocesses with several ``PYTHONHASHSEED`` values and key
    orders of the corpus JSON, check that every run agrees (PNG bytes included: same
    codec environment), compare the decoded pixels with the reviewed RGBA manifest
    (``expected.json``) and write ``determinism-report.json`` plus expected/actual/diff
    PNGs for every divergent case. It records backend, lock digest, codec and platform.
``compare``
    Standard library only: read the reports of every CI job and separate pixel
    divergences (contract failure) from codec differences (PNG bytes may differ
    between Pillow/zlib builds, ADR-019). It never writes the expected manifest.

The expected manifest is reviewed data; nothing in this module rewrites it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
FIXTURES: Final = ROOT / "tests" / "fixtures" / "determinism"
CORPUS_PATH: Final = FIXTURES / "corpus.json"
EXPECTED_PATH: Final = FIXTURES / "expected.json"
LOCK_PATH: Final = ROOT / "uv.lock"

CORPUS_FORMAT: Final = "moana-determinism-corpus/1"
EXPECTED_FORMAT: Final = "moana-determinism-expected/1"
REPORT_FORMAT: Final = "moana-determinism-report/1"
SUMMARY_FORMAT: Final = "moana-determinism-summary/1"
REPORT_NAME: Final = "determinism-report.json"

HASH_SEEDS: Final = ("0", "1", "4242", "random")
VARIANTS: Final = ("canonical", "reversed", "compact")
"""JSON serialisations of the corpus fed to the probes (key order and whitespace)."""

STDERR_TAIL: Final = 2000
"""Characters of a failing probe's stderr kept in the report."""

DIFF_CHANGED: Final = (255, 0, 255, 255)
DIFF_SAME: Final = (48, 48, 48, 255)

Json = dict[str, Any]


# --- Corpus and expected manifest ------------------------------------------------------


def read_json(path: Path) -> Json:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: a JSON object is required")
    return value


def load_corpus(path: Path = CORPUS_PATH) -> Json:
    corpus = read_json(path)
    if corpus.get("format") != CORPUS_FORMAT or not isinstance(corpus.get("cases"), dict):
        raise ValueError(f"{path.name}: unsupported corpus format")
    return corpus


def load_expected(path: Path = EXPECTED_PATH) -> Json:
    expected = read_json(path)
    if expected.get("format") != EXPECTED_FORMAT or not isinstance(expected.get("cases"), dict):
        raise ValueError(f"{path.name}: unsupported expected manifest format")
    return expected


def parse_hex(text: str) -> tuple[int, int, int, int]:
    if len(text) != 9 or text[0] != "#":
        raise ValueError(f"colour must be #RRGGBBAA: {text!r}")
    value = bytes.fromhex(text[1:])
    return value[0], value[1], value[2], value[3]


def rows_to_bytes(rows: Sequence[Sequence[str]]) -> bytes:
    """Row-major straight RGBA of a manifest grid of ``#RRGGBBAA`` strings."""
    return b"".join(bytes(parse_hex(cell)) for row in rows for cell in row)


def bytes_to_rows(width: int, height: int, rgba: bytes) -> list[list[str]]:
    if len(rgba) != width * height * 4:
        raise ValueError("RGBA size does not match the dimensions")
    return [
        [
            "#" + rgba[(y * width + x) * 4 : (y * width + x) * 4 + 4].hex().upper()
            for x in range(width)
        ]
        for y in range(height)
    ]


def digest_of(width: int, height: int, rgba: bytes) -> str:
    """Visual digest of MOANA.md section 14, recomputed with the standard library."""
    data = width.to_bytes(4, "big") + height.to_bytes(4, "big") + rgba
    return "sha256:" + hashlib.sha256(data).hexdigest()


def reordered(node: Any) -> Any:
    """Same JSON value with every object's keys reversed (arrays preserved)."""
    if isinstance(node, dict):
        return {key: reordered(node[key]) for key in reversed(list(node))}
    if isinstance(node, list):
        return [reordered(item) for item in node]
    return node


def serialise(value: Any, variant: str) -> bytes:
    if variant == "canonical":
        return json.dumps(value, ensure_ascii=False).encode("utf-8")
    if variant == "reversed":
        return json.dumps(reordered(value), ensure_ascii=True, indent=3).encode("utf-8")
    if variant == "compact":
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    raise ValueError(f"unknown variant: {variant}")


# --- Probe (needs the engine; imports are local so ``compare`` stays stdlib-only) ----


@dataclass(frozen=True, slots=True)
class Frame:
    """A rendered frame (satisfies ``moana.export.RasterFrame``)."""

    width: int
    height: int
    rgba: bytes


def _mask(spec: Mapping[str, Any], width: int, height: int) -> Any:
    from moana.core import Box, Dimensions, Point
    from moana.geometry import (
        rasterize_ellipse,
        rasterize_line,
        rasterize_pixel,
        rasterize_polygon,
        rasterize_rect,
    )

    dimensions = Dimensions(width, height)
    kind = spec["type"]
    if kind == "pixel":
        return rasterize_pixel(Point(*spec["at"]), dimensions)
    if kind == "line":
        return rasterize_line(Point(*spec["start"]), Point(*spec["end"]), dimensions)
    if kind == "rect":
        return rasterize_rect(Box(*spec["box"]), dimensions)
    if kind == "ellipse":
        return rasterize_ellipse(Box(*spec["box"]), dimensions)
    if kind == "polygon":
        return rasterize_polygon([Point(*point) for point in spec["points"]], dimensions)
    raise ValueError(f"unknown fill type: {kind}")


def _node(spec: Mapping[str, Any], width: int, height: int) -> Any:
    from moana.layers import Fill, Group, Layer
    from moana.palette import Rgba

    visible = bool(spec.get("visible", True))
    opacity = int(spec.get("opacity", 255))
    if spec["kind"] == "group":
        children = tuple(_node(child, width, height) for child in spec["children"])
        return Group(spec["id"], spec["id"], children, visible=visible, opacity=opacity)
    if spec["kind"] == "layer":
        fills = tuple(
            Fill(_mask(fill, width, height), Rgba.parse(fill["rgba"])) for fill in spec["fills"]
        )
        return Layer(spec["id"], spec["id"], fills, visible=visible, opacity=opacity)
    raise ValueError(f"unknown node kind: {spec['kind']}")


def render_case(case: Mapping[str, Any], variant: str = "canonical") -> tuple[Frame, list[str]]:
    """Render one corpus case; returns the frame and its warning pointers."""
    if case["kind"] == "document":
        from moana.render import render
        from moana.schema import validate_document

        result = render(validate_document(serialise(case["document"], variant)))
        warnings = [warning.json_pointer for warning in result.warnings]
        return Frame(result.width, result.height, result.rgba), warnings
    if case["kind"] == "tree":
        from moana.core import Dimensions, RenderLimits
        from moana.layers import LayerTree, compose

        spec = json.loads(serialise(case["tree"], variant).decode("utf-8"))
        width, height = int(spec["width"]), int(spec["height"])
        children = tuple(_node(child, width, height) for child in spec["children"])
        tree = LayerTree(Dimensions(width, height), children, profile=spec["profile"])
        canvas = compose(tree, limits=RenderLimits())
        return Frame(canvas.width, canvas.height, canvas.to_bytes()), []
    raise ValueError(f"unknown case kind: {case['kind']}")


def decode_png(data: bytes, mode: str) -> tuple[int, int, bytes]:
    """Decode PNG bytes with plain Pillow (independent of the exporter's own check).

    ``mode`` is the Pillow mode the export promises (``RGBA`` master, ``P`` indexed);
    any other mode is an error instead of a silent conversion.
    """
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
            raise ValueError("expected a single-frame PNG")
        if image.mode != mode:
            raise ValueError(f"expected PNG mode {mode}, found {image.mode}")
        rgba = image.convert("RGBA") if mode != "RGBA" else image
        return rgba.width, rgba.height, rgba.tobytes("raw", "RGBA")


def _png_entry(data: bytes, mode: str = "RGBA") -> Json:
    width, height, rgba = decode_png(data, mode)
    return {
        "decoded_digest": digest_of(width, height, rgba),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def probe_case(case: Mapping[str, Any], variant: str, scratch: Path) -> Json:
    from moana.export import encode_png, export_png

    frame, warnings = render_case(case, variant)
    entry: Json = {
        "width": frame.width,
        "height": frame.height,
        "digest": digest_of(frame.width, frame.height, frame.rgba),
        "rows": bytes_to_rows(frame.width, frame.height, frame.rgba),
        "warnings": warnings,
        "png": {"rgba": _png_entry(encode_png(frame).data)},
    }
    target = scratch / f"{case['name']}.png"
    manifest = export_png(frame, target)
    file_entry = _png_entry(target.read_bytes())
    file_entry["manifest_pixel_digest"] = manifest.pixel_digest
    file_entry["manifest_sha256"] = manifest.file_sha256
    entry["png"]["file"] = file_entry
    document: Json = case["document"] if case["kind"] == "document" else {}
    if document and document["canvas"]["profile"] == "strict":
        from moana.palette import Palette

        palette = Palette.from_mapping(document["palette"], profile="strict")
        indexed = encode_png(frame, mode="indexed", palette=palette)
        entry["png"]["indexed"] = _png_entry(indexed.data, "P")
    return entry


def probe(variant: str = "canonical", corpus_path: Path = CORPUS_PATH) -> Json:
    corpus = load_corpus(corpus_path)
    with tempfile.TemporaryDirectory(prefix="moana-determinism-") as scratch:
        return {
            name: probe_case({**case, "name": name}, variant, Path(scratch))
            for name, case in sorted(corpus["cases"].items())
        }


# --- Environment ---------------------------------------------------------------------


def environment() -> Json:
    """Facts that identify where a report was produced (no paths, no timestamps)."""
    import numpy
    import PIL
    from PIL import features

    import moana
    from moana.render import ESTIMATOR_VERSION, RENDERER_BACKEND, RENDERER_VERSION

    lock = hashlib.sha256(LOCK_PATH.read_bytes()).hexdigest() if LOCK_PATH.is_file() else None
    return {
        "platform": sys.platform,
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "moana": moana.__version__,
        "renderer_version": RENDERER_VERSION,
        "renderer_backend": RENDERER_BACKEND,
        "estimator_version": ESTIMATOR_VERSION,
        "lock_sha256": lock,
        "numpy": numpy.__version__,
        "pillow": PIL.__version__,
        "zlib": features.version("zlib"),
        "byteorder": sys.byteorder,
    }


def codec_key(env: Mapping[str, Any]) -> str:
    """The codec environment in which PNG bytes are promised equal (ADR-019)."""
    return f"pillow {env.get('pillow')} / zlib {env.get('zlib')}"


# --- Report --------------------------------------------------------------------------


class ProbeFailure(RuntimeError):
    """A probe interpreter failed; carries what is needed to reproduce it."""

    def __init__(self, hash_seed: str, variant: str, detail: str) -> None:
        super().__init__(f"probe failed (seed {hash_seed}, {variant}): {detail}")
        self.hash_seed = hash_seed
        self.variant = variant
        self.detail = detail


def run_probe(hash_seed: str, variant: str, corpus_path: Path = CORPUS_PATH) -> Json:
    """``probe`` in a fresh interpreter with ``PYTHONHASHSEED=hash_seed``."""
    env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONIOENCODING": "utf-8"}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.determinism",
            "probe",
            "--variant",
            variant,
            "--corpus",
            str(corpus_path),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise ProbeFailure(hash_seed, variant, stderr[-STDERR_TAIL:])
    try:
        value = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeFailure(hash_seed, variant, f"invalid probe output: {error}") from error
    if not isinstance(value, dict):
        raise ProbeFailure(hash_seed, variant, "probe output must be a JSON object")
    return value


def _bbox_and_count(
    width: int, height: int, expected: bytes, actual: bytes
) -> tuple[int, dict[str, int] | None]:
    count, xs, ys = 0, [], []
    for y in range(height):
        for x in range(width):
            offset = (y * width + x) * 4
            if expected[offset : offset + 4] != actual[offset : offset + 4]:
                count += 1
                xs.append(x)
                ys.append(y)
    if not count:
        return 0, None
    return count, {"x0": min(xs), "y0": min(ys), "x1": max(xs) + 1, "y1": max(ys) + 1}


def write_diagnostics(folder: Path, expected: Mapping[str, Any], actual: Mapping[str, Any]) -> Json:
    """expected/actual/diff PNGs of one divergent case (MOANA.md section 21)."""
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    exp_size = (int(expected["width"]), int(expected["height"]))
    act_size = (int(actual["width"]), int(actual["height"]))
    exp_rgba, act_rgba = rows_to_bytes(expected["rows"]), rows_to_bytes(actual["rows"])
    for name, size, data in (("expected", exp_size, exp_rgba), ("actual", act_size, act_rgba)):
        Image.frombytes("RGBA", size, data).save(folder / f"{name}.png", "PNG")
        files[name] = f"{name}.png"
    result: Json = {"dimensions_match": exp_size == act_size, "files": files}
    if exp_size == act_size:
        count, bbox = _bbox_and_count(*exp_size, exp_rgba, act_rgba)
        diff = bytearray()
        for offset in range(0, len(exp_rgba), 4):
            same = exp_rgba[offset : offset + 4] == act_rgba[offset : offset + 4]
            diff.extend(DIFF_SAME if same else DIFF_CHANGED)
        Image.frombytes("RGBA", exp_size, bytes(diff)).save(folder / "diff.png", "PNG")
        files["diff"] = "diff.png"
        result.update({"differing_pixels": count, "bbox": bbox})
    return result


def _strip(entry: Mapping[str, Any]) -> Json:
    """The comparable part of a probe entry."""
    return {key: value for key, value in entry.items() if key != "rows"}


def build_report(
    runs: Sequence[tuple[str, str, Json]], expected: Json, env: Json, output: Path
) -> Json:
    """Check runs against each other and the reviewed manifest; write diagnostics."""
    errors: list[str] = []
    cases: Json = {}
    reference = runs[0][2]
    if any(set(result) != set(expected["cases"]) for _, _, result in runs):
        errors.append("corpus cases differ from the expected manifest")
    for name in sorted(expected["cases"]):
        oracle = expected["cases"][name]
        if any(name not in result for _, _, result in runs):
            errors.append(f"{name}: missing from a probe")
            continue
        observed: list[Json] = [result[name] for _, _, result in runs]
        first = reference[name]
        consistent = all(_strip(item) == _strip(first) for item in observed)
        decoded = sorted(
            {
                png["decoded_digest"]
                for item in observed
                for png in item["png"].values()
                if isinstance(png, dict)
            }
            | {item["digest"] for item in observed}
        )
        pixel_match = decoded == [oracle["digest"]] and all(
            item["warnings"] == oracle["warnings"] for item in observed
        )
        file_entry = first["png"]["file"]
        export_consistent = (
            file_entry["sha256"] == first["png"]["rgba"]["sha256"]
            and file_entry["manifest_sha256"] == "sha256:" + file_entry["sha256"]
            and file_entry["manifest_pixel_digest"] == first["digest"]
        )
        entry: Json = {
            "expected_digest": oracle["digest"],
            "digest": first["digest"],
            "decoded_digests": decoded,
            "warnings": first["warnings"],
            "png_sha256": {mode: png["sha256"] for mode, png in sorted(first["png"].items())},
            "consistent_across_runs": consistent,
            "export_consistent": export_consistent,
            "pixel_match": pixel_match,
            "diagnostics": None,
        }
        if not consistent:
            errors.append(f"{name}: runs disagree (hash seed, key order or codec state)")
        if not export_consistent:
            errors.append(f"{name}: file export differs from the in-memory encoding")
        if not pixel_match:
            errors.append(f"{name}: pixels differ from the reviewed RGBA manifest")
            folder = output / "diagnostics" / name
            entry["diagnostics"] = write_diagnostics(folder, oracle, first)
            entry["diagnostics"]["folder"] = f"diagnostics/{name}"
            entry["actual_rows"] = first["rows"]
        cases[name] = entry
    return {
        "format": REPORT_FORMAT,
        "status": "divergent" if errors else "ok",
        "environment": env,
        "codec": codec_key(env),
        "runs": [{"hash_seed": seed, "variant": variant} for seed, variant, _ in runs],
        "cases": cases,
        "errors": errors,
    }


def error_report(failure: ProbeFailure, env: Json) -> Json:
    """Report of a job whose probe could not run: still uploaded as evidence (AC2)."""
    return {
        "format": REPORT_FORMAT,
        "status": "error",
        "environment": env,
        "codec": codec_key(env),
        "runs": [{"hash_seed": failure.hash_seed, "variant": failure.variant}],
        "failure": {
            "hash_seed": failure.hash_seed,
            "variant": failure.variant,
            "stderr_tail": failure.detail,
        },
        "cases": {},
        "errors": [str(failure)],
    }


def _write_report(output: Path, result: Json) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / REPORT_NAME).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def report(
    output: Path,
    *,
    hash_seeds: Iterable[str] = HASH_SEEDS,
    variants: Iterable[str] = VARIANTS,
    corpus_path: Path = CORPUS_PATH,
    expected_path: Path = EXPECTED_PATH,
) -> Json:
    """Run the probes and write ``determinism-report.json`` (also when a probe fails)."""
    expected = load_expected(expected_path)
    try:
        runs = [
            (seed, variant, run_probe(seed, variant, corpus_path))
            for seed in hash_seeds
            for variant in variants
        ]
    except ProbeFailure as failure:
        result = error_report(failure, environment())
    else:
        output.mkdir(parents=True, exist_ok=True)
        result = build_report(runs, expected, environment(), output)
    _write_report(output, result)
    return result


# --- Compare (standard library only) -------------------------------------------------


def _source(path: Path) -> str:
    """CI artifact a report came from (``<artifact>/determinism/determinism-report.json``)."""
    folder = path.parent
    return folder.parent.name if folder.name == "determinism" else folder.name


def _label(report_value: Mapping[str, Any], path: Path) -> str:
    """Platform of a report plus the CI artifact it came from."""
    env = report_value.get("environment", {})
    return f"{env.get('system')}-{env.get('machine')}/py{env.get('python')} ({_source(path)})"


def _python_minor(env: Mapping[str, Any]) -> str:
    return ".".join(str(env.get("python")).split(".")[:2])


def _check_coverage(
    reports: Sequence[tuple[Path, Json]], expected_reports: int, platforms: Iterable[str]
) -> list[str]:
    """Count, uniqueness of (system, Python minor) and required operating systems."""
    errors: list[str] = []
    if len(reports) != expected_reports:
        errors.append(f"expected {expected_reports} reports, found {len(reports)}")
    pairs: dict[tuple[str, str], list[str]] = {}
    for path, value in reports:
        env = value.get("environment", {})
        pairs.setdefault((str(env.get("system")), _python_minor(env)), []).append(_source(path))
    for (system, python), sources in sorted(pairs.items()):
        if len(sources) > 1:
            errors.append(f"duplicate platform {system}/py{python}: {sorted(sources)}")
    missing = sorted(set(platforms) - {system for system, _ in pairs})
    if missing:
        errors.append(f"missing platforms: {missing}")
    return errors


def _codec_findings(
    name: str, png: Mapping[str, Mapping[str, Mapping[str, list[str]]]], pixel_ok: bool
) -> tuple[list[str], list[str]]:
    """Warnings (bytes differ inside one codec build) and notes (across codec builds)."""
    warnings: list[str] = []
    notes: list[str] = []
    pixels = "agree" if pixel_ok else "DIVERGE"
    for mode, by_codec in sorted(png.items()):
        for codec, groups in sorted(by_codec.items()):
            if len(groups) > 1:
                who = sorted(label for labels in groups.values() for label in labels)
                warnings.append(
                    f"{name}/{mode}: PNG bytes differ within {codec} ({len(groups)} variants: "
                    f"{who}); decoded pixels {pixels}"
                )
        variants = {sha for groups in by_codec.values() for sha in groups}
        if len(by_codec) > 1 and len(variants) > 1:
            notes.append(
                f"{name}/{mode}: PNG bytes differ between codec builds "
                f"({len(variants)} variants); decoded pixels {pixels}"
            )
    return warnings, notes


def compare(
    reports: Sequence[tuple[Path, Json]],
    expected: Json,
    expected_reports: int,
    expected_platforms: Iterable[str] = (),
) -> Json:
    """Cross-job table: pixel divergences fail, codec differences are informational.

    Within one codec build (same Pillow and zlib) differing PNG bytes are a warning,
    since ADR-019 promises equal bytes there; across builds they are only listed.
    """
    errors = _check_coverage(reports, expected_reports, expected_platforms)
    warnings: list[str] = []
    notes: list[str] = []
    labels = [_label(value, path) for path, value in reports]
    for (_, value), label in zip(reports, labels, strict=True):
        if value.get("format") != REPORT_FORMAT:
            errors.append(f"{label}: unsupported report format")
        elif value.get("status") != "ok":
            errors.append(f"{label}: report status {value.get('status')}")
    for key in ("lock_sha256", "renderer_version", "renderer_backend"):
        seen = {str(value.get("environment", {}).get(key)) for _, value in reports}
        if len(seen) > 1:
            errors.append(f"reports disagree on {key}: {sorted(seen)}")
    table: Json = {}
    for name in sorted(expected["cases"]):
        oracle = expected["cases"][name]["digest"]
        digests: dict[str, list[str]] = {}
        png: dict[str, dict[str, dict[str, list[str]]]] = {}
        for (_, value), label in zip(reports, labels, strict=True):
            case = value.get("cases", {}).get(name)
            if not isinstance(case, dict):
                errors.append(f"{label}: case {name} missing")
                continue
            for digest in [case.get("digest"), *case.get("decoded_digests", [])]:
                digests.setdefault(str(digest), []).append(label)
            codec = str(value.get("codec"))
            for mode, sha in case.get("png_sha256", {}).items():
                by_codec = png.setdefault(mode, {}).setdefault(codec, {})
                by_codec.setdefault(str(sha), []).append(label)
        pixel_ok = set(digests) <= {oracle}
        if not pixel_ok:
            wrong = {
                digest: sorted(set(who)) for digest, who in digests.items() if digest != oracle
            }
            errors.append(f"{name}: pixel divergence {wrong}")
        case_warnings, case_notes = _codec_findings(name, png, pixel_ok)
        warnings += case_warnings
        notes += case_notes
        table[name] = {
            "expected_digest": oracle,
            "pixel_ok": pixel_ok,
            "png_variants": {
                mode: len({sha for groups in by_codec.values() for sha in groups})
                for mode, by_codec in sorted(png.items())
            },
        }
    codecs: dict[str, list[str]] = {}
    for (_, value), label in zip(reports, labels, strict=True):
        codecs.setdefault(str(value.get("codec")), []).append(label)
    return {
        "format": SUMMARY_FORMAT,
        "status": "divergent" if errors else "ok",
        "reports": sorted(labels),
        "artifacts": sorted({_source(path) for path, _ in reports}),
        "codecs": {key: sorted(who) for key, who in sorted(codecs.items())},
        "cases": table,
        "errors": errors,
        "codec_warnings": warnings,
        "codec_notes": notes,
    }


def find_reports(folder: Path) -> list[tuple[Path, Json]]:
    return [(path, read_json(path)) for path in sorted(folder.rglob(REPORT_NAME))]


def summary_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        f"## Determinismo entre plataformas: {summary['status']}",
        "",
        f"Informes: {len(summary['reports'])}",
        "",
        "Artefactos: " + (", ".join(summary["artifacts"]) or "ninguno"),
        "",
        "| Caso | Digest esperado | Píxeles | Variantes de bytes PNG |",
        "| --- | --- | --- | --- |",
    ]
    for name, case in summary["cases"].items():
        variants = ", ".join(f"{mode}: {count}" for mode, count in case["png_variants"].items())
        status = "iguales" if case["pixel_ok"] else "**DIVERGEN**"
        lines.append(f"| {name} | `{case['expected_digest'][:19]}…` | {status} | {variants} |")
    lines += ["", "Codecs:"] + [
        f"- {key}: {len(who)} informes" for key, who in summary["codecs"].items()
    ]
    if summary["errors"]:
        lines += ["", "Errores:"] + [f"- {error}" for error in summary["errors"]]
    if summary["codec_warnings"]:
        lines += ["", "Avisos: bytes PNG distintos con el mismo codec:"]
        lines += [f"- {warning}" for warning in summary["codec_warnings"]]
    if summary["codec_notes"]:
        lines += ["", "Diferencias de codec (informativas):"]
        lines += [f"- {note}" for note in summary["codec_notes"]]
    return "\n".join(lines) + "\n"


# --- CLI -----------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    commands = parser.add_subparsers(dest="command", required=True)
    probe_parser = commands.add_parser("probe", help="render/export/decode the corpus once")
    probe_parser.add_argument("--variant", choices=VARIANTS, default="canonical")
    probe_parser.add_argument("--corpus", type=Path, default=CORPUS_PATH)
    report_parser = commands.add_parser("report", help="fresh processes and manifest check")
    report_parser.add_argument("--output", type=Path, required=True)
    compare_parser = commands.add_parser("compare", help="compare the reports of CI jobs")
    compare_parser.add_argument("folder", type=Path)
    compare_parser.add_argument("--expected-reports", type=int, required=True)
    compare_parser.add_argument(
        "--expected-platforms",
        default="",
        help="comma-separated platform.system() values that must all be present",
    )
    compare_parser.add_argument("--output", type=Path)
    compare_parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)

    if args.command == "probe":
        sys.stdout.write(json.dumps(probe(args.variant, args.corpus), sort_keys=True))
        return 0
    if args.command == "report":
        result = report(args.output)
        for error in result["errors"]:
            print(error)
        print(f"Determinism report {result['status']}: {args.output / REPORT_NAME}")
        return int(result["status"] != "ok")
    platforms = [item for item in args.expected_platforms.split(",") if item]
    summary = compare(find_reports(args.folder), load_expected(), args.expected_reports, platforms)
    text = summary_markdown(summary)
    print(text, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    if args.summary is not None:
        with args.summary.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return int(summary["status"] != "ok")


if __name__ == "__main__":  # pragma: no cover - exercised through subprocesses
    raise SystemExit(main())
