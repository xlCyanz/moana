"""Static ``moana`` command line (MOANA.md section 13, ADR-020).

``moana validate|inspect|render|export|capabilities`` compose :mod:`moana.api`; see
:mod:`moana.cli.commands` for the JSON output and exit codes. Nothing in the engine
imports this package.
"""

from moana.cli.commands import AVAILABLE_COMMANDS, PLANNED_COMMANDS, build_parser, main

__all__ = ["AVAILABLE_COMMANDS", "PLANNED_COMMANDS", "build_parser", "main"]
