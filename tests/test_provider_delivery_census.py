"""Behavioral tests for scripts/provider_delivery_census.py over a generated memo."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from orchestrator.workflow.run_ref.contracts import canonical_sha256

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "provider_delivery_census.py"
HEAD = 40


def _attempt(run: Path, name: str, *, prompt: bool, stdout: str | None) -> str:
    rel = f"effects/{name}/attempt-1/result.json"
    directory = run / Path(rel).parent
    directory.mkdir(parents=True)
    if prompt:
        (directory / "prompt.txt").write_text("p", encoding="utf-8")
    if stdout is not None:
        (directory / "stdout.txt").write_text(stdout, encoding="utf-8")
    return rel


def _started(identity: str, rel: str, parts: dict) -> dict:
    return {"record": "started", "identity": identity, "attempt": 1,
            "result_path": rel, "input_parts": parts}


def _write_fixture(state: Path) -> None:
    run = state / "run-a"
    reply = "first   line\n\tsecond line " + "x" * 200
    rows = [
        _started("wf::run / cmd", _attempt(run, "cmd", prompt=False, stdout="ignored"), {}),
        {"record": "committed", "identity": "wf::run / cmd", "attempt": 1},
        _started("wf::run / loop[1] / white", _attempt(run, "w1", prompt=True, stdout=reply),
                 {"prompt": "sha256:p"}),
        {"record": "committed", "identity": "wf::run / loop[1] / white", "attempt": 1},
        _started("wf::run / loop[2] / white", _attempt(run, "w2", prompt=True, stdout="oops"),
                 {"delivery": canonical_sha256("file/1")}),
        {"record": "failed", "identity": "wf::run / loop[2] / white", "attempt": 1,
         "code": "provider_result_missing"},
        _started("wf::run / black", _attempt(run, "b1", prompt=True, stdout=None),
                 {"delivery": canonical_sha256("legacy")}),
        {"record": "failed", "identity": "wf::run / black", "attempt": 1,
         "code": "provider_exit_nonzero"},
    ]
    lines = [json.dumps(row) for row in rows]
    lines.insert(3, "{not json")
    (run / "memo.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (state / "run-without-memo").mkdir()


def _census(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    state = tmp_path / "runs"
    _write_fixture(state)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--state-dir", str(state), "--head", str(HEAD)],
        capture_output=True, text=True, env={"PYTHONPATH": str(REPO)}, check=False,
    )


def _attempt_rows(stdout: str) -> dict[str, list[str]]:
    table = stdout.split("\n\n")[0].splitlines()[1:]
    return {f"{cols[1]}:{cols[3]}": cols for cols in (line.split("\t") for line in table)}


def test_exits_zero_and_reports_malformed_line(tmp_path: Path) -> None:
    result = _census(tmp_path)
    assert (result.returncode, "run-a" in result.stderr) == (0, True)


def test_command_attempts_are_excluded(tmp_path: Path) -> None:
    rows = _attempt_rows(_census(tmp_path).stdout)
    assert sorted(rows) == ["black:provider_exit_nonzero", "white:committed", "white:missing"]


def test_delivery_names_resolve(tmp_path: Path) -> None:
    rows = _attempt_rows(_census(tmp_path).stdout)
    assert {key: cols[4] for key, cols in rows.items()} == {
        "white:committed": "legacy",
        "white:missing": "file/1",
        "black:provider_exit_nonzero": "legacy",
    }


def test_stdout_head_is_bounded_and_collapsed(tmp_path: Path) -> None:
    head = _attempt_rows(_census(tmp_path).stdout)["white:committed"][5]
    assert head == ("first line second line " + "x" * 200)[:HEAD]


def test_counts_by_site_and_outcome(tmp_path: Path) -> None:
    summary = _census(tmp_path).stdout.split("\n\n")[1].splitlines()[1:]
    assert summary == [
        "black\tprovider_exit_nonzero\t1",
        "white\tcommitted\t1",
        "white\tmissing\t1",
        "total\t3\tcommitted=1, missing=1, provider_exit_nonzero=1",
    ]
