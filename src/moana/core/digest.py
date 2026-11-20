"""Visual digest of RGBA pixels (MOANA.md section 14), shared by canvas and render.

``sha256:`` + hex SHA-256 of width and height as ``uint32`` big-endian followed by
the straight RGBA bytes in row-major order. Standard library only.
"""

from __future__ import annotations

import hashlib

__all__ = ["visual_digest"]


def visual_digest(width: int, height: int, rgba: bytes | memoryview) -> str:
    """Digest of a ``width`` x ``height`` frame whose pixels are ``rgba``."""
    digest = hashlib.sha256(width.to_bytes(4, "big") + height.to_bytes(4, "big"))
    digest.update(rgba)
    return "sha256:" + digest.hexdigest()
