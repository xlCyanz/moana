"""Write or check the versioned JSON Schema generated from moana.schema (MOANA-002).

The file in ``schemas/`` is a reviewed artifact: regenerate it only for an intended
contract change, review the diff for compatibility and bump the schema version when
documents valid before would become invalid.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support the documented direct invocation as well as python -m scripts.generate_schema.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moana.schema import SCHEMA_VERSION, document_json_schema
from scripts.validate import ROOT

SCHEMA_PATH = ROOT / "schemas" / f"moana-document-{SCHEMA_VERSION}.schema.json"


def render_schema() -> str:
    """Deterministic text of the generated schema."""
    return json.dumps(document_json_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args(argv)
    expected = render_schema()
    if args.check:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.is_file() else ""
        if current != expected:
            print(f"{SCHEMA_PATH.relative_to(ROOT)} is stale; run scripts/generate_schema.py")
            return 1
        print("JSON Schema up to date")
        return 0
    SCHEMA_PATH.parent.mkdir(exist_ok=True)
    SCHEMA_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print(f"Wrote {SCHEMA_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
