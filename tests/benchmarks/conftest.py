"""Shared smoke run of the benchmark CLI (1 warmup, 3 samples, fresh processes)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .corpus import ROOT, Json

SMOKE_WARMUPS = 1
SMOKE_SAMPLES = 3
SMOKE_TIMEOUT_S = 300


@pytest.fixture(scope="session")
def smoke_output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run ``python -m tests.benchmarks run`` once for the static and animation cases."""
    output = tmp_path_factory.mktemp("benchmark") / "smoke"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.benchmarks",
            "run",
            "--warmups",
            str(SMOKE_WARMUPS),
            "--samples",
            str(SMOKE_SAMPLES),
            "--case",
            "static",
            "--case",
            "animation",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
        timeout=SMOKE_TIMEOUT_S,
    )
    assert completed.returncode == 0, completed.stderr
    return output


@pytest.fixture(scope="session")
def smoke_report(smoke_output: Path) -> Json:
    value: Json = json.loads(smoke_output.with_suffix(".json").read_text("utf-8"))
    return value
