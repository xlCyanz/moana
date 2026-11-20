"""MOANA-033: executable oracle of the AI workflow tutorial (docs/guides/ai-workflows.md).

T2: every JSON example of ``examples/tutorial`` validates with the current schema and
the recolor by ID changes only the pixels of the intended region, keeping IDs and
untouched properties. The guide's ``sh`` blocks are parsed and run in order by
``scripts.tutorial`` (``moana`` through the real CLI entry point in process,
``python`` in an isolated subprocess) from a scratch copy, so the documented
commands, paths and exit codes cannot drift. T1 (clean wheel) runs the same steps
from ``scripts/check_wheel.py`` with the installed ``moana`` and venv interpreter.

The expected pixels come from the document geometry by hand: ``liquid_fill`` is the
half-open box ``[5, 9, 11, 14)`` (6 x 5 = 30 pixels) and ``liquid_shine``, drawn on
top, covers ``(6, 10)`` and ``(6, 11)``; so exactly 28 pixels may change.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from moana import api
from moana.cli import main
from moana.core.errors import EditConflict, ReferenceError
from moana.schema import normalize_document
from scripts.tutorial import (
    GUIDE,
    GuideError,
    MoanaRunner,
    Outcome,
    Step,
    StepFailed,
    check_outputs,
    code_blocks,
    guide_steps,
    parse_step,
    parse_steps,
    prepare,
    run_steps,
)

ROOT = Path(__file__).resolve().parents[3]
TUTORIAL = ROOT / "examples" / "tutorial"
DOCUMENT = TUTORIAL / "potion.moana.json"
RECOLOR = TUTORIAL / "potion-recolor.edit.json"
TYPO = TUTORIAL / "potion-typo.edit.json"
FLOW = TUTORIAL / "potion_flow.py"
SCHEMA = ROOT / "schemas" / "moana-document-1.0.schema.json"

LIQUID = {(x, y) for x in range(5, 11) for y in range(9, 14)}
SHINE = {(6, 10), (6, 11)}
EXPECTED_CHANGED = LIQUID - SHINE
GREEN = (0x38, 0xB7, 0x64, 0xFF)
RED = (0xB1, 0x3E, 0x53, 0xFF)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch copy of the files the guide reads, laid out as the repository root."""
    prepare(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _in_process(capsys: pytest.CaptureFixture[str], workspace: Path) -> MoanaRunner:
    def run(arguments: Sequence[str], cwd: Path) -> tuple[int, str, str]:
        assert cwd == workspace == Path.cwd()  # relative paths resolve against cwd
        capsys.readouterr()
        code = main(list(arguments))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


def _digests(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / "examples").rglob("*"))
        if path.is_file()
    }


def _pixel(image: Image.Image, x: int, y: int) -> tuple[int, ...]:
    value = image.getpixel((x, y))
    assert isinstance(value, tuple)
    return value


def _pixels(path: Path) -> dict[tuple[int, int], tuple[int, ...]]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        return {(x, y): _pixel(rgba, x, y) for x in range(width) for y in range(height)}


def _tree(document: api.Document) -> dict[str, Any]:
    """The normalised document as plain JSON values."""
    value = json.loads(json.dumps(normalize_document(document)))
    assert isinstance(value, dict)
    return value


def _payload(outcome: Outcome) -> dict[str, Any]:
    value = json.loads(outcome.stdout)
    assert isinstance(value, dict)
    return value


def _find(outcomes: list[Outcome], predicate: str) -> Outcome:
    matches = [outcome for outcome in outcomes if predicate in outcome.step.line]
    assert len(matches) == 1, predicate
    return matches[0]


def test_guide_shell_blocks_run_as_documented(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC1/T2: the documented commands reproduce creation, inspection and recolor."""
    steps = guide_steps()
    moana_commands = {step.arguments[0] for step in steps if step.program == "moana"}
    assert moana_commands == {"capabilities", "validate", "inspect", "export", "edit"}
    inputs = _digests(workspace)
    outcomes = run_steps(
        steps,
        workspace,
        moana=_in_process(capsys, workspace),
        python=[sys.executable, "-I"],
    )
    assert [outcome.step for outcome in outcomes] == steps
    assert _digests(workspace) == inputs  # the guide writes only under artifacts/tutorial
    check_outputs(workspace)

    out = workspace / "artifacts" / "tutorial"
    edit = json.loads((out / "potion-edit.json").read_text(encoding="utf-8"))["edit"]
    assert (edit["revision"], edit["affected_ids"]) == (1, ["liquid_fill"])
    saved = api.load_document(out / "potion-r1.moana.json")
    assert saved.revision == 1

    with Image.open(out / "potion-1x.png") as master, Image.open(out / "potion-4x.png") as big:
        assert (master.size, big.size) == ((16, 16), (64, 64))
        for x, y in [(0, 0), (6, 10), (8, 12), (15, 15)]:  # nearest-neighbour blocks
            block = {_pixel(big, 4 * x + i, 4 * y + j) for i in range(4) for j in range(4)}
            assert block == {_pixel(master, x, y)}

    before, after = _pixels(out / "potion-1x.png"), _pixels(out / "potion-r1-1x.png")
    changed = {point for point in before if before[point] != after[point]}
    assert changed == EXPECTED_CHANGED
    assert {after[point] for point in changed} == {GREEN}
    assert before[(5, 9)] == RED

    diff = _find(outcomes, "getpixel")
    assert diff.stdout.strip() == "bbox (5, 9, 11, 14) changed 28"
    summary = _payload(_find(outcomes, "potion_flow.py"))
    assert summary["changed_pixels"] == len(EXPECTED_CHANGED)
    assert summary["changed_outside_region"] == 0
    assert summary["revision"] == [0, 1]
    assert summary["snapshot_digest"] == api.snapshot_digest(saved)

    errors = [_payload(outcome)["error"] for outcome in outcomes if outcome.exit_code != 0]
    reasons = sorted((error["exit_code"], error["code"]) for error in errors)
    assert reasons == [
        (2, "REFERENCE_ERROR"),
        (2, "VALIDATION_ERROR"),
        (3, "BUDGET_EXCEEDED"),
        (4, "EDIT_CONFLICT"),
        (5, "EXPORT_ERROR"),
    ]
    conflict = next(error for error in errors if error["code"] == "EDIT_CONFLICT")
    assert conflict["context"]["reason"] == "stale_revision"
    budget = next(error for error in errors if error["code"] == "BUDGET_EXCEEDED")
    resources = {detail["context"]["resource"]: detail["context"] for detail in budget["details"]}
    assert resources["export_dimension"]["limit"] == 2048
    assert resources["export_area"]["limit"] == 2048 * 2048
    assert not (out / "huge.png").exists() and not (out / "bad.png").exists()


def test_guide_paths_and_python_excerpt_exist() -> None:
    """The guide names only existing tutorial files and quotes potion_flow.py verbatim."""
    text = GUIDE.read_text(encoding="utf-8")
    blocks = code_blocks(text)
    for step in parse_steps(text):
        for argument in step.arguments:
            if argument.startswith("examples/"):
                assert (ROOT / argument).is_file(), argument
    source = FLOW.read_text(encoding="utf-8")
    (excerpt,) = [body for language, body in blocks if language == "python"]
    for line in excerpt.splitlines():
        assert line.strip() in source, line
    (batch_text,) = [body for language, body in blocks if language == "json"]
    assert json.loads(batch_text) == json.loads(RECOLOR.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "line",
    [
        "moana validate a.json | cat",
        "moana validate a.json && moana inspect a.json",
        "moana validate a.json ; ls",
        "moana validate a.json >> out.json",
        "moana validate a.json 2> err.txt",
        "moana validate < a.json",
        "moana validate a.json > one.json two.json",
        "moana validate a.json > a.json > b.json",
        "moana validate $HOME/a.json",
        "moana validate *.json",
        "moana validate `ls`",
        "moana validate a.json \\",
        "moana validate a.json # a comment",
        "mkdir out",
        "mkdir -p a b",
        "rm -rf out",
        "",
    ],
)
def test_parser_rejects_unsupported_shell(line: str) -> None:
    with pytest.raises(GuideError):
        parse_step(line)


def test_parser_reads_redirect_and_exit_code() -> None:
    step = parse_step("moana edit a.json b.json > out/edit.json  # exit 4")
    assert step == Step(
        "moana edit a.json b.json > out/edit.json",
        "moana",
        ("edit", "a.json", "b.json"),
        "out/edit.json",
        4,
    )
    assert parse_step("mkdir -p out").arguments == ("-p", "out")


def test_unknown_block_language_and_wrong_exit_fail(tmp_path: Path) -> None:
    with pytest.raises(GuideError, match="bash"):
        code_blocks("```bash\nmoana capabilities\n```\n")
    with pytest.raises(GuideError):
        code_blocks("```\nmoana capabilities\n```\n")
    step = parse_step("python -c pass  # exit 3")
    with pytest.raises(StepFailed, match="exited 0, documented 3"):
        run_steps(
            [step], tmp_path, moana=lambda arguments, cwd: (0, "", ""), python=[sys.executable]
        )


def test_examples_validate_against_current_schema() -> None:
    """T2: the document and both batches parse with the current 1.0 schema."""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    tree = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    assert set(tree) <= set(schema["properties"])
    assert tree["schema_version"] == schema["properties"]["schema_version"]["const"]
    document = api.load_document(DOCUMENT)
    digest = api.snapshot_digest(document)
    for path in (RECOLOR, TYPO):
        batch = api.load_edit_batch(path)
        assert (batch.base_revision, batch.base_snapshot) == (document.revision, digest)
    region = api.resolve_region(document, "potion_liquid")
    assert region.operation_ids == ("liquid_fill", "liquid_shine")
    assert region.layer_ids == ("liquid",)


def _operation_colors(tree: dict[str, Any]) -> dict[str, str]:
    return {
        operation["id"]: operation["color"]
        for layer in tree["layers"]
        for operation in layer["operations"]
    }


def test_recolor_changes_only_the_region_and_preserves_the_rest() -> None:
    """T2: only the region's pixels change; IDs and untouched members are preserved."""
    document = api.load_document(DOCUMENT)
    result = api.edit_document(document, RECOLOR)
    assert result.revision == document.revision + 1 == 1
    assert result.affected_ids == ("liquid_fill",)
    old, new = _tree(document), _tree(result.document)
    old_colors, new_colors = _operation_colors(old), _operation_colors(new)
    assert old_colors.keys() == new_colors.keys()
    assert {key for key in old_colors if old_colors[key] != new_colors[key]} == {"liquid_fill"}
    assert new_colors["liquid_fill"] == "potion_green"
    for key in old:
        if key not in {"revision", "layers"}:
            assert new[key] == old[key], key
    assert [layer["id"] for layer in new["layers"]] == [layer["id"] for layer in old["layers"]]

    before, after = api.render(document).rgba, api.render(result.document).rgba
    changed = {
        (index % 16, index // 16)
        for index in range(16 * 16)
        if before[4 * index : 4 * index + 4] != after[4 * index : 4 * index + 4]
    }
    assert changed == EXPECTED_CHANGED
    assert api.render(document).rgba == before  # the source document is untouched


def test_documented_failures_are_atomic() -> None:
    """Error recovery: a stale base and an unknown ID raise without changing anything."""
    document = api.load_document(DOCUMENT)
    revised = api.apply_edit(document, RECOLOR)
    with pytest.raises(EditConflict) as conflict:
        api.apply_edit(revised, RECOLOR)
    assert (conflict.value.exit_code, conflict.value.context["reason"]) == (4, "stale_revision")
    with pytest.raises(ReferenceError) as unknown:
        api.apply_edit(document, TYPO)
    assert (unknown.value.exit_code, unknown.value.context["reason"]) == (2, "unknown_target")
    assert api.snapshot_digest(document) == api.load_edit_batch(RECOLOR).base_snapshot


def test_python_flow_reports_moana_errors(workspace: Path) -> None:
    """potion_flow.py prints a Moana error as JSON and exits with its CLI code."""
    tutorial = workspace / "examples" / "tutorial"
    (tutorial / "potion-recolor.edit.json").write_bytes(TYPO.read_bytes())
    completed = subprocess.run(
        [sys.executable, "-I", str(tutorial / "potion_flow.py"), "artifacts/tutorial"],
        cwd=workspace,
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )
    assert completed.returncode == 2, completed.stderr
    failure = json.loads(completed.stdout)
    assert (failure["error"], failure["context"]["reason"]) == ("REFERENCE_ERROR", "unknown_target")
