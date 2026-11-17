"""Run the same non-mutating quality gate locally and in CI."""

from __future__ import annotations

import argparse
import os
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


def tool_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.setdefault("UV_CACHE_DIR", str(ROOT / ".cache/uv"))
    environment.setdefault("UV_PYTHON_INSTALL_DIR", str(ROOT / ".tools/python"))
    environment.setdefault("UV_PYTHON_BIN_DIR", str(ROOT / ".tools/bin"))
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


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
        [
            python,
            "-m",
            "pytest",
            "--cov=moana",
            "--cov=scripts",
            "--cov-report=term-missing",
            "--cov-report=xml:artifacts/coverage.xml",
            "--junitxml=artifacts/pytest.xml",
        ],
    ]
    if not args.check_only:
        commands.append([uv_executable(), "build", "--no-build-isolation"])
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with (artifacts / "validation.log").open("w", encoding="utf-8", newline="\n") as log:
        for command in commands:
            heading = "+ " + " ".join(command)
            print(heading, flush=True)
            log.write(heading + "\n")
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=tool_environment(),
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
            )
            print(result.stdout, end="", flush=True)
            log.write(result.stdout)
            log.write(f"Exit code: {result.returncode}\n")
            log.flush()
            if result.returncode:
                return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
