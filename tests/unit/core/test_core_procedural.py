"""Per-cell randomness keyed by identity in ``moana.core.procedural`` (§14, MOANA-010)."""

from __future__ import annotations

import hashlib

import pytest

from moana.core.errors import ValidationError
from moana.core.procedural import RNG_VERSION, cell_choice, cell_unit


def _hand_unit(text: str) -> int:
    """Oracle written from section 14: SHA-256 of the canonical array, first 8 bytes."""
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def test_unit_matches_the_section_14_formula_by_hand() -> None:
    assert RNG_VERSION == "cell-sha256-v1"
    expected = _hand_unit('[42,"grass",3,-7,1,"cell-sha256-v1"]')
    assert cell_unit(42, "grass", 3, -7, 1) == expected
    top = _hand_unit('[18446744073709551615,"a",0,0,0,"cell-sha256-v1"]')
    assert cell_unit(2**64 - 1, "a", 0, 0, 0) == top


@pytest.mark.parametrize("n", [1, 2, 3, 7, 256, 2**32, 2**64])
def test_choice_maps_u_with_integer_scaling(n: int) -> None:
    u = cell_unit(7, "noise", 10, 20, 2)
    assert cell_choice(7, "noise", 10, 20, 2, n) == u * n // 2**64
    assert 0 <= cell_choice(7, "noise", 10, 20, 2, n) < n
    assert cell_choice(7, "noise", 10, 20, 2, 1) == 0
    assert cell_choice(7, "noise", 10, 20, 2, 2**64) == u


def test_ac2_an_operation_sequence_depends_only_on_its_own_identity() -> None:
    """Adding another operation cannot shift this one's stream: there is no stream."""
    before = [cell_unit(5, "stone", x, y, 0) for y in range(4) for x in range(4)]
    others = [cell_unit(5, "moss", x, y, 0) for y in range(4) for x in range(4)]
    after = [cell_unit(5, "stone", x, y, 0) for y in range(4) for x in range(4)]
    assert before == after
    assert before != others
    assert len(set(before)) == len(before)


@pytest.mark.parametrize(
    "changed",
    [
        {"seed": 6},
        {"operation_id": "stone2"},
        {"x": 1},
        {"y": 1},
        {"channel": 1},
        {"version": "cell-sha256-v2"},
    ],
)
def test_every_key_part_changes_the_value(changed: dict[str, object]) -> None:
    base: dict[str, object] = {
        "seed": 5,
        "operation_id": "stone",
        "x": 0,
        "y": 0,
        "channel": 0,
        "version": RNG_VERSION,
    }
    assert cell_unit(**{**base, **changed}) != cell_unit(**base)  # type: ignore[arg-type]  # mapping of mixed values


def test_choices_are_spread_over_the_range() -> None:
    counts = [0] * 4
    for y in range(32):
        for x in range(32):
            counts[cell_choice(1, "dither", x, y, 0, 4)] += 1
    assert all(200 <= count <= 312 for count in counts)  # 1024 draws, 256 expected


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"seed": -1}, ValidationError),
        ({"seed": 2**64}, ValidationError),
        ({"seed": True}, ValidationError),
        ({"operation_id": "Bad"}, ValidationError),
        ({"x": 1_048_577}, ValidationError),
        ({"y": 1.0}, ValidationError),
        ({"channel": -1}, ValidationError),
        ({"version": ""}, TypeError),
        ({"version": 1}, TypeError),
    ],
)
def test_inputs_are_validated(kwargs: dict[str, object], error: type[Exception]) -> None:
    base: dict[str, object] = {"seed": 0, "operation_id": "a", "x": 0, "y": 0, "channel": 0}
    with pytest.raises(error):
        cell_unit(**{**base, **kwargs})  # type: ignore[arg-type]  # invalid on purpose


@pytest.mark.parametrize("n", [0, -1, 2**64 + 1, True])
def test_choice_range_is_validated(n: int) -> None:
    with pytest.raises(ValidationError):
        cell_choice(0, "a", 0, 0, 0, n)
