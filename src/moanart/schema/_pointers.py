"""JSON Pointer helpers shared by the reader and error mapping (RFC 6901).

Pointers locate input nodes, so member names from the input can appear in them.
Names longer than :data:`MAX_POINTER_TOKEN` characters are never copied into an
error: the pointer stops at the nearest ancestor that can be named safely. Every
schema member name is far shorter, so valid paths are never shortened.
"""

from __future__ import annotations

from typing import Final

from moanart.core.errors import detail_sort_key

__all__ = ["MAX_POINTER_TOKEN", "ROOT", "Location", "child_pointer", "detail_sort_key"]

MAX_POINTER_TOKEN: Final = 64


Location = tuple[str, bool]
"""A pointer and whether it is exact (``False`` once it stopped at an ancestor)."""

ROOT: Final[Location] = ("", True)


def child_pointer(location: Location, token: str | int) -> Location:
    """Location of a child; it stays at the ancestor once a token is too long."""
    pointer, exact = location
    text = str(token)
    if not exact or len(text) > MAX_POINTER_TOKEN:
        return pointer, False
    return f"{pointer}/{text.replace('~', '~0').replace('/', '~1')}", True
