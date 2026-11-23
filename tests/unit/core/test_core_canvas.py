"""Owned RGBA canvas and its NumPy/Pillow adapters (MOANA-004, ADR-013)."""

from __future__ import annotations

import copy
import hashlib
import io
import tracemalloc

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from PIL import Image

from moanart.core import (
    BudgetExceeded,
    Dimensions,
    GeometryLimits,
    OutOfBoundsError,
    Point,
    RenderLimits,
    ValidationError,
)
from moanart.core.canvas import Canvas, check_canvas_budget
from moanart.core.coordinates import MAX_DIMENSION
from moanart.core.pillow_adapter import canvas_from_pillow, canvas_to_pillow

REFERENCE = Dimensions(128, 128)
LIMITS = RenderLimits()
channel = st.integers(min_value=0, max_value=255)
rgba = st.tuples(channel, channel, channel, channel)


def residual_array(width: int, height: int) -> np.ndarray:
    """Deterministic pixels where every fourth pixel is transparent with residual RGB."""
    values = np.arange(width * height * 4, dtype=np.uint64) * 37 % 256
    pixels = values.astype(np.uint8).reshape(height, width, 4)
    pixels[:, :, 3] = np.where(np.arange(width * height).reshape(height, width) % 4 == 0, 0, 200)
    return pixels


def expected_normalized(pixels: np.ndarray) -> np.ndarray:
    """Independent oracle: transparent pixels become (0, 0, 0, 0)."""
    out = pixels.copy()
    for y in range(out.shape[0]):
        for x in range(out.shape[1]):
            if out[y, x, 3] == 0:
                out[y, x] = (0, 0, 0, 0)
    return out


# --- T1: fixtures 1x1 and 128x128, transparent with residual RGB, roundtrips -------


@pytest.mark.parametrize("dimensions", [Dimensions(1, 1), REFERENCE])
def test_blank_canvas_is_transparent_black_uint8_c_contiguous(dimensions: Dimensions) -> None:
    canvas = Canvas.blank(dimensions, limits=LIMITS)
    array = canvas.to_array()
    assert array.dtype == np.uint8
    assert array.shape == (dimensions.height, dimensions.width, 4)
    assert array.flags.c_contiguous
    assert not array.any()
    assert (canvas.width, canvas.height, canvas.dimensions) == (
        dimensions.width,
        dimensions.height,
        dimensions,
    )


def test_one_by_one_pixel_roundtrip() -> None:
    canvas = Canvas.blank(Dimensions(1, 1), limits=LIMITS)
    canvas.set_pixel(Point(0, 0), (1, 2, 3, 4))
    assert canvas.get_pixel(Point(0, 0)) == (1, 2, 3, 4)
    assert canvas.to_bytes() == bytes([1, 2, 3, 4])


@pytest.mark.parametrize("size", [(1, 1), (128, 128), (5, 3)])
def test_from_array_normalizes_transparent_residual_rgb(size: tuple[int, int]) -> None:
    width, height = size
    source = residual_array(width, height)
    canvas = Canvas.from_array(source, limits=LIMITS)
    np.testing.assert_array_equal(canvas.to_array(), expected_normalized(source))


def test_array_layout_is_row_major_y_x_channel() -> None:
    canvas = Canvas.blank(Dimensions(3, 2), limits=LIMITS)
    canvas.set_pixel(Point(2, 1), (10, 20, 30, 40))
    array = canvas.to_array()
    assert tuple(array[1, 2]) == (10, 20, 30, 40)
    assert canvas.to_bytes()[(1 * 3 + 2) * 4 :][:4] == bytes([10, 20, 30, 40])


@pytest.mark.parametrize("size", [(1, 1), (128, 128), (7, 4)])
def test_numpy_and_pillow_roundtrip_preserve_rgba(size: tuple[int, int]) -> None:
    width, height = size
    canvas = Canvas.from_array(residual_array(width, height), limits=LIMITS)
    assert Canvas.from_array(canvas.to_array(), limits=LIMITS) == canvas
    image = canvas_to_pillow(canvas)
    assert (image.mode, image.size) == ("RGBA", (width, height))
    assert image.tobytes() == canvas.to_bytes()
    assert canvas_from_pillow(image, limits=LIMITS) == canvas


def test_from_pillow_normalizes_transparent_residual_rgb() -> None:
    source = residual_array(6, 5)
    image = Image.frombytes("RGBA", (6, 5), source.tobytes())
    canvas = canvas_from_pillow(image, limits=LIMITS)
    np.testing.assert_array_equal(canvas.to_array(), expected_normalized(source))


def test_visual_digest_matches_section_14_oracle() -> None:
    canvas = Canvas.from_array(residual_array(3, 2), limits=LIMITS)
    header = (3).to_bytes(4, "big") + (2).to_bytes(4, "big")
    oracle = hashlib.sha256(header + expected_normalized(residual_array(3, 2)).tobytes())
    assert canvas.visual_digest() == "sha256:" + oracle.hexdigest()
    # Same bytes, different shape: digest differs because the size is hashed.
    reshaped = Canvas.from_array(canvas.to_array().reshape(3, 2, 4), limits=LIMITS)
    assert reshaped.visual_digest() != canvas.visual_digest()


# --- AC1: valid coordinates preserve RGBA, negatives never wrap --------------------


@given(x=st.integers(0, 127), y=st.integers(0, 127), color=rgba)
def test_set_get_preserves_rgba_or_normalizes_alpha_zero(
    x: int, y: int, color: tuple[int, int, int, int]
) -> None:
    canvas = Canvas.blank(REFERENCE, limits=LIMITS)
    canvas.set_pixel(Point(x, y), color)
    expected = (0, 0, 0, 0) if color[3] == 0 else color
    assert canvas.get_pixel(Point(x, y)) == expected
    array = canvas.to_array()
    array[y, x] = 0
    assert not array.any(), "no other pixel was written"


@pytest.mark.parametrize(
    "point", [Point(-1, 0), Point(0, -1), Point(-1, -1), Point(128, 0), Point(0, 128)]
)
def test_out_of_range_access_raises_without_wrap(point: Point) -> None:
    canvas = Canvas.blank(REFERENCE, limits=LIMITS)
    canvas.set_pixel(Point(127, 127), (9, 9, 9, 9))
    before = canvas.to_array()
    with pytest.raises(OutOfBoundsError) as excinfo:
        canvas.get_pixel(point)
    assert excinfo.value.context["x"] == point.x
    with pytest.raises(OutOfBoundsError):
        canvas.set_pixel(point, (1, 2, 3, 4))
    np.testing.assert_array_equal(canvas.to_array(), before)


@pytest.mark.parametrize(
    "value",
    [
        (1, 2, 3),
        (1, 2, 3, 4, 5),
        [1, 2, 3, 4],
        (256, 0, 0, 1),
        (-1, 0, 0, 1),
        (True, 0, 0, 1),
        (1.0, 0, 0, 1),
        (np.uint8(1), 0, 0, 1),
    ],
)
def test_set_pixel_rejects_invalid_color_without_writing(value: object) -> None:
    canvas = Canvas.blank(Dimensions(2, 2), limits=LIMITS)
    with pytest.raises(ValidationError):
        canvas.set_pixel(Point(0, 0), value)  # type: ignore[arg-type]  # invalid on purpose
    assert not canvas.to_array().any()


# --- AC2 / T2: aliasing ------------------------------------------------------------


def test_exported_array_does_not_alias_canvas() -> None:
    canvas = Canvas.blank(Dimensions(4, 4), limits=LIMITS)
    exported = canvas.to_array()
    exported[:] = 255
    assert not canvas.to_array().any()
    assert not np.shares_memory(exported, canvas.to_array())


def test_imported_array_is_copied_and_never_modified() -> None:
    source = residual_array(4, 4)
    original = source.copy()
    canvas = Canvas.from_array(source, limits=LIMITS)
    np.testing.assert_array_equal(source, original)  # normalisation left the caller alone
    source[:] = 7
    np.testing.assert_array_equal(canvas.to_array(), expected_normalized(original))


def test_shallow_and_deep_copy_do_not_share_the_buffer() -> None:
    canvas = Canvas.blank(Dimensions(2, 2), limits=LIMITS)
    for clone in (copy.copy(canvas), copy.deepcopy(canvas)):
        clone.set_pixel(Point(0, 0), (1, 2, 3, 4))
        assert canvas.get_pixel(Point(0, 0)) == (0, 0, 0, 0)


def test_direct_construction_is_closed() -> None:
    with pytest.raises(TypeError):
        Canvas()


@pytest.mark.parametrize("point", [(0, 0), None])
def test_pixel_access_requires_point(point: object) -> None:
    canvas = Canvas.blank(Dimensions(1, 1), limits=LIMITS)
    with pytest.raises(TypeError):
        canvas.get_pixel(point)  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError):
        canvas.set_pixel(point, (1, 1, 1, 1))  # type: ignore[arg-type]  # invalid on purpose


def test_from_array_rejects_masked_array() -> None:
    masked = np.ma.array(np.full((1, 1, 4), 7, dtype=np.uint8), mask=True)
    with pytest.raises(ValidationError) as excinfo:
        Canvas.from_array(masked, limits=LIMITS)
    assert excinfo.value.context["reason"] == "not_ndarray"


def test_from_array_accepts_read_only_and_negative_stride_views() -> None:
    source = residual_array(4, 3)
    readonly = source.copy()
    readonly.flags.writeable = False
    flipped = source[::-1, ::-1, ::-1]
    assert Canvas.from_array(readonly, limits=LIMITS).to_array().tolist() == (
        expected_normalized(source).tolist()
    )
    np.testing.assert_array_equal(
        Canvas.from_array(flipped, limits=LIMITS).to_array(), expected_normalized(flipped)
    )


def test_copy_is_independent_and_equal() -> None:
    canvas = Canvas.from_array(residual_array(3, 3), limits=LIMITS)
    clone = canvas.copy()
    assert clone == canvas and clone is not canvas
    clone.set_pixel(Point(1, 1), (1, 1, 1, 1))
    assert clone != canvas


def test_pillow_export_and_import_do_not_alias() -> None:
    canvas = Canvas.blank(Dimensions(2, 2), limits=LIMITS)
    image = canvas_to_pillow(canvas)
    image.putpixel((0, 0), (5, 6, 7, 8))
    assert canvas.get_pixel(Point(0, 0)) == (0, 0, 0, 0)
    imported = canvas_from_pillow(image, limits=LIMITS)
    image.putpixel((0, 0), (9, 9, 9, 9))
    assert imported.get_pixel(Point(0, 0)) == (5, 6, 7, 8)


def test_from_array_accepts_non_contiguous_view_and_stores_c_contiguous() -> None:
    base = residual_array(8, 8)
    view = base[::2, ::2]
    assert not view.flags.c_contiguous
    canvas = Canvas.from_array(view, limits=LIMITS)
    np.testing.assert_array_equal(canvas.to_array(), expected_normalized(view))
    assert canvas.to_array().flags.c_contiguous


def test_canvas_is_unhashable_and_compares_by_value() -> None:
    canvas = Canvas.blank(Dimensions(1, 1), limits=LIMITS)
    with pytest.raises(TypeError):
        hash(canvas)
    assert canvas == Canvas.blank(Dimensions(1, 1), limits=LIMITS)
    assert canvas != Canvas.blank(Dimensions(1, 2), limits=LIMITS)
    assert canvas.__eq__(object()) is NotImplemented
    assert repr(canvas) == "Canvas(width=1, height=1)"


# --- T2: invalid dtype / shape -----------------------------------------------------


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ([[[0, 0, 0, 0]]], "not_ndarray"),
        (np.zeros((1, 1, 4), dtype=np.uint16), "wrong_dtype"),
        (np.zeros((1, 1, 4), dtype=np.float64), "wrong_dtype"),
        (np.zeros((1, 1, 4), dtype=np.int8), "wrong_dtype"),
        (np.zeros((1, 1, 4), dtype=bool), "wrong_dtype"),
        (np.zeros((1, 4), dtype=np.uint8), "wrong_shape"),
        (np.zeros((1, 1, 3), dtype=np.uint8), "wrong_shape"),
        (np.zeros((1, 1, 1, 4), dtype=np.uint8), "wrong_shape"),
    ],
)
def test_from_array_rejects_invalid_type_dtype_shape(value: object, reason: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Canvas.from_array(value, limits=LIMITS)
    assert excinfo.value.context["reason"] == reason


@pytest.mark.parametrize("shape", [(0, 1, 4), (1, 0, 4), (4097, 1, 4)])
def test_from_array_rejects_dimensions_outside_contract(shape: tuple[int, int, int]) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Canvas.from_array(np.zeros(shape, dtype=np.uint8), limits=LIMITS)
    assert excinfo.value.context["reason"] == "out_of_range"


def test_blank_rejects_non_dimensions() -> None:
    with pytest.raises(TypeError):
        Canvas.blank((1, 1), limits=LIMITS)  # type: ignore[arg-type]  # invalid on purpose


@pytest.mark.parametrize(
    ("image", "reason"),
    [
        (np.zeros((1, 1, 4), dtype=np.uint8), "not_image"),
        (Image.new("RGB", (1, 1)), "wrong_mode"),
        (Image.new("RGBa", (1, 1)), "wrong_mode"),
        (Image.new("LA", (1, 1)), "wrong_mode"),
        (Image.new("P", (1, 1)), "wrong_mode"),
    ],
)
def test_from_pillow_rejects_wrong_source_or_mode(image: object, reason: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        canvas_from_pillow(image, limits=LIMITS)
    assert excinfo.value.context["reason"] == reason


def _encoded(image: Image.Image, **params: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", **params)
    return buffer.getvalue()


def test_from_pillow_rejects_multiframe_image() -> None:
    frames = [Image.new("RGBA", (2, 2), (i, 0, 0, 255)) for i in range(2)]
    data = _encoded(frames[0], save_all=True, append_images=frames[1:])
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == "RGBA"
        with pytest.raises(ValidationError) as excinfo:
            canvas_from_pillow(image, limits=LIMITS)
    assert excinfo.value.context["reason"] == "multiple_frames"


def test_from_pillow_wraps_closed_and_truncated_images() -> None:
    closed = Image.new("RGBA", (2, 2))
    closed.close()
    data = _encoded(Image.new("RGBA", (64, 64), (1, 2, 3, 4)))
    truncated = Image.open(io.BytesIO(data[: len(data) // 2]))
    for image in (closed, truncated):
        with pytest.raises(ValidationError) as excinfo:
            canvas_from_pillow(image, limits=LIMITS)
        assert excinfo.value.context["reason"] == "unreadable_image"
        assert isinstance(excinfo.value.__cause__, (OSError, ValueError))


def test_lazy_oversized_image_is_rejected_before_decoding() -> None:
    data = _encoded(Image.new("RGBA", (MAX_DIMENSION + 1, 1)))
    with Image.open(io.BytesIO(data)) as image, pytest.raises(ValidationError):
        canvas_from_pillow(image, limits=LIMITS)


# --- T2: memory limit before allocation --------------------------------------------


def test_budget_is_checked_before_numpy_allocates(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("allocated before the budget check")

    monkeypatch.setattr(np, "zeros", forbidden)
    limits = RenderLimits(max_buffer_bytes=4 * 128 * 128 - 1)
    with pytest.raises(BudgetExceeded) as excinfo:
        Canvas.blank(REFERENCE, limits=limits)
    assert excinfo.value.context == {
        "resource": "buffer_bytes",
        "limit": 4 * 128 * 128 - 1,
        "estimated": 4 * 128 * 128,
    }


def test_budget_admits_exact_limit() -> None:
    limits = RenderLimits(max_buffer_bytes=4 * 128 * 128)
    assert Canvas.blank(REFERENCE, limits=limits).dimensions == REFERENCE


def test_lowered_geometry_rejects_largest_canvas_without_allocating() -> None:
    # Contract maximum (16 MiB) fits the default; lowered host geometry rejects it.
    geometry = GeometryLimits(max_dimension=64, max_area=64 * 64, max_coordinate=64)
    limits = RenderLimits(geometry=geometry)
    tracemalloc.start()
    try:
        with pytest.raises(BudgetExceeded) as excinfo:
            Canvas.blank(Dimensions(MAX_DIMENSION, MAX_DIMENSION), limits=limits)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024
    resources = [detail.context["resource"] for detail in excinfo.value.details]
    assert resources == ["canvas_dimension", "canvas_dimension", "canvas_area"]


def test_from_array_checks_budget_before_copying(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("copied before the budget check")

    source = np.zeros((2, 2, 4), dtype=np.uint8)
    monkeypatch.setattr(np, "array", forbidden)
    with pytest.raises(BudgetExceeded):
        Canvas.from_array(source, limits=RenderLimits(max_buffer_bytes=15))


def test_from_array_and_pillow_respect_budget() -> None:
    limits = RenderLimits(max_buffer_bytes=15)
    with pytest.raises(BudgetExceeded):
        Canvas.from_array(np.zeros((2, 2, 4), dtype=np.uint8), limits=limits)
    with pytest.raises(BudgetExceeded):
        canvas_from_pillow(Image.new("RGBA", (2, 2)), limits=limits)


def test_check_canvas_budget_default_admits_largest_canvas() -> None:
    largest = Dimensions(MAX_DIMENSION, MAX_DIMENSION)
    check_canvas_budget(largest, RenderLimits())


def test_canvas_peak_memory_stays_within_estimated_4a() -> None:
    area = 128 * 128
    tracemalloc.start()
    try:
        canvas = Canvas.blank(REFERENCE, limits=LIMITS)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert canvas.width == 128
    assert peak <= 4 * area + 4096  # buffer plus small object overhead


def test_transparent_import_peak_memory_stays_near_4a() -> None:
    side = 512
    source = np.full((side, side, 4), 9, dtype=np.uint8)
    source[:, :, 3] = 0
    tracemalloc.start()
    try:
        canvas = Canvas.from_array(source, limits=LIMITS)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert not canvas.to_array().any()
    # Owned 4A buffer + A-byte alpha mask; boolean indexing would need about 17A.
    assert peak <= 5 * side * side + 4096
