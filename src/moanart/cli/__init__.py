"""Static ``moanart`` command line (MOANART.md section 13, ADR-020).

``moanart validate|inspect|render|export|capabilities`` compose :mod:`moanart.api`; see
:mod:`moanart.cli.commands` for the JSON output and exit codes. Nothing in the engine
imports this package.
"""

from moanart.cli.commands import AVAILABLE_COMMANDS, PLANNED_COMMANDS, build_parser, main

__all__ = ["AVAILABLE_COMMANDS", "PLANNED_COMMANDS", "build_parser", "main"]
