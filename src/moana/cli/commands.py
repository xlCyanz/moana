"""Static ``moana`` command over the public facade (MOANA.md section 13, ADR-020).

Every invocation prints exactly one JSON object on stdout (sorted keys, ASCII, one
line) with ``"ok"`` and ``"command"``; failures add an ``"error"`` object and a short
line on stderr. Only ``--help`` and ``--version`` print text for humans. The exit code
is the ``exit_code`` of the domain error (ADR-010, ADR-020): 0 success, 2 invalid input
(including usage errors and planned capabilities), 3 budget, 4 edit conflict, 5 I/O
(including a stdout that can no longer be written), 1 internal failure and 130 when
interrupted (an ``INTERRUPTED`` error object). Tracebacks are only printed with
``--debug``, accepted before or after the command.

The command opens only the paths passed as arguments and reports file names, never
resolved paths. ``--help`` lists available commands apart from planned ones; a planned
command (``edit``) answers ``UNSUPPORTED_OPERATION``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from collections.abc import Callable, Mapping, Sequence
from typing import Final, NoReturn

from moana import __version__
from moana.api import (
    MAX_SCALE,
    PLANNED_FUNCTIONS,
    RenderResult,
    capabilities,
    export_png,
    inspect_document,
    load_document,
    render,
    snapshot_digest,
)
from moana.core.errors import ErrorDetail, MoanaError, UnsupportedOperation, ValidationError

__all__ = [
    "AVAILABLE_COMMANDS",
    "EXIT_INTERRUPTED",
    "EXIT_OUTPUT_CLOSED",
    "PLANNED_COMMANDS",
    "USAGE_MESSAGE",
    "build_parser",
    "main",
]

AVAILABLE_COMMANDS: Final = ("capabilities", "export", "inspect", "render", "validate")
PLANNED_COMMANDS: Final = ("edit",)

EXIT_INTERRUPTED: Final = 130
"""Exit code after Ctrl+C (128 + SIGINT); stdout carries an ``INTERRUPTED`` error."""
EXIT_OUTPUT_CLOSED: Final = 5
"""Exit code when stdout cannot be written (closed pipe): an I/O failure of section 13."""

USAGE_MESSAGE: Final = "invalid command line usage"
"""Fixed message of a usage error; argparse's own explanation goes to stderr only."""

_DESCRIPTION: Final = (
    "Deterministic pixel art engine: validate, inspect, render and export static "
    "Moana documents (schema 1.0). Each command prints one JSON object on stdout."
)
_EPILOG: Final = (
    "available commands: capabilities, export, inspect, render, validate\n"
    "planned commands (NOT available in this version): edit\n"
    "\n"
    "exit codes: 0 success, 2 invalid input or unsupported capability, 3 budget "
    "exceeded,\n"
    "            4 edit conflict, 5 I/O error, 1 internal error, 130 interrupted"
)
_SCALE_TEXT: Final = re.compile(r"[0-9]{1,2}", re.ASCII)

type _Payload = dict[str, object]
type _Handler = Callable[[argparse.Namespace], _Payload]
type _Commands = argparse._SubParsersAction[_Parser]


class _UsageError(Exception):
    """Raised instead of argparse's own exit so usage errors become JSON too."""

    def __init__(self, command: str | None) -> None:
        super().__init__(command)
        self.command = command


class _OutputClosed(Exception):
    """stdout can no longer be written; nothing else is emitted on it."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        _, _, command = self.prog.partition(" ")
        raise _UsageError(command or None)


def _render_summary(result: RenderResult) -> _Payload:
    return {
        "digest": result.digest,
        "height": result.height,
        "provenance": result.provenance.to_mapping(),
        "renderer_version": result.renderer_version,
        "warnings": [
            {"code": item.code, "json_pointer": item.json_pointer, "message": item.message}
            for item in result.warnings
        ],
        "width": result.width,
    }


def _validate(args: argparse.Namespace) -> _Payload:
    document = load_document(args.document)
    summary: _Payload = {
        "document_id": document.id,
        "height": document.canvas.height,
        "profile": document.canvas.profile,
        "revision": document.revision,
        "schema_version": document.schema_version,
        "snapshot_digest": snapshot_digest(document),
        "width": document.canvas.width,
    }
    return {"document": summary}


def _inspect(args: argparse.Namespace) -> _Payload:
    return {"document": inspect_document(load_document(args.document)).to_mapping()}


def _render(args: argparse.Namespace) -> _Payload:
    return {"render": _render_summary(render(load_document(args.document)))}


def _export(args: argparse.Namespace) -> _Payload:
    result = render(load_document(args.document))
    manifest = export_png(result, args.output, scale=args.scale, overwrite=args.overwrite)
    return {"export": manifest.to_mapping(), "render": _render_summary(result)}


def _capabilities(args: argparse.Namespace) -> _Payload:
    listing = capabilities().to_mapping()
    listing["commands"] = list(AVAILABLE_COMMANDS)
    listing["planned_commands"] = list(PLANNED_COMMANDS)
    return {"capabilities": listing}


def _planned(args: argparse.Namespace) -> _Payload:
    raise UnsupportedOperation(
        "this command is planned but not available in this version",
        context={
            "reason": "planned_command",
            "command": args.command,
            "planned_functions": PLANNED_FUNCTIONS,
        },
    )


def _scale(text: str) -> int:
    """ASCII decimal ``1..MAX_SCALE``: no sign, spaces, underscores or other digits."""
    value = int(text, 10) if _SCALE_TEXT.fullmatch(text) else 0
    if not 1 <= value <= MAX_SCALE:
        raise argparse.ArgumentTypeError(f"scale must be an integer 1..{MAX_SCALE}")
    return value


def _command(
    commands: _Commands,
    name: str,
    handler: _Handler,
    summary: str,
    *,
    description: str | None = None,
    document: bool = True,
) -> argparse.ArgumentParser:
    parser = commands.add_parser(
        name, help=summary, description=description or summary, allow_abbrev=False
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print the traceback of an internal error",
    )
    if document:
        parser.add_argument("document", help="path of a .moana.json document (schema 1.0)")
    parser.set_defaults(handler=handler)
    return parser


def build_parser() -> argparse.ArgumentParser:
    """The ``moana`` argument parser; usage errors raise instead of exiting."""
    parser = _Parser(
        prog="moana",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=f"moana {__version__}")
    parser.add_argument(
        "--debug", action="store_true", help="print the traceback of an internal error"
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    _command(commands, "validate", _validate, "validate and normalise a document")
    _command(
        commands,
        "inspect",
        _inspect,
        "summarise layers, palette and the render budget (draws nothing)",
    )
    _command(commands, "render", _render, "render in memory and report the digest (writes no file)")
    export = _command(commands, "export", _export, "render and write an RGBA PNG atomically")
    export.add_argument("output", help="destination .png path (never replaced by default)")
    export.add_argument(
        "--scale",
        type=_scale,
        default=1,
        help=f"integer nearest-neighbour scale 1..{MAX_SCALE}; >1 is a preview (default 1)",
    )
    export.add_argument("--overwrite", action="store_true", help="replace an existing file")
    _command(
        commands,
        "capabilities",
        _capabilities,
        "list available and planned capabilities",
        document=False,
    )
    edit = _command(
        commands,
        "edit",
        _planned,
        "PLANNED, NOT AVAILABLE: apply an edit batch (fails with exit code 2)",
        description=(
            "PLANNED, NOT AVAILABLE in this version: editing documents with batches "
            "(apply_edit). Any invocation answers UNSUPPORTED_OPERATION with exit code 2."
        ),
        document=False,
    )
    edit.add_argument("arguments", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    return parser


def _detail(detail: ErrorDetail) -> _Payload:
    return {
        "code": detail.code,
        "context": dict(detail.context),
        "json_pointer": detail.json_pointer,
        "message": detail.message,
    }


def _error_payload(error: MoanaError) -> _Payload:
    return {
        "code": error.code,
        "context": dict(error.context),
        "details": [_detail(detail) for detail in error.details],
        "exit_code": error.exit_code,
        "json_pointer": error.json_pointer,
        "message": error.message,
    }


def _silence_stdout() -> None:
    """Point the stdout descriptor at the null device so the final flush cannot fail."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
    except (OSError, ValueError):  # no real descriptor (embedded or captured stdout)
        pass


def _emit(payload: Mapping[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=True) + "\n"
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except OSError:  # BrokenPipeError and any other failure to deliver the result
        _silence_stdout()
        raise _OutputClosed from None


def _stderr(text: str) -> None:
    try:
        sys.stderr.write(text)
        sys.stderr.flush()
    except OSError:
        pass


def _fail(command: str | None, error: MoanaError) -> int:
    _emit({"command": command, "error": _error_payload(error), "ok": False})
    _stderr(f"moana: error: {error.code}: {error.message}\n")
    return error.exit_code


def _interrupted(command: str | None) -> int:
    error: _Payload = {
        "code": "INTERRUPTED",
        "context": {"reason": "keyboard_interrupt"},
        "details": [],
        "exit_code": EXIT_INTERRUPTED,
        "json_pointer": None,
        "message": "interrupted by the user",
    }
    _stderr("moana: interrupted\n")
    _emit({"command": command, "error": error, "ok": False})
    return EXIT_INTERRUPTED


def _internal(command: str, debug: bool) -> int:
    if debug:
        _stderr(traceback.format_exc())
    internal = MoanaError(
        "unexpected internal error; rerun with --debug for the traceback",
        context={"reason": "internal"},
    )
    return _fail(command, internal)


def _named_command(arguments: list[str]) -> str | None:
    """The command of a rejected command line: global options are flags, so it comes first."""
    first = next((argument for argument in arguments if not argument.startswith("-")), None)
    return first if first in AVAILABLE_COMMANDS + PLANNED_COMMANDS else None


def _run(arguments: list[str], state: dict[str, str | None]) -> int:
    try:
        args = build_parser().parse_args(arguments)
    except _UsageError as exc:
        named = exc.command or _named_command(arguments)
        return _fail(named, ValidationError(USAGE_MESSAGE, context={"reason": "usage"}))
    except SystemExit as exc:  # --help and --version print and exit successfully
        return exc.code if isinstance(exc.code, int) else 0
    command: str = args.command
    state["command"] = command
    handler: _Handler = args.handler
    try:
        payload = handler(args)
    except MoanaError as error:
        return _fail(command, error)
    except Exception:
        return _internal(command, args.debug)
    _emit({"command": command, "ok": True, **payload})
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``moana`` command and return its exit code (never raises by default)."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    state: dict[str, str | None] = {"command": None}
    try:
        try:
            return _run(arguments, state)
        except KeyboardInterrupt:
            return _interrupted(state["command"])
    except _OutputClosed:
        _stderr("moana: error: stdout is closed; the result was not delivered\n")
        return EXIT_OUTPUT_CLOSED
