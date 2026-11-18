"""``moana edit DOC BATCH``: one JSON object, exit codes 0/2/4/5 (MOANA-018, ADR-024).

Exit codes are written by hand from MOANA.md section 13, not read from the classes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from moana.cli import main

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "specs" / "minimal.moana.json"
BATCH = ROOT / "examples" / "specs" / "recolor.edit.json"


def run(capsys: Any, *arguments: str) -> tuple[int, dict[str, Any], str]:
    code = main(list(arguments))
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 1, captured.out
    assert "Traceback" not in captured.err
    payload: dict[str, Any] = json.loads(lines[0])
    return code, payload, captured.err


def write(path: Path, value: object) -> str:
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_edit_success_prints_the_new_revision_and_document(capsys: Any, tmp_path: Path) -> None:
    code, payload, err = run(capsys, "edit", str(EXAMPLE), str(BATCH))
    assert (code, payload["ok"], payload["command"], err) == (0, True, "edit", "")
    edit = payload["edit"]
    assert (edit["revision"], edit["base_revision"]) == (1, 0)
    assert edit["affected_ids"] == ["body_fill"]
    assert edit["document"]["layers"][0]["operations"][0]["color"] == "ink"
    assert edit["document"]["revision"] == 1
    assert edit["base_snapshot"] == json.loads(BATCH.read_text(encoding="utf-8"))["base_snapshot"]
    assert edit["snapshot_digest"] != edit["base_snapshot"]
    # The printed document validates on its own and is the next base.
    code, payload, _ = run(
        capsys, "validate", write(tmp_path / "next.moana.json", edit["document"])
    )
    assert (code, payload["document"]["snapshot_digest"]) == (0, edit["snapshot_digest"])


def test_edit_conflict_exits_with_4(capsys: Any, tmp_path: Path) -> None:
    document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    document["revision"] = 3
    code, payload, err = run(capsys, "edit", write(tmp_path / "doc.json", document), str(BATCH))
    assert (code, payload["error"]["code"], payload["error"]["exit_code"]) == (
        4,
        "EDIT_CONFLICT",
        4,
    )
    assert payload["error"]["context"]["reason"] == "stale_revision"
    assert "EDIT_CONFLICT" in err
    document["revision"], document["seed"] = 0, 43  # same revision, other branch
    code, payload, _ = run(capsys, "edit", write(tmp_path / "doc.json", document), str(BATCH))
    assert (code, payload["error"]["context"]["reason"]) == (4, "snapshot_mismatch")


def test_edit_invalid_input_exits_with_2(capsys: Any, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{not json")
    code, payload, _ = run(capsys, "edit", str(EXAMPLE), str(bad))
    assert (code, payload["error"]["code"]) == (2, "VALIDATION_ERROR")
    edit = json.loads(BATCH.read_text(encoding="utf-8"))
    edit["commands"][0]["color"] = "nope"
    code, payload, _ = run(capsys, "edit", str(EXAMPLE), write(tmp_path / "b.json", edit))
    assert (code, payload["error"]["code"]) == (2, "REFERENCE_ERROR")
    assert payload["error"]["json_pointer"] == "/commands/0/color"
    code, payload, _ = run(capsys, "edit", str(EXAMPLE))
    assert (code, payload["command"], payload["error"]["context"]) == (
        2,
        "edit",
        {"reason": "usage"},
    )


def test_edit_missing_batch_exits_with_5(capsys: Any, tmp_path: Path) -> None:
    code, payload, _ = run(capsys, "edit", str(EXAMPLE), str(tmp_path / "no batch.json"))
    assert (code, payload["error"]["code"]) == (5, "READ_ERROR")
    assert payload["error"]["context"]["file_name"] == "no batch.json"
    assert str(tmp_path) not in json.dumps(payload)


def test_edit_writes_no_files(capsys: Any, tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "doc.moana.json").write_bytes(EXAMPLE.read_bytes())
    (tmp_path / "batch.edit.json").write_bytes(BATCH.read_bytes())
    before = sorted(p.name for p in tmp_path.iterdir())
    snapshot = {name: (tmp_path / name).read_bytes() for name in before}
    code, payload, _ = run(capsys, "edit", "doc.moana.json", "batch.edit.json")
    assert (code, payload["edit"]["revision"]) == (0, 1)
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert {name: (tmp_path / name).read_bytes() for name in before} == snapshot
