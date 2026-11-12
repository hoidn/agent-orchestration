"""Public SIGKILL, resume and refusal evidence for parallel map (Phase 5 Task 5).

Every run and resume goes through `orchestrator run` / `orchestrator resume`; the process
group is killed by `kill_at` once the planned memo is durable.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.workflow_evaluated_parallel_kill_helpers import (
    FOUR_VALUE, Batch, child_launches, committed, item_of, run_ref_batch,
)
from tests.workflow_evaluated_recovery_helpers import resume


HOLDS = (("b", "second"), ("c", "first"))


def _killed_after_two(tmp_path: Path) -> tuple[Batch, list[dict]]:
    """Kill the four-item batch while `b`'s second step and `c` block: `a` and `b` first committed."""
    batch = Batch(tmp_path)
    seen = {}

    def two_commits(_marker):
        seen["commits"] = committed(batch.snapshot())

    batch.kill(HOLDS, two_commits)
    assert sorted((item_of(row["identity"]), row["value"]) for row in seen["commits"]) == [("a", 1), ("b", 20)]
    snapshot = batch.snapshot()
    assert committed(snapshot) == seen["commits"] and snapshot.terminal is None
    assert sorted(item_of(identity) for identity in snapshot.pending_starts) == ["b", "c"]
    return batch, seen["commits"]


def _assert_resumed(batch: Batch, before: list[dict]) -> None:
    snapshot = batch.snapshot()
    assert snapshot.terminal.data["outcome"] == "completed"
    assert snapshot.terminal.data["value"] == FOUR_VALUE
    assert committed(snapshot)[:2] == before
    assert Counter(batch.dispatches()) == {
        ("a", "first"): 1, ("b", "first"): 1, ("b", "second"): 2, ("c", "first"): 2, ("d", "first"): 1}


def test_kill_after_two_of_four_commits_resumes_only_missing_effects(tmp_path):
    batch, before = _killed_after_two(tmp_path)
    result = resume(batch.ws, batch.run_root().name)
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_resumed(batch, before)
    (first,) = [row for row in before if row["value"] == 20]
    (second,) = [row for row in committed(batch.snapshot()) if row["value"] == 21]
    assert second["depends_on"] == [first["identity"]]


def test_relocated_workspace_keeps_relative_item_cwd(tmp_path):
    batch, before = _killed_after_two(tmp_path)
    original = batch.ws
    batch.ws = tmp_path / "moved"
    original.rename(batch.ws)
    result = resume(batch.ws, batch.run_root().name)
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_resumed(batch, before)
    log = [json.loads(line) for line in (batch.control / "dispatches.jsonl").read_text().splitlines()]
    resumed = [row for row in log if row["bundle"].startswith(str(batch.ws))]
    assert sorted((row["repo"], row["stage"]) for row in resumed) == [("b", "second"), ("c", "first"), ("d", "first")]


def test_two_completed_resumes_leave_identical_bytes(tmp_path):
    batch, _before = _killed_after_two(tmp_path)
    assert resume(batch.ws, batch.run_root().name).returncode == 0
    evidence = _tree_bytes(batch.ws), _tree_bytes(batch.control)
    for _ in range(2):
        result = resume(batch.ws, batch.run_root().name)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (_tree_bytes(batch.ws), _tree_bytes(batch.control)) == evidence


def _failed_first_item(tmp_path: Path) -> Batch:
    """`a` fails its only step; `b`, `c` and `d` commit; the run ends failed."""
    batch = Batch(tmp_path)
    (batch.ws / "a" / "fail").write_text("")
    result = batch.run()
    assert result.returncode != 0
    (batch.ws / "a" / "fail").unlink()
    assert sorted(item_of(row["identity"]) for row in committed(batch.snapshot())) == ["b", "b", "c", "d"]
    return batch


def _assert_refused_without_writes(batch: Batch, code: str, *details: str) -> None:
    before, dispatched = _tree_bytes(batch.ws), batch.dispatches()
    result = resume(batch.ws, batch.run_root().name)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert all(text in output for text in (f"[{code}]", *details)), output
    assert _tree_bytes(batch.ws) == before
    assert batch.dispatches() == dispatched


def test_later_sibling_divergence_refuses(tmp_path):
    batch = _failed_first_item(tmp_path)
    (batch.ws / "d" / "step.py").write_text((batch.ws / "d" / "step.py").read_text() + "\n# changed\n")
    with (batch.run_root() / "memo.jsonl").open("ab") as memo:
        memo.write(b'{"partial":')
    _assert_refused_without_writes(batch, "effect_input_diverged", "par-map:repo[3]", "d/step.py")


def test_deleted_committed_result_file_does_not_change_resume(tmp_path):
    """The memo row is the authority: completed replay never re-reads committed result bytes."""
    batch = Batch(tmp_path)
    assert batch.run().returncode == 0
    (commit,) = [row for row in committed(batch.snapshot()) if item_of(row["identity"]) == "c"]
    (batch.run_root() / commit["result_path"]).unlink()
    memo, dispatched = (batch.run_root() / "memo.jsonl").read_bytes(), batch.dispatches()
    result = resume(batch.ws, batch.run_root().name)
    assert result.returncode == 0, result.stdout + result.stderr
    assert batch.snapshot().terminal.data["value"] == FOUR_VALUE
    assert (batch.run_root() / "memo.jsonl").read_bytes() == memo
    assert batch.dispatches() == dispatched


def test_parallel_item_that_writes_no_result_fails_with_command_result_missing(tmp_path):
    batch = Batch(tmp_path)
    (batch.ws / "c" / "noresult").write_text("")
    result = batch.run()
    assert result.returncode != 0 and "[command_result_missing]" in result.stdout + result.stderr
    snapshot = batch.snapshot()
    failed = [row.data for row in snapshot.entries if row.data["record"] == "failed"]
    assert [(item_of(row["identity"]), row["code"]) for row in failed] == [("c", "command_result_missing")]
    kept = committed(snapshot)
    assert sorted(item_of(row["identity"]) for row in kept) == ["a", "b", "b", "d"]
    (batch.ws / "c" / "noresult").unlink()
    resumed = resume(batch.ws, batch.run_root().name)
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    after = batch.snapshot()
    assert after.terminal.data["value"] == FOUR_VALUE
    assert committed(after)[:4] == kept
    assert Counter(batch.dispatches()) == {
        ("a", "first"): 1, ("b", "first"): 1, ("b", "second"): 1, ("c", "first"): 2, ("d", "first"): 1}


WINDOW_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule main) (export run)
  (defworkflow worker ((repo String)) -> Int
    (if (= repo "b")
        (command-result target :argv ("python" "step.py" repo "first") :returns Int)
        (command-result peer :argv ("python" "step.py" repo "first") :returns Int)))
  (defworkflow run () -> List[Int]
    (list/map-effect ((repo (list "a" "b"))) :max 2 :parallel 2 :workspace repo
      (call worker :repo repo))))
'''
WINDOWS = {"start_reservation": "W2", "output_before_commit": "W8", "commit_before_view": "W9"}


def _window_batch(root: Path, must_not_repeat: bool) -> Batch:
    boundary = {"stable_command": ["python", "step.py"], "closure": []}
    return Batch(root, source=WINDOW_SOURCE, items=("a", "b"), boundaries={
        "peer": boundary, "target": {**boundary, "must_not_repeat": must_not_repeat}})


def _target_identity(tmp_path: Path) -> str:
    baseline = _window_batch(tmp_path / "baseline", False)
    assert baseline.run().returncode == 0
    snapshot = baseline.snapshot()
    assert snapshot.terminal.data["value"] == [1, 20]
    (identity,) = [row["identity"] for row in committed(snapshot) if item_of(row["identity"]) == "b"]
    return identity


def test_malformed_settlement_obligations_refuse(tmp_path):
    """Both items' E1 final rows are missing; only one may follow its pending row at the head."""
    from tests.test_workflow_evaluated_cli import _run_cli
    from tests.test_workflow_evaluated_parallel_run_ref import _parallel_e1_fixture, _without_e1_finals
    from tests.test_workflow_evaluated_run_ref import _authority
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, snapshot = _authority(parent)
    _without_e1_finals(authority, snapshot)
    before = _tree_bytes(parent), _tree_bytes(refs)
    refused = resume(parent, authority.run_root.name)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "parallel E1 recovery" in refused.stderr
    assert (_tree_bytes(parent), _tree_bytes(refs)) == before


COORDINATED = '''(defworkflow invoke ((repo String)) -> Int
  (if (= repo "b")
      (let* ((child CALL) (after (command-result target :argv ("python" "step.py" repo "first") :returns Int)))
        (if child.value after 0))
      (command-result peer :argv ("python" "step.py" repo "first") :returns Int)))'''
BEHIND_POOL = '''(defworkflow invoke ((repo String)) -> Int
  (if (= repo "c")
      (let* ((child CALL)) (if child.value 3 0))
      (command-result peer :argv ("python" "step.py" repo "first") :returns Int)))'''


def _run_ref_identity(root: Path, invoke: str, items: tuple[str, ...]) -> str:
    baseline = run_ref_batch(root, invoke, items)
    result = baseline.run()
    assert result.returncode == 0, result.stderr
    (identity,) = [row["identity"] for row in committed(baseline.snapshot()) if row["effect_class"] == "run_ref"]
    return identity


def _kill_at_commit(batch: Batch, identity: str, window: str = "W9") -> None:
    from tests.workflow_evaluated_recovery_helpers import digest
    batch.kill((), window={"window": window, "identity": identity, "attempt": 1, "digest": digest(identity)})


def _command_window(tmp_path: Path, window: str, must_not_repeat: bool) -> None:
    identity = _target_identity(tmp_path)
    batch = _window_batch(tmp_path / "killed", must_not_repeat)
    _kill_at_commit(batch, identity, WINDOWS[window])
    pending = identity in batch.snapshot().pending_starts
    assert pending == (window != "commit_before_view")
    if pending and must_not_repeat:
        _assert_refused_without_writes(batch, "lexical_restore_pending_effect_unsafe", "par-map:repo[1]")
        return
    result = resume(batch.ws, batch.run_root().name)
    assert result.returncode == 0, result.stdout + result.stderr
    assert batch.snapshot().terminal.data["value"] == [1, 20]
    expected = 2 if window == "output_before_commit" else 1
    assert Counter(batch.dispatches())[("b", "first")] == expected


def _coordinator_window(tmp_path: Path, must_not_repeat: bool) -> None:
    """Kill after `b`'s run-reference commit, before its settlement; its successor never started."""
    identity = _run_ref_identity(tmp_path / "baseline", COORDINATED, ("a", "b"))
    batch = run_ref_batch(tmp_path / "killed", COORDINATED, ("a", "b"), must_not_repeat=must_not_repeat)
    _kill_at_commit(batch, identity)
    assert [key for key, _attempt in batch.snapshot().unsettled_coordinators] == [identity]
    result = resume(batch.ws, batch.run_root().name)
    assert result.returncode == 0, result.stdout + result.stderr
    snapshot = batch.snapshot()
    assert snapshot.terminal.data["value"] is True and not snapshot.unsettled_coordinators
    assert child_launches(batch) == 1
    assert Counter(batch.dispatches())[("b", "first")] == 1


@pytest.mark.parametrize("must_not_repeat", [False, True], ids=["retryable", "must_not_repeat"])
@pytest.mark.parametrize("window", [*WINDOWS, "coordinator_commit_before_settle"])
def test_kill_in_each_parallel_window_resumes_to_the_same_value(tmp_path, window, must_not_repeat):
    if window == "coordinator_commit_before_settle":
        _coordinator_window(tmp_path, must_not_repeat)
    else:
        _command_window(tmp_path, window, must_not_repeat)


def _killed_behind_failures(batch: Batch, identity: str, failing: tuple[str, ...]) -> int:
    """Fail `failing` once and kill at `identity`'s commit; return the journal length at the kill."""
    for item in failing:
        (batch.ws / item / "fail").write_text("")
    _kill_at_commit(batch, identity)
    for item in failing:
        (batch.ws / item / "fail").unlink()
    snapshot = batch.snapshot()
    assert [key for key, _attempt in snapshot.unsettled_coordinators] == [identity]
    codes = [row.data["code"] for row in snapshot.entries if row.data["record"] == "failed"]
    assert codes == ["command_exit_nonzero"] * len(failing)
    return len(snapshot.entries)


def _first_index(rows: list[dict], record: str) -> int:
    return next(index for index, row in enumerate(rows) if row["record"] == record)


def test_unsettled_run_ref_behind_a_full_pool_is_not_launched_twice(tmp_path):
    """`a` and `b` fail and fill the pool on resume; `c`'s committed run reference is reconciled first."""
    identity = _run_ref_identity(tmp_path / "baseline", BEHIND_POOL, ("a", "b", "c"))
    batch = run_ref_batch(tmp_path / "killed", BEHIND_POOL, ("a", "b", "c"))
    killed_rows = _killed_behind_failures(batch, identity, ("a", "b"))
    result = resume(batch.ws, batch.run_root().name)
    assert result.returncode == 0, result.stdout + result.stderr
    after = batch.snapshot()
    assert after.terminal.data["value"] is True and child_launches(batch) == 1
    resumed = [row.data for row in after.entries[killed_rows:]]
    settled = _first_index(resumed, "settled")
    assert resumed[settled]["identity"] == identity and settled < _first_index(resumed, "started")
    assert Counter(batch.dispatches()) == {("a", "first"): 2, ("b", "first"): 2}
