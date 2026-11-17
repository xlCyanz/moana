"""Palettes, ramps, profiles, edits, warnings and explicit remaps (MOANA-005)."""

from __future__ import annotations

import copy
import json
import pickle
from typing import Any

import pytest

from moana.core import MAX_RAMP_ENTRIES, ValidationError
from moana.core import errors as core_errors
from moana.palette import (
    RAMP_LUMINANCE_NOT_INCREASING,
    RAMP_PARTIAL_ALPHA_STEP,
    RAMP_TRANSPARENT_STEP,
    ColorProfile,
    ColorRemap,
    Palette,
    PaletteColor,
    Ramp,
    Rgba,
)

BLACK = Rgba(0, 0, 0, 255)
DARK = Rgba(40, 40, 60, 255)
MID = Rgba(120, 120, 140, 255)
LIGHT = Rgba(220, 220, 230, 255)


def colors(*pairs: tuple[str, Rgba]) -> tuple[PaletteColor, ...]:
    return tuple(PaletteColor(color_id, rgba) for color_id, rgba in pairs)


def sample(profile: ColorProfile = "strict") -> Palette:
    return Palette(
        "main",
        profile,
        colors(("ink", BLACK), ("shade", DARK), ("base", MID), ("light", LIGHT)),
        (Ramp("skin", ("shade", "base", "light")),),
    )


def with_ramps(palette: Palette, *ramps: Ramp) -> Palette:
    return Palette(palette.id, palette.profile, palette.colors, ramps)


def mapping(n: int, *, alpha: str = "FF") -> dict[str, Any]:
    return {
        "id": "main",
        "colors": [{"id": f"c{i}", "rgba": f"#{i % 256:02X}0000{alpha}"} for i in range(n)],
        "ramps": [],
    }


def reasons(error: core_errors.MoanaError) -> list[tuple[str | None, str]]:
    return [(d.json_pointer, str(d.context["reason"])) for d in error.details]


# --- lookup and identity -------------------------------------------------------------


def test_lookup_by_id_and_stable_index() -> None:
    palette = sample()
    assert [palette.index_of(c) for c in ("ink", "shade", "base", "light")] == [0, 1, 2, 3]
    assert palette.color("base") == MID
    assert palette.ramp("skin") == (DARK, MID, LIGHT)
    assert "ink" in palette and "nope" not in palette and 3 not in palette


@pytest.mark.parametrize("unknown", ["nope", 3, None])
def test_unknown_ids_raise_reference_error(unknown: object) -> None:
    palette = sample()
    with pytest.raises(core_errors.ReferenceError) as excinfo:
        palette.color(unknown)  # type: ignore[arg-type]  # invalid on purpose
    assert excinfo.value.context == {"reason": "unknown_color"}
    with pytest.raises(core_errors.ReferenceError) as ramp_error:
        palette.ramp("nope")
    assert ramp_error.value.context == {"reason": "unknown_ramp"}


# --- T1: duplicate values vs duplicate IDs -------------------------------------------


def test_same_value_different_ids_are_independent_colors() -> None:
    palette = Palette("main", "strict", colors(("eye_l", BLACK), ("eye_r", BLACK)))
    assert palette.ids_with_value(BLACK) == ("eye_l", "eye_r")
    edited = palette.replace_color("eye_l", MID)
    assert edited.color("eye_l") == MID and edited.color("eye_r") == BLACK


def test_duplicate_color_ids_are_invalid() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Palette("main", "strict", colors(("ink", BLACK), ("ink", MID)))
    assert reasons(excinfo.value) == [("/colors/1/id", "duplicate_id")]
    assert excinfo.value.details[0].context["first"] == "/colors/0/id"
    assert excinfo.value.context == {"issue_count": 1}


def test_ids_are_unique_across_palette_colors_and_ramps() -> None:
    pair = ("ink", "mid")
    ramps = (Ramp("ink", pair), Ramp("r", pair), Ramp("r", pair))
    with pytest.raises(ValidationError) as excinfo:
        Palette("base", "strict", colors(("ink", BLACK), ("base", MID), ("mid", MID)), ramps)
    assert [(d.json_pointer, d.context["first"]) for d in excinfo.value.details] == [
        ("/colors/1/id", "/id"),
        ("/ramps/0/id", "/colors/0/id"),
        ("/ramps/2/id", "/ramps/1/id"),
    ]


def test_transparent_values_match_after_normalisation() -> None:
    palette = Palette("main", "strict", colors(("clear", Rgba(9, 9, 9, 0)), ("ink", BLACK)))
    assert palette.ids_with_value(Rgba(0, 0, 0, 0)) == ("clear",)
    assert palette.contains_value(Rgba(200, 1, 1, 0))
    assert not palette.contains_value(Rgba(9, 9, 9, 255))


# --- AC1: strict profile and ramp references -----------------------------------------


@pytest.mark.parametrize("alpha", [1, 128, 254])
def test_strict_rejects_intermediate_alpha(alpha: int) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Palette("main", "strict", colors(("ink", BLACK), ("glass", Rgba(1, 2, 3, alpha))))
    assert reasons(excinfo.value) == [("/colors/1/rgba", "partial_alpha")]
    assert excinfo.value.details[0].context["profile"] == "strict"
    rgba_palette = Palette("main", "rgba", colors(("glass", Rgba(1, 2, 3, alpha))))
    assert rgba_palette.color("glass").a == alpha


def test_strict_accepts_alpha_0_and_255() -> None:
    palette = Palette("main", "strict", colors(("clear", Rgba(0, 0, 0, 0)), ("ink", BLACK)))
    assert len(palette.colors) == 2


def test_missing_ramp_reference_is_a_reference_error() -> None:
    with pytest.raises(core_errors.ReferenceError) as excinfo:
        Palette("main", "strict", colors(("ink", BLACK)), (Ramp("r", ("ink", "ghost")),))
    assert reasons(excinfo.value) == [("/ramps/0/colors/1", "unknown_color")]


def test_validation_problems_take_precedence_and_are_sorted() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Palette(
            "main",
            "strict",
            colors(("ink", Rgba(0, 0, 0, 7))),
            (Ramp("short", ("ink",)), Ramp("r", ("ghost", "ink", "ink"))),
        )
    assert reasons(excinfo.value) == [
        ("/colors/0/rgba", "partial_alpha"),
        ("/ramps/0/colors", "too_short"),
        ("/ramps/1/colors/0", "unknown_color"),
        ("/ramps/1/colors/2", "duplicate_ramp_color"),
    ]
    assert excinfo.value.json_pointer == "/colors/0/rgba"
    assert excinfo.value.context == {"issue_count": 4}


def test_ramp_length_bounds() -> None:
    palette = Palette.from_mapping(mapping(4096), profile="rgba")
    all_ids = tuple(c.id for c in palette.colors)
    assert len(with_ramps(palette, Ramp("r", all_ids)).ramps[0].colors) == 4096
    assert with_ramps(palette, Ramp("r", all_ids[:2])).ramps
    with pytest.raises(ValidationError) as excinfo:
        Ramp("r", (*all_ids, "extra"))
    assert excinfo.value.context["reason"] == "too_many"


def test_invalid_construction_arguments() -> None:
    with pytest.raises(ValidationError):
        Palette("main", "cmyk", colors(("ink", BLACK)))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Palette("main", "strict", [PaletteColor("ink", BLACK)])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Palette("main", "strict", colors(("ink", BLACK)), [Ramp("r", ("ink", "ink"))])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        PaletteColor("ink", "#000000FF")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Ramp("r", ["a", "b"])  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        PaletteColor("Ink", BLACK)
    with pytest.raises(ValidationError):
        Ramp("r", ("ok", "Bad"))


# --- T2: cardinality 256 / 4096 ------------------------------------------------------


@pytest.mark.parametrize(
    ("profile", "limit", "reason"), [("strict", 256, "too_many"), ("rgba", 4096, "too_long")]
)
def test_profile_color_limits_exact_and_plus_one(
    profile: ColorProfile, limit: int, reason: str
) -> None:
    ok = Palette.from_mapping(mapping(limit), profile=profile)
    assert len(ok.colors) == limit
    with pytest.raises(ValidationError) as excinfo:
        Palette.from_mapping(mapping(limit + 1), profile=profile)
    assert reasons(excinfo.value) == [("/colors", reason)]


def test_strict_limit_also_applies_to_the_constructor() -> None:
    rgba = Palette.from_mapping(mapping(257), profile="rgba")
    with pytest.raises(ValidationError) as excinfo:
        Palette("main", "strict", rgba.colors)
    assert reasons(excinfo.value) == [("/colors", "too_many")]


def test_empty_palette_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Palette("main", "rgba", ())
    assert reasons(excinfo.value) == [("/colors", "too_short")]


def test_ramp_budget_is_checked_before_walking_members() -> None:
    members: list[object] = [7] * 4096  # invalid IDs: walking them would add details
    data = mapping(2)
    data["ramps"] = [
        {"id": f"r{i}", "colors": members} for i in range(MAX_RAMP_ENTRIES // 4096 + 1)
    ]
    with pytest.raises(ValidationError) as excinfo:
        Palette.from_mapping(data, profile="rgba")
    assert reasons(excinfo.value) == [("/ramps", "too_many")]
    two = Palette.from_mapping(mapping(2), profile="rgba")
    ramps = tuple(Ramp(f"r{i}", ("c0", "c1")) for i in range(MAX_RAMP_ENTRIES // 2 + 1))
    with pytest.raises(ValidationError) as constructor_error:
        with_ramps(two, *ramps)
    assert reasons(constructor_error.value) == [("/ramps", "too_many")]


# --- AC2: serialisation --------------------------------------------------------------


@pytest.mark.parametrize("profile", ["strict", "rgba"])
def test_mapping_roundtrip_preserves_order_values_and_identity(profile: ColorProfile) -> None:
    palette = sample(profile)
    data = json.loads(json.dumps(palette.to_mapping()))
    assert data == {
        "id": "main",
        "colors": [
            {"id": "ink", "rgba": "#000000FF"},
            {"id": "shade", "rgba": "#28283CFF"},
            {"id": "base", "rgba": "#78788CFF"},
            {"id": "light", "rgba": "#DCDCE6FF"},
        ],
        "ramps": [{"id": "skin", "colors": ["shade", "base", "light"]}],
    }
    loaded = Palette.from_mapping(data, profile=palette.profile)
    assert loaded == palette
    assert [c.id for c in loaded.colors] == ["ink", "shade", "base", "light"]


def test_from_mapping_canonicalises_lower_case_and_defaults_ramps() -> None:
    loaded = Palette.from_mapping(
        {"id": "p", "colors": [{"id": "a", "rgba": "#abcdef80"}]}, profile="rgba"
    )
    assert loaded.color("a").hex == "#ABCDEF80" and loaded.ramps == ()


class Hostile(dict[str, object]):
    def __getitem__(self, key: str) -> object:
        raise KeyError(key)


class SneakyStr(str):
    pass


ONE = [{"id": "a", "rgba": "#000000FF"}]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ([], [("", "wrong_type")]),
        ({1: "x"}, [("", "wrong_type")]),
        (Hostile(id="p", colors=[]), [("", "wrong_type")]),
        ({"colors": []}, [("/id", "missing")]),
        ({"id": "p"}, [("/colors", "missing")]),
        ({"id": "p", "colors": [], "extra": 1}, [("", "unknown_field")]),
        ({"id": "P", "colors": ONE}, [("/id", "invalid_id")]),
        ({"id": SneakyStr("p"), "colors": ONE}, [("/id", "invalid_id")]),
        ({"id": "p", "colors": {}}, [("/colors", "wrong_type")]),
        ({"id": "p", "colors": ("x",)}, [("/colors", "wrong_type")]),
        ({"id": "p", "colors": ["x"]}, [("/colors/0", "wrong_type")]),
        (
            {"id": "p", "colors": [{"id": "a", "rgba": "#000000"}]},
            [("/colors/0/rgba", "not_rgba_hex")],
        ),
        ({"id": "p", "colors": [{"id": "a", "rgba": True}]}, [("/colors/0/rgba", "not_rgba_hex")]),
        ({"id": "p", "colors": [{"id": "a"}]}, [("/colors/0/rgba", "missing")]),
        ({"id": "p", "colors": ONE, "ramps": [{"id": "r"}]}, [("/ramps/0/colors", "missing")]),
        (
            {"id": "p", "colors": ONE, "ramps": [{"id": "r", "colors": ["a", 7]}]},
            [("/ramps/0/colors/1", "invalid_id")],
        ),
        ({"id": "p", "colors": ONE, "ramps": ["r"]}, [("/ramps/0", "wrong_type")]),
        ({"id": "p", "colors": ONE, "ramps": "r"}, [("/ramps", "wrong_type")]),
    ],
)
def test_from_mapping_reports_structure_problems(
    data: object, expected: list[tuple[str, str]]
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Palette.from_mapping(data, profile="rgba")
    assert reasons(excinfo.value) == expected


def test_from_mapping_rejects_oversized_arrays_before_walking_items() -> None:
    class Exploding(list[object]):
        def __iter__(self) -> Any:
            raise AssertionError("walked an array subclass")

    with pytest.raises(ValidationError) as excinfo:
        Palette.from_mapping({"id": "p", "colors": [0] * 4097}, profile="rgba")
    assert reasons(excinfo.value) == [("/colors", "too_long")]
    with pytest.raises(ValidationError):  # subclasses of list are not JSON arrays
        Palette.from_mapping({"id": "p", "colors": Exploding([0])}, profile="rgba")


# --- AC2: luminance warnings never block ---------------------------------------------


def test_increasing_ramp_has_no_warnings() -> None:
    assert sample().luminance_warnings() == ()


def test_luminance_warning_does_not_block_stylised_ramp() -> None:
    base = Palette("main", "strict", colors(("shade", DARK), ("base", MID), ("light", LIGHT)))
    palette = with_ramps(
        base, Ramp("up", ("shade", "base", "light")), Ramp("stylised", ("light", "shade", "base"))
    )
    assert palette.ramp("stylised") == (LIGHT, DARK, MID)
    (warning,) = palette.luminance_warnings()
    assert (warning.code, warning.reason, warning.json_pointer) == (
        RAMP_LUMINANCE_NOT_INCREASING,
        "decreasing",
        "/ramps/1/colors/1",
    )
    assert (warning.ramp_id, warning.previous_color_id, warning.color_id) == (
        "stylised",
        "light",
        "shade",
    )
    assert warning.previous_luminance == LIGHT.luminance > DARK.luminance == warning.luminance


def test_hue_shifted_ramp_ordered_by_linear_luminance() -> None:
    grey = Rgba(0x3C, 0x3C, 0x3C, 255)
    blue = Rgba(0, 0, 255, 255)
    palette = Palette("p", "strict", colors(("grey", grey), ("blue", blue)))
    assert with_ramps(palette, Ramp("r", ("grey", "blue"))).luminance_warnings() == ()
    bad = with_ramps(palette, Ramp("r", ("blue", "grey"))).luminance_warnings()
    assert [w.reason for w in bad] == ["decreasing"]


def test_duplicate_value_equal_and_translucent_steps_are_distinguished() -> None:
    red = Rgba(200, 0, 0, 255)
    palette = Palette(
        "p",
        "rgba",
        colors(("a", red), ("a2", red), ("x", Rgba(10, 20, 30, 255)), ("y", Rgba(10, 20, 30, 254))),
    )
    dup = with_ramps(palette, Ramp("r", ("a", "a2"))).luminance_warnings()
    assert [(w.reason, w.color_id, w.previous_color_id) for w in dup] == [
        ("duplicate_value", "a2", "a")
    ]
    equal = with_ramps(palette, Ramp("r", ("x", "y"))).luminance_warnings()
    assert [(w.code, w.reason) for w in equal] == [
        (RAMP_PARTIAL_ALPHA_STEP, "partial_alpha"),
        (RAMP_LUMINANCE_NOT_INCREASING, "equal"),
    ]


def test_transparent_steps_are_reported_and_skipped_for_ordering() -> None:
    palette = Palette(
        "p", "strict", colors(("clear", Rgba(255, 255, 255, 0)), ("shade", DARK), ("light", LIGHT))
    )
    first = with_ramps(palette, Ramp("r", ("clear", "shade", "light"))).luminance_warnings()
    assert [(w.code, w.json_pointer, w.color_id, w.reason) for w in first] == [
        (RAMP_TRANSPARENT_STEP, "/ramps/0/colors/0", "clear", "transparent")
    ]
    middle = with_ramps(palette, Ramp("m", ("shade", "clear", "light"))).luminance_warnings()
    assert [w.code for w in middle] == [RAMP_TRANSPARENT_STEP], "shade -> light still ordered"


# --- edits keep IDs and positions ----------------------------------------------------


def test_replace_color_keeps_ids_order_and_ramps() -> None:
    palette = sample()
    edited = palette.replace_color("base", Rgba(130, 120, 140, 255))
    assert [c.id for c in edited.colors] == [c.id for c in palette.colors]
    assert edited.ramps == palette.ramps
    assert edited.index_of("base") == palette.index_of("base")
    assert edited.color("base") == Rgba(130, 120, 140, 255)
    assert palette.color("base") == MID, "palette values are immutable"
    with pytest.raises(ValidationError):
        palette.replace_color("base", Rgba(1, 1, 1, 100))  # strict profile still applies


def test_duplicate_color_appends_without_renumbering() -> None:
    palette = sample()
    local = palette.duplicate_color("base", "base_cheek")
    assert [palette.index_of(c.id) for c in palette.colors] == [
        local.index_of(c.id) for c in palette.colors
    ]
    assert local.index_of("base_cheek") == 4 and local.color("base_cheek") == MID
    assert local.ramps == palette.ramps, "the duplicate joins no ramp"
    tinted = palette.duplicate_color("base", "blush", Rgba(200, 100, 100, 255))
    assert tinted.color("blush") == Rgba(200, 100, 100, 255)
    with pytest.raises(ValidationError):
        palette.duplicate_color("base", "ink")


def test_values_are_hashable_copyable_and_picklable() -> None:
    palette = sample()
    assert hash(palette) == hash(sample()) and len({palette, sample()}) == 1
    assert copy.copy(palette) is palette and copy.deepcopy(palette) is palette
    restored = pickle.loads(pickle.dumps(palette))
    assert restored == palette and restored.index_of("light") == 3
    remap = ColorRemap(palette, {"ink": "base"})
    assert copy.copy(remap) is remap and copy.deepcopy(remap) is remap
    assert pickle.loads(pickle.dumps(remap)) == remap
    assert hash(remap) == hash(ColorRemap(sample(), {"ink": "base"}))
    assert remap != ColorRemap(palette, {"ink": "light"}) and remap.__eq__(1) is NotImplemented
    assert repr(remap) == "ColorRemap(palette='main', entries=1)"


# --- T2: explicit remap without hidden colors ----------------------------------------


def test_remap_is_explicit_single_step_and_closed_over_the_palette() -> None:
    palette = sample()
    remap = ColorRemap(palette, {"shade": "ink", "ink": "base"})
    assert remap.palette is palette
    assert remap.resolve("shade") == "ink", "not chained to base"
    assert remap.resolve("light") == "light"
    assert remap.color("shade") == BLACK
    assert remap.used_ids(["shade", "ink", "light", "shade"]) == ("ink", "base", "light")
    # Hand oracle: ink->base, shade->ink, base and light unchanged.
    assert [remap.color(c) for c in ("ink", "shade", "base", "light")] == [MID, BLACK, MID, LIGHT]


def test_remap_rejects_unknown_ids_and_non_strings_without_pointers() -> None:
    palette = sample()
    with pytest.raises(core_errors.ReferenceError) as excinfo:
        ColorRemap(palette, {"ink": "ghost", "ghost": "ink"})
    found = {(d.json_pointer, tuple(sorted(d.context.items()))) for d in excinfo.value.details}
    assert found == {
        (None, (("position", 0), ("reason", "unknown_color"), ("side", "target"))),
        (None, (("position", 1), ("reason", "unknown_color"), ("side", "source"))),
    }
    with pytest.raises(ValidationError):
        ColorRemap(palette, {"ink": 1})  # type: ignore[dict-item]
    with pytest.raises(core_errors.ReferenceError):
        ColorRemap(palette, {}).resolve("ghost")
    with pytest.raises(TypeError):
        ColorRemap(palette, [("ink", "base")])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ColorRemap(palette.to_mapping(), {})  # type: ignore[arg-type]


def test_remap_larger_than_palette_is_rejected_before_iterating() -> None:
    class Exploding(dict[str, str]):
        def items(self) -> Any:
            raise AssertionError("iterated an oversized remap")

    oversized = Exploding({f"x{i}": "ink" for i in range(5)})
    with pytest.raises(ValidationError) as excinfo:
        ColorRemap(sample(), oversized)
    assert excinfo.value.context == {"reason": "too_many", "maximum": 4}


def test_remap_mapping_is_a_read_only_snapshot() -> None:
    source = {"ink": "base"}
    remap = ColorRemap(sample(), source)
    source["ink"] = "light"
    assert remap.resolve("ink") == "base"
    with pytest.raises(TypeError):
        remap.mapping["ink"] = "light"  # type: ignore[index]
