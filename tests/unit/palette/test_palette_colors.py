"""RGBA values, canonical hex and linear luminance (MOANA-005, ADR-014)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from moanart.core import ValidationError
from moanart.palette import (
    LINEAR_SCALE,
    LUMINANCE_SCALE,
    PROFILE_MAX_COLORS,
    SRGB_TO_LINEAR,
    TRANSPARENT,
    Rgba,
)

channel = st.integers(0, 255)


class Sneaky(str):
    def __getitem__(self, key: object) -> str:  # hostile on purpose
        return "zz"


@given(r=channel, g=channel, b=channel, a=channel)
def test_hex_roundtrip_is_canonical_upper_case(r: int, g: int, b: int, a: int) -> None:
    color = Rgba(r, g, b, a)
    text = color.hex
    assert text == "#" + "".join(f"{v:02X}" for v in (r, g, b, a))
    assert Rgba.parse(text) == color
    assert Rgba.parse(text.lower()) == color


@pytest.mark.parametrize(
    "text",
    [
        "#ABCDEF",  # #RRGGBB is not canonical
        "ABCDEF12",
        "#ABCDEF123",
        "#GGFFFFFF",
        "#ABCDEF12\n",
        "#١٢٣٤٥٦٧٨",  # non-ASCII digits
        " #ABCDEF12",
        Sneaky("#ABCDEF12"),
        None,
        0xABCDEF12,
    ],
)
def test_parse_rejects_non_canonical_forms_without_echo(text: object) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Rgba.parse(text)
    assert excinfo.value.context == {"field": "rgba", "reason": "not_rgba_hex"}
    assert "ABCDEF" not in str(excinfo.value) and "ABCDEF" not in repr(excinfo.value.context)


@pytest.mark.parametrize(
    "channels", [(256, 0, 0, 0), (-1, 0, 0, 0), (True, 0, 0, 0), (1.0, 0, 0, 0)]
)
def test_channels_must_be_int_in_range(channels: tuple[object, ...]) -> None:
    with pytest.raises(ValidationError):
        Rgba(*channels)  # type: ignore[arg-type]  # invalid on purpose


def test_transparency_normalisation() -> None:
    residual = Rgba(10, 20, 30, 0)
    assert residual.is_transparent and not residual.is_opaque
    assert residual.normalized() == TRANSPARENT == Rgba(0, 0, 0, 0)
    assert residual != TRANSPARENT, "the value itself keeps its authored channels"
    opaque = Rgba(1, 2, 3, 255)
    assert opaque.normalized() is opaque and opaque.is_opaque
    assert Rgba(1, 2, 3, 128).normalized() == Rgba(1, 2, 3, 128)
    assert Rgba(1, 2, 3, 4).as_tuple() == (1, 2, 3, 4)


def _srgb_to_linear(value: int) -> float:
    """IEC 61966-2-1 transfer function, written independently of the module."""
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def test_linear_table_matches_the_srgb_formula() -> None:
    assert len(SRGB_TO_LINEAR) == 256
    for value, entry in enumerate(SRGB_TO_LINEAR):
        assert abs(entry - LINEAR_SCALE * _srgb_to_linear(value)) <= 0.5 + 1e-9
    assert list(SRGB_TO_LINEAR) == sorted(set(SRGB_TO_LINEAR)), "strictly increasing"
    assert (SRGB_TO_LINEAR[0], SRGB_TO_LINEAR[255]) == (0, LINEAR_SCALE)


def test_luminance_hand_oracle() -> None:
    assert Rgba(255, 255, 255, 255).luminance == LUMINANCE_SCALE
    assert Rgba(0, 0, 0, 255).luminance == 0
    assert Rgba(255, 0, 0, 255).luminance == 2126 * LINEAR_SCALE
    assert Rgba(0, 0, 255, 255).luminance == 722 * LINEAR_SCALE
    assert Rgba(255, 255, 255, 0).luminance == LUMINANCE_SCALE, "alpha is the caller's concern"


@pytest.mark.parametrize(
    ("darker", "lighter"),
    [
        # Encoded-value luma got these backwards (pixel-art review); CIE L* agrees.
        (Rgba(0x3C, 0x3C, 0x3C, 255), Rgba(0, 0, 255, 255)),  # L* 25.3 < 32.3
        (Rgba(0x6E, 0x6E, 0x6E, 255), Rgba(255, 0, 0, 255)),  # L* 46.4 < 53.2
    ],
)
def test_saturated_colors_order_like_cie_lightness(darker: Rgba, lighter: Rgba) -> None:
    assert darker.luminance < lighter.luminance


def test_profile_limits_are_read_only() -> None:
    assert dict(PROFILE_MAX_COLORS) == {"strict": 256, "rgba": 4096}
    with pytest.raises(TypeError):
        PROFILE_MAX_COLORS["strict"] = 1  # type: ignore[index]  # read-only on purpose
