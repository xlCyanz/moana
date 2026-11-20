"""``python -m moana.cli`` runs the same command as the ``moana`` entry point."""

from moana.cli.commands import main

raise SystemExit(main())
