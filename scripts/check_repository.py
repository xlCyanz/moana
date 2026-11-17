"""Check planning, skill metadata, links and configuration without rendering sprites."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml
from pydantic import Field

# Also support direct invocation from the repository's documented skill commands.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.planning import (
    ROOT,
    StrictModel,
    check_generated,
    generated_documents,
    load_catalog,
)

EXPECTED_SKILLS = {
    "moana-python",
    "moana-graphics",
    "moana-pixel-art",
    "moana-architecture",
    "moana-testing",
    "moana-code-review",
    "moana-issue-planning",
}


class SkillMetadata(StrictModel):
    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)
    description: str = Field(min_length=1, max_length=1024)


class SkillInterface(StrictModel):
    display_name: str = Field(min_length=1)
    short_description: str = Field(min_length=25, max_length=64)
    default_prompt: str = Field(min_length=1)


class SkillUI(StrictModel):
    interface: SkillInterface


class AgentRole(StrictModel):
    name: str = Field(pattern=r"^moana_[a-z_]+$")
    description: str = Field(min_length=1)
    developer_instructions: str = Field(min_length=1)


def check_skill(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n(.+)\Z", content, re.DOTALL)
    if not match:
        raise ValueError(f"Missing frontmatter or body: {path}")
    metadata = SkillMetadata.model_validate(yaml.safe_load(match[1]))
    if metadata.name != path.parent.name:
        raise ValueError(f"Skill name/directory mismatch: {path}")
    if "[TODO:" in content or "<" in metadata.description or ">" in metadata.description:
        raise ValueError(f"Invalid skill placeholder or description: {path}")
    ui = SkillUI.model_validate(
        yaml.safe_load((path.parent / "agents/openai.yaml").read_text(encoding="utf-8"))
    )
    if f"${metadata.name}" not in ui.interface.default_prompt:
        raise ValueError(f"Default prompt must mention skill: {path}")


def markdown_files(root: Path) -> list[Path]:
    files = list(root.glob("*.md"))
    for folder in ("docs", "examples", ".agents", ".github"):
        files.extend((root / folder).rglob("*.md"))
    return sorted(files)


def check_links(root: Path) -> list[str]:
    errors = []
    for path in markdown_files(root):
        for target in re.findall(r"\[[^\]\n]*\]\(([^)\s]+)\)", path.read_text(encoding="utf-8")):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve()
            if not destination.is_relative_to(root.resolve()) or not destination.exists():
                errors.append(
                    f"Broken or external local link: {path.relative_to(root)} -> {target}"
                )
    return errors


def check_repository(root: Path = ROOT) -> list[str]:
    issues, requirements = load_catalog(root)
    errors = check_generated(root, generated_documents(issues, requirements))
    errors.extend(check_links(root))
    sections = re.findall(
        r"^## (\d+)\. ", (root / "MOANA.md").read_text(encoding="utf-8"), re.MULTILINE
    )
    if sections != [str(i) for i in range(1, 26)]:
        errors.append("MOANA.md must contain the 25 numbered sections in order")
    covered_sections = {section for requirement in requirements for section in requirement.sections}
    if covered_sections != set(range(1, 26)):
        errors.append("Requirement catalog does not cover all specification sections")
    skills = list((root / ".agents/skills").glob("*/SKILL.md"))
    if {path.parent.name for path in skills} != EXPECTED_SKILLS:
        errors.append("Expected seven named Moana skills")
    for skill in skills:
        check_skill(skill)
    names = []
    for path in (root / ".codex/agents").glob("*.toml"):
        role = AgentRole.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
        names.append(role.name)
    if len(names) != 8 or len(set(names)) != 8 or "moana_documentation_writer" not in names:
        errors.append("Expected eight distinct Codex roles including documentation")
    config = tomllib.loads((root / ".codex/config.toml").read_text(encoding="utf-8"))
    if config != {"agents": {"enabled": True, "max_concurrent_threads_per_session": 3}}:
        errors.append("Codex settings changed; review capability audit and validator together")
    for path in [root / "pyproject.toml", root / "uv.lock"]:
        tomllib.loads(path.read_text(encoding="utf-8"))
    for path in (root / "examples/specs").glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    for path in (root / ".github").rglob("*.yml"):
        if not isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict):
            errors.append(f"YAML mapping required: {path}")
    # BaseLoader preserves GitHub's `on` key instead of treating it as a YAML 1.1 boolean.
    workflow = yaml.load(
        (root / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader
    )
    if not isinstance(workflow, dict) or not {"on", "jobs", "permissions"} <= workflow.keys():
        errors.append("CI must define triggers, jobs and permissions")
    else:
        steps = workflow["jobs"]["verify"]["steps"]
        uv_steps = [
            step for step in steps if step.get("uses", "").startswith("astral-sh/setup-uv@")
        ]
        if (
            len(uv_steps) != 1
            or uv_steps[0]["with"]["version"]
            != (root / ".uv-version").read_text(encoding="utf-8").strip()
        ):
            errors.append("CI and bootstrap must pin the same uv version")
    if not isinstance(
        yaml.safe_load((root / ".pre-commit-config.yaml").read_text(encoding="utf-8")), dict
    ):
        errors.append("Invalid pre-commit configuration")
    return errors


def main() -> int:
    try:
        errors = check_repository()
    except (ValueError, OSError, yaml.YAMLError) as exception:
        print(f"Repository validation failed: {exception}")
        return 1
    for error in errors:
        print(error)
    if not errors:
        issues, requirements = load_catalog()
        print(f"Repository OK: {len(issues)} issues, {len(requirements)} requirements, 7 skills")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
