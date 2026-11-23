"""Positive controls of the instrumentation: the tripwires really fire (T2).

Without these controls a tripwire that patched the wrong attribute would make every
"rejected before allocation/IO" test pass vacuously. A valid render must reach the
allocation tripwire, a valid save must reach the write tripwire, and neither may be
swallowed by ``except Exception`` in the code under test.
"""

from __future__ import annotations

import io
import os
import tracemalloc
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from moanart.api import export_png, load_document, render
from moanart.project import Asset, Project, load_project, save_project

from .corpus import MINIMAL, tiny_png
from .guards import (
    TripwireHit,
    forbid,
    forbid_allocation,
    forbid_effects,
    forbid_writes,
    peak_bytes,
    tree_state,
)

pytestmark = pytest.mark.security


def test_t2_allocation_tripwire_fires_on_numpy_and_pillow() -> None:
    with forbid_allocation():
        for call in (
            lambda: np.zeros((2, 2)),
            lambda: np.empty(4),
            lambda: np.full(3, 1),
            lambda: np.frombuffer(b"\0" * 4, dtype=np.uint8),
            lambda: np.array([1, 2]),
            lambda: np.asarray([1, 2]),
            lambda: np.ascontiguousarray([1, 2]),
            lambda: np.arange(4),
            lambda: np.repeat([1], 4),
            lambda: np.pad([1], 1),
            lambda: np.concatenate([[1], [2]]),
            lambda: np.stack([[1], [2]]),
            lambda: np.tile([1], 4),
            lambda: np.broadcast_to(1, (2, 2)),
            lambda: Image.new("RGBA", (1, 1)),
            lambda: Image.open(io.BytesIO(b"")),
            lambda: Image.frombytes("RGBA", (1, 1), b"\0" * 4),
            lambda: Image.frombuffer("RGBA", (1, 1), b"\0" * 4),
            lambda: Image.fromarray(np.zeros((1, 1), dtype=np.uint8)),
        ):
            with pytest.raises(TripwireHit):
                call()
    assert np.zeros(1).shape == (1,)  # restored afterwards


def test_t2_tripwire_is_not_swallowed_by_except_exception() -> None:
    def careless() -> None:
        try:  # noqa: SIM105 - the literal swallowing handler of careless code is the point
            np.zeros(4)
        except Exception:
            pass

    assert issubclass(TripwireHit, pytest.fail.Exception)
    assert not issubclass(TripwireHit, Exception)
    with forbid_allocation(), pytest.raises(TripwireHit):
        careless()


def test_t2_forbid_trips_any_named_attribute() -> None:
    with forbid(Image.Image, "load"), pytest.raises(TripwireHit):
        Image.open(io.BytesIO(tiny_png())).load()


def test_t2_write_tripwire_fires_and_reads_still_work(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.write_bytes(b"data")
    with forbid_writes():
        assert existing.read_bytes() == b"data"
        for call in (
            lambda: (tmp_path / "new").write_bytes(b"x"),
            lambda: os.open(tmp_path / "raw", os.O_WRONLY | os.O_CREAT),
            lambda: os.replace(existing, tmp_path / "moved"),
            lambda: os.mkdir(tmp_path / "dir"),
            lambda: os.unlink(existing),
            lambda: os.link(existing, tmp_path / "linked"),
        ):
            with pytest.raises(TripwireHit):
                call()
    assert tree_state(tmp_path) == {"existing": b"data"}


def test_t2_valid_render_and_export_reach_the_tripwires(tmp_path: Path) -> None:
    document = load_document(MINIMAL)
    with forbid_allocation(), pytest.raises(TripwireHit):
        render(document)
    result = render(document)
    with forbid_writes(), pytest.raises(TripwireHit):
        export_png(result, tmp_path / "out.png")
    assert tree_state(tmp_path) == {}


def test_t2_valid_project_load_and_save_reach_the_tripwires(tmp_path: Path) -> None:
    project = Project(load_document(MINIMAL), (Asset.from_png("tex", tiny_png()),))
    with forbid_effects(), pytest.raises(TripwireHit):
        save_project(project, tmp_path / "p")
    save_project(project, tmp_path / "saved")
    with forbid_allocation(), pytest.raises(TripwireHit):
        load_project(tmp_path / "saved")  # the asset is decoded with Pillow


def test_peak_bytes_measures_python_allocations() -> None:
    error, peak = peak_bytes(lambda: bytearray(4 * 1024 * 1024))
    assert error is None
    assert peak >= 4 * 1024 * 1024


def test_peak_bytes_is_relative_and_keeps_an_outer_trace_running() -> None:
    """Under ``PYTHONTRACEMALLOC=1`` (or any outer tracer) tracing is already on."""
    outer = tracemalloc.is_tracing()
    if not outer:
        tracemalloc.start()
    try:
        held = bytearray(8 * 1024 * 1024)  # traced before the measurement: baseline
        error, peak = peak_bytes(lambda: bytearray(1024 * 1024))
        assert error is None
        assert 1024 * 1024 <= peak < 4 * 1024 * 1024  # the 8 MiB already held are excluded
        assert tracemalloc.is_tracing()  # the outer trace was not stopped
        del held
    finally:
        if not outer:
            tracemalloc.stop()
    assert tracemalloc.is_tracing() == outer
