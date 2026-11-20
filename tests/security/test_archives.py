"""ZIP → filesystem: zip slip, links, bombs and bounded reads of project sources (T1, AC2).

Reading a project never extracts to disk: these tests arm the write tripwire, and for
budget cases also forbid ``zipfile.ZipFile.open`` (no entry may be decompressed
before the central directory is fully accepted). The limits are those of MOANA.md
section 16 and ``ProjectLimits``; hostile names are generated, never copied from an
engine message.
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from moana.core.errors import BudgetExceeded, MoanaError, ValidationError
from moana.project import MANIFEST_NAME, ProjectLimits, load_project

from .corpus import SECRET, archive, asset_name, symlink_entry, with_central_size
from .guards import (
    assert_bounded,
    assert_clean_error,
    bounded_settings,
    forbid,
    forbid_effects,
    measure,
    tree_state,
)

pytestmark = pytest.mark.security

BOUNDED = bounded_settings(60)  # tmp_path_factory is session-scoped


def _no_decompression() -> AbstractContextManager[None]:
    """No entry may be decompressed: ``zipfile.ZipFile.open`` is a tripwire."""
    return forbid(zipfile.ZipFile, "open")


def _load_hostile(source: Path, limits: ProjectLimits | None = None) -> MoanaError:
    root = source.parent
    before = tree_state(root)
    chosen = ProjectLimits() if limits is None else limits
    with forbid_effects():
        rejection = measure(lambda: load_project(source, limits=chosen))
    error = assert_bounded(rejection)
    assert tree_state(root) == before
    return assert_clean_error(error, root, SECRET)


# --- zip slip: every name with a traversal feature is refused --------------------------

_SEGMENT = st.sampled_from(["assets", "history", "x.json", SECRET, "a.png"])
_HOSTILE = st.sampled_from(["..", ".", "", "C:", "c:x", "..\\..", "a\\b"])


@st.composite
def _hostile_names(draw: st.DrawFn) -> str:
    segments = draw(st.lists(_SEGMENT, max_size=4))
    position = draw(st.integers(0, len(segments)))
    segments.insert(position, draw(_HOSTILE))
    name = "/".join(segments)
    if draw(st.booleans()):
        name = "/" + name
    return name


@BOUNDED
@given(name=_hostile_names(), first=st.booleans())
def test_t1_property_traversal_names_are_refused_before_extraction(
    tmp_path_factory: pytest.TempPathFactory, name: str, first: bool
) -> None:
    root = tmp_path_factory.mktemp("slip")
    entries = [(name, b"payload"), (MANIFEST_NAME, b"{}")]
    if not first:
        entries.reverse()
    source = root / "evil.moana"
    source.write_bytes(archive(entries))
    error = _load_hostile(source)
    assert isinstance(error, ValidationError)
    assert error.context["reason"] == "unsafe_archive"
    assert error.context["entry_reason"] in (
        "parent_reference",
        "absolute_path",
        "invalid_name",
        "unexpected_entry",
    )
    assert error.context["entry"] == (0 if first else 1)
    assert not (root.parent / "x.json").exists()


def test_t1_symlink_entry_is_refused_even_with_a_layout_name(tmp_path: Path) -> None:
    source = tmp_path / "link.moana"
    source.write_bytes(
        archive([(MANIFEST_NAME, b"{}"), (symlink_entry(asset_name()), b"/etc/passwd")])
    )
    error = _load_hostile(source)
    assert error.context["entry_reason"] == "symlink"
    assert error.context["entry"] == 1


# --- bombs: ratios and totals from the central directory --------------------------------


def test_t1_expanded_total_is_budgeted_before_any_entry_is_decompressed(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 16  # 4096 bytes that deflate poorly (ratio < 100)
    names = [asset_name(digit) for digit in "0123"]
    source = tmp_path / "wide.moana"
    source.write_bytes(archive([(MANIFEST_NAME, b"{}"), *((n, payload) for n in names)]))
    limits = ProjectLimits(max_archive_expanded_bytes=3 * 4096)  # 2 + 4 x 4096 declared
    with _no_decompression():
        error = _load_hostile(source, limits)
    assert isinstance(error, BudgetExceeded)
    assert error.context["resource"] == "archive_expanded_bytes"
    assert error.context["limit"] == 3 * 4096


@pytest.mark.parametrize("ratio", [101, 1000, 2**20])
def test_t1_declared_ratio_bomb_is_refused_before_decompression(tmp_path: Path, ratio: int) -> None:
    data = archive([(MANIFEST_NAME, b"{}"), (asset_name(), b"z" * 10)])
    # compressed (stored) size 10: declaring 10·ratio bytes exceeds 100:1 when ratio > 100
    source = tmp_path / "bomb.moana"
    source.write_bytes(with_central_size(data, 1, min(10 * ratio, 2**32 - 2)))
    with _no_decompression():
        error = _load_hostile(source)
    assert error.context["entry_reason"] == "expansion_ratio"
    assert error.context["entry"] == 1


def test_t1_entry_count_is_budgeted_from_the_end_record(tmp_path: Path) -> None:
    entries = [(f"assets/{index:064x}.png", b"") for index in range(9)]
    source = tmp_path / "many.moana"
    source.write_bytes(archive([(MANIFEST_NAME, b"{}"), *entries]))
    with _no_decompression():
        error = _load_hostile(source, ProjectLimits(max_archive_entries=9))
    assert isinstance(error, BudgetExceeded)
    assert (error.context["resource"], error.context["estimated"]) == ("archive_entries", 10)


# --- bounded reads: a huge source is never read whole -------------------------------------


@contextmanager
def _counted_reads(total: list[int]) -> Iterator[None]:
    real = os.read

    def counting(descriptor: int, size: int) -> bytes:
        chunk = real(descriptor, size)
        total[0] += len(chunk)
        return chunk

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "read", counting)
        yield


def _sparse(path: Path, head: bytes, size: int) -> None:
    with path.open("wb") as handle:
        handle.write(head)
        handle.truncate(size)


@pytest.mark.parametrize(
    ("head", "limits", "bound", "resource"),
    [
        (b"PK\x03\x04", ProjectLimits(max_archive_bytes=4096), 4097, "archive_bytes"),
        (b'{"kind":"', ProjectLimits(max_manifest_bytes=4096), 4097, None),
    ],
    ids=["archive", "json"],
)
def test_t2_oversized_sources_are_read_only_up_to_their_bound(
    tmp_path: Path, head: bytes, limits: ProjectLimits, bound: int, resource: str | None
) -> None:
    source = tmp_path / "huge.moana"
    _sparse(source, head, 64 * 1024 * 1024)  # 64 MiB on disk, sparse: no real IO
    total = [0]
    with _counted_reads(total):
        error = _load_hostile(source, limits)
    assert 0 < total[0] <= bound  # something was read, never the whole file
    if resource is None:
        assert error.context["reason"] == "too_large"
    else:
        assert error.context["resource"] == resource
