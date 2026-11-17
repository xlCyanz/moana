"""Run the same non-mutating quality gate locally and in CI."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def uv_executable() -> str:
    local = ROOT / ".tools" / "bootstrap" / "bin" / "uv"
    found = shutil.which("uv")
    if found:
        return found
    if local.is_file():
        return str(local)
    raise RuntimeError("uv missing; run sh scripts/bootstrap.sh")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Skip distribution build")
    args = parser.parse_args()
    python = sys.executable
    commands = [
        [uv_executable(), "lock", "--check", "--offline"],
        [python, "-m", "ruff", "check", "."],
        [python, "-m", "ruff", "format", "--check", "."],
        [python, "-m", "mypy"],
        [python, "-m", "scripts.check_repository"],
        [python, "-m", "pytest", "--cov=moana", "--cov-report=term-missing"],
    ]
    if not args.check_only:
        commands.append([python, "-m", "build", "--no-isolation"])
    for command in commands:
        print("+ " + " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
