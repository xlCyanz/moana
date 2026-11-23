"""``python -m moanart.cli`` runs the same command as the ``moanart`` entry point."""

from moanart.cli.commands import main

raise SystemExit(main())
