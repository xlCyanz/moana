"""RenderLimits and the cooperative Deadline (MOANA.md section 20)."""

import pickle
from typing import Any

import pytest

from moana.core import errors
from moana.core.budget import (
    DEFAULT_MAX_BUFFER_BYTES,
    DEFAULT_MAX_FRAME_PIXELS,
    DEFAULT_MAX_PIXEL_VISITS,
    DEFAULT_RENDER_LIMITS,
    Deadline,
    RenderLimits,
)
from moana.core.limits import MAX_LAYERS, MAX_OPERATIONS, GeometryLimits


def test_defaults_match_section_20() -> None:
    assert DEFAULT_MAX_BUFFER_BYTES == 256 * 2**20
    assert DEFAULT_MAX_PIXEL_VISITS == 100_000_000
    assert DEFAULT_MAX_FRAME_PIXELS == 16_777_216
    limits = DEFAULT_RENDER_LIMITS
    assert (limits.max_operations, limits.max_layers) == (MAX_OPERATIONS, MAX_LAYERS)
    assert limits.geometry == GeometryLimits()
    assert limits.host_override is False


def test_budgets_can_be_lowered_but_not_raised_without_host_override() -> None:
    lowered = RenderLimits(max_buffer_bytes=1, max_pixel_visits=1, max_frame_pixels=1)
    assert lowered.max_pixel_visits == 1
    for name in ("max_buffer_bytes", "max_pixel_visits", "max_frame_pixels"):
        default = getattr(DEFAULT_RENDER_LIMITS, name)
        with pytest.raises(errors.ValidationError) as raised:
            RenderLimits(**{name: default + 1})
        assert raised.value.context["maximum"] == default
        assert getattr(RenderLimits(host_override=True, **{name: default + 1}), name) > default


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_operations": MAX_OPERATIONS + 1, "host_override": True},
        {"max_layers": MAX_LAYERS + 1, "host_override": True},
        {"max_pixel_visits": 0},
        {"max_pixel_visits": True},
        {"max_buffer_bytes": 2**62 + 1, "host_override": True},
    ],
)
def test_invalid_limits_are_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(errors.ValidationError):
        RenderLimits(**overrides)


def test_limit_types_are_checked() -> None:
    with pytest.raises(TypeError):
        RenderLimits(geometry=object())  # type: ignore[arg-type]  # runtime guard
    with pytest.raises(TypeError):
        RenderLimits(host_override=1)  # type: ignore[arg-type]  # runtime guard


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_deadline_expires_at_its_limit_and_reports_resource() -> None:
    clock = FakeClock()
    deadline = Deadline(250, clock=clock)
    assert deadline.milliseconds == 250
    clock.now = 100.249
    deadline.checkpoint("layer")
    assert not deadline.expired()
    clock.now = 100.25
    assert deadline.expired()
    with pytest.raises(errors.BudgetExceeded) as raised:
        deadline.checkpoint("layer")
    assert dict(raised.value.context) == {
        "resource": "time",
        "limit": 250,
        "unit": "ms",
        "stage": "layer",
    }
    clone = pickle.loads(pickle.dumps(raised.value))
    assert clone.context == raised.value.context


@pytest.mark.parametrize("milliseconds", [0, -1, True, 1.5])
def test_deadline_requires_positive_integer_milliseconds(milliseconds: object) -> None:
    with pytest.raises(errors.ValidationError):
        Deadline(milliseconds)  # type: ignore[arg-type]  # runtime guard


def test_default_deadline_uses_monotonic_clock() -> None:
    assert not Deadline(60_000).expired()


def test_deadline_rejects_bad_clock_and_stage() -> None:
    with pytest.raises(TypeError):
        Deadline(10, clock=1.0)  # type: ignore[arg-type]  # runtime guard
    with pytest.raises(TypeError):
        Deadline(10).checkpoint(1)  # type: ignore[arg-type]  # runtime guard
