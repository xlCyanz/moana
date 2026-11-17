"""Exercise repository reads under a Windows-like non-UTF-8 default codec."""

from pathlib import Path

import pytest

from scripts.check_repository import check_repository
from scripts.planning import ROOT, generated_documents, load_catalog


def test_repository_checks_do_not_depend_on_default_text_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Path.read_text

    def windows_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        return original(path, encoding=encoding or "cp1252", errors=errors)

    monkeypatch.setattr(Path, "read_text", windows_read_text)
    issues, requirements = load_catalog(ROOT)
    assert generated_documents(issues, requirements)
    assert check_repository(ROOT) == []
