"""Errors never leak secrets, absolute paths or tracebacks (MOANART.md section 20, AC1).

The planted :data:`~tests.security.corpus.SECRET` is placed where an attacker or an
unlucky host would put sensitive text: the directory of the input, a hostile value,
the message of an unexpected internal failure. The CLI output and every domain error
must reveal none of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from moanart.api import load_document
from moanart.cli import commands
from moanart.core.errors import MoanArtError, ReadError
from moanart.project import load_project

from .corpus import SECRET
from .guards import assert_clean_error

pytestmark = pytest.mark.security


def _secret_directory(tmp_path: Path) -> Path:
    directory = tmp_path / f"home-{SECRET}" / "private"
    directory.mkdir(parents=True)
    return directory


def _run_cli(capsys: pytest.CaptureFixture[str], *arguments: str) -> tuple[int, str]:
    code = commands.main(list(arguments))
    captured = capsys.readouterr()
    return code, captured.out + captured.err


@pytest.mark.parametrize(
    ("payload", "exit_code"),
    [
        (b'{"a":' * 64 + b"0" + b"}" * 64, 2),
        (f'{{"schema_version":"1.0","id":"{SECRET}"}}'.encode(), 2),
        (b"\xff" * 16, 2),
    ],
    ids=["too-deep", "secret-value", "binary"],
)
def test_ac1_cli_rejection_reveals_no_path_or_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], payload: bytes, exit_code: int
) -> None:
    source = _secret_directory(tmp_path) / "input.moanart.json"
    source.write_bytes(payload)
    code, output = _run_cli(capsys, "validate", str(source))
    assert code == exit_code
    assert SECRET not in output
    assert str(tmp_path) not in output
    assert json.dumps(str(tmp_path))[1:-1] not in output  # nor its JSON-escaped form
    assert "Traceback" not in output
    result = json.loads(output.splitlines()[0])
    assert result["ok"] is False


def test_ac1_cli_missing_file_names_only_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = _secret_directory(tmp_path) / "absent.moanart.json"
    code, output = _run_cli(capsys, "validate", str(missing))
    assert code == ReadError.exit_code
    assert SECRET not in output
    assert "absent.moanart.json" in output  # the bare name helps; the path is never echoed


def test_ac1_cli_internal_failure_hides_its_message_and_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError(f"connection string password={SECRET}")

    monkeypatch.setattr(commands, "load_document", explode)
    code, output = _run_cli(capsys, "validate", str(tmp_path / "any.moanart.json"))
    assert code == MoanArtError.exit_code
    assert SECRET not in output
    assert "Traceback" not in output


def test_ac1_domain_errors_never_echo_paths(tmp_path: Path) -> None:
    directory = _secret_directory(tmp_path)
    for call in (
        lambda: load_document(directory / "absent.moanart.json"),
        lambda: load_project(directory / "absent"),
        lambda: load_document(directory),
        lambda: load_project(directory),
    ):
        with pytest.raises(MoanArtError) as caught:
            call()
        assert_clean_error(caught.value, tmp_path, SECRET, directory)
