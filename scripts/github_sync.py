"""Mirror the local backlog to GitHub: labels, milestones, issues and dependencies.

The catalog in docs/issues/catalog.json stays the source of truth. This tool is
idempotent: issues are matched by their MOANA-xxx title prefix and updated in place.
It defaults to a dry run; pass --apply to write through the authenticated `gh` CLI.

Every object is compared with its current state on GitHub first and only changed
fields are written, so an unchanged backlog costs reads only. Transient network
failures are retried with exponential backoff; a POST is retried only when the
failure happened before the request reached GitHub, so it can never be duplicated.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.planning import PHASE_GATES, ROOT, Issue, generated_documents, load_catalog

BACKLOG_LABEL = "moana"  # remote label, not renamed (ADR-041)
MAP_PATH = "docs/issues/github-map.json"
ISSUE_LINK = re.compile(r"^(MOANA-\d{3}|MOA-\d{3})\.md$")
MARKDOWN_LINK = re.compile(r"\[([^\]\n]*)\]\(([^)\s]+)\)")
SYNC_NOTE = (
    "> Sincronizado desde `docs/issues/catalog.json` con `scripts/github_sync.py`. "
    "Edita el catálogo y vuelve a sincronizar: los cambios hechos aquí se sobrescriben.\n"
)


IDEMPOTENT_METHODS = frozenset({"GET", "PATCH", "PUT", "DELETE"})
# The request never left this machine: safe to retry any method, POST included.
CONNECT_ERRORS = ("dial tcp", "no such host", "connection refused", "tls handshake timeout")
# The request may have reached GitHub: safe to retry only idempotent methods.
TRANSIENT_ERRORS = (
    "i/o timeout",
    "connection reset",
    "unexpected eof",
    "(http 500)",
    "(http 502)",
    "(http 503)",
    "(http 504)",
    "secondary rate limit",
)
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 2.0

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class Label:
    name: str
    color: str
    description: str


PHASE_COLORS = ("bfd4f2", "c5def5", "a2c4f0", "7fa7e0", "5b8bd0", "3a6fc0")
PRIORITY_COLORS = {"P0": "b60205", "P1": "d93f0b", "P2": "fbca04", "P3": "c2e0c6"}
STATUS_COLORS = {
    "todo": "ededed",
    "ready": "0e8a16",
    "in_progress": "1d76db",
    "blocked": "e99695",
    "review": "5319e7",
    "done": "006b75",
}
PRIORITY_TEXT = {
    "P0": "Fundamento o bloqueante",
    "P1": "Funcionalidad central",
    "P2": "Funcionalidad avanzada",
    "P3": "Mejora opcional",
}


def milestone_title(phase: str) -> str:
    return f"{phase} — {PHASE_GATES[phase][0]}"


def issue_title(issue: Issue) -> str:
    return f"{issue.id} — {issue.title}"


def issue_labels(issue: Issue) -> list[str]:
    """Labels applied to one issue; status mirrors the catalog."""
    return [
        BACKLOG_LABEL,
        f"phase:{issue.phase}",
        f"priority:{issue.priority}",
        f"complexity:{issue.complexity}",
        f"status:{issue.status}",
        *(f"module:{module}" for module in issue.modules),
    ]


def label_specs(issues: Sequence[Issue]) -> list[Label]:
    """All labels the backlog needs, in a stable order."""
    labels = [Label(BACKLOG_LABEL, "0b3d91", "Issue sincronizado desde el backlog de Moana")]
    labels += [
        Label(f"phase:{phase}", PHASE_COLORS[index], f"Fase {phase}: {name}")
        for index, (phase, (name, _)) in enumerate(PHASE_GATES.items())
    ]
    labels += [
        Label(f"priority:{key}", color, PRIORITY_TEXT[key])
        for key, color in PRIORITY_COLORS.items()
    ]
    labels += [
        Label(f"complexity:{size}", "f9d0c4", f"Complejidad relativa {size}")
        for size in ("S", "M", "L", "XL")
    ]
    labels += [
        Label(f"status:{state}", color, f"Estado del catálogo: {state}")
        for state, color in STATUS_COLORS.items()
    ]
    modules = sorted({module for issue in issues for module in issue.modules})
    labels += [Label(f"module:{module}", "d4c5f9", f"Módulo {module}") for module in modules]
    return labels


def github_body(
    markdown: str,
    *,
    repository: str,
    numbers: Mapping[str, int],
    aliases: Mapping[str, str],
    own_number: int | None,
    branch: str = "main",
) -> str:
    """Convert a generated issue document into a GitHub issue body.

    Links to other issues become issue URLs, other relative links become blob URLs,
    the H1 is dropped (GitHub shows the title) and the generator note is replaced.
    """
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    text = "\n".join(lines).lstrip("\n")
    text = re.sub(r"^> Generado por .*\n", SYNC_NOTE, text, count=1, flags=re.M)

    def replace(match: re.Match[str]) -> str:
        label, target = match[1], match[2]
        if target.startswith(("http://", "https://", "#", "mailto:")):
            return match[0]
        path, _, anchor = target.partition("#")
        if issue := ISSUE_LINK.match(path):
            identifier = aliases.get(issue[1], issue[1])
            if identifier in numbers:
                return f"[{label}](https://github.com/{repository}/issues/{numbers[identifier]})"
        resolved = posixpath.normpath(posixpath.join("docs/issues", path))
        suffix = f"#{anchor}" if anchor else ""
        return f"[{label}](https://github.com/{repository}/blob/{branch}/{resolved}{suffix})"

    text = MARKDOWN_LINK.sub(replace, text)
    if own_number is not None:
        text = text.replace("#<número>", f"#{own_number}")
    return text


def is_retryable(method: str, stderr: str) -> bool:
    """Whether a failed `gh api` call may be repeated without side effects."""
    message = stderr.lower()
    if any(marker in message for marker in CONNECT_ERRORS):
        return True
    return method in IDEMPOTENT_METHODS and any(marker in message for marker in TRANSIENT_ERRORS)


class GitHub:
    """Thin wrapper over `gh api`; writes are logged, counted and optionally skipped."""

    def __init__(
        self,
        repository: str,
        *,
        apply: bool,
        run: Runner = subprocess.run,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.repository = repository
        self.apply = apply
        self.writes = 0
        self._run = run
        self._sleep = sleep

    def call(
        self,
        method: str,
        endpoint: str,
        payload: Mapping[str, Any] | None = None,
        *,
        paginate: bool = False,
        allow_missing: bool = False,
    ) -> Any:
        write = method != "GET"
        if write:
            self.writes += 1
            if not self.apply:
                print(f"[dry-run] {method} {endpoint}")
                return None
        command = ["gh", "api", "-X", method, endpoint.format(repo=self.repository)]
        if paginate:
            command.append("--paginate")
        if payload is not None:
            command += ["--input", "-"]
        result = self._execute(method, endpoint, command, payload)
        if result.returncode:
            if allow_missing and ("404" in result.stderr or "Not Found" in result.stdout):
                return None
            raise RuntimeError(f"gh api {method} {endpoint} failed: {result.stderr.strip()}")
        if write:
            self._sleep(0.5)  # Stay below GitHub secondary rate limits for content creation.
        if not result.stdout.strip():
            return None
        if paginate:
            return _paginated(result.stdout)
        return json.loads(result.stdout)

    def _execute(
        self,
        method: str,
        endpoint: str,
        command: list[str],
        payload: Mapping[str, Any] | None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one call, retrying transient failures with exponential backoff."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            result = self._run(
                command,
                input=json.dumps(payload) if payload is not None else None,
                capture_output=True,
                encoding="utf-8",
                check=False,
            )
            if not result.returncode or attempt == MAX_ATTEMPTS:
                return result
            if not is_retryable(method, result.stderr):
                return result
            delay = BACKOFF_SECONDS * 2 ** (attempt - 1)
            print(
                f"[retry {attempt}/{MAX_ATTEMPTS - 1}] {method} {endpoint} in {delay:g}s: "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
            self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover


def changed_fields(current: Mapping[str, Any], desired: Mapping[str, Any]) -> dict[str, Any]:
    """Fields of `desired` whose value differs from `current`."""
    return {key: value for key, value in desired.items() if current.get(key) != value}


def label_update(item: Mapping[str, Any], label: Label) -> dict[str, Any]:
    """Fields to PATCH on an existing label; empty when it already matches."""
    current = {
        "color": str(item.get("color") or "").lower(),
        "description": item.get("description") or "",
    }
    return changed_fields(current, {"color": label.color, "description": label.description})


def milestone_update(item: Mapping[str, Any], desired: Mapping[str, Any]) -> dict[str, Any]:
    """Fields to PATCH on an existing milestone; empty when it already matches."""
    current = {
        "title": item.get("title"),
        "description": item.get("description") or "",
        "state": item.get("state"),
    }
    return changed_fields(current, desired)


def _normalized_body(body: object) -> str:
    return str(body or "").replace("\r\n", "\n").strip()


def issue_update(item: Mapping[str, Any], desired: Mapping[str, Any]) -> dict[str, Any]:
    """Fields to PATCH on an existing issue; empty when it already matches.

    Labels compare as sets and bodies ignore line-ending and edge-whitespace
    differences introduced by GitHub; a changed field is sent in its desired form.
    """
    milestone = item.get("milestone")
    update: dict[str, Any] = {}
    if item.get("title") != desired["title"]:
        update["title"] = desired["title"]
    if _normalized_body(item.get("body")) != _normalized_body(desired["body"]):
        update["body"] = desired["body"]
    if {label["name"] for label in item.get("labels", [])} != set(desired["labels"]):
        update["labels"] = desired["labels"]
    if (milestone["number"] if milestone else None) != desired["milestone"]:
        update["milestone"] = desired["milestone"]
    if item.get("state") != desired["state"]:
        update["state"] = desired["state"]
    reason = desired.get("state_reason")
    if reason is not None and (update.get("state") or item.get("state_reason") != reason):
        update["state"] = desired["state"]
        update["state_reason"] = reason
    return update


def _paginated(raw: str) -> list[Any]:
    """Decode the concatenated JSON arrays printed by `gh api --paginate`."""
    decoder = json.JSONDecoder()
    items: list[Any] = []
    position = 0
    raw = raw.strip()
    while position < len(raw):
        chunk, position = decoder.raw_decode(raw, position)
        items.extend(chunk)
        while position < len(raw) and raw[position].isspace():
            position += 1
    return items


def sync_labels(github: GitHub, labels: Sequence[Label]) -> None:
    existing = {
        item["name"]: item
        for item in github.call("GET", "repos/{repo}/labels?per_page=100", paginate=True)
    }
    for label in labels:
        if label.name in existing:
            update = label_update(existing[label.name], label)
            if update:
                endpoint = f"repos/{{repo}}/labels/{label.name.replace(':', '%3A')}"
                github.call("PATCH", endpoint, update)
        else:
            payload = {"name": label.name, "color": label.color, "description": label.description}
            github.call("POST", "repos/{repo}/labels", payload)


def sync_milestones(github: GitHub, issues: Sequence[Issue]) -> dict[str, int]:
    existing = {
        item["title"]: item
        for item in github.call(
            "GET", "repos/{repo}/milestones?state=all&per_page=100", paginate=True
        )
    }
    numbers: dict[str, int] = {}
    for phase, (_, gate) in PHASE_GATES.items():
        title = milestone_title(phase)
        selected = [issue for issue in issues if issue.phase == phase]
        state = "closed" if selected and all(i.status == "done" for i in selected) else "open"
        payload = {"title": title, "description": f"Puerta de salida: {gate}", "state": state}
        if title in existing:
            number = existing[title]["number"]
            update = milestone_update(existing[title], payload)
            if update:
                github.call("PATCH", f"repos/{{repo}}/milestones/{number}", update)
            numbers[phase] = number
        else:
            created = github.call("POST", "repos/{repo}/milestones", payload)
            numbers[phase] = created["number"] if created else 0
    return numbers


def existing_issues(github: GitHub) -> dict[str, dict[str, Any]]:
    items = github.call(
        "GET", f"repos/{{repo}}/issues?state=all&labels={BACKLOG_LABEL}&per_page=100", paginate=True
    )
    found: dict[str, dict[str, Any]] = {}
    for item in items:
        match = re.match(r"^(MOANA-\d{3}) ", item["title"])
        if match and "pull_request" not in item:
            found[match[1]] = item
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="xlCyanz/moana", help="owner/name on GitHub")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = parser.parse_args(argv)
    issues, requirements = load_catalog()
    documents = generated_documents(issues, requirements)
    aliases = {alias: issue.id for issue in issues for alias in issue.aliases}
    github = GitHub(args.repo, apply=args.apply)

    sync_labels(github, label_specs(issues))
    milestones = sync_milestones(github, issues)
    found = existing_issues(github)

    # Pass 1: make sure every issue exists so cross-links can use real numbers.
    for issue in issues:
        if issue.id not in found:
            created = github.call(
                "POST",
                "repos/{repo}/issues",
                {"title": issue_title(issue), "body": "Sincronizando…", "labels": [BACKLOG_LABEL]},
            )
            if created:
                found[issue.id] = created
    numbers = {identifier: item["number"] for identifier, item in found.items()}

    # Pass 2: full body, labels, milestone and state.
    for issue in issues:
        own = numbers.get(issue.id)
        body = github_body(
            documents[f"docs/issues/{issue.id}.md"],
            repository=args.repo,
            numbers=numbers,
            aliases=aliases,
            own_number=own,
        )
        payload: dict[str, Any] = {
            "title": issue_title(issue),
            "body": body,
            "labels": issue_labels(issue),
            "milestone": milestones.get(issue.phase) or None,
            "state": "closed" if issue.status == "done" else "open",
        }
        if issue.status == "done":
            payload["state_reason"] = "completed"
        update = issue_update(found[issue.id], payload) if issue.id in found else payload
        if update:
            github.call("PATCH", f"repos/{{repo}}/issues/{own or 0}", update)

    # Pass 3: native "blocked by" relationships.
    for issue in issues:
        own = numbers.get(issue.id)
        if own is None:
            continue
        current = github.call(
            "GET", f"repos/{{repo}}/issues/{own}/dependencies/blocked_by", allow_missing=True
        )
        linked = {item["number"] for item in current or []}
        for dependency in issue.dependencies:
            target = found.get(dependency)
            if target and target["number"] not in linked:
                github.call(
                    "POST",
                    f"repos/{{repo}}/issues/{own}/dependencies/blocked_by",
                    {"issue_id": target["id"]},
                )

    if args.apply:
        mapping = {"repository": args.repo, "issues": dict(sorted(numbers.items()))}
        (ROOT / MAP_PATH).write_text(
            json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    mode = "applied" if args.apply else "dry run"
    print(f"Synced {len(issues)} issues to {args.repo} ({mode}; {github.writes} writes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
