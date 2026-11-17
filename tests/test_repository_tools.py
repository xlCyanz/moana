"""Exercise failure cases in repository tools using temporary artifacts."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.check_repository import check_links, check_skill
from scripts.planning import check_generated


def test_stale_and_orphan_issue_documents_fail(tmp_path: Path) -> None:
    folder = tmp_path / "docs/issues"
    folder.mkdir(parents=True)
    (folder / "MOA-001.md").write_text("stale", encoding="utf-8")
    (folder / "MOA-999.md").write_text("orphan", encoding="utf-8")
    errors = check_generated(tmp_path, {"docs/issues/MOA-001.md": "current"})
    assert any("Stale" in error for error in errors)
    assert any("Orphan" in error for error in errors)


def test_links_detect_missing_and_escaping_targets(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[missing](docs/missing.md) [escape](../external.md) "
        "[website](https://example.com/) [self](README.md)",
        encoding="utf-8",
    )
    assert len(check_links(tmp_path)) == 2


@pytest.mark.parametrize(
    "content",
    [
        "# No metadata",
        "---\nname: wrong-name\ndescription: A valid description\n---\nInstructions",
        "---\nname: moana-python\ndescription: ''\n---\nInstructions",
    ],
)
def test_invalid_skills_fail(tmp_path: Path, content: str) -> None:
    folder = tmp_path / "moana-python"
    folder.mkdir()
    entry = folder / "SKILL.md"
    entry.write_text(content, encoding="utf-8")
    with pytest.raises((ValueError, ValidationError)):
        check_skill(entry)
