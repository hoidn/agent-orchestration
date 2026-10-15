"""Unresolved turns keep `started` pending; resume commits a completed native turn at the same ordinal with zero redispatch."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.memo_reducer_agents import DISPATCHED_FAILURE_CODES
from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_agent_turns import BROKEN_PROJECT, BROKEN_VERIFY, PLAN, SOURCE, fixture, memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli
from tests.workflow_evaluated_consumer_sources import ROOT

# Kill-point drivers. Every module that appends a memo record is patched (attempts: `started`; runtime: `committed`,
# `failed`, `terminal`; agent_turns: `settled`, bootstrap `failed`), following tests/workflow_evaluated_recovery_helpers.py:124.
# Receipt stops patch `agent_turns.write_receipt`, the name the coordinator calls (`agent_sessions.write_receipt` is the
# definition, not the call site). STOP_AT_COMPLETION may also be `proof` (= the `result_digest` write, M12) or `abandoned`.
STOP_AFTER_RECEIPT = r'''import os, sys
from orchestrator.workflow.evaluated import agent_turns
write = agent_turns.write_receipt
def stop(files, receipt):
    write(files, receipt)
    wanted = os.environ["STOP_AT_COMPLETION"]
    hit = (receipt.result_digest is not None) if wanted == "proof" else (receipt.completion == wanted and receipt.result_digest is None)
    if hit and os.environ["STOP_TURN"] in receipt.turn:
        os._exit(75)
agent_turns.write_receipt = stop
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''

STOP_AFTER_RECORD = r'''import os, sys
from orchestrator.workflow.evaluated import agent_turns, attempts, runtime
append = runtime.append_record
def stop(path, record, **kwargs):
    entry = append(path, record, **kwargs)
    if record["record"] == os.environ["STOP_RECORD"] and os.environ["STOP_TURN"] in record.get("identity", ""):
        os._exit(75)
    return entry
attempts.append_record = runtime.append_record = agent_turns.append_record = stop
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''

# The orchestrator dies while the CLI is still running: the shim's `orphan` mode forks a grandchild at startup (stdio on
# /dev/null, pid in `.codex.orphan`), completes the native turn, writes `.codex.done` and waits for its parent to die.
STOP_WHEN_ORPHANED = r'''import os, sys, threading, time
from pathlib import Path
marks = [Path(os.environ["ORPHAN_DIR"]) / name for name in (".codex.orphan", ".codex.done")]
def watch():
    while not all(mark.exists() for mark in marks):
        time.sleep(0.02)
    os._exit(75)
threading.Thread(target=watch, daemon=True).start()
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


# `_stopped` runs every driver (here and in the modules importing it) with the file-only observation fake: a driver
# killed by `os._exit` skips the runtime's cleanup and would otherwise leak a real tmux server.
_FAKE_OBSERVATION = ("from orchestrator.workflow.evaluated import runtime\n"
                     "from tests.test_provider_observation import _FakeObservationBackend\n"
                     "runtime.observation_backend = _FakeObservationBackend\n")


def _stopped(root, script, env, *argv):
    done = subprocess.run([sys.executable, "-c", _FAKE_OBSERVATION + script, *argv], cwd=root, check=False, capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", **env})
    assert done.returncode == 75, done.stderr
    return done


def _install(tmp_path, monkeypatch, plan=PLAN):
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)


def _receipt(run_root, start) -> dict:
    return json.loads((run_root / Path(start.data["result_path"]).parent / "receipt.json").read_text())


# 5 s, not 2: `complete-then-hang` must finish its store and result writes before the timeout on a loaded host.
SHORT = SOURCE.replace(":prompt (revise :text a1.text :notes b1.notes) :timeout-sec 60", ":prompt (revise :text a1.text :notes b1.notes) :timeout-sec 5")


@pytest.mark.parametrize("plan_mode", ["interrupted", "nonzero", "complete-then-hang"])
def test_uncertain_or_advanced_transport_failure_keeps_started_pending_without_failed_or_terminal(tmp_path, monkeypatch, plan_mode) -> None:
    plan = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": plan_mode, "result": {"text": "d2"}}], "codex": PLAN["codex"]}
    _install(tmp_path, monkeypatch, plan)
    run = _cli(tmp_path, "run", *fixture(tmp_path, SHORT))
    assert run.returncode == 1 and "agent_turn_unresolved" in run.stderr
    _root, _authority, classes, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts
    assert pending.endswith("/ a2") and memo.terminal is None
    assert not any(e.data["record"] == "failed" for e in memo.entries)
    assert set(turns(memo, classes)) == {"a1", "b1"}
    assert len(shim_requests(tmp_path)) == 3


def test_timeout_before_any_append_is_an_ordinary_failure_and_resume_retries(tmp_path, monkeypatch) -> None:
    """Design row 4: the adapter proves the predecessor head unchanged, so the next attempt is allowed."""
    plan = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": "timeout", "result": {}}, {"mode": "success", "result": {"text": "d2"}}], "codex": PLAN["codex"]}
    _install(tmp_path, monkeypatch, plan)
    assert _cli(tmp_path, "run", *fixture(tmp_path, SHORT)).returncode == 1
    run_root, _a, classes, memo = memo_of(tmp_path)
    (failed,) = [e.data for e in memo.entries if e.data["record"] == "failed"]       # closed `failed`, not kept pending
    assert failed["identity"].endswith("/ a2") and memo.terminal.data["outcome"] == "failed"
    assert _receipt(run_root, memo.latest_starts[failed["identity"]])["completion"] == "not_dispatched"
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["a2"]["attempt"] == 2
    assert [r["tool"] for r in shim_requests(tmp_path)] == ["claude", "codex", "claude", "codex"]   # the timed-out call logged nothing


def test_timeout_after_adapter_confirmed_completion_recovers_the_same_ordinal_without_redispatch(tmp_path, monkeypatch) -> None:
    """Design verification: transport timeout, completed store, intact result -> start pending; resume commits ordinal 1, zero redispatch."""
    plan = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": "complete-then-hang", "result": {"text": "d2"}}], "codex": PLAN["codex"]}
    _install(tmp_path, monkeypatch, plan)
    assert _cli(tmp_path, "run", *fixture(tmp_path, SHORT)).returncode == 1
    run_root, _a, classes, memo = memo_of(tmp_path)
    assert next(iter(memo.pending_starts)).endswith("/ a2") and memo.terminal is None
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["a2"]["attempt"] == 1 and after.terminal.data["outcome"] == "completed"
    assert len(shim_requests(tmp_path)) == 4


def test_orphaned_process_group_is_quiesced_before_recovery(tmp_path, monkeypatch) -> None:
    """The orchestrator died while the CLI ran; its grandchild outlives both. Resume admits the live group
    (`needs_quiescence` at the read-only preflight), stops it under the writer lock, then recovers b2 without redispatch."""
    from orchestrator.workflow.evaluated.agent_sessions import Receipt
    from orchestrator.workflow.evaluated.agent_turn_recovery import quiesce
    plan = {"claude": PLAN["claude"], "codex": [PLAN["codex"][0], {"mode": "orphan", "result": {"notes": ["done"]}}]}
    _install(tmp_path, monkeypatch, plan)
    _stopped(tmp_path, STOP_WHEN_ORPHANED, {"ORPHAN_DIR": str(tmp_path / "bin")}, "run", *fixture(tmp_path))
    run_root, _a, _c, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts.values()
    receipt = _receipt(run_root, pending)
    assert pending.data["identity"].endswith("/ b2") and receipt["completion"] == "launching"
    orphan = int((tmp_path / "bin" / ".codex.orphan").read_text())
    try:
        assert os.getpgid(orphan) == receipt["pgid"]      # the grandchild is a live member of the recorded group ...
        assert quiesce(Receipt(**receipt), probe_only=True) == "alive"   # ... so the read-only preflight sees `needs_quiescence`
        resumed = _cli(tmp_path, "resume", run_root.name)
        assert resumed.returncode == 0, resumed.stderr
        with pytest.raises(ProcessLookupError):
            os.killpg(receipt["pgid"], 0)
    finally:
        try:
            os.killpg(receipt["pgid"], signal.SIGKILL)
        except ProcessLookupError:
            pass
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["b2"]["attempt"] == 1 and len(shim_requests(tmp_path)) == 4


def _launched_receipt(pgid, start_time):
    from orchestrator.workflow.evaluated.agent_sessions import Receipt
    return Receipt(run_id="r", agent="a", turn="t", attempt=1, predecessor=None, input_digest="sha256:" + "0" * 64,
                   adapter="codex_exec_jsonl_stdout", config_digest="sha256:" + "0" * 64, mode="resume", locator="s",
                   pgid=pgid, leader_start_time=start_time, position_before=None, position_after=None,
                   completion="launching", result_digest=None)


def test_quiesce_never_signals_a_reused_pgid(tmp_path) -> None:
    """R3: after our group is gone its pgid can be handed to an unrelated process of the same user. A live leader whose
    start time differs from the one the receipt recorded at `launching` is that stranger: `quiescent`, no signal sent."""
    from orchestrator.workflow.evaluated.agent_turn_recovery import quiesce
    from orchestrator.workflow.evaluated.agent_turns import leader_start_time
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)   # a group leader we do not own
    try:
        live = leader_start_time(stranger.pid)
        assert live is not None
        assert quiesce(_launched_receipt(stranger.pid, live + 1)) == "quiescent"   # full mode (SIGTERM/SIGKILL allowed), yet ...
        assert stranger.poll() is None                    # ... the stranger was never signalled
        os.killpg(stranger.pid, 0)                        # and its group is still there
    finally:
        stranger.kill()
        stranger.wait()


def test_not_dispatched_needs_a_proven_empty_group_before_any_head_check() -> None:
    """Task 10 review: an unchanged head alone never closes `not_dispatched`. A group that cannot be proven stopped (here an
    unreaped zombie leader still answers `killpg(pgid, 0)`) is unresolved, and the head is not even consulted."""
    from orchestrator.workflow.evaluated.agent_turns import _proves_no_dispatch, leader_start_time
    from orchestrator.workflow.evaluated.providers import ProviderPerformerError
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        receipt = _launched_receipt(child.pid, leader_start_time(child.pid))
        assert _proves_no_dispatch(None, receipt, ProviderPerformerError("provider_exit_nonzero", "x")) is False
    finally:
        child.kill()
        child.wait()


@pytest.mark.parametrize("driver, receipt_state", [(BROKEN_VERIFY, "unknown"), (BROKEN_PROJECT, "completed")], ids=["verify", "project"])
def test_unmapped_exception_after_launch_is_recovered_on_resume_when_the_native_turn_completed(tmp_path, monkeypatch, driver, receipt_state) -> None:
    """Resume half of Task 10's unmapped-exception rules (rows 3 and 6): whether the receipt stayed `unknown` (verification
    seam) or `completed` (projection seam), the native store shows the completed turn bound to the attempt and `result.json`
    is intact, so the same ordinal is committed with zero redispatch."""
    _install(tmp_path, monkeypatch)
    run = subprocess.run([sys.executable, "-c", driver, "run", *fixture(tmp_path)], cwd=tmp_path, capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "BROKEN_TURN": "/ a2"})
    assert run.returncode == 1 and "agent_turn_unresolved" in run.stderr, run.stderr
    run_root, _a, _c, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts.values()
    assert pending.data["identity"].endswith("/ a2") and len(shim_requests(tmp_path)) == 3
    assert _receipt(run_root, pending)["completion"] == receipt_state
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["a2"]["attempt"] == 1 and after.terminal.data["outcome"] == "completed"
    assert len(shim_requests(tmp_path)) == 4             # a2 never redispatched
    assert _receipt(run_root, pending)["result_digest"] == turns(after, classes)["a2"]["result_digest"]


@pytest.mark.parametrize("stop_at", ["completed", "proof"])
def test_kill_between_native_completion_and_commit_recovers_the_same_ordinal_with_zero_redispatch(tmp_path, monkeypatch, stop_at) -> None:
    _install(tmp_path, monkeypatch)
    frontend = fixture(tmp_path)
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": stop_at, "STOP_TURN": "/ b1"}, "run", *frontend)
    run_root, _authority, classes, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts
    assert pending.endswith("/ b1") and len(shim_requests(tmp_path)) == 2
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _root, _authority, classes, after = memo_of(tmp_path)
    t = turns(after, classes)
    assert t["b1"]["attempt"] == 1 and after.terminal.data["outcome"] == "completed"
    assert [r["tool"] for r in shim_requests(tmp_path)] == ["claude", "codex", "claude", "codex"]   # b1 never redispatched


def test_kill_after_intent_before_launch_allocates_the_next_attempt_on_resume(tmp_path, monkeypatch) -> None:
    """Design row 2: reserved but demonstrably not dispatched (no `launching`) -> evidence kept, next ordinal allowed."""
    _install(tmp_path, monkeypatch)
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "intent", "STOP_TURN": "/ a2"}, "run", *fixture(tmp_path))
    run_root, _a, _c, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts.values()
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["a2"]["attempt"] == 2 and _receipt(run_root, pending)["completion"] == "not_dispatched"
    (closed,) = [e.data for e in after.entries if e.data["record"] == "failed"]     # the reducer admits one pending start
    assert closed["attempt"] == 1 and closed["code"] not in DISPATCHED_FAILURE_CODES   # never blocks an invalidation cut
    assert closed["code"] == "provider_preparation_failed" and closed["exit_info"]["error"]   # R5: the proof is recorded
    assert len(shim_requests(tmp_path)) == 4


@pytest.mark.parametrize("crash_in_window", [False, True], ids=["once", "crash-after-receipt"])
def test_resume_proves_a_launched_attempt_not_dispatched_and_allocates_the_next(tmp_path, monkeypatch, crash_in_window) -> None:
    """R5/R6: killed after `launching` while the CLI still sleeps before any store write. Resume stops the live group,
    the adapter proves the predecessor head unchanged, the receipt records `not_dispatched`, the attempt closes `failed`
    with its proof, and a2 runs as attempt 2. A resume that dies between that receipt write and the `failed` row is
    finished by the next resume from the receipt alone."""
    plan = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": "timeout", "result": {}},
                       {"mode": "success", "result": {"text": "d2"}}], "codex": PLAN["codex"]}
    _install(tmp_path, monkeypatch, plan)
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "launching", "STOP_TURN": "/ a2"}, "run", *fixture(tmp_path))
    run_root, _a, _c, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts.values()
    assert _receipt(run_root, pending)["completion"] == "launching"
    if crash_in_window:
        _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "not_dispatched", "STOP_TURN": "/ a2"}, "resume", run_root.name)
        assert set(memo_of(tmp_path)[3].pending_starts) == {pending.data["identity"]}
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["a2"]["attempt"] == 2 and _receipt(run_root, pending)["completion"] == "not_dispatched"
    rows = [e.data for e in after.entries if e.data.get("identity") == pending.data["identity"] and e.data["record"] in {"started", "failed"}]
    assert [r["record"] for r in rows] == ["started", "failed", "started"]
    expected = "receipt records proven non-dispatch" if crash_in_window else "head unchanged, process group quiescent"
    assert rows[1]["code"] == "provider_preparation_failed" and expected in rows[1]["exit_info"]["error"]
    assert [r["tool"] for r in shim_requests(tmp_path)] == ["claude", "codex", "claude", "codex"]


def test_kill_between_started_and_attempt_directory_allocates_the_next_attempt(tmp_path, monkeypatch) -> None:
    """`started` is appended before `mkdir_exclusive`: a kill in that window leaves no directory, no receipt, no launch.
    Resume classifies it like a missing receipt (read-only at preflight), closes it `failed` and runs attempt 2."""
    _install(tmp_path, monkeypatch)
    _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": "started", "STOP_TURN": "/ a2"}, "run", *fixture(tmp_path))
    run_root, _a, _c, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts.values()
    assert not (run_root / Path(pending.data["result_path"]).parent).exists()
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    rows = [e.data for e in after.entries if e.data.get("identity") == pending.data["identity"] and e.data["record"] in {"started", "failed"}]
    assert [r["record"] for r in rows] == ["started", "failed", "started"]
    assert rows[1]["code"] == "provider_preparation_failed" and "attempt directory never created" in rows[1]["exit_info"]["error"]
    assert turns(after, classes)["a2"]["attempt"] == 2 and len(shim_requests(tmp_path)) == 4


@pytest.mark.parametrize("record, turn", [("committed", "/ b1"), ("settled", "/ a2")])
def test_kill_after_commit_or_settle_reconciles_without_native_append(tmp_path, monkeypatch, record, turn) -> None:
    _install(tmp_path, monkeypatch)
    frontend = fixture(tmp_path)
    _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": record, "STOP_TURN": turn}, "run", *frontend)
    run_root, *_ = memo_of(tmp_path)
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _root, _authority, classes, after = memo_of(tmp_path)
    t = turns(after, classes)
    assert set(t) == {"a1", "b1", "a2", "b2"} and all(v["attempt"] == 1 for v in t.values())
    settled_by = {e.data["identity"].rsplit("/ ", 1)[1]: e.data["by"] for e in after.entries if e.data["record"] == "settled"}
    assert settled_by[turn.strip("/ ")] == ("reconcile" if record == "committed" else "settle")
    assert len(shim_requests(tmp_path)) == 4             # every turn dispatched exactly once across run and resume


def test_completed_run_resumes_readonly_after_native_stores_disappear(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    run_root, *_ = memo_of(tmp_path)
    import shutil
    shutil.rmtree(tmp_path / "codex"); shutil.rmtree(tmp_path / "claude")
    for attempt in (run_root / "effects").rglob("receipt.json"):
        attempt.unlink()
    before = {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"}
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    assert {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"} == before


@pytest.mark.parametrize("mode", ["interrupted", "nonzero"])
def test_later_turn_unresolved_refuses_on_resume_and_preserves_the_pending_start(tmp_path, monkeypatch, mode) -> None:
    plan = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": mode, "result": {}}], "codex": PLAN["codex"]}
    _install(tmp_path, monkeypatch, plan)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 1
    run_root, _a, _c, memo = memo_of(tmp_path)
    memo_bytes = (run_root / "memo.jsonl").read_bytes()
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 2 and "agent_turn_unresolved" in resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes() == memo_bytes
    assert len(shim_requests(tmp_path)) == 3


def test_codex_overlap_after_an_interrupted_turn_classifies_unresolved(tmp_path, monkeypatch) -> None:
    """Task 6 WATCH: someone resumes the thread by hand after b2 was interrupted; Codex appends a new `task_started` after
    the unclosed turn, which the adapter rejects as an overlap. Resume must refuse `agent_turn_unresolved`, never crash."""
    from orchestrator.providers.native_store import NativeStoreError, native_store_adapter
    plan = {"claude": PLAN["claude"], "codex": [PLAN["codex"][0], {"mode": "interrupted"}, {"mode": "interrupted"}]}
    _install(tmp_path, monkeypatch, plan)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 1
    run_root, _a, _c, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts.values()
    session = _receipt(run_root, pending)["locator"]
    subprocess.run([str(tmp_path / "bin" / "codex"), "exec", "resume", session], input=b"by hand", cwd=tmp_path, check=False)
    adapter = native_store_adapter("codex_exec_jsonl_stdout")
    with pytest.raises(NativeStoreError, match="overlaps"):
        adapter.head(adapter.locate(session).path)
    memo_bytes = (run_root / "memo.jsonl").read_bytes()
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 2 and "agent_turn_unresolved" in resumed.stderr, resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes() == memo_bytes


@pytest.mark.parametrize("field, value", [("locator", "other"), ("position_after", {"turn_id": "x", "end_line": 99}),
                                          ("result_digest", "sha256:" + "2" * 64)])
def test_completed_receipt_freezes_its_native_facts(tmp_path, field, value) -> None:
    """Task 10 review: once `completed`, `locator` and `position_after` are frozen; `completed -> completed` may only add
    the first `result_digest`."""
    from orchestrator.workflow.evaluated.agent_sessions import write_receipt
    from orchestrator.workflow.evaluated.agent_turns import update_receipt
    from orchestrator.workflow.evaluated.memo import MemoError
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    files = WorkspaceFiles(tmp_path)
    write_receipt(files, _launched_receipt(4242, 77))
    update_receipt(files, position_after={"turn_id": "t", "end_line": 9}, completion="completed")
    update_receipt(files, result_digest="sha256:" + "1" * 64)
    with pytest.raises(MemoError, match="memo_inconsistent"):
        update_receipt(files, **{field: value})
    files.close()


@pytest.mark.parametrize("field, value", [("adapter", "claude_stream_json_stdout"), ("locator", "00000000-0000-4000-8000-000000000000")])
def test_replay_refuses_a_committed_proof_that_disagrees_with_its_receipt(tmp_path, monkeypatch, field, value) -> None:
    """Task 10 review: replay checks the proof against the receipt it can see (tamper detection), without the template."""
    _install(tmp_path, monkeypatch)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    run_root, _a, classes, memo = memo_of(tmp_path)
    path = run_root / Path(turns(memo, classes)["b1"]["result_path"]).parent / "receipt.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), field: value}))
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 2 and "memo_inconsistent" in resumed.stderr, resumed.stderr
