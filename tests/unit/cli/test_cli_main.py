"""Static ``moana`` command: exit codes, JSON stdout, no tracebacks (MOANA-012 T2, AC2).

Expected exit codes come from MOANA.md section 13 (0 success, 2 invalid input, 3
budget, 4 conflict, 5 I/O, 1 internal), written here by hand rather than read back
from the error classes, so a drift in either side fails.
"""

from __future__ import annotations

import copy
import errno
import io
import json
import os
import runpy
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import pytest
from PIL import Image

from moana.cli import AVAILABLE_COMMANDS, PLANNED_COMMANDS, build_parser, main
from moana.cli import commands as cli_module
from moana.cli.commands import EXIT_INTERRUPTED, EXIT_OUTPUT_CLOSED, USAGE_MESSAGE
from moana.core import errors

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "specs" / "minimal.moana.json"
MINIMAL: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))

type Run = Callable[..., tuple[int, dict[str, Any], str]]


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Run:
    """Call ``main`` and return (exit code, the single stdout JSON object, stderr)."""

    def invoke(*arguments: str) -> tuple[int, dict[str, Any], str]:
        code = main(list(arguments))
        captured = capsys.readouterr()
        lines = captured.out.splitlines()
        assert len(lines) == 1, captured.out
        payload = json.loads(lines[0])
        assert isinstance(payload, dict)
        assert captured.out.isascii()
        assert "Traceback" not in captured.err
        return code, payload, captured.err

    return invoke


def write(path: Path, document: object) -> str:
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def variant(**changes: Any) -> dict[str, Any]:
    document = copy.deepcopy(MINIMAL)
    document.update(changes)
    return document


def over_budget() -> dict[str, Any]:
    operations = [
        {"id": f"r{index}", "type": "rect", "box": [0, 0, 2048, 2048], "color": "ink"}
        for index in range(30)
    ]
    document = variant(canvas={"width": 2048, "height": 2048, "profile": "strict"})
    document["layers"][0]["operations"] = operations
    return document


# --- success -----------------------------------------------------------------------


def test_validate(run: Run) -> None:
    code, payload, err = run("validate", str(EXAMPLE))
    assert (code, payload["ok"], payload["command"], err) == (0, True, "validate", "")
    document = payload["document"]
    assert (document["document_id"], document["width"], document["height"]) == (
        "sprite_demo",
        128,
        128,
    )
    assert document["snapshot_digest"].startswith("sha256:")


def test_inspect(run: Run) -> None:
    code, payload, _ = run("inspect", str(EXAMPLE))
    assert code == 0
    document = payload["document"]
    assert document["colors"] == ["ink", "cloth"]
    assert document["layers"][0]["operations"] == [
        {"color": "cloth", "id": "body_fill", "type": "rect"}
    ]
    assert document["budget"]["within_limits"] is True


def test_inspect_over_budget_reports_without_failing(run: Run, tmp_path: Path) -> None:
    code, payload, _ = run("inspect", write(tmp_path / "big.json", over_budget()))
    assert code == 0
    budget = payload["document"]["budget"]
    assert budget["within_limits"] is False
    assert "pixel_visits" in {item["resource"] for item in budget["exceeded"]}


def test_render_writes_no_file(run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    code, payload, _ = run("render", str(EXAMPLE))
    assert code == 0
    summary = payload["render"]
    assert (summary["width"], summary["height"], summary["warnings"]) == (128, 128, [])
    assert summary["digest"].startswith("sha256:")
    assert summary["provenance"]["document_id"] == "sprite_demo"
    assert list(tmp_path.iterdir()) == []


def test_render_reports_warnings(run: Run, tmp_path: Path) -> None:
    document = copy.deepcopy(MINIMAL)
    document["layers"][0]["operations"].append(
        {"id": "outside", "type": "rect", "box": [200, 200, 210, 210], "color": "ink"}
    )
    code, payload, _ = run("render", write(tmp_path / "w.json", document))
    assert code == 0
    assert payload["render"]["warnings"] == [
        {
            "code": "empty_bounds",
            "json_pointer": "/layers/0/operations/1",
            "message": "operation bounds are empty once clipped to the canvas",
        }
    ]


def test_export_and_scale(run: Run, tmp_path: Path) -> None:
    target = tmp_path / "sprite.png"
    code, payload, _ = run("export", str(EXAMPLE), str(target))
    assert code == 0
    manifest = payload["export"]
    assert (manifest["width"], manifest["height"], manifest["master"]) == (128, 128, True)
    assert manifest["path"] == str(target)
    assert manifest["source_digest"] == payload["render"]["digest"]
    with Image.open(target) as image:
        assert image.size == (128, 128)
        assert image.getpixel((40, 32)) == (0x36, 0xAF, 0xA5, 0xFF)
    code, payload, _ = run("export", str(EXAMPLE), str(tmp_path / "big.png"), "--scale", "3")
    assert code == 0
    assert (payload["export"]["width"], payload["export"]["warnings"]) == (384, ["scaled_preview"])


def test_export_overwrite(run: Run, tmp_path: Path) -> None:
    target = tmp_path / "sprite.png"
    target.write_bytes(b"previous")
    code, payload, _ = run("export", str(EXAMPLE), str(target))
    assert (code, payload["error"]["code"]) == (5, "EXPORT_ERROR")
    assert payload["error"]["context"]["reason"] == "exists"
    assert target.read_bytes() == b"previous"
    code, payload, _ = run("export", str(EXAMPLE), str(target), "--overwrite")
    assert code == 0
    assert target.read_bytes() != b"previous"


def test_capabilities_lists_available_apart_from_planned(run: Run) -> None:
    code, payload, _ = run("capabilities")
    assert code == 0
    listing = payload["capabilities"]
    assert listing["commands"] == ["capabilities", "export", "inspect", "render", "validate"]
    assert listing["planned_commands"] == ["edit"]
    assert listing["planned_functions"] == ["apply_edit"]
    assert set(listing["operations"]).isdisjoint(listing["planned_operations"])
    assert set(AVAILABLE_COMMANDS).isdisjoint(PLANNED_COMMANDS)


# --- help and version --------------------------------------------------------------


def test_help_distinguishes_available_and_planned(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    text = capsys.readouterr().out
    assert "available commands: capabilities, export, inspect, render, validate" in text
    assert "planned commands (NOT available in this version): edit" in text
    assert "PLANNED, NOT AVAILABLE" in text
    for code in ("0 success", "2 invalid input", "3 budget", "4 edit conflict", "5 I/O"):
        assert code in text


def test_subcommand_help_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["export", "--help"]) == 0
    assert "--overwrite" in capsys.readouterr().out
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.startswith("moana ")


def test_main_reads_sys_argv(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["moana", "validate", str(EXAMPLE)])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_module_entry_point(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["moana", "capabilities"])
    with pytest.raises(SystemExit) as caught:
        runpy.run_module("moana.cli", run_name="__main__", alter_sys=True)
    assert caught.value.code == 0
    assert json.loads(capsys.readouterr().out)["command"] == "capabilities"


def test_parser_is_static() -> None:
    parser = build_parser()
    assert parser.prog == "moana"


# --- failures ----------------------------------------------------------------------


def test_planned_command_is_unsupported(run: Run) -> None:
    code, payload, err = run("edit", "doc.json", "batch.json")
    assert code == 2
    assert payload["ok"] is False
    assert payload["command"] == "edit"
    error = payload["error"]
    assert (error["code"], error["exit_code"]) == ("UNSUPPORTED_OPERATION", 2)
    assert error["context"]["reason"] == "planned_command"
    assert "UNSUPPORTED_OPERATION" in err


@pytest.mark.parametrize(
    ("document", "code", "exit_code"),
    [
        (b"{not json", "VALIDATION_ERROR", 2),
        (variant(schema_version="9.0"), "UNSUPPORTED_VERSION", 2),
        (variant(materials=[{"id": "m"}]), "UNSUPPORTED_OPERATION", 2),
        (variant(seed=-1), "VALIDATION_ERROR", 2),
        (over_budget(), "BUDGET_EXCEEDED", 3),
    ],
)
@pytest.mark.parametrize("command", ["render", "export"])
def test_document_errors_map_to_exit_codes(
    run: Run, tmp_path: Path, document: object, code: str, exit_code: int, command: str
) -> None:
    path = tmp_path / "doc.json"
    if isinstance(document, bytes):
        path.write_bytes(document)
    else:
        write(path, document)
    arguments = [command, str(path)] + ([str(tmp_path / "o.png")] if command == "export" else [])
    status, payload, err = run(*arguments)
    assert (status, payload["ok"], payload["error"]["code"]) == (exit_code, False, code)
    assert payload["error"]["exit_code"] == exit_code
    assert err.startswith(f"moana: error: {code}:")
    assert not (tmp_path / "o.png").exists()


def test_reference_error_has_located_details(run: Run, tmp_path: Path) -> None:
    document = copy.deepcopy(MINIMAL)
    document["layers"][0]["operations"][0]["color"] = "missing"
    status, payload, _ = run("validate", write(tmp_path / "r.json", document))
    assert status == 2
    error = payload["error"]
    assert error["code"] == "REFERENCE_ERROR"
    assert error["json_pointer"] == "/layers/0/operations/0/color"
    assert [detail["json_pointer"] for detail in error["details"]] == [
        "/layers/0/operations/0/color"
    ]


def test_io_errors_do_not_leak_the_full_path(run: Run, tmp_path: Path) -> None:
    secret = tmp_path / "private parent"
    status, payload, err = run("validate", str(secret / "absent.json"))
    assert (status, payload["error"]["code"]) == (5, "READ_ERROR")
    assert payload["error"]["context"]["file_name"] == "absent.json"
    status, payload, err2 = run("export", str(EXAMPLE), str(secret / "missing dir" / "o.png"))
    assert (status, payload["error"]["code"]) == (5, "EXPORT_ERROR")
    for text in (json.dumps(payload), err, err2):
        assert "private parent" not in text


@pytest.mark.parametrize(
    ("arguments", "command"),
    [
        ([], None),
        (["unknown"], None),
        (["--debug"], None),
        (["validate"], "validate"),
        (["export", "a.json"], "export"),
        (["export", "a.json", "b.png", "--scale", "x"], "export"),
        (["export", "a.json", "b.png", "--scale", "0"], "export"),
        (["export", "a.json", "b.png", "--scale", "65"], "export"),
        (["export", "a.json", "b.png", "--scale", " 3"], "export"),
        (["export", "a.json", "b.png", "--scale", "٣"], "export"),  # ARABIC-INDIC 3
        (["export", "a.json", "b.png", "--scale", "1_0"], "export"),
        (["export", "a.json", "b.png", "--scale", "+2"], "export"),
        (["export", "a.json", "b.png", "--sc", "2"], "export"),  # no abbreviations
        (["--debug", "render", "a.json", "--frame", "f"], "render"),
        (["--deb", "render", "a.json"], "render"),
    ],
)
def test_usage_errors_are_invalid_input(
    run: Run, arguments: list[str], command: str | None
) -> None:
    status, payload, err = run(*arguments)
    assert status == 2
    assert payload["command"] == command
    error = payload["error"]
    assert (error["code"], error["context"], error["message"]) == (
        "VALIDATION_ERROR",
        {"reason": "usage"},
        USAGE_MESSAGE,
    )
    assert "usage: moana" in err
    assert "error:" in err  # argparse's explanation goes to stderr only
    assert "invalid" not in json.dumps(payload).replace(USAGE_MESSAGE, "")


def test_valid_scale_boundaries(run: Run, tmp_path: Path) -> None:
    for text, width in (("1", 128), ("16", 128 * 16), ("08", 128 * 8)):
        target = tmp_path / f"s{text}.png"
        status, payload, _ = run("export", str(EXAMPLE), str(target), "--scale", text)
        assert (status, payload["export"]["width"]) == (0, width)


def test_debug_is_accepted_after_the_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def crash(args: object) -> dict[str, object]:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(cli_module, "_validate", crash)
    assert main(["validate", str(EXAMPLE), "--debug"]) == 1
    captured = capsys.readouterr()
    assert "Traceback" in captured.err
    assert json.loads(captured.out)["error"]["code"] == "INTERNAL_ERROR"
    assert main(["validate", "--debug", str(EXAMPLE)]) == 1
    assert "Traceback" in capsys.readouterr().err


def test_edit_help_says_it_is_planned(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["edit", "--help"]) == 0
    text = capsys.readouterr().out
    assert "PLANNED, NOT AVAILABLE in this version" in text
    assert "UNSUPPORTED_OPERATION" in text


def test_wrong_extension_is_invalid_input(run: Run, tmp_path: Path) -> None:
    status, payload, _ = run("export", str(EXAMPLE), str(tmp_path / "o.jpg"))
    assert (status, payload["error"]["code"]) == (2, "VALIDATION_ERROR")


ERROR_EXIT_CODES = [
    (errors.MoanaError, 1),
    (errors.ValidationError, 2),
    (errors.OutOfBoundsError, 2),
    (errors.ReferenceError, 2),
    (errors.UnsupportedVersion, 2),
    (errors.UnsupportedOperation, 2),
    (errors.BudgetExceeded, 3),
    (errors.EditConflict, 4),
    (errors.ExportError, 5),
    (errors.ReadError, 5),
]


@pytest.mark.parametrize(("error", "exit_code"), ERROR_EXIT_CODES)
def test_every_domain_error_maps_to_its_exit_code(
    run: Run, monkeypatch: pytest.MonkeyPatch, error: type[errors.MoanaError], exit_code: int
) -> None:
    def failing(args: object) -> dict[str, object]:
        raise error("boom", context={"reason": "test", "bounds": (1, 2)})

    monkeypatch.setattr(cli_module, "_render", failing)
    status, payload, _ = run("render", str(EXAMPLE))
    assert status == exit_code == payload["error"]["exit_code"]
    assert payload["error"]["code"] == error.code
    assert payload["error"]["context"] == {"reason": "test", "bounds": [1, 2]}


def test_internal_error_hides_the_traceback_unless_debug(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def crash(args: object) -> dict[str, object]:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(cli_module, "_validate", crash)
    assert main(["validate", str(EXAMPLE)]) == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert "Traceback" not in captured.err
    assert "secret internal detail" not in captured.out + captured.err
    assert main(["--debug", "validate", str(EXAMPLE)]) == 1
    captured = capsys.readouterr()
    assert "Traceback" in captured.err
    assert "secret internal detail" in captured.err
    assert json.loads(captured.out)["error"]["code"] == "INTERNAL_ERROR"


def interrupt(*args: object, **kwargs: object) -> NoReturn:
    raise KeyboardInterrupt


@pytest.mark.parametrize(
    ("target", "arguments", "command"),
    [
        ("_inspect", ["inspect", str(EXAMPLE)], "inspect"),  # while working
        ("build_parser", ["inspect", str(EXAMPLE)], None),  # while parsing
        ("_fail", ["validate", "missing.json"], "validate"),  # while reporting an error
    ],
)
def test_interrupt_exits_130_with_an_interrupted_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    target: str,
    arguments: list[str],
    command: str | None,
) -> None:
    monkeypatch.setattr(cli_module, target, interrupt)
    assert main(arguments) == EXIT_INTERRUPTED == 130
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert (payload["ok"], payload["command"]) == (False, command)
    assert (payload["error"]["code"], payload["error"]["exit_code"]) == ("INTERRUPTED", 130)
    assert captured.err == "moana: interrupted\n"


class BrokenStream(io.StringIO):
    """A stream whose writes fail like a closed pipe; ``fileno`` is optional."""

    def __init__(self, descriptor: int | None = None) -> None:
        super().__init__()
        self.descriptor = descriptor

    def write(self, text: str) -> int:
        raise BrokenPipeError(errno.EPIPE, "broken pipe")

    def fileno(self) -> int:
        if self.descriptor is None:
            raise io.UnsupportedOperation("no descriptor")
        return self.descriptor


def test_closed_stdout_exits_with_the_documented_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "stdout", BrokenStream())
    assert main(["validate", str(EXAMPLE)]) == EXIT_OUTPUT_CLOSED == 5
    assert capsys.readouterr().err == (
        "moana: error: stdout is closed; the result was not delivered\n"
    )
    # With a real descriptor, it is pointed at the null device before returning.
    with (tmp_path / "out.txt").open("w", encoding="utf-8") as handle:
        monkeypatch.setattr(sys, "stdout", BrokenStream(handle.fileno()))
        assert main(["validate", "missing.json"]) == EXIT_OUTPUT_CLOSED
        os.write(handle.fileno(), b"discarded")
    assert (tmp_path / "out.txt").read_bytes() == b""


def test_closed_stderr_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stderr", BrokenStream())
    assert main(["validate", "missing.json"]) == 5


@pytest.mark.skipif(sys.platform == "win32", reason="SIGPIPE semantics of POSIX pipes")
def test_closed_pipe_in_a_real_process() -> None:
    reader, writer = os.pipe()
    os.close(reader)  # nobody will read: the first write fails with EPIPE
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    completed = subprocess.run(
        [sys.executable, "-m", "moana.cli", "inspect", str(EXAMPLE)],
        stdout=writer,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        env=environment,
        check=False,
        timeout=120,
    )
    os.close(writer)
    assert completed.returncode == EXIT_OUTPUT_CLOSED
    assert "Traceback" not in completed.stderr
    assert "Exception ignored" not in completed.stderr
    assert "stdout is closed" in completed.stderr
