"""The reducer admits `agent` (ordinary) and `agent_turn` (coordinator) records and their proof shape."""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.memo import MemoError, read_memo
from orchestrator.workflow.evaluated.memo_reducer import COORDINATOR_CLASSES, is_coordinator_class
from tests.test_workflow_evaluated_memo import _committed, _line, _started, _write

ALLOC = "workflow:demo::run / designer"
TURN = "workflow:demo::run / a1"
SITES = {ALLOC: "agent", TURN: "agent_turn"}
DIGEST = "sha256:" + "0" * 64
PROOF = {"adapter": "codex_exec_jsonl_stdout", "locator": "01a1-sess", "position": {"turn_id": "t1", "end_line": 7},
         "predecessor": None, "agent": ALLOC, "config_digest": DIGEST}
AGENT_VALUE = {"run_id": "run", "identity": ALLOC, "provider": "codex", "policy": {"model": "m"}, "config_digest": DIGEST}


def _alloc_commit():
    return _committed(ALLOC, value=AGENT_VALUE, effect_class="agent")


def _turn_commit(identity=TURN, **over):
    row = _committed(identity, value={"ok": True}, effect_class="agent_turn", depends_on=[ALLOC])
    row["proof"] = dict(PROOF)
    row.update(over)
    return row


def test_predicate_names_both_coordinators() -> None:
    assert COORDINATOR_CLASSES == frozenset({"run_ref", "agent_turn"})
    assert [is_coordinator_class(c) for c in ("command", "provider", "agent", "run_ref", "agent_turn")] == [False, False, False, True, True]


def test_allocation_is_ordinary_and_turn_is_an_unsettled_coordinator_until_settled(tmp_path: Path) -> None:
    path = tmp_path / "memo.jsonl"
    _write(path, _started(ALLOC), _alloc_commit(), _started(TURN), _turn_commit())
    snapshot = read_memo(path, SITES)
    assert set(snapshot.active_commits) == {ALLOC, TURN}
    assert set(snapshot.unsettled_coordinators) == {(TURN, 1)}
    with path.open("ab") as stream:
        stream.write(_line({"record": "settled", "identity": TURN, "attempt": 1, "by": "settle"}))
    settled = read_memo(path, SITES)
    assert settled.unsettled_coordinators == {} and (TURN, 1) in settled.settlements


@pytest.mark.parametrize("bad", [
    {"proof": None},
    {"proof": {**PROOF, "extra": 1}},
    {"proof": {**PROOF, "position": {"turn_id": "t1"}}},
    {"proof": {**PROOF, "agent": "workflow:demo::run / nobody"}},
    {"proof": {**PROOF, "predecessor": 3}},
    {"proof": {**PROOF, "config_digest": "sha256:" + "1" * 64}},
])
def test_turn_proof_shape_is_exact_and_bound_to_an_active_allocation(tmp_path: Path, bad) -> None:
    path = tmp_path / "memo.jsonl"
    _write(path, _started(ALLOC), _alloc_commit(), _started(TURN), _turn_commit(**bad))
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(path, SITES)


def test_allocation_cannot_carry_proof_and_settled_rejects_ordinary_classes(tmp_path: Path) -> None:
    path = tmp_path / "memo.jsonl"
    _write(path, _started(ALLOC), {**_alloc_commit(), "proof": PROOF})
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(path, SITES)
    _write(path, _started(ALLOC), _alloc_commit(), {"record": "settled", "identity": ALLOC, "attempt": 1, "by": "settle"})
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(path, SITES)


def test_invalidation_anchor_before_a_committed_turn_is_refused_on_replay(tmp_path: Path) -> None:
    path = tmp_path / "memo.jsonl"
    raw = _write(path, _started(ALLOC), _alloc_commit(), _started(TURN), _turn_commit(),
                 {"record": "settled", "identity": TURN, "attempt": 1, "by": "settle"})
    anchor = raw.index(_line(_alloc_commit()))
    with path.open("ab") as stream:
        stream.write(_line({"record": "invalidated", "from_commit": anchor, "time": 1.0}))
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(path, SITES)


def test_predecessor_must_be_the_same_agents_latest_turn(tmp_path: Path) -> None:
    TURN2 = "workflow:demo::run / a2"
    sites = {**SITES, TURN2: "agent_turn", "workflow:demo::run / other": "agent"}
    path = tmp_path / "memo.jsonl"
    # fork: a2 names None as predecessor although a1 is committed on the same agent
    _write(path, _started(ALLOC), _alloc_commit(), _started(TURN), _turn_commit(), _started(TURN2),
           _turn_commit(TURN2, proof={**PROOF, "predecessor": None}))
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(path, sites)
    # the chained form is admitted
    _write(path, _started(ALLOC), _alloc_commit(), _started(TURN), _turn_commit(), _started(TURN2),
           _turn_commit(TURN2, proof={**PROOF, "predecessor": TURN}))
    assert set(read_memo(path, sites).unsettled_coordinators) == {(TURN, 1), (TURN2, 1)}
    # cross-agent predecessor
    other = _committed("workflow:demo::run / other", value={**AGENT_VALUE, "identity": "workflow:demo::run / other"}, effect_class="agent")
    _write(path, _started(ALLOC), _alloc_commit(), _started("workflow:demo::run / other"), other, _started(TURN), _turn_commit(), _started(TURN2),
           _turn_commit(TURN2, proof={**PROOF, "agent": "workflow:demo::run / other", "predecessor": TURN}))
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(path, sites)


def test_turn_start_requires_an_active_allocation(tmp_path: Path) -> None:
    path = tmp_path / "memo.jsonl"
    _write(path, _started(TURN))
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(path, SITES)


@pytest.mark.parametrize("closing", [
    None,
    {"record": "failed", "identity": TURN, "attempt": 1, "code": "agent_bootstrap_restarted", "exit_info": {"abandoned_attempt": 1, "locator": "x"}},
    {"record": "failed", "identity": TURN, "attempt": 1, "code": "agent_turn_result_invalid", "exit_info": {}, "violations": []},
    {"record": "failed", "identity": TURN, "attempt": 1, "code": "provider_result_invalid", "exit_info": {}, "violations": []},
])
def test_invalidation_cut_over_a_dispatched_agent_attempt_is_inconsistent(tmp_path: Path, closing) -> None:
    CMD = "workflow:demo::run / cmd"
    sites = {**SITES, CMD: "command"}
    path = tmp_path / "memo.jsonl"
    cmd_commit = _committed(CMD, value="x", effect_class="command")
    rows = [_started(ALLOC), _alloc_commit(), _started(CMD), cmd_commit, _started(TURN)] + ([closing] if closing else [])
    raw = _write(path, *rows)
    anchor = raw.index(_line(cmd_commit))
    with path.open("ab") as stream:
        stream.write(_line({"record": "invalidated", "from_commit": anchor, "time": 1.0}))
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(path, sites)


def test_terminal_waits_for_the_turn_settlement(tmp_path: Path) -> None:
    path = tmp_path / "memo.jsonl"
    _write(path, _started(ALLOC), _alloc_commit(), _started(TURN), _turn_commit(),
           {"record": "terminal", "outcome": "completed", "value": {"ok": True}})
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(path, SITES)


def test_invalidation_cut_over_an_undispatched_agent_failure_is_admitted(tmp_path: Path) -> None:
    CMD = "workflow:demo::run / cmd"
    sites = {**SITES, CMD: "command"}
    path = tmp_path / "memo.jsonl"
    cmd_commit = _committed(CMD, value="x", effect_class="command")
    raw = _write(path, _started(ALLOC), _alloc_commit(), _started(CMD), cmd_commit, _started(TURN),
                 {"record": "failed", "identity": TURN, "attempt": 1, "code": "provider_timeout", "exit_info": {}})
    with path.open("ab") as stream:
        stream.write(_line({"record": "invalidated", "from_commit": raw.index(_line(cmd_commit)), "time": 1.0}))
    assert set(read_memo(path, sites).active_commits) == {ALLOC}
