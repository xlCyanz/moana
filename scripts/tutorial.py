"""Parse and run the executable ``sh`` blocks of the AI workflow guide (MOANA-033).

``docs/guides/ai-workflows.md`` is the single source of the tutorial commands: its
``sh`` blocks are parsed into an ordered list of :class:`Step` values and run from a
directory laid out like the repository root. ``tests/unit/api/test_tutorial.py``
runs them with the development environment (``moana`` in process) and
``scripts/check_wheel.py`` with the installed wheel (``moana`` executable and the
venv interpreter in isolated mode), so the guide cannot drift from either.

The grammar is deliberately tiny: one command per line, ``moana``, ``python`` or
``mkdir -p DIR``, an optional ``> FILE`` stdout redirect and an optional trailing
``# exit N`` (expected exit code, default 0). Anything else (pipes, chaining, other
redirects, variables, globs, continuations, other fenced block languages) is a
:class:`GuideError`, so a block can never be skipped silently.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
GUIDE: Final = ROOT / "docs" / "guides" / "ai-workflows.md"
INPUTS: Final = (
    "examples/tutorial/potion.moana.json",
    "examples/tutorial/potion-recolor.edit.json",
    "examples/tutorial/potion-typo.edit.json",
    "examples/tutorial/potion_flow.py",
    "examples/specs/minimal.moana.json",
)
"""Repository files the guide's commands read; copy them into the run directory."""
OUTPUT_DIR: Final = "artifacts/tutorial"
ALLOWED_LANGUAGES: Final = frozenset({"sh", "json", "python"})
PROGRAMS: Final = frozenset({"moana", "python", "mkdir"})
FORBIDDEN_TOKENS: Final = frozenset({"|", ">>", "2>", "&&", "||", ";", "<", "&"})
FORBIDDEN_CHARACTERS: Final = ("$", "*", "`")
TIMEOUT: Final = 300

# Hand oracle of the recolor: liquid_fill is [5, 9, 11, 14) (30 pixels) and
# liquid_shine, drawn on top, covers (6, 10) and (6, 11): 28 pixels change.
EXPECTED_CHANGED: Final = frozenset(
    (x, y) for x in range(5, 11) for y in range(9, 14) if (x, y) not in {(6, 10), (6, 11)}
)

_FENCE: Final = re.compile(r"^```([^\n]*)\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
_EXIT: Final = re.compile(r"\s+#\s*exit\s+(\d+)\s*$")


class GuideError(ValueError):
    """The guide contains a block or command outside the executable grammar."""


class StepFailed(RuntimeError):
    """A step exited with a code other than the documented one."""


@dataclass(frozen=True, slots=True)
class Step:
    """One documented command: program, arguments, stdout target and expected exit."""

    line: str
    program: str
    arguments: tuple[str, ...]
    redirect: str | None
    exit_code: int


@dataclass(frozen=True, slots=True)
class Outcome:
    """What running a step produced."""

    step: Step
    exit_code: int
    stdout: str
    stderr: str


type MoanaRunner = Callable[[Sequence[str], Path], tuple[int, str, str]]
"""Runs ``moana ARGS`` in a directory and returns ``(exit code, stdout, stderr)``."""


def code_blocks(text: str) -> list[tuple[str, str]]:
    """Every fenced block as ``(language, body)``; unknown languages are an error."""
    blocks = [(match[1].strip(), match[2]) for match in _FENCE.finditer(text)]
    for language, _ in blocks:
        if language not in ALLOWED_LANGUAGES:
            raise GuideError(f"unsupported fenced block language: {language!r}")
    return blocks


def _tokens(line: str) -> list[str]:
    if line.endswith("\\"):
        raise GuideError(f"line continuation is not supported: {line}")
    tokens = shlex.split(line)
    for token in tokens:
        if token in FORBIDDEN_TOKENS or token.startswith("#"):
            raise GuideError(f"unsupported shell syntax {token!r}: {line}")
        if any(character in token for character in FORBIDDEN_CHARACTERS):
            raise GuideError(f"unsupported shell character in {token!r}: {line}")
    return tokens


def parse_step(raw: str) -> Step:
    """Parse one non-empty line of an ``sh`` block."""
    match = _EXIT.search(raw)
    line = _EXIT.sub("", raw).strip()
    tokens = _tokens(line)
    redirect = None
    if ">" in tokens:
        index = tokens.index(">")
        if tokens.count(">") != 1 or index != len(tokens) - 2:
            raise GuideError(f"'>' needs exactly one final target: {line}")
        tokens, redirect = tokens[:index], tokens[index + 1]
    if not tokens or tokens[0] not in PROGRAMS:
        raise GuideError(f"unsupported program: {line}")
    program, arguments = tokens[0], tuple(tokens[1:])
    if program == "mkdir" and (len(arguments) != 2 or arguments[0] != "-p" or redirect):
        raise GuideError(f"mkdir must be exactly 'mkdir -p DIR': {line}")
    exit_code = int(match[1]) if match else 0
    return Step(line, program, arguments, redirect, exit_code)


def parse_steps(text: str) -> list[Step]:
    """The ``sh`` commands of the guide, in document order."""
    return [
        parse_step(raw)
        for language, body in code_blocks(text)
        if language == "sh"
        for raw in body.splitlines()
        if raw.strip()
    ]


def guide_steps() -> list[Step]:
    """The steps of ``docs/guides/ai-workflows.md``."""
    return parse_steps(GUIDE.read_text(encoding="utf-8"))


def prepare(destination: Path) -> None:
    """Copy the files the guide reads into ``destination`` at their repository paths."""
    for name in INPUTS:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())


def command_runner(
    command: Sequence[str], environment: Mapping[str, str] | None = None
) -> MoanaRunner:
    """A :data:`MoanaRunner` that runs ``command`` (e.g. the installed ``moana``)."""

    def run(arguments: Sequence[str], cwd: Path) -> tuple[int, str, str]:
        completed = subprocess.run(
            [*command, *arguments],
            cwd=cwd,
            env=None if environment is None else dict(environment),
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=TIMEOUT,
        )
        return completed.returncode, completed.stdout, completed.stderr

    return run


def run_steps(
    steps: Sequence[Step],
    cwd: Path,
    *,
    moana: MoanaRunner,
    python: Sequence[str],
    environment: Mapping[str, str] | None = None,
) -> list[Outcome]:
    """Run ``steps`` in order from ``cwd``; :class:`StepFailed` on an unexpected exit.

    ``python`` is the interpreter command (for example ``[venv_python, "-I"]``).
    A redirect writes stdout as UTF-8 to its target, relative to ``cwd``.
    """
    python_runner = command_runner(python, environment)
    outcomes = []
    for step in steps:
        if step.program == "mkdir":
            (cwd / step.arguments[1]).mkdir(parents=True, exist_ok=True)
            outcome = Outcome(step, 0, "", "")
        else:
            runner = moana if step.program == "moana" else python_runner
            code, stdout, stderr = runner(step.arguments, cwd)
            outcome = Outcome(step, code, stdout, stderr)
        if outcome.exit_code != step.exit_code:
            raise StepFailed(
                f"{step.line}\nexited {outcome.exit_code}, documented {step.exit_code}\n"
                f"--- stdout ---\n{outcome.stdout}\n--- stderr ---\n{outcome.stderr}"
            )
        if step.redirect is not None:
            (cwd / step.redirect).write_text(outcome.stdout, encoding="utf-8")
        outcomes.append(outcome)
    return outcomes


def changed_pixels(before: Path, after: Path) -> frozenset[tuple[int, int]]:
    """Coordinates whose RGBA differs between two PNGs of the same size."""
    from PIL import Image  # tooling dependency, imported only when checking outputs

    with Image.open(before) as old_file, Image.open(after) as new_file:
        old, new = old_file.convert("RGBA"), new_file.convert("RGBA")
        if old.size != new.size:
            raise StepFailed(f"preview sizes differ: {old.size} != {new.size}")
        return frozenset(
            (x, y)
            for y in range(old.height)
            for x in range(old.width)
            if old.getpixel((x, y)) != new.getpixel((x, y))
        )


def check_outputs(root: Path) -> None:
    """Post-check of a finished run against the hand oracle of the recolor."""
    out = root / OUTPUT_DIR
    changed = changed_pixels(out / "potion-1x.png", out / "potion-r1-1x.png")
    if changed != EXPECTED_CHANGED:
        raise StepFailed(f"unexpected changed pixels: {sorted(changed ^ EXPECTED_CHANGED)}")
