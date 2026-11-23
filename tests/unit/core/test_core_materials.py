"""Grid hashing of material textures (MOANART.md section 14, ADR-030).

:func:`moanart.core.procedural.cell_choices` must equal :func:`cell_choice` cell by cell;
the oracle here is ``hashlib`` over the canonical JSON key, independent of both.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moanart.core.budget import Deadline
from moanart.core.coordinates import MAX_COORDINATE, Box
from moanart.core.errors import BudgetExceeded, ValidationError
from moanart.core.procedural import MAX_GRID_CHOICES, cell_choice, cell_choices


def oracle(seed: int, op: str, x: int, y: int, channel: int, n: int) -> int:
    key = json.dumps([seed, op, x, y, channel, "cell-sha256-v1"], separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") * n // 2**64


@settings(max_examples=30, deadline=None)
@given(
    seed=st.integers(0, 2**64 - 1),
    x0=st.integers(-30, 30),
    y0=st.integers(-30, 30),
    width=st.integers(1, 6),
    height=st.integers(1, 6),
    channel=st.integers(0, 3),
    n=st.integers(1, MAX_GRID_CHOICES),
)
def test_grid_equals_scalar_cell_choice_and_the_oracle(
    seed: int, x0: int, y0: int, width: int, height: int, channel: int, n: int
) -> None:
    span = Box(x0, y0, x0 + width, y0 + height)
    values = cell_choices(seed, "op_1", span, channel, n)
    expected = [
        oracle(seed, "op_1", x, y, channel, n)
        for y in range(span.y0, span.y1)
        for x in range(span.x0, span.x1)
    ]
    assert list(values) == expected
    assert values[0] == cell_choice(seed, "op_1", x0, y0, channel, n)


def test_grid_reaches_the_coordinate_limits() -> None:
    edge = MAX_COORDINATE
    span = Box(edge - 1, -edge, edge + 1, -edge + 1)
    assert list(cell_choices(7, "a", span, 0, 256)) == [
        oracle(7, "a", edge - 1, -edge, 0, 256),
        oracle(7, "a", edge, -edge, 0, 256),
    ]


def test_grid_validates_its_inputs() -> None:
    span = Box(0, 0, 2, 2)
    with pytest.raises(TypeError, match="span"):
        cell_choices(0, "a", (0, 0, 1, 1), 0, 2)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        cell_choices(0, "a", span, 0, MAX_GRID_CHOICES + 1)
    with pytest.raises(ValidationError):
        cell_choices(0, "a", span, 0, 0)
    with pytest.raises(ValidationError):
        cell_choices(-1, "a", span, 0, 2)
    with pytest.raises(ValidationError):
        cell_choices(0, "Bad", span, 0, 2)
    with pytest.raises(ValidationError):
        cell_choices(0, "a", span, -1, 2)
    with pytest.raises(TypeError, match="deadline"):
        cell_choices(0, "a", span, 0, 2, deadline=1)  # type: ignore[arg-type]


def test_grid_checks_the_deadline_between_rows() -> None:
    ticks = iter([0.0, 0.0, 10.0])
    deadline = Deadline(1, clock=lambda: next(ticks))
    with pytest.raises(BudgetExceeded) as raised:
        cell_choices(0, "a", Box(0, 0, 1, 40), 0, 2, deadline=deadline)
    assert raised.value.context["resource"] == "time"
    assert cell_choices(0, "a", Box(0, 0, 3, 3), 0, 2, deadline=Deadline(60_000)) == bytes(
        cell_choice(0, "a", x, y, 0, 2) for y in range(3) for x in range(3)
    )
