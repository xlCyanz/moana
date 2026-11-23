"""Instrumentation of the adversarial suite: allocation and IO tripwires, bounds, snapshots.

A tripwire replaces the functions that reserve large buffers (NumPy constructors and
array builders, Pillow image creation/opening) or that touch the filesystem for writing
(``os`` primitives and ``open`` in a writing mode) with a function that raises
:class:`TripwireHit`. ``TripwireHit`` is a ``pytest.fail.Exception``: it derives from
``BaseException``, so no ``except Exception`` or ``except OSError`` in the code under
test can swallow it, and Hypothesis still treats it as a test failure it can shrink.

The tripwires are installed only around the call under test, never for the whole
test, so the setup (writing hostile files to ``tmp_path``) is unaffected.

Not tripwired (documented in the README): ``bytearray``/``bytes`` construction,
``ndarray.copy()``/``astype()`` and metadata calls such as ``os.chmod``, ``os.utime``
and ``os.ftruncate``.
"""

from __future__ import annotations

import builtins
import io
import os
import time
import tracemalloc
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Final, NoReturn

import numpy as np
import pytest
from _pytest.outcomes import Failed  # the class of pytest.fail.Exception, typed
from hypothesis import HealthCheck, settings
from PIL import Image

from moanart.core.errors import ErrorDetail, MoanArtError

__all__ = [
    "MAX_REJECTION_BYTES",
    "MAX_REJECTION_SECONDS",
    "Rejection",
    "TripwireHit",
    "assert_bounded",
    "assert_clean_error",
    "bounded_settings",
    "error_text",
    "forbid",
    "forbid_allocation",
    "forbid_effects",
    "forbid_writes",
    "measure",
    "peak_bytes",
    "pointers",
    "reasons",
    "tree_state",
]

_NUMPY_ALLOCATORS: Final = (
    "zeros",
    "empty",
    "full",
    "ones",
    "zeros_like",
    "empty_like",
    "full_like",
    "frombuffer",
    "array",
    "asarray",
    "ascontiguousarray",
    "arange",
    "repeat",
    "pad",
    "concatenate",
    "stack",
    "tile",
    "broadcast_to",
)
_PILLOW_ALLOCATORS: Final = ("new", "open", "frombytes", "frombuffer", "fromarray")
_WRITE_FLAGS: Final = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_OS_WRITERS: Final = (
    "replace",
    "rename",
    "link",
    "symlink",
    "mkdir",
    "makedirs",
    "unlink",
    "remove",
    "rmdir",
    "truncate",
)

MAX_REJECTION_SECONDS: Final = 2.0
"""Wall-clock bound of one hostile rejection (measured maximum on the dev machine: see
the README); far above it means the engine did work proportional to a declared size."""
MAX_REJECTION_BYTES: Final = 32 * 1024 * 1024
"""Python-traced peak bound of one hostile rejection. The largest legitimate input of
the corpus is an 8 MiB document read and decoded once (bytes plus str)."""


class TripwireHit(Failed):
    """A forbidden allocation or side effect was reached by a hostile input."""


def _trip(name: str) -> Callable[..., NoReturn]:
    def tripped(*_args: object, **_kwargs: object) -> NoReturn:
        raise TripwireHit(name)

    return tripped


@contextmanager
def forbid(owner: object, name: str) -> Iterator[None]:
    """Replace ``owner.name`` by a tripwire for the duration of the block."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(owner, name, _trip(f"{type(owner).__name__}.{name}"))
        yield


def _install_allocation(patch: pytest.MonkeyPatch) -> None:
    for name in _NUMPY_ALLOCATORS:
        patch.setattr(np, name, _trip(f"numpy.{name}"))
    for name in _PILLOW_ALLOCATORS:
        patch.setattr(Image, name, _trip(f"PIL.Image.{name}"))


def _writing_mode(mode: object) -> bool:
    return isinstance(mode, str) and any(flag in mode for flag in "wax+")


def _install_writes(patch: pytest.MonkeyPatch) -> None:
    real_open = os.open
    real_builtin_open = builtins.open

    def guarded_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & _WRITE_FLAGS:
            raise TripwireHit("os.open for writing")
        return real_open(path, flags, *args, **kwargs)

    def guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if _writing_mode(mode):
            raise TripwireHit("open for writing")
        return real_builtin_open(file, mode, *args, **kwargs)

    patch.setattr(os, "open", guarded_os_open)
    patch.setattr(builtins, "open", guarded_open)
    patch.setattr(io, "open", guarded_open)
    for name in _OS_WRITERS:
        patch.setattr(os, name, _trip(f"os.{name}"))


@contextmanager
def forbid_allocation() -> Iterator[None]:
    """Fail on any NumPy buffer constructor or Pillow image creation/opening."""
    with pytest.MonkeyPatch.context() as patch:
        _install_allocation(patch)
        yield


@contextmanager
def forbid_writes() -> Iterator[None]:
    """Fail on any filesystem write, creation, rename, link or removal (reads allowed)."""
    with pytest.MonkeyPatch.context() as patch:
        _install_writes(patch)
        yield


@contextmanager
def forbid_effects() -> Iterator[None]:
    """Both tripwires: the rejection must happen before buffers and before any write."""
    with pytest.MonkeyPatch.context() as patch:
        _install_allocation(patch)
        _install_writes(patch)
        yield


def bounded_settings(
    max_examples: int, seconds: float = 5, *, function_fixtures: bool = False
) -> settings:
    """The Hypothesis policy of the suite: bounded, deadline set, derandomised."""
    checks = [HealthCheck.too_slow]
    if function_fixtures:
        checks.append(HealthCheck.function_scoped_fixture)
    return settings(
        max_examples=max_examples,
        deadline=timedelta(seconds=seconds),
        derandomize=True,
        suppress_health_check=checks,
    )


def tree_state(root: Path) -> dict[str, bytes]:
    """Every entry under ``root``: relative POSIX path to bytes (links and dirs marked)."""
    state: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        key = path.relative_to(root).as_posix()
        if path.is_symlink():
            state[key] = b"link:" + os.fsencode(os.readlink(path))
        elif path.is_dir():
            state[key + "/"] = b""
        else:
            state[key] = path.read_bytes()
    return state


def peak_bytes(call: Callable[[], object]) -> tuple[Exception | None, int]:
    """Run ``call``; its exception (if any) and the Python-traced peak above the baseline.

    Works whether or not ``tracemalloc`` is already tracing (``PYTHONTRACEMALLOC``):
    an active trace is reused and left running.
    """
    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()
    try:
        baseline = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        error: Exception | None = None
        try:
            call()
        except Exception as exc:  # the caller asserts the type
            error = exc
        return error, max(0, tracemalloc.get_traced_memory()[1] - baseline)
    finally:
        if not was_tracing:
            tracemalloc.stop()


@dataclass(frozen=True, slots=True)
class Rejection:
    """Outcome of one measured call: its exception, wall-clock seconds and traced peak."""

    error: Exception | None
    seconds: float
    peak: int


def measure(call: Callable[[], object]) -> Rejection:
    """Run ``call`` once, timing it and tracing its Python memory peak."""
    start = time.perf_counter()
    error, peak = peak_bytes(call)
    return Rejection(error, time.perf_counter() - start, peak)


def assert_bounded(
    rejection: Rejection,
    *,
    seconds: float = MAX_REJECTION_SECONDS,
    peak: int = MAX_REJECTION_BYTES,
) -> Exception:
    """The call failed within the time and traced-memory bounds; returns its error."""
    assert rejection.error is not None, "the hostile request was accepted"
    assert rejection.seconds < seconds, f"rejection took {rejection.seconds:.3f} s"
    assert rejection.peak < peak, f"rejection traced {rejection.peak} bytes"
    return rejection.error


def pointers(error: MoanArtError) -> set[str | None]:
    """The pointer of an error and of each of its details."""
    return {error.json_pointer, *(detail.json_pointer for detail in error.details)}


def reasons(error: MoanArtError) -> set[object]:
    """The ``reason`` of an error and of each of its details."""
    return {error.context.get("reason"), *(d.context.get("reason") for d in error.details)}


def _detail_text(detail: ErrorDetail) -> list[str]:
    return [detail.message, str(detail.json_pointer), repr(dict(detail.context))]


def error_text(error: MoanArtError) -> str:
    """Everything an error exposes: message, repr, pointer, context, details and notes."""
    parts = [str(error), repr(error), error.message, str(error.json_pointer)]
    parts.append(repr(dict(error.context)))
    for detail in error.details:
        parts.extend(_detail_text(detail))
    parts.extend(str(note) for note in getattr(error, "__notes__", ()))
    return "\n".join(parts)


def assert_clean_error(error: BaseException, *forbidden: str | Path) -> MoanArtError:
    """The error is a domain error whose exposed text contains none of ``forbidden``.

    The message of a chained non-domain exception (a Pydantic, ``OSError`` or Pillow
    error, which may quote input or paths) must not be copied into the domain error
    either. Context values are scalars or tuples of scalars (ADR-010), so nothing but
    the text checked here can carry untrusted input or a path.
    """
    assert isinstance(error, MoanArtError), f"not a domain error: {type(error).__name__}"
    text = error_text(error)
    for item in forbidden:
        needle = str(item)
        assert needle not in text, "the error leaks a path or an untrusted value"
    for chained in (error.__cause__, error.__context__):
        if chained is None or isinstance(chained, MoanArtError):
            continue
        inner = str(chained)
        if len(inner) > 16:
            assert inner not in text, "the error copies a chained foreign message"
    return error
