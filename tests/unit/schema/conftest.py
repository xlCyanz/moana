"""Shared fixtures: the normative minimal document of MOANART.md section 12."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
MINIMAL_PATH = ROOT / "examples" / "specs" / "minimal.moanart.json"
MINIMAL: dict[str, Any] = json.loads(MINIMAL_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def minimal() -> dict[str, Any]:
    """A fresh, mutable copy of the minimal example document."""
    return copy.deepcopy(MINIMAL)
