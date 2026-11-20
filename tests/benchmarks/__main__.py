"""Command line of the benchmarks: ``uv run python -m tests.benchmarks <command>``.

``run``      measure the corpus in fresh processes and write ``<output>.json``/``.md``.
``compare``  compare two reports (informational; exit 2 when not comparable).
``worker``   internal: measure one case in this process and print JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .compare import compare_reports, comparison_text
from .corpus import case_names
from .measure import DEFAULT_SAMPLES, DEFAULT_WARMUPS
from .measure import main as worker_main
from .report import run_benchmark, write_report

DEFAULT_OUTPUT = Path("artifacts") / "benchmarks" / "benchmark"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tests.benchmarks", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="measure the corpus and write the report")
    run.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    run.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    run.add_argument("--case", action="append", choices=case_names(), dest="cases")
    run.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="path without suffix")
    compare = commands.add_parser("compare", help="compare two reports")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    return parser


def _load(path: Path) -> Any:
    """The JSON value of ``path``; an unreadable or invalid file becomes ``None``."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch ``run``, ``compare`` or the internal ``worker``; return the exit code."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["worker"]:
        return worker_main(arguments[1:])
    parser = _parser()
    args = parser.parse_args(arguments)
    if args.command == "run":
        if args.warmups < 0 or args.samples < 1:
            parser.error("--warmups must be >= 0 and --samples >= 1")
        if args.cases is not None and len(set(args.cases)) != len(args.cases):
            parser.error("--case names a case more than once")
        report = run_benchmark(args.cases, warmups=args.warmups, samples=args.samples)
        json_path, md_path = write_report(report, args.output)
        sys.stdout.write(md_path.read_text(encoding="utf-8"))
        sys.stdout.write(f"\nWrote {json_path.name} and {md_path.name}\n")
        return 0
    result = compare_reports(_load(args.before), _load(args.after))
    sys.stdout.write(comparison_text(result))
    return 0 if result["comparable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
