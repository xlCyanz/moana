"""Cross-process and cross-platform determinism of render -> export -> decode (MOANA-029).

The reviewed RGBA manifest ``tests/fixtures/determinism/expected.json`` is the contract
checked on every OS/Python of the CI matrix. It is *not* a copy of a render: every
expected pixel comes from :data:`SCENES` below, where each mask is listed by hand from
the raster rules of MOANART.md section 6 (ADR-015) and colours are composited with an
independent scalar implementation of the section 11 formula. The manifest digests are
recomputed here with ``hashlib`` (section 14).

T1: diagonals, alpha, groups, transparencies and clipping fixtures.
T2: fresh subprocesses with different ``PYTHONHASHSEED``, key orders and whitespace,
render -> PNG (memory, atomic file, indexed) -> Pillow decode against the RGBA master.
AC2: divergence evidence (report, expected/actual/diff, environment) without ever
rewriting the manifest; codec differences are separated from pixel differences.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from scripts import determinism

RGBA = tuple[int, int, int, int]
Pixels = frozenset[tuple[int, int]]
CLEAR: RGBA = (0, 0, 0, 0)

# --- Independent oracle ----------------------------------------------------------------


def round_half_up(numerator: int, denominator: int) -> int:
    """MOANART.md section 11: ``round_half_up(n/d) = (2n + d) // 2d``."""
    return (2 * numerator + denominator) // (2 * denominator)


def over(dst: RGBA, src: RGBA, opacity: int) -> RGBA:
    """Scalar source-over on straight RGBA, literally as written in section 11."""
    sa = round_half_up(src[3] * opacity, 255)
    da = dst[3]
    total = sa * 255 + da * (255 - sa)
    if total == 0:
        return CLEAR
    channels = tuple(
        round_half_up(src[i] * sa * 255 + dst[i] * da * (255 - sa), total) for i in range(3)
    )
    alpha = round_half_up(total, 255)
    return CLEAR if alpha == 0 else (channels[0], channels[1], channels[2], alpha)


def box(x0: int, y0: int, x1: int, y1: int) -> Pixels:
    return frozenset((x, y) for y in range(y0, y1) for x in range(x0, x1))


def layer(fills: list[tuple[Pixels, RGBA]], opacity: int = 255, visible: bool = True) -> Any:
    return ("layer", opacity, visible, fills)


def group(children: list[Any], opacity: int = 255, visible: bool = True) -> Any:
    return ("group", opacity, visible, children)


def compose_scene(width: int, height: int, nodes: list[Any]) -> list[list[RGBA]]:
    """Isolated buffers per node, fills at opacity 255, node opacity applied once."""

    def into(target: dict[tuple[int, int], RGBA], children: list[Any]) -> None:
        for kind, opacity, visible, payload in children:
            if not visible:
                continue
            buffer: dict[tuple[int, int], RGBA] = {}
            if kind == "group":
                into(buffer, payload)
            else:
                for pixels, color in payload:
                    for point in pixels:
                        buffer[point] = over(buffer.get(point, CLEAR), color, 255)
            for y in range(height):
                for x in range(width):
                    point = (x, y)
                    target[point] = over(
                        target.get(point, CLEAR), buffer.get(point, CLEAR), opacity
                    )

    root: dict[tuple[int, int], RGBA] = {}
    into(root, nodes)
    return [[root.get((x, y), CLEAR) for x in range(width)] for y in range(height)]


INK: RGBA = (0x10, 0x20, 0x30, 255)
GOLD: RGBA = (0xFA, 0xC8, 0x00, 255)
SEA: RGBA = (0x1E, 0x5A, 0x8C, 255)
ROSE: RGBA = (0xC8, 0x3C, 0x5A, 255)
MINT: RGBA = (0x3C, 0xC8, 0x8C, 255)

SCENES: dict[str, tuple[int, int, list[Any], list[str]]] = {
    # Bresenham of section 6 on lexicographically sorted endpoints. 45-degree lines
    # advance x and y every step; "main" starts off-canvas and is clipped to y < 6.
    # "shallow" sorted is (4,5)->(7,4): dx=3, dy=-1 gives (4,5),(5,5),(6,4),(7,4).
    # "tie" is written in reverse, (7,2)->(5,1); sorted it is (5,1)->(7,2) with dx=2,
    # dy=-1, err=1: the first step has e2=2 >= dy and e2 <= dx, so both coordinates
    # advance and the mask is (5,1),(6,2),(7,2). Tracing unsorted from (7,2) would give
    # (7,2),(6,1),(5,1) instead. Later operations win where opaque pixels overlap
    # ((5,5) ends sea).
    "diagonals": (
        8,
        6,
        [
            layer(
                [
                    (frozenset((k, k) for k in range(6)), INK),
                    (frozenset((5 - k, k) for k in range(6)), GOLD),
                    (frozenset({(4, 5), (5, 5), (6, 4), (7, 4)}), SEA),
                    (frozenset({(5, 1), (6, 2), (7, 2)}), ROSE),
                ]
            )
        ],
        [],
    ),
    # Two semi-transparent washes in one layer, then a layer at opacity 128.
    "alpha": (
        4,
        3,
        [
            layer([(box(0, 0, 3, 2), (255, 0, 0, 128)), (box(1, 0, 4, 3), (0, 0, 255, 128))]),
            layer(
                [
                    (frozenset({(2, 1)}), (255, 255, 255, 255)),
                    (frozenset({(0, 2)}), (0, 255, 0, 255)),
                ],
                opacity=128,
            ),
        ],
        [],
    ),
    # Alpha-0 colour is not an eraser, opacity 0 and hidden layers change nothing,
    # alpha 1 survives, and alpha 1 at opacity 1 rounds to sa = 0 (stays clear).
    "transparency": (
        3,
        2,
        [
            layer(
                [
                    (box(0, 0, 2, 1), (0x33, 0x66, 0xCC, 255)),
                    (frozenset({(2, 0)}), (32, 64, 96, 128)),
                ]
            ),
            layer([(box(0, 0, 3, 2), (255, 0, 255, 0))]),
            layer([(box(0, 0, 3, 2), (0x33, 0x66, 0xCC, 255))], opacity=0),
            layer([(box(0, 0, 3, 2), (0x33, 0x66, 0xCC, 255))], visible=False),
            layer([(frozenset({(2, 1)}), (255, 128, 64, 1))]),
            layer([(frozenset({(1, 1)}), (255, 128, 64, 1))], opacity=1),
        ],
        [],
    ),
    # Rect [-3,-3,2,2) keeps x,y in {0,1}. Polygon x in [2,4], y in [-5,1]: only row 0
    # has its centre (0.5) inside, span [2,4). Ellipse box [3,2,9,8): circle centre
    # (6,5) radius 3; centres (4.5,2.5), (3.5,3.5), (4.5,3.5) are inside (8.5, 8.5,
    # 4.5 <= 9), (3.5,2.5) is not (12.5). Line y=3 crosses the whole canvas and
    # overwrites (3,3),(4,3). Pixel (7,1) and rect [5,0,9,4) (x0 == width) are empty
    # once clipped: they draw nothing and warn. "slope" (-3,0)->(4,2) is traced before
    # clipping (dx=7, dy=-2, err=5): (-3,0),(-2,0),(-1,0),(0,1),(1,1),(2,1),(3,2),(4,2),
    # so on canvas (0,1),(1,1),(2,1),(3,2),(4,2). Clipping first and tracing from (0,1)
    # would reach (2,2) instead of (2,1). It is drawn last and overwrites ink/sea.
    "clipping": (
        5,
        4,
        [
            layer(
                [
                    (box(0, 0, 2, 2), INK),
                    (box(2, 0, 4, 1), GOLD),
                    (frozenset({(4, 2), (3, 3), (4, 3)}), SEA),
                    (box(0, 3, 5, 4), ROSE),
                    (frozenset({(0, 1), (1, 1), (2, 1), (3, 2), (4, 2)}), MINT),
                ]
            )
        ],
        ["/layers/0/operations/4", "/layers/0/operations/5"],
    ),
    # Exact .5 tie: dark (192,0,0,128) then speck (1,0,0,128) in one layer. sa=128,
    # D=128*255+128*127=48896, a=round(48896/255)=192 (0xC0), and
    # R=(1*128*255 + 192*128*127)/48896 = 3153792/48896 = 64.5 exactly: half-up gives 65
    # (0x41), half-even or float rounding would give 64.
    "rounding": (
        1,
        1,
        [layer([(frozenset({(0, 0)}), (192, 0, 0, 128)), (frozenset({(0, 0)}), (1, 0, 0, 128))])],
        [],
    ),
    # Group "glass" (128) isolates back/front: (1, y) is opaque blue inside the group
    # before the group opacity applies. Nested "inner" (200) holds a white pixel and a
    # hidden layer.
    "groups": (
        4,
        2,
        [
            layer([(box(2, 0, 4, 1), (0, 255, 0, 255))]),
            group(
                [
                    layer([(box(0, 0, 2, 2), (255, 0, 0, 255))]),
                    layer([(box(1, 0, 3, 2), (0, 0, 255, 255))]),
                    group(
                        [
                            layer([(frozenset({(3, 1)}), (255, 255, 255, 255))]),
                            layer([(box(0, 0, 4, 2), (255, 0, 0, 255))], visible=False),
                        ],
                        opacity=200,
                    ),
                ],
                opacity=128,
            ),
        ],
        [],
    ),
}


def oracle_rows(name: str) -> list[list[str]]:
    width, height, nodes, _ = SCENES[name]
    return [
        ["#" + bytes(pixel).hex().upper() for pixel in row]
        for row in compose_scene(width, height, nodes)
    ]


def hand_digest(width: int, height: int, rows: list[list[str]]) -> str:
    data = bytearray(width.to_bytes(4, "big") + height.to_bytes(4, "big"))
    for row in rows:
        for cell in row:
            data.extend(bytes.fromhex(cell[1:]))
    return "sha256:" + hashlib.sha256(bytes(data)).hexdigest()


EXPECTED = determinism.load_expected()
CORPUS = determinism.load_corpus()


# --- Oracle self-checks ------------------------------------------------------------------


def test_oracle_formula_matches_hand_values() -> None:
    # Blue a=128 over red a=128: sa=128, D=128*255+128*127=48896, a=round(48896/255)=192,
    # R=round(255*128*127/48896)=85, B=round(255*128*255/48896)=170.
    assert over((255, 0, 0, 128), (0, 0, 255, 128), 255) == (85, 0, 170, 192)
    assert over((7, 8, 9, 200), (1, 2, 3, 255), 0) == (7, 8, 9, 200)
    assert over(CLEAR, (255, 128, 64, 1), 1) == CLEAR  # sa = (2 + 255) // 510 = 0
    assert over(CLEAR, (255, 255, 255, 255), 200) == (255, 255, 255, 200)


@pytest.mark.parametrize("name", sorted(SCENES))
def test_t1_manifest_is_the_independent_oracle(name: str) -> None:
    width, height, _, warnings = SCENES[name]
    case = EXPECTED["cases"][name]
    assert (case["width"], case["height"]) == (width, height)
    assert case["rows"] == oracle_rows(name)
    assert case["digest"] == hand_digest(width, height, case["rows"])
    assert case["warnings"] == warnings


def test_t1_corpus_covers_the_required_fixtures() -> None:
    assert set(CORPUS["cases"]) == set(EXPECTED["cases"]) == set(SCENES)
    assert set(SCENES) == {
        "diagonals",
        "alpha",
        "groups",
        "transparency",
        "clipping",
        "rounding",
    }
    alphas = {
        int(cell[7:], 16)
        for case in EXPECTED["cases"].values()
        for row in case["rows"]
        for cell in row
    }
    assert {0, 1, 255} <= alphas and alphas - {0, 1, 255}  # clear, minimal, partial, opaque
    assert CORPUS["cases"]["groups"]["kind"] == "tree"  # schema 1.0 has no groups
    for case in EXPECTED["cases"].values():  # zero alpha is normalised to (0, 0, 0, 0)
        assert all(
            cell == "#00000000" for row in case["rows"] for cell in row if cell.endswith("00")
        )


def test_t1_hand_values_of_the_semitransparent_cases() -> None:
    alpha = EXPECTED["cases"]["alpha"]["rows"]
    assert alpha[0][0] == "#FF000080"  # red alone
    assert alpha[0][1] == "#5500AAC0"  # (85, 0, 170, 192), see the formula test
    groups = EXPECTED["cases"]["groups"]["rows"]
    assert groups[1][0] == "#FF000080"  # opaque red in the group, group opacity 128
    assert groups[1][1] == "#0000FF80"  # front covers back inside the isolated buffer
    # spark: 255 at 200 inside "inner" -> a=200; at 128: sa=(200*256+255)//510=100.
    assert groups[1][3] == "#FFFFFF64"
    transparency = EXPECTED["cases"]["transparency"]["rows"]
    assert transparency == [
        ["#3366CCFF", "#3366CCFF", "#20406080"],
        ["#00000000", "#00000000", "#FF804001"],
    ]
    assert EXPECTED["cases"]["rounding"]["rows"] == [["#410000C0"]]  # 64.5 -> 65


def over_half_even(dst: RGBA, src: RGBA, opacity: int) -> RGBA:
    """Same formula with banker's rounding: the corpus must tell the two apart."""
    sa = round(Fraction(src[3] * opacity, 255))
    total = sa * 255 + dst[3] * (255 - sa)
    channels = [
        round(Fraction(src[i] * sa * 255 + dst[i] * dst[3] * (255 - sa), total)) for i in range(3)
    ]
    return channels[0], channels[1], channels[2], round(Fraction(total, 255))


def test_t1_rounding_case_detects_half_even() -> None:
    under = over(CLEAR, (192, 0, 0, 128), 255)
    assert under == (192, 0, 0, 128)
    assert over(under, (1, 0, 0, 128), 255) == (65, 0, 0, 192)
    assert over_half_even(under, (1, 0, 0, 128), 255) == (64, 0, 0, 192)
    frame, _ = determinism.render_case(CORPUS["cases"]["rounding"])
    assert frame.rgba == bytes((65, 0, 0, 192))


def test_t1_line_masks_depend_on_sorting_and_clip_order() -> None:
    diagonals = EXPECTED["cases"]["diagonals"]["rows"]
    rose = "#C83C5AFF"
    assert [diagonals[y][x] for x, y in [(5, 1), (6, 2), (7, 2)]] == [rose] * 3
    assert diagonals[1][6] != rose  # unsorted tracing would paint (6, 1)
    clipping = EXPECTED["cases"]["clipping"]["rows"]
    mint = "#3CC88CFF"
    assert [clipping[y][x] for x, y in [(0, 1), (1, 1), (2, 1), (3, 2), (4, 2)]] == [mint] * 5
    assert clipping[2][2] != mint  # clip-then-trace from (0, 1) would paint (2, 2)


# --- T1/T2 in process --------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCENES))
@pytest.mark.parametrize("variant", determinism.VARIANTS)
def test_t1_render_matches_manifest(name: str, variant: str) -> None:
    frame, warnings = determinism.render_case(CORPUS["cases"][name], variant)
    expected = EXPECTED["cases"][name]
    assert (frame.width, frame.height) == (expected["width"], expected["height"])
    assert determinism.bytes_to_rows(frame.width, frame.height, frame.rgba) == expected["rows"]
    assert warnings == expected["warnings"]


def test_t2_export_and_decode_agree_with_the_master(tmp_path: Path) -> None:
    for name in sorted(SCENES):
        entry = determinism.probe_case(
            {**CORPUS["cases"][name], "name": name}, "canonical", tmp_path
        )
        digest = EXPECTED["cases"][name]["digest"]
        assert entry["digest"] == digest
        modes = (
            {"rgba", "file", "indexed"} if name in {"diagonals", "clipping"} else {"rgba", "file"}
        )
        assert set(entry["png"]) == modes
        assert {png["decoded_digest"] for png in entry["png"].values()} == {digest}
        assert entry["png"]["file"]["sha256"] == entry["png"]["rgba"]["sha256"]
        assert entry["png"]["file"]["manifest_pixel_digest"] == digest


@pytest.mark.slow
def test_ac1_t2_fresh_processes_seeds_and_key_orders_agree(tmp_path: Path) -> None:
    result = determinism.report(tmp_path)
    assert result["status"] == "ok", result["errors"]
    assert len(result["runs"]) == len(determinism.HASH_SEEDS) * len(determinism.VARIANTS)
    assert {run["hash_seed"] for run in result["runs"]} == set(determinism.HASH_SEEDS)
    for name, case in result["cases"].items():
        assert case["consistent_across_runs"] and case["pixel_match"] and case["export_consistent"]
        assert case["decoded_digests"] == [EXPECTED["cases"][name]["digest"]]
    environment = result["environment"]
    assert environment["renderer_backend"] == "integer"
    assert (
        environment["lock_sha256"] == hashlib.sha256(determinism.LOCK_PATH.read_bytes()).hexdigest()
    )
    assert {"platform", "python", "pillow", "zlib", "numpy", "renderer_version"} <= set(environment)
    written = json.loads((tmp_path / determinism.REPORT_NAME).read_text(encoding="utf-8"))
    assert written == result
    assert not (tmp_path / "diagnostics").exists()


# --- AC2: divergence evidence, never a manifest update ------------------------------------


def _probe_runs(tmp_path: Path) -> list[tuple[str, str, dict[str, Any]]]:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    result = {
        name: determinism.probe_case({**case, "name": name}, "canonical", scratch)
        for name, case in CORPUS["cases"].items()
    }
    return [("0", "canonical", result), ("1", "canonical", copy.deepcopy(result))]


def test_ac2_pixel_divergence_writes_diagnostics_and_keeps_the_manifest(tmp_path: Path) -> None:
    before = determinism.EXPECTED_PATH.read_bytes()
    tampered = copy.deepcopy(EXPECTED)
    case = tampered["cases"]["alpha"]
    case["rows"][2][3] = "#FFFFFFFF"
    case["digest"] = hand_digest(case["width"], case["height"], case["rows"])
    output = tmp_path / "out"
    report = determinism.build_report(_probe_runs(tmp_path), tampered, {"pillow": "x"}, output)
    assert report["status"] == "divergent"
    assert report["errors"] == ["alpha: pixels differ from the reviewed RGBA manifest"]
    alpha = report["cases"]["alpha"]
    assert alpha["pixel_match"] is False and alpha["consistent_across_runs"] is True
    diagnostics = alpha["diagnostics"]
    assert diagnostics["differing_pixels"] == 1
    assert diagnostics["bbox"] == {"x0": 3, "y0": 2, "x1": 4, "y1": 3}
    folder = output / "diagnostics" / "alpha"
    assert sorted(path.name for path in folder.iterdir()) == [
        "actual.png",
        "diff.png",
        "expected.png",
    ]
    assert alpha["actual_rows"] == EXPECTED["cases"]["alpha"]["rows"]
    assert all(
        other["diagnostics"] is None for key, other in report["cases"].items() if key != "alpha"
    )
    assert determinism.EXPECTED_PATH.read_bytes() == before


def test_ac2_runs_that_disagree_are_reported(tmp_path: Path) -> None:
    runs = _probe_runs(tmp_path)
    runs[1][2]["groups"]["png"]["rgba"]["sha256"] = "0" * 64
    report = determinism.build_report(runs, EXPECTED, {}, tmp_path / "out")
    assert report["status"] == "divergent"
    assert report["errors"] == ["groups: runs disagree (hash seed, key order or codec state)"]
    assert report["cases"]["groups"]["pixel_match"] is True


def _job_report(
    tmp_path: Path,
    label: str,
    *,
    codec: str = "zlib 1",
    status: str = "ok",
    system: str | None = None,
    python: str = "3.12.3",
    salt: str = "",
) -> Path:
    """A CI job's report as downloaded: ``reports/<artifact>/determinism/<report>``."""
    folder = tmp_path / "reports" / f"diagnostics-{label}" / "determinism"
    folder.mkdir(parents=True)
    cases = {
        name: {
            "digest": case["digest"],
            "decoded_digests": [case["digest"]],
            "png_sha256": {"rgba": hashlib.sha256(f"{name}{codec}{salt}".encode()).hexdigest()},
        }
        for name, case in EXPECTED["cases"].items()
    }
    value = {
        "format": determinism.REPORT_FORMAT,
        "status": status,
        "codec": codec,
        "environment": {
            "system": system or label,
            "machine": "x86_64",
            "python": python,
            "lock_sha256": "abc",
            "renderer_version": "render-v1",
            "renderer_backend": "integer",
        },
        "cases": cases,
    }
    path = folder / determinism.REPORT_NAME
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_ac2_compare_separates_codec_from_pixel_differences(tmp_path: Path) -> None:
    _job_report(tmp_path, "Linux")
    _job_report(tmp_path, "Windows", codec="zlib 2")
    reports = determinism.find_reports(tmp_path / "reports")
    summary = determinism.compare(reports, EXPECTED, expected_reports=2)
    assert summary["status"] == "ok", summary["errors"]
    assert len(summary["codec_notes"]) == len(EXPECTED["cases"])
    assert all("decoded pixels agree" in note for note in summary["codec_notes"])
    assert set(summary["codecs"]) == {"zlib 1", "zlib 2"}
    assert "iguales" in determinism.summary_markdown(summary)


def test_ac2_compare_fails_on_pixel_divergence_missing_jobs_and_lock_drift(tmp_path: Path) -> None:
    _job_report(tmp_path, "Linux")
    windows = _job_report(tmp_path, "Windows")
    value = json.loads(windows.read_text(encoding="utf-8"))
    value["cases"]["clipping"]["decoded_digests"] = ["sha256:" + "f" * 64]
    value["environment"]["lock_sha256"] = "other"
    windows.write_text(json.dumps(value), encoding="utf-8")
    summary = determinism.compare(determinism.find_reports(tmp_path / "reports"), EXPECTED, 3)
    assert summary["status"] == "divergent"
    errors = summary["errors"]
    assert errors[0] == "expected 3 reports, found 2"
    assert any(error.startswith("reports disagree on lock_sha256") for error in errors)
    assert any(
        error.startswith("clipping: pixel divergence") and "Windows" in error for error in errors
    )
    assert summary["cases"]["clipping"]["pixel_ok"] is False
    assert "**DIVERGEN**" in determinism.summary_markdown(summary)


def test_ac2_compare_cli_writes_summary_and_exit_code(tmp_path: Path) -> None:
    _job_report(tmp_path, "Linux", status="divergent")
    output, summary = tmp_path / "summary.json", tmp_path / "step-summary.md"
    code = determinism.main(
        [
            "compare",
            str(tmp_path / "reports"),
            "--expected-reports",
            "1",
            "--output",
            str(output),
            "--summary",
            str(summary),
        ]
    )
    assert code == 1
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "divergent"
    assert "report status divergent" in summary.read_text(encoding="utf-8")


def test_unknown_inputs_are_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "corpus.json"
    bad.write_text('{"format": "other", "cases": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="corpus format"):
        determinism.load_corpus(bad)
    with pytest.raises(ValueError, match="expected manifest"):
        determinism.load_expected(bad)
    with pytest.raises(ValueError, match="RRGGBBAA"):
        determinism.parse_hex("#FFF")
    with pytest.raises(ValueError, match="variant"):
        determinism.serialise({}, "pretty")
    with pytest.raises(ValueError, match="case kind"):
        determinism.render_case({"kind": "sprite"})
    with pytest.raises(ValueError, match="fill type"):
        determinism._mask({"type": "spline"}, 2, 2)
    with pytest.raises(ValueError, match="node kind"):
        determinism._node({"kind": "mask", "id": "m"}, 2, 2)
    with pytest.raises(ValueError, match="dimensions"):
        determinism.bytes_to_rows(2, 2, b"\0" * 4)
    listing = tmp_path / "list.json"
    listing.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        determinism.read_json(listing)


# --- M1/M2/M3 review: platform coverage, failing probes, negative branches ----------------


def test_ac2_compare_rejects_duplicate_and_missing_platforms(tmp_path: Path) -> None:
    _job_report(tmp_path, "linux-a", system="Linux")
    _job_report(tmp_path, "linux-b", system="Linux", python="3.12.9")
    summary = determinism.compare(
        determinism.find_reports(tmp_path / "reports"),
        EXPECTED,
        expected_reports=2,
        expected_platforms=["Darwin", "Linux", "Windows"],
    )
    assert summary["status"] == "divergent"
    assert summary["errors"] == [
        "duplicate platform Linux/py3.12: ['diagnostics-linux-a', 'diagnostics-linux-b']",
        "missing platforms: ['Darwin', 'Windows']",
    ]
    assert summary["artifacts"] == ["diagnostics-linux-a", "diagnostics-linux-b"]
    assert "Artefactos: diagnostics-linux-a, diagnostics-linux-b" in (
        determinism.summary_markdown(summary)
    )


def test_ac1_compare_accepts_the_full_matrix(tmp_path: Path) -> None:
    for system in ("Linux", "Darwin", "Windows"):
        for python in ("3.12.1", "3.13.2", "3.14.0"):
            _job_report(tmp_path, f"{system}-{python}", system=system, python=python)
    summary = determinism.compare(
        determinism.find_reports(tmp_path / "reports"), EXPECTED, 9, ["Darwin", "Linux", "Windows"]
    )
    assert summary["status"] == "ok", summary["errors"]
    assert summary["codec_warnings"] == [] and summary["codec_notes"] == []
    assert len(summary["artifacts"]) == 9


def test_ac2_compare_warns_when_bytes_differ_within_one_codec(tmp_path: Path) -> None:
    _job_report(tmp_path, "Linux")
    _job_report(tmp_path, "Windows", salt="other bytes")
    summary = determinism.compare(determinism.find_reports(tmp_path / "reports"), EXPECTED, 2)
    assert summary["status"] == "ok"  # a warning, not a contract failure
    assert len(summary["codec_warnings"]) == len(EXPECTED["cases"])
    assert all("within zlib 1" in warning for warning in summary["codec_warnings"])
    assert summary["codec_notes"] == []
    assert "mismo codec" in determinism.summary_markdown(summary)


def test_ac2_compare_reports_unknown_format_and_missing_cases(tmp_path: Path) -> None:
    linux = _job_report(tmp_path, "Linux")
    windows = _job_report(tmp_path, "Windows")
    value = json.loads(linux.read_text(encoding="utf-8"))
    value["format"] = "other/1"
    linux.write_text(json.dumps(value), encoding="utf-8")
    value = json.loads(windows.read_text(encoding="utf-8"))
    del value["cases"]["groups"]
    windows.write_text(json.dumps(value), encoding="utf-8")
    summary = determinism.compare(determinism.find_reports(tmp_path / "reports"), EXPECTED, 2)
    assert summary["status"] == "divergent"
    assert any(
        e.endswith("(diagnostics-Linux): unsupported report format") for e in summary["errors"]
    )
    assert any(e.endswith("(diagnostics-Windows): case groups missing") for e in summary["errors"])


def test_ac2_failing_probe_still_writes_an_error_report(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(determinism.ProbeFailure) as excinfo:
        determinism.run_probe("7", "compact", broken)
    assert (excinfo.value.hash_seed, excinfo.value.variant) == ("7", "compact")
    assert "JSONDecodeError" in excinfo.value.detail
    output = tmp_path / "out"
    result = determinism.report(
        output, hash_seeds=("0",), variants=("reversed",), corpus_path=broken
    )
    assert result["status"] == "error"
    assert result["failure"]["hash_seed"] == "0" and result["failure"]["variant"] == "reversed"
    assert "JSONDecodeError" in result["failure"]["stderr_tail"]
    assert len(result["failure"]["stderr_tail"]) <= determinism.STDERR_TAIL
    assert result["environment"]["renderer_backend"] == "integer"
    written = json.loads((output / determinism.REPORT_NAME).read_text(encoding="utf-8"))
    assert written == result
    # The comparison names the artifact whose job failed.
    job = tmp_path / "reports" / "diagnostics-windows-latest-3.13" / "determinism"
    job.mkdir(parents=True)
    (job / determinism.REPORT_NAME).write_text(json.dumps(result), encoding="utf-8")
    summary = determinism.compare(determinism.find_reports(tmp_path / "reports"), EXPECTED, 1)
    assert summary["artifacts"] == ["diagnostics-windows-latest-3.13"]
    assert any(
        "(diagnostics-windows-latest-3.13): report status error" in error
        for error in summary["errors"]
    )


def test_run_probe_rejects_invalid_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(stdout: bytes) -> Any:
        return lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout, b"")

    monkeypatch.setattr(subprocess, "run", fake(b"[]"))
    with pytest.raises(determinism.ProbeFailure, match="JSON object"):
        determinism.run_probe("0", "canonical")
    monkeypatch.setattr(subprocess, "run", fake(b"not json"))
    with pytest.raises(determinism.ProbeFailure, match="invalid probe output"):
        determinism.run_probe("0", "canonical")


def test_build_report_flags_missing_cases_and_inconsistent_exports(tmp_path: Path) -> None:
    runs = _probe_runs(tmp_path)
    del runs[1][2]["alpha"]
    file_entry = runs[0][2]["groups"]["png"]["file"]
    file_entry["manifest_sha256"] = "sha256:" + "0" * 64
    report = determinism.build_report(runs, EXPECTED, {}, tmp_path / "out")
    assert report["status"] == "divergent"
    assert report["errors"][:2] == [
        "corpus cases differ from the expected manifest",
        "alpha: missing from a probe",
    ]
    assert "groups: file export differs from the in-memory encoding" in report["errors"]
    assert report["cases"]["groups"]["export_consistent"] is False
    assert "alpha" not in report["cases"]


def test_diagnostics_with_different_dimensions_have_no_diff(tmp_path: Path) -> None:
    expected = {"width": 2, "height": 1, "rows": [["#00000000", "#FF0000FF"]]}
    actual = {"width": 1, "height": 1, "rows": [["#FF0000FF"]]}
    result = determinism.write_diagnostics(tmp_path / "case", expected, actual)
    assert result == {
        "dimensions_match": False,
        "files": {"expected": "expected.png", "actual": "actual.png"},
    }
    assert sorted(path.name for path in (tmp_path / "case").iterdir()) == [
        "actual.png",
        "expected.png",
    ]
    same = determinism.write_diagnostics(tmp_path / "same", actual, actual)
    assert same["differing_pixels"] == 0 and same["bbox"] is None


def test_decode_requires_the_promised_png_mode() -> None:
    frame, _ = determinism.render_case(CORPUS["cases"]["diagonals"])
    from moanart.export import encode_png
    from moanart.palette import Palette

    rgba = encode_png(frame).data
    palette = Palette.from_mapping(
        CORPUS["cases"]["diagonals"]["document"]["palette"], profile="strict"
    )
    indexed = encode_png(frame, mode="indexed", palette=palette).data
    assert determinism.decode_png(rgba, "RGBA")[2] == frame.rgba
    assert determinism.decode_png(indexed, "P")[2] == frame.rgba
    with pytest.raises(ValueError, match="expected PNG mode RGBA, found P"):
        determinism.decode_png(indexed, "RGBA")
    with pytest.raises(ValueError, match="expected PNG mode P, found RGBA"):
        determinism.decode_png(rgba, "P")
    buffer = io.BytesIO()
    Image.new("RGBA", (1, 1)).save(buffer, "GIF")
    with pytest.raises(ValueError, match="single-frame PNG"):
        determinism.decode_png(buffer.getvalue(), "RGBA")


def test_tree_fills_accept_every_primitive() -> None:
    # Hand masks on a 3x3 canvas (same section 6 rules as the scenes above).
    specs: dict[tuple[int, int], dict[str, Any]] = {
        (0, 0): {"type": "pixel", "at": [0, 0]},
        (1, 0): {"type": "line", "start": [2, 2], "end": [0, 0]},
        (2, 0): {"type": "rect", "box": [-1, 1, 1, 9]},
        (3, 0): {"type": "ellipse", "box": [0, 0, 3, 3]},
        (4, 0): {"type": "polygon", "points": [[0, 0], [3, 0], [3, 3]]},
    }
    expected = [
        {(0, 0)},
        {(0, 0), (1, 1), (2, 2)},
        {(0, 1), (0, 2)},
        # Centre (1.5, 1.5), radius 1.5: corner centres give (1 + 1) / 2.25 <= 1.
        box(0, 0, 3, 3),
        # Even-odd: row y spans [ceil(y + 0.5 - 0.5), ceil(3 - 0.5)) = [y, 3).
        {(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 1)},
    ]
    for spec, pixels in zip(specs.values(), expected, strict=True):
        mask = determinism._mask(spec, 3, 3)
        assert {(point.x, point.y) for point in mask.points()} == pixels, spec


def test_cli_compare_without_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _job_report(tmp_path, "Linux")
    assert determinism.main(["compare", str(tmp_path / "reports"), "--expected-reports", "1"]) == 0
    assert "Determinismo entre plataformas: ok" in capsys.readouterr().out


def test_environment_without_lock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(determinism, "LOCK_PATH", tmp_path / "missing.lock")
    assert determinism.environment()["lock_sha256"] is None


def test_cli_probe_and_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert determinism.main(["probe", "--variant", "compact"]) == 0
    probed = json.loads(capsys.readouterr().out)
    assert {name: case["digest"] for name, case in probed.items()} == {
        name: case["digest"] for name, case in EXPECTED["cases"].items()
    }

    def fake_report(output: Path) -> dict[str, Any]:
        return {"status": "divergent", "errors": ["alpha: pixels differ"]}

    monkeypatch.setattr(determinism, "report", fake_report)
    assert determinism.main(["report", "--output", str(tmp_path)]) == 1
    assert "alpha: pixels differ" in capsys.readouterr().out
