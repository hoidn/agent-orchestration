"""Only an agent without a committed turn may be bootstrapped, and only by explicit resume; later turns refuse."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECORD, _stopped
from tests.test_workflow_evaluated_agent_turns import PLAN, SOURCE, fixture, memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli


# Dies just before `agent_turns.append_record` writes the matching record: for the bootstrap `failed`, after
# `abandoned.json` is durable. Only that module's writer is hooked; it is the one `abandon_candidate` calls.
STOP_BEFORE_RECORD = r'''import os, sys
from orchestrator.workflow.evaluated import agent_turns
append = agent_turns.append_record
def stop(path, record, **kwargs):
    if record["record"] == os.environ["STOP_RECORD"] and os.environ["STOP_TURN"] in record.get("identity", ""):
        os._exit(75)
    return append(path, record, **kwargs)
agent_turns.append_record = stop
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


def _install(tmp_path, monkeypatch, plan):
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)


def _rows(memo, kind, suffix):
    return [e.data for e in memo.entries if e.data["record"] == kind and e.data.get("identity", "").endswith(suffix)]


@pytest.mark.parametrize("first_mode", ["interrupted", "invalid-result"])
def test_reviewer_first_turn_failure_bootstraps_a_fresh_candidate_on_explicit_resume(tmp_path, monkeypatch, first_mode) -> None:
    plan = {"claude": PLAN["claude"], "codex": [{"mode": first_mode, "result": {"notes": ["n"]}}, {"mode": "success", "result": {"notes": ["n"]}}, {"mode": "success", "result": {"notes": ["done"]}}]}
    _install(tmp_path, monkeypatch, plan)
    run = _cli(tmp_path, "run", *fixture(tmp_path))
    assert run.returncode == 1
    run_root, _a, classes, memo = memo_of(tmp_path)
    assert set(turns(memo, classes)) == {"a1"}
    if first_mode == "interrupted":
        assert list(memo.pending_starts) == [next(i for i in memo.pending_starts)] and memo.terminal is None
    else:
        (failed,) = _rows(memo, "failed", "/ b1")
        assert failed["code"] == "provider_result_invalid" and memo.terminal.data["outcome"] == "failed"
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    t = turns(after, classes)
    assert t["a1"]["attempt"] == 1 and t["b1"]["attempt"] == 2 and set(t) == {"a1", "b1", "a2", "b2"}
    failed_rows = _rows(after, "failed", "/ b1")
    expected_code = "agent_bootstrap_restarted" if first_mode == "interrupted" else "provider_result_invalid"
    assert [r["code"] for r in failed_rows] == [expected_code]
    assert "agent_bootstrap_restarted" in resumed.stderr      # diagnostic on both bootstrap paths
    requests = shim_requests(tmp_path)
    codex = [r for r in requests if r["tool"] == "codex"]
    assert len(codex) == 3 and codex[0]["session"] != codex[1]["session"] == codex[2]["session"]
    assert "resume" not in codex[1]["argv"]       # fresh candidate, never adopting the abandoned session
    attempt1 = run_root / Path(_rows(after, "started", "/ b1")[0]["result_path"]).parent
    receipt = json.loads((attempt1 / "receipt.json").read_text())
    assert receipt["completion"] == "abandoned" and (attempt1 / "abandoned.json").exists()
    assert f"[agent_bootstrap_restarted] {_rows(after, 'failed', '/ b1')[0]['identity']} abandoned attempt 1" in resumed.stderr
    assert receipt["locator"] and receipt["locator"] not in resumed.stderr      # evidence only, never the log


def test_recoverable_first_turn_proof_wins_over_bootstrap(tmp_path, monkeypatch) -> None:
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECEIPT
    _install(tmp_path, monkeypatch, PLAN)
    # killed after native completion was verified and result.json exists, before `committed`: a recoverable first turn
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "completed", "STOP_TURN": "/ b1"}, "run", *fixture(tmp_path))
    run_root, *_ = memo_of(tmp_path)
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["b1"]["attempt"] == 1
    assert len([r for r in shim_requests(tmp_path) if r["tool"] == "codex"]) == 2


@pytest.mark.parametrize("tool, turn", [("claude", "/ a1"), ("codex", "/ b1")])
def test_first_turn_completed_without_result_bootstraps_on_first_explicit_resume(tmp_path, monkeypatch, tool, turn) -> None:
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECEIPT, _stopped
    plan = {name: [dict(step) for step in steps] for name, steps in PLAN.items()}
    plan[tool].insert(0, {**plan[tool][0], "mode": "missing-result"})
    _install(tmp_path, monkeypatch, plan)
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "completed", "STOP_TURN": turn}, "run", *fixture(tmp_path))
    run_root, _authority, _classes, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts.values()
    attempt = run_root / Path(pending.data["result_path"]).parent
    assert json.loads((attempt / "receipt.json").read_text())["completion"] == "completed"
    assert not (attempt / "result.json").exists()

    resumed = _cli(tmp_path, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert "agent_bootstrap_restarted" in resumed.stderr
    _root, _authority, classes, after = memo_of(tmp_path)
    failed = _rows(after, "failed", turn)
    assert [row["code"] for row in failed] == ["agent_bootstrap_restarted"]
    assert turns(after, classes)[turn.rsplit("/ ", 1)[1]]["attempt"] == 2


@pytest.mark.parametrize("mode, code", [("interrupted", "agent_turn_unresolved"), ("invalid-result", "agent_turn_result_invalid")])
def test_later_turn_failures_cannot_bootstrap(tmp_path, monkeypatch, mode, code) -> None:
    plan = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": mode, "result": {"text": "d2"}}], "codex": PLAN["codex"]}
    _install(tmp_path, monkeypatch, plan)
    run = _cli(tmp_path, "run", *fixture(tmp_path))
    assert run.returncode == 1 and code in run.stderr
    run_root, _a, _c, memo = memo_of(tmp_path)
    if code == "agent_turn_result_invalid":
        (failed,) = _rows(memo, "failed", "/ a2")
        assert failed["code"] == code and failed["exit_info"] == {} and "violations" not in failed
    memo_bytes = (run_root / "memo.jsonl").read_bytes()
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 2 and code in resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes() == memo_bytes
    assert len(shim_requests(tmp_path)) == 3


@pytest.mark.parametrize("hook, env, failed_rows_after_kill", [
    ("receipt", {"STOP_AT_COMPLETION": "abandoned", "STOP_TURN": "/ b1"}, 0),     # after the `abandoned` receipt, before `abandoned.json`
    ("record", {"STOP_RECORD": "failed", "STOP_TURN": "/ b1"}, 1),                 # between failure closure and the next start
    ("marker", {"STOP_RECORD": "failed", "STOP_TURN": "/ b1"}, 0),                 # after `abandoned.json`, before failure closure
])
def test_kill_between_abandonment_failure_and_next_start_keeps_ordering_valid(tmp_path, monkeypatch, hook, env, failed_rows_after_kill) -> None:
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECEIPT
    plan = {"claude": PLAN["claude"], "codex": [{"mode": "interrupted", "result": {}}, {"mode": "success", "result": {"notes": ["n"]}}, {"mode": "success", "result": {"notes": ["done"]}}]}
    _install(tmp_path, monkeypatch, plan)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 1
    run_root, *_ = memo_of(tmp_path)
    _stopped(tmp_path, {"receipt": STOP_AFTER_RECEIPT, "record": STOP_AFTER_RECORD, "marker": STOP_BEFORE_RECORD}[hook], env, "resume", run_root.name)
    _r, _a, classes, memo = memo_of(tmp_path)
    assert len(_rows(memo, "failed", "/ b1")) == failed_rows_after_kill
    attempt1 = run_root / Path(_rows(memo, "started", "/ b1")[0]["result_path"]).parent
    receipt = json.loads((attempt1 / "receipt.json").read_text())
    assert receipt["completion"] == "abandoned" and (attempt1 / "abandoned.json").exists() == (hook != "receipt")
    assert receipt["locator"] and receipt["locator"] not in (run_root / "state.json").read_text()   # never in the view
    assert len([r for r in shim_requests(tmp_path) if r["tool"] == "codex"]) == 1
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert "[agent_bootstrap_restarted]" in resumed.stderr and receipt["locator"] not in resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    assert [r["code"] for r in _rows(after, "failed", "/ b1")] == ["agent_bootstrap_restarted"]   # not duplicated
    assert turns(after, classes)["b1"]["attempt"] == 2


@pytest.mark.parametrize("crash_in_window", [False, True], ids=["once", "crash-after-unknown"])
def test_first_turn_killed_after_launch_is_quiesced_and_abandoned(tmp_path, monkeypatch, crash_in_window) -> None:
    """The orchestrator dies right after binding b1's child (`launching`, no locator yet). Resume stops the group, finds
    nothing recoverable and abandons the candidate (`launching -> unknown -> abandoned`) before attempt 2 starts. A resume
    that dies at the `unknown` write, before `abandoned`, leaves no marker and no `failed`; the next resume finishes."""
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECEIPT
    plan = {"claude": PLAN["claude"], "codex": [{"mode": "interrupted", "result": {}}, {"mode": "success", "result": {"notes": ["n"]}}, {"mode": "success", "result": {"notes": ["done"]}}]}
    _install(tmp_path, monkeypatch, plan)
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "launching", "STOP_TURN": "/ b1"}, "run", *fixture(tmp_path))
    run_root, *_ = memo_of(tmp_path)
    if crash_in_window:
        _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "unknown", "STOP_TURN": "/ b1"}, "resume", run_root.name)
        _r, _a, _c, memo = memo_of(tmp_path)
        (pending,) = memo.pending_starts.values()
        attempt1 = run_root / Path(pending.data["result_path"]).parent
        assert json.loads((attempt1 / "receipt.json").read_text())["completion"] == "unknown"
        assert not (attempt1 / "abandoned.json").exists() and not _rows(memo, "failed", "/ b1")
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["b1"]["attempt"] == 2
    assert [r["code"] for r in _rows(after, "failed", "/ b1")] == ["agent_bootstrap_restarted"]
    attempt1 = run_root / Path(_rows(after, "started", "/ b1")[0]["result_path"]).parent
    assert json.loads((attempt1 / "receipt.json").read_text())["completion"] == "abandoned"
    assert (attempt1 / "abandoned.json").exists()
