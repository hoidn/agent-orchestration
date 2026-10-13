"""Behavioral tests for scripts/provider_delivery_census.py over a generated memo."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.contracts import canonical_sha256

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "provider_delivery_census.py"
HEAD = 40
REPLY = "first   line\n\tsecond line " + "x" * 200
FILE_1 = {"delivery": canonical_sha256("file/1")}


def _attempt(run: Path, name: str, *, attempt: int = 1, prompt: bool = True,
             stdout: str | None = None) -> str:
    rel = f"effects/{name}/attempt-{attempt}/result.json"
    directory = run / Path(rel).parent
    directory.mkdir(parents=True)
    if prompt:
        (directory / "prompt.txt").write_text("p", encoding="utf-8")
    if stdout is not None:
        (directory / "stdout.txt").write_text(stdout, encoding="utf-8")
    return rel


def _started(identity: str, rel: str, parts: dict, attempt: int = 1) -> dict:
    return {"record": "started", "identity": identity, "attempt": attempt,
            "result_path": rel, "input_parts": parts}


def _end(identity: str, code: str | None = None, attempt: int = 1) -> dict:
    if code is None:
        return {"record": "committed", "identity": identity, "attempt": attempt}
    return {"record": "failed", "identity": identity, "attempt": attempt, "code": code}


def _write_memo(run: Path, lines: list[str]) -> None:
    (run / "memo.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_run_a(run: Path) -> None:
    w1, w2 = "wf::run / loop[1] / white", "wf::run / loop[2] / blind"
    rows = [
        _started("wf::run / cmd", _attempt(run, "cmd", prompt=False, stdout="ignored"), {}),
        _end("wf::run / cmd"),
        _started(w1, _attempt(run, "w1", stdout=REPLY), {"prompt": "sha256:p"}),
        _end(w1),
        _started(w2, _attempt(run, "w2", stdout="oops"), FILE_1),
        _end(w2, "provider_result_missing"),
        _started("wf::run / black", _attempt(run, "b1"), {"delivery": canonical_sha256("legacy")}),
        _end("wf::run / black", "provider_exit_nonzero"),
        _started("wf::run / retry", _attempt(run, "r", attempt=1), {}, attempt=1),
        _end("wf::run / retry", "provider_result_missing", attempt=1),
        _started("wf::run / retry", _attempt(run, "r", attempt=2), {}, attempt=2),
        _end("wf::run / retry", attempt=2),
        _started("wf::run / pending", _attempt(run, "p"), {}),
        _started("wf::run / odd", _attempt(run, "o"), {"delivery": "sha256:feed"}),
        _end("wf::run / odd"),
    ]
    lines = [json.dumps(row) for row in rows]
    lines.insert(3, "{not json")
    lines.insert(6, "[1, 2]")
    _write_memo(run, lines)


def _write_run_b(run: Path) -> None:
    rows = [_started("wf::run / white", _attempt(run, "w"), FILE_1), _end("wf::run / white")]
    _write_memo(run, [json.dumps(row) for row in rows])


@pytest.fixture(scope="module")
def census(tmp_path_factory: pytest.TempPathFactory) -> subprocess.CompletedProcess[str]:
    root = tmp_path_factory.mktemp("census")
    _write_run_a(root / "state-a" / "run-a")
    (root / "state-a" / "run-without-memo").mkdir()
    _write_run_b(root / "state-b" / "run-b")
    args = ["--state-dir", str(root / "state-a"), "--state-dir", str(root / "absent"),
            "--state-dir", str(root / "state-b"), "--head", str(HEAD)]
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        capture_output=True, text=True, env={"PYTHONPATH": str(REPO)}, check=False,
    )


def _rows(stdout: str) -> dict[tuple[str, str, str], list[str]]:
    table = stdout.split("\n\n")[0].splitlines()[1:]
    return {(cols[0], cols[1], cols[2]): cols for cols in (line.split("\t") for line in table)}


def _column(census: subprocess.CompletedProcess[str], index: int) -> dict[tuple[str, str, str], str]:
    return {key: cols[index] for key, cols in _rows(census.stdout).items()}


def test_exits_zero_and_reports_both_bad_lines(census: subprocess.CompletedProcess[str]) -> None:
    assert (census.returncode, "line 4" in census.stderr, "line 7" in census.stderr) == (0, True, True)


def test_missing_state_dir_is_reported(census: subprocess.CompletedProcess[str]) -> None:
    assert "absent" in census.stderr


def test_rows_come_from_every_state_dir(census: subprocess.CompletedProcess[str]) -> None:
    assert {run for run, _, _ in _rows(census.stdout)} == {"run-a", "run-b"}


def test_command_attempts_are_excluded(census: subprocess.CompletedProcess[str]) -> None:
    assert "cmd" not in {site for _, site, _ in _rows(census.stdout)}


def test_outcomes_pair_by_identity_and_attempt(census: subprocess.CompletedProcess[str]) -> None:
    assert _column(census, 3) == {
        ("run-a", "white", "1"): "committed",
        ("run-a", "blind", "1"): "missing",
        ("run-a", "black", "1"): "provider_exit_nonzero",
        ("run-a", "retry", "1"): "missing",
        ("run-a", "retry", "2"): "committed",
        ("run-a", "pending", "1"): "open",
        ("run-a", "odd", "1"): "committed",
        ("run-b", "white", "1"): "committed",
    }


def test_delivery_names_resolve(census: subprocess.CompletedProcess[str]) -> None:
    deliveries = _column(census, 4)
    assert {key: deliveries[key] for key in [
        ("run-a", "white", "1"), ("run-a", "blind", "1"), ("run-a", "black", "1"),
        ("run-a", "odd", "1"),
    ]} == {
        ("run-a", "white", "1"): "legacy",
        ("run-a", "blind", "1"): "file/1",
        ("run-a", "black", "1"): "legacy",
        ("run-a", "odd", "1"): "sha256:feed",
    }


def test_stdout_head_is_bounded_and_collapsed(census: subprocess.CompletedProcess[str]) -> None:
    head = _column(census, 5)[("run-a", "white", "1")]
    assert head == ("first line second line " + "x" * 200)[:HEAD]


def test_counts_by_site_delivery_and_outcome(census: subprocess.CompletedProcess[str]) -> None:
    summary = census.stdout.split("\n\n")[1].splitlines()[1:]
    assert summary == [
        "black\tlegacy\tprovider_exit_nonzero\t1",
        "blind\tfile/1\tmissing\t1",
        "odd\tsha256:feed\tcommitted\t1",
        "pending\tlegacy\topen\t1",
        "retry\tlegacy\tcommitted\t1",
        "retry\tlegacy\tmissing\t1",
        "white\tfile/1\tcommitted\t1",
        "white\tlegacy\tcommitted\t1",
        "total\t8\tfile/1=2 (committed=1, missing=1); "
        "legacy=5 (committed=2, missing=1, open=1, provider_exit_nonzero=1); "
        "sha256:feed=1 (committed=1)",
    ]
