"""Mask is an immutable pixel set that never leaks its storage (ADR-015)."""

from __future__ import annotations

import copy
import pickle

import pytest
from hypothesis import given
from hypothesis import strategies as st

from moanart.core.coordinates import Box, Dimensions, Point
from moanart.core.errors import ValidationError
from moanart.geometry import Mask, rasterize_ellipse, rasterize_line, rasterize_rect
from moanart.geometry.mask import _restore

DIMS = Dimensions(6, 5)


def test_direct_construction_is_closed() -> None:
    with pytest.raises(TypeError):
        Mask()


def test_empty_mask_has_no_storage_or_pixels() -> None:
    empty = Mask.empty()
    assert empty.box is None and empty.bounds is None
    assert empty.count == 0 and empty.is_empty
    assert list(empty.points()) == []
    assert empty.to_array().shape == (0, 0)
    assert not empty.contains(Point(0, 0))
    assert repr(empty) == "Mask(box=None, count=0)"


def test_points_are_row_major_and_bounds_are_tight() -> None:
    mask = rasterize_line(Point(4, 3), Point(1, 0), DIMS)
    assert list(mask.points()) == [Point(1, 0), Point(2, 1), Point(3, 2), Point(4, 3)]
    assert mask.bounds == Box(1, 0, 5, 4)
    assert mask.count == 4 and not mask.is_empty


def test_contains_outside_storage_is_false_and_requires_point() -> None:
    mask = rasterize_rect(Box(1, 1, 3, 3), DIMS)
    assert mask.contains(Point(1, 1)) and not mask.contains(Point(3, 3))
    assert not mask.contains(Point(-1, -1))
    with pytest.raises(TypeError):
        mask.contains((1, 1))  # type: ignore[arg-type]  # deliberate misuse


def test_to_array_is_an_independent_copy() -> None:
    mask = rasterize_rect(Box(0, 0, 2, 2), DIMS)
    array = mask.to_array()
    assert array.flags.writeable and array.shape == (2, 2)
    array[:] = False
    assert mask.count == 4


def test_equality_compares_pixels_not_storage() -> None:
    # Same pixel set stored in different boxes: equal, with equal hashes.
    collinear_box = rasterize_line(Point(0, 0), Point(0, 2), DIMS)
    rect = rasterize_rect(Box(0, 0, 1, 3), DIMS)
    wider = rasterize_ellipse(Box(0, 0, 1, 3), DIMS)
    assert collinear_box == rect == wider
    assert hash(collinear_box) == hash(rect)
    assert rect != rasterize_rect(Box(0, 0, 1, 2), DIMS)
    assert rect != "mask"
    corner = rasterize_line(Point(-3, 2), Point(2, -3), DIMS)  # storage, no pixels
    assert corner == Mask.empty() and hash(corner) == hash(Mask.empty())


@given(
    st.integers(-8, 10),
    st.integers(-8, 10),
    st.integers(1, 12),
    st.integers(1, 12),
)
def test_every_pixel_lies_inside_the_clipped_box(x0: int, y0: int, w: int, h: int) -> None:
    box = Box(x0, y0, x0 + w, y0 + h)
    clipped = box.clip_to(DIMS)
    for mask in (rasterize_rect(box, DIMS), rasterize_ellipse(box, DIMS)):
        assert mask.box == clipped
        for point in mask.points():
            assert clipped is not None and clipped.contains(point)


def test_copy_and_deepcopy_return_the_same_immutable_mask() -> None:
    mask = rasterize_rect(Box(0, 0, 2, 2), DIMS)
    for duplicate in (copy.copy(mask), copy.deepcopy(mask)):
        assert duplicate is mask
        assert duplicate == mask
        assert not duplicate._bits.flags.writeable


@pytest.mark.parametrize(
    "mask",
    [rasterize_ellipse(Box(-1, 0, 5, 4), DIMS), Mask.empty()],
    ids=["ellipse", "empty"],
)
def test_pickle_roundtrip_keeps_value_and_read_only_bits(mask: Mask) -> None:
    restored = pickle.loads(pickle.dumps(mask))
    assert restored == mask and restored.box == mask.box
    assert not restored._bits.flags.writeable
    assert restored.to_array().tolist() == mask.to_array().tolist()


BOX = Box(0, 0, 2, 1)


@pytest.mark.parametrize(
    ("box", "shape", "data", "reason"),
    [
        ((0, 0, 2, 1), (1, 2), b"\x01\x00", "not_box"),
        (BOX, (2, 1), b"\x01\x00", "shape_mismatch"),
        (BOX, [1, 2], b"\x01\x00", "shape_mismatch"),
        (None, (1, 2), b"\x01\x00", "shape_mismatch"),
        (BOX, (1, 2), b"\x01", "size_mismatch"),
        (BOX, (1, 2), bytearray(b"\x01\x00"), "size_mismatch"),
        (None, (0, 0), b"\x01", "size_mismatch"),
        (BOX, (1, 2), b"\x02\x00", "not_binary"),
    ],
)
def test_tampered_pickle_state_is_rejected(
    box: object, shape: object, data: object, reason: str
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _restore(box, shape, data)
    assert excinfo.value.context["reason"] == reason
