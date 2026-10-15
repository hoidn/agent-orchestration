# Agent Sessions Implementation Plan B: Runtime, Observation, Consumer And Qualification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use `superpowers:test-driven-development` for every behavior change, `tmux` for broad pytest runs and real-provider smokes, and `superpowers:verification-before-completion` before any acceptance claim.

**Goal:** run agent allocations and sequential native-session turns on the evaluated runtime at target 2.38 with memo-committed typed results, receipt-backed recovery, C8 whole-suffix guards, per-agent tmux views, the opt-in two-agent `design_review_execute` consumer, and the PQ-1a qualification gate (deterministic proofs plus one bounded real-provider smoke per adapter), stopping at the named acceptance-comparison gate.

**Architecture:** three new evaluated modules plus two splits. `agent_sessions.py` owns the non-coordinator `agent` class (allocation commit of the runtime-produced `Agent` descriptor with its pinned-configuration digest, reference decoding against the active allocation commit) and the attempt receipt. `agent_guards.py` owns the receipt-based C8 and resume-prefix guards (R1). `agent_turns.py` is the one bounded native-turn coordinator (`prepare`/`settle`/`reconcile` in the K2/K3 shape used by `run_ref.py`): it resolves the turn's input (agent, predecessor, continuation digest plus the ordinary provider parts), performs the D1 pre-append head check, writes the receipt before dispatch, launches through `providers.launch_provider` with a `ProviderSessionRequest`, verifies exact native completion through `native_store`, validates the typed result through `provider_result`, and returns the inline proof. `memo_reducer.py` generalizes "coordinator" from the literal `run_ref` to a class predicate and, through `memo_reducer_agents.py`, validates the `agent_turn` proof shape and every journal-only agent guard (R1); `memo.invalidate_suffix` adds the receipt-based whole-suffix guard and `_validate_discovered_prefix` the resume-time receipt guard. `runtime.py` keeps every memo-appending helper (the kill-point hooks patch `runtime.append_record`, `attempts.append_record` and `agent_turns.append_record`) and moves its read-only resume-prefix helpers to `resume_prefix.py`. Views add agent identity and continuation status. `ProviderObservationManager` is constructed only for evaluated runs whose checked program contains agent effects (R2); agent turns share one pre-opened handle per agent instance. Plan A (`2026-10-14-agent-sessions-implementation-plan.md`) owns the compiler, transport and fake CLIs; its "Interface contract with Plan B" section is the only contract this plan assumes.

**Tech Stack:** Python 3.12, pytest, the evaluated runtime (`orchestrator/workflow/evaluated/`), `orchestrator/providers` executor/observation, Workflow Lisp.

**Spec:** `docs/design/workflow_lisp_agent_sessions.md` (authoritative). Deferred owners: `docs/design/workflow_lisp_evaluated_execution.md` §§6–9 (identity, memo, K-rules, C8), `specs/{providers,io,state,cli,versioning,observability}.md`. Owner decisions D1–D8 are reflected in the design text.

**Schema/profile decision:** additive, no version bump. Evaluated runs keep `evaluated_execution.v1`, schema `3.0`, representation `table/1`. The journal gains two `effect_class` values (`agent`, `agent_turn`) and one class-specific `proof` shape for `agent_turn`; no new record kind, no new `started`/`failed` field, no new header field. Receipts and abandonment markers live in attempt storage (`effects/<digest>/attempt-N/receipt.json`, `abandoned.json`), per the design ("no second run journal, session database or agent-head file"). Rule applied: `specs/versioning.md` ties state-schema bumps to changes in the shape of existing records or views that old readers would misread; a run at 2.35–2.37 can never contain the new classes (its checked site table lacks them), so old runs reduce exactly as before and no reader misreads an old journal. `specs/state.md` and `specs/versioning.md` are amended to say so (Tasks 8 and 21).

## Global Constraints

- Everything in Plan A's Global Constraints applies (target 2.38 only; no provider-name dispatch; default native home; <= 500 lines/module, complexity <= 12; pathspec commits without attribution trailers; no `git add .`; narrow selectors first, `--collect-only` for new modules, broad runs in tmux).
- Memo invariants kept: `committed` matches a pending `started`; no `terminal` while a start is pending or a coordinator is unsettled (`runtime._append_failed_terminal_if_clear`); a committed coordinator is never superseded (K8).
- Agent turns: at most one active turn per agent; allocation never launches a provider; model/effort come from the allocation only; no automatic in-run retry; native history is never reset; the first turn may be bootstrapped only by an explicit public `resume`.
- Runtime diagnostics introduced (exact codes): `agent_session_unavailable`, `agent_session_diverged`, `agent_policy_mismatch`, `agent_turn_unresolved`, `agent_turn_result_invalid`, `agent_bootstrap_restarted`, `invalidate_agent_session_advanced`; compile-time codes are the twelve listed in Plan A's Global Constraints. No others.
- Tests assert memo records, receipts, proofs, diagnostics, dispatch counts, dataflow (`depends_on`, typed values) and artifact lineage; never literal prompt text.
- The only paid steps are Tasks 19 and 20 (one bounded real smoke per adapter), each gated by an explicit environment flag and run in tmux; every other task uses the Plan A fake CLIs.
- Line budget (counts today / after this plan): `runtime.py` 491 → about 440 (Task 10 moves the read-only helpers `_replay_resume_prefix`, `_prepare_parallel_recovery`, `_validate_discovered_prefix`, `_resume_refusal`, `_replayed_halt_result` to `resume_prefix.py`; every helper that appends a memo record — `_append_effect_commit`, `_fail_started_effect`, `_append_failed_terminal_if_clear`, `_persist_completed_terminal` — stays in `runtime.py`, and agent decisions enter through one dispatch line each into `agent_turns.prepare_agent_attempt`); `providers.py` 334 → about 352 (Plan A); `memo_reducer.py` 381 → about 400 (agent proof and journal guards in `memo_reducer_agents.py`, about 120); `sites.py` 554 → about 440 (Plan A `node_walk.py`); `observation.py` 584, untouched (R2: the backend is injected through the existing `backend=` constructor parameter); `effect_inputs.py` 335 → about 360; `replay.py` 196 → about 215; `views.py` 199 → about 212; `memo.py` 174 → about 180; `agent_sessions.py` about 170; `agent_turns.py` about 420; `agent_guards.py` about 130. Every task touching `runtime.py` ends with `wc -l` on it and the stdlib complexity check below (no function above 12), recorded in the commit body; no new tool is added.

```bash
python - orchestrator/workflow/evaluated/runtime.py orchestrator/workflow/evaluated/agent_turns.py <<'EOF'
import ast, sys
BRANCH = (ast.If, ast.For, ast.While, ast.IfExp, ast.ExceptHandler, ast.With, ast.Assert, ast.comprehension, ast.BoolOp, ast.Match)
for path in sys.argv[1:]:
    for node in ast.walk(ast.parse(open(path).read())):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            score = 1 + sum(isinstance(n, BRANCH) + (len(n.values) - 1 if isinstance(n, ast.BoolOp) else 0) for n in ast.walk(node))
            if score > 12:
                print(f"{path}:{node.lineno} {node.name} complexity {score}"); sys.exit(1)
print("complexity ok")
EOF
```
- Kill-point hooks: all test drivers patch `attempts.append_record`, `runtime.append_record` and `agent_turns.append_record` (the three modules that append) and `agent_turns.write_receipt`, following `tests/workflow_evaluated_recovery_helpers.py:114-124`. The six existing drivers that patch only `runtime.append_record` — `tests/test_workflow_evaluated_verified_drain.py:110`, `tests/test_workflow_evaluated_resume_kills.py:28-40`, `tests/workflow_evaluated_program_sources.py:128-139`, `tests/test_workflow_evaluated_parallel_failures.py:49,70`, `tests/workflow_evaluated_recovery_helpers.py:114-124`, `tests/workflow_evaluated_shared_union_helpers.py:59` — keep working because `committed`, `failed` and `terminal` rows still go through `runtime.append_record` and `started` through `attempts.append_record` exactly as today.

## Review Focus

1. `orchestrator report` on a run whose agent turn is pending unresolved: an operator expects a `running` row with the agent identity, not `failed` or `memo_inconsistent`. Test pinned in Task 14.
2. Invalidating an allocation that no turn ever used: must succeed under C8 (an unused allocation is not protected). Test pinned in Task 13.
3. Deleting `~/.claude`/`~/.codex` after a run completed: `resume` must still exit 0 read-only from committed proofs (no receipt or native store read). Test pinned in Task 11.
4. The same agent invoked twice where the second prompt does not consume the first result: `depends_on` and the proof must still record the predecessor. Test pinned in Task 10.
5. An ordinary `provider-result` in the same program as agents: still `session_request=None`, still one pane per invocation, still `file/2`. Test pinned in Task 15.

---

## Interface contract consumed from Plan A

See `docs/plans/2026-10-14-agent-sessions-implementation-plan.md` "Interface contract with Plan B". Plan B additionally fixes these cross-task names:

| Produced by | Name and signature |
| --- | --- |
| Task 8 | `memo_reducer.COORDINATOR_CLASSES = frozenset({"run_ref", "agent_turn"})`; `memo_reducer.is_coordinator_class(name: str) -> bool`; `agent_turn` proof shape `{"adapter": str, "locator": str, "position": {"turn_id": str, "end_line": int}, "predecessor": str | None, "agent": str, "config_digest": str}`; `memo_reducer_agents.check_started/check_committed_proof/check_invalidation_cut` (journal-only guards) |
| Task 9 | `agent_sessions.AgentBinding(identity, run_id, provider, policy, config_digest)`; `agent_sessions.pinned_config_digest(template, policy, launch_cwd) -> str` (canonical digest over `session_support.fresh_command`, `resume_command`, `metadata_mode`, `input_mode`, resolved `defaults`, `call_policy_bindings` targets, the policy and the launch cwd locator); `agent_sessions.resolve_agent_reference(snapshot, value, *, run_id) -> AgentBinding`; `agent_sessions.resolve_allocation_input(node, operands) -> tuple[dict, dict[str, str]]`; `agent_sessions.perform_allocation(attempt) -> ExternalOutcome`; `agent_sessions.allocation_result(attempt) -> tuple[EvaluatedValue, str]`; `agent_sessions.Receipt` (fields in Task 9; `completion ∈ {intent, launching, completed, not_dispatched, unknown, abandoned}`, `pgid: int | None`, `leader_start_time: int | None` (R3: the group leader's `/proc/<pid>/stat` start time, recorded with `pgid` at `launching`), `config_digest`), `read_receipt(attempt_dir_files) -> Receipt | None`, `write_receipt(attempt_dir_files, receipt) -> None` |
| Task 10 | `agent_turns.AgentTurnError(code, message, *, exit_info=None, violations=None, keep_pending=False)`; `agent_turns.resolve_turn_input(authority, node, operands, identity, workspace, reader, *, snapshot, result_path, launch_cwd, committed_offset: int | None = None) -> ResolvedTurn`; `agent_turns.prepare_agent_attempt(authority, node, operands, identity, snapshot, *, ordinal, attempt_directory, result_path, resolved, parts, implementation_files, dependencies, context) -> PreparedAttempt` (start-order check, D1 head check, pending-turn classification, recovery or bootstrap, then `allocate_attempt`); `agent_turns.turn_dependencies(resolved, operand_dependencies) -> tuple[str, ...]` (operand dependencies plus the predecessor identity); `agent_turns.leader_start_time(pid: int) -> int | None` (field 22 of `/proc/<pid>/stat`, the parsing `scripts/experiments/native_session_cli_process.py::_process_table` uses; `None` when the pid has no `/proc` entry or `/proc` is absent); `agent_turns.AgentTurnControl(ProviderExecutionControl)` whose `bind(process, pgid)` writes the receipt `launching` with `pgid` and `leader_start_time=leader_start_time(pgid)` before returning; `agent_turns.perform_turn(attempt, *, views) -> ExternalOutcome` (every exception raised after the receipt reached `launching` leaves as `AgentTurnError("agent_turn_unresolved", keep_pending=True)` with the receipt at `unknown`; before `launching` an unmapped exception is an ordinary failure); `agent_turns.project_turn(attempt, outcome) -> (EvaluatedValue, digest, proof, prepared)` (only the typed-result validation failure closes `failed` — `provider_result_invalid` on a first turn, `agent_turn_result_invalid` afterwards; any other exception after the receipt reached `completed` leaves as `AgentTurnError("agent_turn_unresolved", keep_pending=True)` with the receipt unchanged at `completed`, design row 6); `agent_turns.settle_turn(authority, resolved, identity, attempt, workspace, site_classes, prepared, committed) -> None` (same arity as `settle_evaluated_run_ref`); `agent_turns.update_receipt(attempt_files, **changes) -> Receipt` (monotone: reads the stored receipt, never drops a set field, only advances `completion`); `agent_turns.validate_turn(authority, resolved, identity, commit, *, settled) -> None`; `agent_turns.reconcile_turn(authority, resolved, identity, commit, site_classes) -> None`; `agent_turns.predecessor_commit(snapshot, agent_identity, *, before_offset: int | None = None) -> JournalEntry | None`; `effect_execution.ExternalOutcome` gains `agent_turn: Any = None` (the verified `NativeTurn`) |
| Task 11 | `agent_turns.PendingTurn(disposition, receipt, native_turn, detail)`; `agent_turns.quiesce(receipt, *, probe_only: bool = False) -> str` returning `"quiescent"`, `"alive"` (only with `probe_only=True`: the group answers `killpg(pgid, 0)`, nothing was signalled) or `"unprovable"` (a `PermissionError` on the probe, or still alive after `SIGTERM` + 2 s grace + `SIGKILL` + 2 s, using the executor's process-tree termination shape); R3: before probing or signalling, a live leader pid whose `leader_start_time(pgid)` differs from `receipt.leader_start_time` is a reused pid and returns `"quiescent"` without any signal; `agent_turns.classify_pending_turn(authority, node, identity, snapshot, workspace, resolved: ResolvedTurn, *, probe_only: bool = False) -> PendingTurn` with `disposition ∈ {"recoverable", "not_dispatched", "unresolved", "bootstrap", "needs_quiescence"}` (`needs_quiescence` only with `probe_only=True`: the read-only preflight admits it; `_prepare_pending` quiesces under the writer lock and re-classifies); `ResolvedTurn.pending: PendingTurn | None = None` (set with `dataclasses.replace`) |
| Task 13 | `agent_guards.check_invalidation_suffix(snapshot, chosen, run_files, site_classes) -> None`; `agent_guards.validate_prefix_receipts(authority, snapshot, site_classes) -> None` (resume-time, R1) |
| Task 15 | `agent_turns.AgentViews(manager) .handle_for(agent_identity, turn_identity, ordinal) .close()`; `runtime.provider_executor_for_run(workspace, run_root, *, agents_present: bool) -> tuple[ProviderExecutor, ProviderObservationManager | None]`; `runtime.observation_backend() -> _ObservationBackend | None` (module-level factory returning `None` = tmux default; tests replace it in their driver script, never through the environment) |

---

### Task 8: Memo admission of the agent classes and the coordinator predicate

**Files:**
- Modify: `orchestrator/workflow/evaluated/memo_reducer.py:16` (`_CLASSES`), `:214-233` (`started`: one call `agents.check_started(self, identity, kind)`), `:242-269` (`committed`: proof per coordinator class through `agents.check_committed_proof(self, row, identity, attempt, kind)`), `:286-305` (`_proof` becomes `_run_ref_proof`), `:327-338` (`settled` accepts any coordinator class), `:351-355` (`_check_invalidation` uses the predicate and one call `agents.check_invalidation_cut(self, anchor)`)
- Create: `orchestrator/workflow/evaluated/memo_reducer_agents.py` (`check_started`, `check_committed_proof`, `check_invalidation_cut`, `_agent_turn_proof`; pure functions over the reducer state, no I/O — R1)
- Modify: `orchestrator/workflow/evaluated/memo.py:159-174` (`invalidate_suffix` coordinator predicate; the receipt guard is Task 13)
- Modify: `orchestrator/workflow/evaluated/replay.py:107-112` (`_settled_offset` uses the predicate)
- Modify: `orchestrator/workflow/evaluated/views.py:156-186` (no change needed for status; `settling` already keys on `unsettled_coordinators`)
- Create: `tests/test_workflow_evaluated_memo_agent_classes.py`
- Modify (spec amendment): `specs/state.md:372-400` ("Memo records": `effect_class` set, `proof` rule, reducer rules), `:428-447` ("Attempt directories": agent turn files `prompt.txt`, `receipt.json`, `result.json`, `stdout.txt`, `stderr.txt`, optional `abandoned.json`; allocation: `result.json` only), `:449-470` ("Coordinator records": agent turn paragraph), `specs/cli.md:440-470` (diagnostics table rows for the seven codes with exit/evidence columns; the raising sites are filled by Tasks 10–13)

**Interfaces:**
- Produces: `COORDINATOR_CLASSES`, `is_coordinator_class`, the `agent_turn` proof validation and the journal-only agent guards: (i) `proof.predecessor` must be a turn of the same `proof.agent` and equal that agent's latest active committed turn preceding this commit (no forks, no skips); (ii) an `agent_turn` `started` requires an active allocation commit of class `agent` in the journal; (iii) an `invalidated` anchor at or before an `agent_turn` attempt that is pending, or failed with `agent_bootstrap_restarted`, `agent_turn_result_invalid` or a first-turn `provider_result_invalid`, is `memo_inconsistent` (journal evidence of a dispatched or advanced attempt).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_memo_agent_classes.py
"""The reducer admits `agent` (ordinary) and `agent_turn` (coordinator) records and their proof shape."""
from __future__ import annotations

import json
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


def _turn_commit(**over):
    row = _committed(TURN, value={"ok": True}, effect_class="agent_turn", depends_on=[ALLOC])
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


def _row(record, identity, attempt, **fields):
    return {"record": record, "identity": identity, "attempt": attempt, **fields}


def test_predecessor_must_be_the_same_agents_latest_turn(tmp_path: Path) -> None:
    TURN2 = "workflow:demo::run / a2"
    sites = {**SITES, TURN2: "agent_turn", "workflow:demo::run / other": "agent"}
    path = tmp_path / "memo.jsonl"
    # fork: a2 names None as predecessor although a1 is committed on the same agent
    _write(path, _started(ALLOC), _alloc_commit(), _started(TURN), _turn_commit(), _started(TURN2),
           {**_turn_commit(), "identity": TURN2, "proof": {**PROOF, "predecessor": None}})
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(path, sites)
    # cross-agent predecessor
    other = _committed("workflow:demo::run / other", value={**AGENT_VALUE, "identity": "workflow:demo::run / other"}, effect_class="agent")
    _write(path, _started(ALLOC), _alloc_commit(), _started("workflow:demo::run / other"), other, _started(TURN), _turn_commit(), _started(TURN2),
           {**_turn_commit(), "identity": TURN2, "proof": {**PROOF, "agent": "workflow:demo::run / other", "predecessor": TURN}})
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
```

Use the `_committed` helper from `tests/test_workflow_evaluated_memo.py`; if it does not accept `effect_class`/`depends_on`/`value` keywords, extend it there with keyword arguments defaulting to its current values (no behavior change for existing tests).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_evaluated_memo_agent_classes.py -q`
Expected: FAIL — `ImportError: COORDINATOR_CLASSES`; then `memo_inconsistent: checked site table is malformed`.

- [ ] **Step 3: Implement the reducer generalization**

```python
# orchestrator/workflow/evaluated/memo_reducer.py
_CLASSES = {"command", "provider", "run_ref", "agent", "agent_turn"}
COORDINATOR_CLASSES = frozenset({"run_ref", "agent_turn"})


def is_coordinator_class(name: str) -> bool:
    return name in COORDINATOR_CLASSES
```

In `committed`:

```python
        if expected_class in COORDINATOR_CLASSES:
            if expected_class == "run_ref":
                self._run_ref_proof(row.get("proof"), identity)
            else:
                agents.check_committed_proof(self, row, identity)
            self.unsettled[(identity, attempt)] = entry
        elif "proof" in row:
            raise _inconsistent("ordinary effect cannot carry coordinator proof")
```

In `started`, after the ordinal check: `agents.check_started(self, identity, self.site_class(identity))`. In `_check_invalidation`, after the coordinator check: `agents.check_invalidation_cut(self, anchor)`.

```python
# orchestrator/workflow/evaluated/memo_reducer_agents.py
"""Journal-only agent guards for the pure reducer (R1): no receipt or filesystem access."""
from __future__ import annotations

from typing import Any

DISPATCHED_FAILURE_CODES = {"agent_bootstrap_restarted", "agent_turn_result_invalid", "provider_result_invalid"}


def check_started(reducer, identity: str, kind: str) -> None:
    if kind != "agent_turn":
        return
    if not any(c.data["effect_class"] == "agent" for c in reducer.active.values()):
        raise reducer.inconsistent("agent turn started without an active allocation commit")


def check_committed_proof(reducer, row: dict[str, Any], identity: str) -> None:
    proof = _agent_turn_proof(reducer, row.get("proof"), identity)
    same_agent = [c for c in reducer.active.values() if c.data["effect_class"] == "agent_turn" and c.data["proof"]["agent"] == proof["agent"]]
    latest = max(same_agent, key=lambda c: c.offset, default=None)
    expected = None if latest is None else latest.data["identity"]
    if proof["predecessor"] != expected:
        raise reducer.inconsistent(f"agent turn {identity} names predecessor {proof['predecessor']!r}; the agent's latest committed turn is {expected!r}")


def check_invalidation_cut(reducer, anchor: int) -> None:
    for entry in reducer.entries:
        row = entry.data
        if row.get("record") != "started" or entry.offset < anchor or reducer.site_class(row["identity"]) != "agent_turn":
            continue
        closing = next((e.data for e in reducer.entries if e.offset > entry.offset and e.data.get("identity") == row["identity"]
                        and e.data.get("attempt") == row["attempt"] and e.data["record"] in {"committed", "failed"}), None)
        if closing is None or (closing["record"] == "failed" and closing["code"] in DISPATCHED_FAILURE_CODES):
            raise reducer.inconsistent(f"invalidation range covers a dispatched or pending agent turn attempt: {row['identity']} #{row['attempt']}")


def _agent_turn_proof(reducer, value: Any, identity: str) -> dict[str, Any]:
    from .memo_reducer import _object, _text
    proof = _object(value, "agent turn proof")
    if set(proof) != {"adapter", "locator", "position", "predecessor", "agent", "config_digest"}:
        raise reducer.inconsistent("agent turn proof must contain adapter, locator, position, predecessor, agent and config_digest")
    _text(proof["adapter"], "proof.adapter"); _text(proof["locator"], "proof.locator"); _text(proof["config_digest"], "proof.config_digest")
    position = _object(proof["position"], "proof.position")
    if set(position) != {"turn_id", "end_line"} or type(position["end_line"]) is not int or position["end_line"] < 1:
        raise reducer.inconsistent("agent turn position must carry turn_id and a positive end_line")
    _text(position["turn_id"], "proof.position.turn_id")
    agent = _text(proof["agent"], "proof.agent")
    if reducer.site_class(agent) != "agent" or agent not in reducer.active:
        raise reducer.inconsistent("agent turn proof names no active allocation commit")
    if proof["predecessor"] is not None:
        _text(proof["predecessor"], "proof.predecessor")
        if reducer.site_class(proof["predecessor"]) != "agent_turn" or proof["predecessor"] not in reducer.active:
            raise reducer.inconsistent("agent turn predecessor is not an active committed turn")
    return proof
```

Rule (iii) stated exactly: `check_invalidation_cut` walks every `agent_turn` `started` row at or after the anchor; a row with no `committed`/`failed` closing row (pending) or closed `failed` with a code in `DISPATCHED_FAILURE_CODES` is `memo_inconsistent`; a row closed `failed` with any other code, or committed (then K8 already refused), is allowed. `agent_guards.check_invalidation_suffix` applies the identical journal rule before any write (Task 13), so a durable `invalidated` row can never be refused on read. `_Reducer` gains `inconsistent = staticmethod(_inconsistent)` so the helper module raises through the reducer without importing its private name; `memo_reducer.py` imports `memo_reducer_agents as agents` at module top (no cycle: the agents module imports from `memo_reducer` only inside the function).

`settled`: `if kind not in COORDINATOR_CLASSES or commit is None ...`. `_check_invalidation`: `item.data["effect_class"] in COORDINATOR_CLASSES`. `memo.invalidate_suffix:168`: `if any(is_coordinator_class(item.data["effect_class"]) for item in suffix)`. `replay._settled_offset`: `if not is_coordinator_class(commit.data['effect_class']): return commit.offset`.

- [ ] **Step 4: Amend `specs/state.md` and `specs/cli.md` (sections named in Files)**

"Memo records" table: `committed` row — "`effect_class` ∈ `command`, `provider`, `run_ref`, `agent`, `agent_turn`; `proof` only, and always, when the class is a coordinator (`run_ref`: `{settled_result, artifacts}`; `agent_turn`: `{adapter, locator, position {turn_id, end_line}, predecessor, agent, config_digest}`, `agent` naming the active allocation commit, `predecessor` the previous active committed turn of that agent or `null`, `config_digest` equal to the allocation's pinned configuration)"; `depends_on` definition — "identities with active commits whose values the resolved input read, plus, for an `agent_turn`, its predecessor turn even when the prompt does not consume its result". Reducer rules paragraph: "a coordinator is a `run_ref` or `agent_turn` site; `settled` requires an unsettled coordinator commit of either class; an invalidation suffix must contain no coordinator commit; an `agent_turn` `started` requires an active allocation; an `agent_turn` proof's predecessor must be the same agent's latest active committed turn; an invalidation anchor at or before a pending agent turn attempt, or one closed `failed` with `agent_bootstrap_restarted`, `agent_turn_result_invalid` or a first-turn `provider_result_invalid`, is `memo_inconsistent`". Add after the table: "The additive classes `agent`/`agent_turn` appear only in journals of target-2.38 programs; the profile, schema and representation are unchanged, and journals of earlier targets reduce exactly as before." "Attempt directories": agent allocation leaves `result.json` only (the Agent descriptor, no process); an agent turn leaves `prompt.txt`, `receipt.json` (`agent_turn_receipt.v1`, written before dispatch and updated monotonically), then `result.json` when the provider wrote one, `stdout.txt`, `stderr.txt`, and `abandoned.json` when a bootstrap resume abandoned the candidate. "Coordinator records": "An agent turn commits with `effect_class: "agent_turn"` and the inline continuation proof; `settled` with `by: settle` follows immediately (local bookkeeping, no prompt); a stop after `committed` is reconciled on the next resume from the proof with `by: reconcile`, with no native append. A committed turn is never superseded (`invalidate_coordinator_committed`)."

`specs/cli.md` diagnostics table (after the `invalidate_not_committed` row): rows for `agent_session_unavailable`, `agent_session_diverged`, `agent_policy_mismatch` (raised before `started`/dispatch of a new turn; exit 1 during execution, 2 in resume preflight; `failed` terminal where the journal permits; no dispatch), `agent_turn_unresolved` (after a dispatched attempt whose completion/result cannot be established; exit 1; the `started` stays pending, no `failed`, no terminal; `resume` reconciles), `agent_turn_result_invalid` (a later turn completed natively with an invalid result; `failed` row with `violations`; `resume` refuses with the same code at preflight, exit 2), `agent_bootstrap_restarted` (diagnostic logged by `resume` when it abandons a first-turn candidate; the `failed` row of the abandoned attempt carries this code with `exit_info {abandoned_attempt, locator}`), `invalidate_agent_session_advanced` (`invalidate`, exit 2, none written).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workflow_evaluated_memo_agent_classes.py tests/test_workflow_evaluated_memo.py tests/test_workflow_evaluated_memo_writes.py tests/test_workflow_evaluated_invalidate.py tests/test_workflow_evaluated_run_ref_settlement.py -q`
Expected: PASS; `wc -l orchestrator/workflow/evaluated/memo_reducer.py orchestrator/workflow/evaluated/memo_reducer_agents.py` about 400 and 120.

- [ ] **Step 6: Commit**

```bash
git add tests/test_workflow_evaluated_memo_agent_classes.py orchestrator/workflow/evaluated/memo_reducer_agents.py
git commit -m "feat: admit agent and agent_turn memo classes behind a coordinator predicate" -- orchestrator/workflow/evaluated/memo_reducer_agents.py orchestrator/workflow/evaluated/memo_reducer.py orchestrator/workflow/evaluated/memo.py orchestrator/workflow/evaluated/replay.py tests/test_workflow_evaluated_memo_agent_classes.py tests/test_workflow_evaluated_memo.py specs/state.md specs/cli.md
```

---

### Task 9: Allocation effect, `Agent` reference decoding and receipts

**Files:**
- Create: `orchestrator/workflow/evaluated/agent_sessions.py`
- Modify: `orchestrator/workflow/evaluated/runtime.py:80` (handler gate adds `"agent"`, `"agent_turn"`), `orchestrator/workflow/evaluated/effect_execution.py:43-64` (`agent` → `perform_allocation`), `orchestrator/workflow/evaluated/effect_inputs.py:93-118` (`agent` branch → `resolve_allocation_input`), `:58-90` (`_check_resume_boundary`: `agent` needs nothing beyond the generic start check)
- Create: `tests/test_workflow_evaluated_agent_allocation.py`

**Interfaces:**
- Consumes: Plan A closed `agent` node, `Agent` value shape; Task 8 classes.
- Produces: the Task 9 names in the contract table. `Receipt` dataclass fields: `schema="agent_turn_receipt.v1"`, `run_id`, `agent`, `turn`, `attempt`, `predecessor: str | None`, `input_digest`, `adapter`, `config_digest`, `mode: "fresh" | "resume"`, `locator: str | None`, `pgid: int | None`, `leader_start_time: int | None` (R3: the process-group leader's start time, field 22 of `/proc/<pgid>/stat`, recorded together with `pgid` when the executor binds the child; `None` before launch or where `/proc` is absent), `position_before: dict | None`, `position_after: dict | None`, `completion: "intent" | "launching" | "completed" | "not_dispatched" | "unknown" | "abandoned"`, `result_digest: str | None`. Pinned configuration (I7): `pinned_config_digest(template, policy, launch_cwd)` is computed at allocation and stored in the descriptor; every turn recomputes it from the current registry template and refuses `agent_policy_mismatch` on difference, so a template or default change between run and resume cannot silently change the conversation's policy.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_agent_allocation.py
"""Allocation commits a runtime-owned Agent descriptor without launching anything; replay reconstructs it."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.agent_sessions import AgentBinding, Receipt, read_receipt, resolve_agent_reference, write_receipt
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import MemoError, read_memo
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_invalidate import _cli

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Note (text String))
  (defworkflow run ((task String) (n Int)) -> Note
    (let* ((designer (agent providers.codex :model "chosen-model" :effort "low"))
           (copies (loop/recur :max 3 (loop-state (i Int 0) (acc List[String] (list)))
                      (if (>= i n) (done acc)
                          (let* ((inner (agent providers.claude :model "m2")))
                            (continue (+ i 1) acc))))))
      (Note :text task))))'''


def _fixture(root: Path) -> list[str]:
    (root / "main.orc").write_text(SOURCE, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.codex": "codex", "providers.claude": "claude_unrestricted_workspace"}))
    return ["run", "main.orc", "--source-root", str(root), "--provider-externs-file", "providers.json", "--input", "task=t", "--input", "n=2"]


def test_allocations_commit_descriptors_with_no_dispatch_and_replay_readonly(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan={"codex": [], "claude": []})
    run = _cli(tmp_path, *_fixture(tmp_path))
    assert run.returncode == 0, run.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    classes = site_classes(authority.program)
    memo = read_memo(authority.memo_path, classes)
    from orchestrator.workflow.evaluated.memo_reducer import _DYNAMIC_INDEX
    allocations = {i: c for i, c in memo.active_commits.items() if (classes.get(i) or classes[_DYNAMIC_INDEX.sub("[*]", i)]) == "agent"}
    assert len(allocations) == 3  # designer + two loop activations
    designer = next(c for i, c in allocations.items() if i.endswith("/ designer"))
    value = designer.data["value"]
    assert {k: value[k] for k in ("run_id", "identity", "provider", "policy")} == {"run_id": run_root.name, "identity": designer.data["identity"], "provider": "codex", "policy": {"model": "chosen-model", "effort": "low"}}
    from orchestrator.providers.registry import ProviderRegistry
    from orchestrator.workflow.evaluated.agent_sessions import pinned_config_digest
    assert value["config_digest"] == pinned_config_digest(ProviderRegistry().get("codex"), value["policy"], None)
    assert designer.data["effect_class"] == "agent" and "proof" not in designer.data
    assert {c.data["value"]["identity"] for c in allocations.values()} == set(allocations)
    assert shim_requests(tmp_path) == []
    assert (run_root / Path(designer.data["result_path"])).read_bytes()
    assert sorted(p.name for p in (run_root / Path(designer.data["result_path"]).parent).iterdir()) == ["result.json"]
    before = {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"}
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"} == before


def test_reference_decoding_requires_the_active_allocation_commit(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan={"codex": [], "claude": []})
    assert _cli(tmp_path, *_fixture(tmp_path)).returncode == 0
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    memo = read_memo(authority.memo_path, site_classes(authority.program))
    designer = next(c for i, c in memo.active_commits.items() if i.endswith("/ designer"))
    binding = resolve_agent_reference(memo, designer.data["value"], run_id=run_root.name)
    assert binding == AgentBinding(designer.data["identity"], run_root.name, "codex", {"model": "chosen-model", "effort": "low"}, designer.data["value"]["config_digest"])
    with pytest.raises(MemoError, match="memo_inconsistent"):
        resolve_agent_reference(memo, {**designer.data["value"], "policy": {"model": "other"}}, run_id=run_root.name)
    with pytest.raises(MemoError, match="memo_inconsistent"):
        resolve_agent_reference(memo, designer.data["value"], run_id="another-run")


def test_receipt_round_trips_and_rejects_foreign_schema(tmp_path) -> None:
    files = WorkspaceFiles(tmp_path)
    receipt = Receipt(run_id="r", agent="a", turn="t", attempt=1, predecessor=None, input_digest="sha256:" + "0" * 64,
                      adapter="codex_exec_jsonl_stdout", config_digest="sha256:" + "0" * 64, mode="fresh", locator=None, pgid=None,
                      leader_start_time=None, position_before=None, position_after=None, completion="intent", result_digest=None)
    write_receipt(files, receipt)
    assert read_receipt(files) == receipt
    (tmp_path / "receipt.json").write_text(json.dumps({"schema": "other"}))
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_receipt(files)
    files.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_evaluated_agent_allocation.py -q`
Expected: FAIL — `ModuleNotFoundError: agent_sessions`; CLI run fails `unsupported evaluated effect class`.

- [ ] **Step 3: Implement allocation and receipts**

```python
# orchestrator/workflow/evaluated/agent_sessions.py
"""Run-local agent allocation (ordinary effect) and the attempt receipt of a turn."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.workspace_files import WorkspaceFiles

from .memo import MemoError, MemoSnapshot
from .values import EvaluatedValue, coerce_evaluated_value

AGENT_DESCRIPTOR = {"kind": "primitive", "name": "Agent"}
RECEIPT_SCHEMA = "agent_turn_receipt.v1"


@dataclass(frozen=True)
class AgentBinding:
    identity: str
    run_id: str
    provider: str
    policy: Mapping[str, str]
    config_digest: str

    def record(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "identity": self.identity, "provider": self.provider, "policy": dict(self.policy),
                "config_digest": self.config_digest}


def pinned_config_digest(template, policy: Mapping[str, str], launch_cwd) -> str:
    """Everything the conversation's native configuration depends on, pinned once at allocation."""
    session = template.session_support
    return canonical_sha256({
        "name": template.name, "command": list(template.command), "input_mode": template.input_mode.value,
        "defaults": dict(template.defaults),
        "bindings": {k: b.target_param for k, b in template.call_policy_bindings.items()},
        "session": None if session is None else {"metadata_mode": session.metadata_mode, "fresh": list(session.fresh_command),
                                                   "resume": list(session.resume_command or [])},
        "policy": dict(policy), "launch_cwd": None if launch_cwd is None else str(launch_cwd),
    })


def resolve_allocation_input(node: Mapping[str, Any], operands) -> tuple[dict[str, Any], dict[str, str]]:
    """Pin provider and policy once; the parts enter the ordinary input digest."""
    policy = dict(zip(node["policy"], (v.json_value() for v in operands), strict=True))
    if any(not isinstance(v, str) for v in policy.values()):
        raise MemoError("memo_inconsistent", "agent policy operands must be strings")
    resolved = {"provider": node["provider"], "policy": policy}
    return resolved, {"provider": canonical_sha256(node["provider"]), "policy": canonical_sha256(policy)}


def perform_allocation(attempt):
    """Write the descriptor as the attempt result; no provider, no session, no process."""
    from orchestrator.providers.registry import ProviderRegistry
    from .effect_execution import ExternalOutcome
    template = ProviderRegistry().get(attempt.resolved["provider"])
    if template is None:
        raise MemoError("memo_inconsistent", f"agent provider {attempt.resolved['provider']!r} is not registered")
    binding = AgentBinding(attempt.identity, attempt.authority.header["run_id"], attempt.resolved["provider"],
                           attempt.resolved["policy"], pinned_config_digest(template, attempt.resolved["policy"], attempt.launch_cwd))
    attempt.attempt_files.write_atomic("result.json", canonical_json_bytes(binding.record()))
    return ExternalOutcome(result_path=attempt.result_path)


def allocation_result(attempt) -> tuple[EvaluatedValue, str]:
    raw = attempt.attempt_files.read("result.json")
    value = coerce_evaluated_value(json.loads(raw), AGENT_DESCRIPTOR, committed_result_path=attempt.result_path,
                                   context="agent allocation result")
    return value, "sha256:" + __import__("hashlib").sha256(raw).hexdigest()


def resolve_agent_reference(snapshot: MemoSnapshot, value: Any, *, run_id: str) -> AgentBinding:
    """Decode a handle only against this run's active allocation commit with the same pinned configuration."""
    if not isinstance(value, Mapping) or value.get("run_id") != run_id:
        raise MemoError("memo_inconsistent", "agent reference does not belong to this run")
    commit = snapshot.active_commits.get(value.get("identity"))
    if commit is None or commit.data["effect_class"] != "agent" or commit.data["value"] != dict(value):
        raise MemoError("memo_inconsistent", f"agent reference has no matching active allocation: {value.get('identity')!r}")
    return AgentBinding(value["identity"], run_id, value["provider"], dict(value["policy"]), value["config_digest"])


@dataclass(frozen=True)
class Receipt:
    run_id: str
    agent: str
    turn: str
    attempt: int
    predecessor: str | None
    input_digest: str
    adapter: str
    config_digest: str
    mode: str
    locator: str | None
    pgid: int | None
    leader_start_time: int | None    # R3: /proc/<pgid>/stat field 22 at `launching`; quiesce never signals a leader with a different one
    position_before: dict | None
    position_after: dict | None
    completion: str
    result_digest: str | None
    schema: str = RECEIPT_SCHEMA


def write_receipt(files: WorkspaceFiles, receipt: Receipt) -> None:
    files.write_atomic("receipt.json", canonical_json_bytes(asdict(receipt)))


def read_receipt(files: WorkspaceFiles) -> Receipt | None:
    try:
        raw = files.read("receipt.json")
    except FileNotFoundError:
        return None
    try:
        row = json.loads(raw)
        if row.pop("schema") != RECEIPT_SCHEMA:
            raise ValueError("unknown receipt schema")
        return Receipt(**row, schema=RECEIPT_SCHEMA)
    except (ValueError, TypeError, KeyError) as exc:
        raise MemoError("memo_inconsistent", f"agent turn receipt is unreadable: {exc}") from exc
```

Wiring: `runtime.execute_pure_run` gate set → `{"command", "provider", "run_ref", "agent", "agent_turn"}`; `effect_inputs._resolve_effect_input` adds `elif node["class"] == "agent": resolved, parts = resolve_allocation_input(node, operands); implementation_files = {}`; `effect_execution.perform_external` adds `if node['class'] == 'agent': return perform_allocation(attempt)`; `runtime._validate_attempt_outcome` adds `if attempt.node['class'] == 'agent': result, digest = allocation_result(attempt); return result, digest, None, None`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_evaluated_agent_allocation.py tests/test_workflow_evaluated_invalidate_smoke.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow/evaluated/agent_sessions.py tests/test_workflow_evaluated_agent_allocation.py
git commit -m "feat: commit agent allocations as runtime-owned descriptors and add turn receipts" -- orchestrator/workflow/evaluated/agent_sessions.py orchestrator/workflow/evaluated/runtime.py orchestrator/workflow/evaluated/effect_execution.py orchestrator/workflow/evaluated/effect_inputs.py tests/test_workflow_evaluated_agent_allocation.py
```

---

### Task 10: The agent-turn coordinator: clean two-agent interleaving

**Files:**
- Create: `orchestrator/workflow/evaluated/agent_turns.py`
- Create: `orchestrator/workflow/evaluated/resume_prefix.py` (moves the read-only helpers `_replay_resume_prefix`, `_prepare_parallel_recovery`, `_validate_discovered_prefix`, `_resume_refusal`, `_replayed_halt_result` out of `runtime.py:186-250`; `runtime.py` imports them back under the same names; none of them appends a record, so every existing `runtime.append_record` hook is untouched)
- Modify: `orchestrator/workflow/evaluated/runtime.py` (`execute_pure_run:80-85` handler gate and executor creation for `provider` **and** `agent_turn`; `prepare_effect:350` one dispatch line `if node['class'] == 'agent_turn': return agent_turns.prepare_agent_attempt(...)` placed after `_resolve_effect_input` and before the `started` row is built; `_reuse_reached_commit:365` one `agent_turn` branch; `finish_effect:385-420` settles any coordinator and honours `keep_pending`; `_validate_attempt_outcome:438` one `agent_turn` branch; `_append_effect_commit`, `_fail_started_effect`, `_append_failed_terminal_if_clear`, `_persist_completed_terminal` stay where they are)
- Modify: `orchestrator/workflow/evaluated/effect_inputs.py:93-118` (`agent_turn` → `resolve_turn_input(..., committed_offset=None if commit is None else commit.offset)`), `:42-55` (`_replay_committed_effect` validates the turn proof), `:150-152` (`effect_dependencies` unchanged; the predecessor is added by `agent_turns.turn_dependencies`), `:117-130` untouched
- Modify: `orchestrator/workflow/evaluated/effect_execution.py` (`agent_turn` → `perform_turn`; `PreparedAttempt` gains `views: Any = None`, `recovered: bool = False`; `ExternalOutcome` gains `agent_turn: Any = None`)
- Modify: `orchestrator/workflow/evaluated/replay.py:70-105` (logical cursor: a reached `agent_turn` commit's `proof.predecessor` must equal the cursor head for `proof.agent`, then advances it; the cursor head is a legal entry of that commit's `depends_on` beside the operand dependencies)
- Create: `tests/test_workflow_evaluated_agent_turns.py`
- Modify (spec amendment): `specs/io.md:324-480` new bullet "Agent turn request and attempt files (target 2.38)" after "Provider request and attempt files"

**Interfaces:**
- Consumes: Plan A `launch_provider(session_request=..., observation_handle=...)`, `native_store_adapter`, `provider_delivery_name_for_template`; Task 9.
- Produces: the Task 10 names. `ResolvedTurn(agent: AgentBinding, predecessor: JournalEntry | None, provider: ResolvedProviderInput, provider_node: dict, template, adapter, input_parts: dict[str, str], delivery_name: str, pending: PendingTurn | None = None)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_agent_turns.py
"""Two agents, four typed turns: distinct native identities, predecessor lineage, exactly four dispatches."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_invalidate import _cli

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Draft (text String)) (defrecord Feedback (notes List[String]))
  (defprompt draft (:fills (task :text)) -> Draft "Draft: {task}")
  (defprompt review (:fills (text :text)) -> Feedback "Review: {text}")
  (defprompt revise (:fills (text :text) (notes :value List[String])) -> Draft "Revise: {text} {notes}")
  (defprompt execute (:fills (text :text)) -> Feedback "Execute: {text}")
  (defworkflow run ((task String)) -> Feedback
    (let* ((designer (agent providers.claude :model "planner" :effort "high"))
           (reviewer (agent providers.codex :model "reviewer" :effort "high"))
           (a1 (provider-result designer :prompt (draft :task task) :timeout-sec 60))
           (b1 (provider-result reviewer :prompt (review :text a1.text) :timeout-sec 60))
           (a2 (provider-result designer :prompt (revise :text a1.text :notes b1.notes) :timeout-sec 60))
           (b2 (provider-result reviewer :prompt (execute :text a2.text) :timeout-sec 60)))
      b2)))'''

PLAN = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": "success", "result": {"text": "d2"}}],
        "codex": [{"mode": "success", "result": {"notes": ["n"]}}, {"mode": "success", "result": {"notes": ["done"]}}]}


def fixture(root: Path, source: str = SOURCE) -> list[str]:
    (root / "main.orc").write_text(source, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.claude": "claude_unrestricted_workspace", "providers.codex": "codex"}))
    return ["main.orc", "--source-root", str(root), "--provider-externs-file", "providers.json", "--input", "task=t"]


def memo_of(root: Path):
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    classes = site_classes(authority.program)
    return run_root, authority, classes, read_memo(authority.memo_path, classes)


def turns(memo, classes):
    return {i.rsplit("/ ", 1)[1]: c.data for i, c in memo.active_commits.items() if classes[i] == "agent_turn"}


def test_clean_run_commits_four_turns_on_two_native_sessions(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    run = _cli(tmp_path, "run", *fixture(tmp_path))
    assert run.returncode == 0, run.stderr
    run_root, _authority, classes, memo = memo_of(tmp_path)
    assert memo.terminal.data == {"record": "terminal", "outcome": "completed", "value": {"notes": ["done"]}}
    t = turns(memo, classes)
    assert set(t) == {"a1", "b1", "a2", "b2"}
    assert [t[k]["value"] for k in ("a1", "b1", "a2", "b2")] == [{"text": "d1"}, {"notes": ["n"]}, {"text": "d2"}, {"notes": ["done"]}]
    designer = t["a1"]["proof"]["agent"]; reviewer = t["b1"]["proof"]["agent"]
    assert designer.endswith("/ designer") and reviewer.endswith("/ reviewer")
    assert (t["a1"]["proof"]["predecessor"], t["a2"]["proof"]["predecessor"]) == (None, t["a1"]["identity"])
    assert (t["b1"]["proof"]["predecessor"], t["b2"]["proof"]["predecessor"]) == (None, t["b1"]["identity"])
    assert t["a1"]["proof"]["locator"] == t["a2"]["proof"]["locator"] != t["b1"]["proof"]["locator"] == t["b2"]["proof"]["locator"]
    assert t["a2"]["proof"]["position"]["end_line"] > t["a1"]["proof"]["position"]["end_line"]
    assert (t["a1"]["proof"]["adapter"], t["b1"]["proof"]["adapter"]) == ("claude_stream_json_stdout", "codex_exec_jsonl_stdout")
    # predecessor is a dependency even where the prompt does not consume it (b2 reads a2 only)
    assert t["b1"]["identity"] in t["b2"]["depends_on"] and designer in t["a1"]["depends_on"]
    for row in t.values():
        assert (row["identity"], row["attempt"]) in memo.settlements
    requests = shim_requests(tmp_path)
    assert [r["tool"] for r in requests] == ["claude", "codex", "claude", "codex"]
    assert requests[0]["session"] == requests[2]["session"] and "--resume" in requests[2]["argv"] and "--resume" not in requests[0]["argv"]
    assert requests[1]["session"] == requests[3]["session"] and "resume" in requests[3]["argv"]
    assert all("--model" in r["argv"] or "--model" in " ".join(r["argv"]) for r in requests)
    attempt = run_root / Path(t["a1"]["result_path"]).parent
    receipt = json.loads((attempt / "receipt.json").read_text())
    assert receipt["completion"] == "completed" and receipt["locator"] == t["a1"]["proof"]["locator"]
    assert receipt["position_after"] == t["a1"]["proof"]["position"] and receipt["result_digest"] == t["a1"]["result_digest"]
    assert receipt["pgid"] is not None and receipt["leader_start_time"] is not None       # launch facts recorded at bind (R3) ...
    assert receipt["config_digest"] == t["a1"]["proof"]["config_digest"]                    # ... and monotone: they survive completion


def test_input_parts_bind_agent_and_predecessor(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    _root, _authority, classes, memo = memo_of(tmp_path)
    t = turns(memo, classes)
    for name, row in t.items():
        assert {"agent", "predecessor", "declaration", "values", "policy", "params", "prompt", "dependency_rows", "delivery"} <= set(row["input_parts"])
    assert t["a1"]["input_parts"]["agent"] == t["a2"]["input_parts"]["agent"] != t["b1"]["input_parts"]["agent"]
    assert t["a1"]["input_parts"]["predecessor"] != t["a2"]["input_parts"]["predecessor"]


def test_completed_resume_is_readonly_and_dispatches_nothing(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    run_root, *_ = memo_of(tmp_path)
    before = {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"}
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    assert {p: p.read_bytes() for p in run_root.rglob("*") if p.is_file() and p.name != "run.lock"} == before
    assert len(shim_requests(tmp_path)) == 4


def test_receipt_updates_are_monotone(tmp_path) -> None:
    from orchestrator.workflow.evaluated.agent_sessions import Receipt, read_receipt, write_receipt
    from orchestrator.workflow.evaluated.agent_turns import update_receipt
    from orchestrator.workflow.evaluated.memo import MemoError
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    files = WorkspaceFiles(tmp_path)
    write_receipt(files, Receipt(run_id="r", agent="a", turn="t", attempt=1, predecessor=None, input_digest="sha256:" + "0" * 64,
                                 adapter="codex_exec_jsonl_stdout", config_digest="sha256:" + "0" * 64, mode="fresh", locator=None,
                                 pgid=None, leader_start_time=None, position_before=None, position_after=None, completion="intent", result_digest=None))
    update_receipt(files, completion="launching", pgid=4242, leader_start_time=77)
    done = update_receipt(files, locator="sess", position_after={"turn_id": "t", "end_line": 9}, completion="completed")
    assert (done.pgid, done.leader_start_time, done.locator, done.completion) == (4242, 77, "sess", "completed")   # launch facts survive later writes
    assert (read_receipt(files).pgid, read_receipt(files).leader_start_time) == (4242, 77)
    with pytest.raises(MemoError, match="memo_inconsistent"):
        update_receipt(files, completion="intent")                                          # never backwards
    files.close()


def test_policy_mismatch_refuses_before_dispatch(tmp_path, monkeypatch) -> None:
    from orchestrator.workflow.evaluated.agent_sessions import AgentBinding
    from orchestrator.workflow.evaluated.agent_turns import AgentTurnError, check_origins
    with pytest.raises(AgentTurnError) as excinfo:
        check_origins({"origins": ["codex"]}, AgentBinding("x", "r", "claude_unrestricted_workspace", {}, "sha256:" + "0" * 64))
    assert excinfo.value.code == "agent_policy_mismatch"


# Kill-free seam: the executor has bound the child (receipt `launching`) and the CLI completed normally; completion
# verification then raises an exception the coordinator does not map. Task 11 reuses this driver for the resume half.
BROKEN_VERIFY = r'''import os, sys
from orchestrator.workflow.evaluated import agent_turns
verify = agent_turns._verify_completion
def broken(attempt, resolved, session_id, before):
    if attempt.identity.endswith(os.environ["BROKEN_TURN"]):
        raise OSError("disk hiccup after launch")
    return verify(attempt, resolved, session_id, before)
agent_turns._verify_completion = broken
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


def test_unmapped_exception_after_launch_keeps_started_pending_as_unresolved(tmp_path, monkeypatch) -> None:
    """Design failure table row 3: once the child is bound, an exception the coordinator does not map is an unknown
    append/completion outcome, not a failed attempt: tail = pending `started`, no `failed`, no terminal, receipt `unknown`
    with its launch facts, public exit 1 with `agent_turn_unresolved`."""
    import os, subprocess, sys
    from tests.workflow_evaluated_consumer_sources import ROOT
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    run = subprocess.run([sys.executable, "-c", BROKEN_VERIFY, "run", *fixture(tmp_path)], cwd=tmp_path, capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "BROKEN_TURN": "/ a2"})
    assert run.returncode == 1 and "agent_turn_unresolved" in run.stderr, run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    tail = memo.entries[-1].data
    assert tail["record"] == "started" and tail["identity"].endswith("/ a2") and tail["identity"] in memo.pending_starts
    assert memo.terminal is None and not any(e.data["record"] == "failed" for e in memo.entries)
    t = turns(memo, classes)
    assert set(t) == {"a1", "b1"}
    receipt = json.loads((run_root / Path(tail["result_path"]).parent / "receipt.json").read_text())
    assert receipt["completion"] == "unknown"                                               # uncertainty, never `not_dispatched`
    assert receipt["pgid"] is not None and receipt["locator"] == t["a1"]["proof"]["locator"]  # launch facts kept for resume
    assert [r["tool"] for r in shim_requests(tmp_path)] == ["claude", "codex", "claude"]


# Kill-free seam for design row 6: the adapter confirmed completion (receipt `completed`) and the typed result validated;
# the prepared-proof write (`update_receipt(result_digest=...)`, the only update carrying just that key) then raises.
BROKEN_PROJECT = r'''import os, sys
from orchestrator.workflow.evaluated import agent_turns
update = agent_turns.update_receipt
def broken(files, **changes):
    if set(changes) == {"result_digest"} and agent_turns.read_receipt(files).turn.endswith(os.environ["BROKEN_TURN"]):
        raise OSError("disk hiccup while projecting the result")
    return update(files, **changes)
agent_turns.update_receipt = broken
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


def test_unmapped_exception_during_projection_keeps_started_pending_with_a_completed_receipt(tmp_path, monkeypatch) -> None:
    """Design failure table row 6: native completion confirmed, interrupted before the prepared proof -> `started` stays
    pending and the receipt stays `completed` (not `unknown`, no `failed`, no terminal); only an invalid typed result
    may close `failed`. Resume recovers this ordinal (Task 11)."""
    import os, subprocess, sys
    from tests.workflow_evaluated_consumer_sources import ROOT
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    run = subprocess.run([sys.executable, "-c", BROKEN_PROJECT, "run", *fixture(tmp_path)], cwd=tmp_path, capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "BROKEN_TURN": "/ a2"})
    assert run.returncode == 1 and "agent_turn_unresolved" in run.stderr, run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    tail = memo.entries[-1].data
    assert tail["record"] == "started" and tail["identity"].endswith("/ a2") and tail["identity"] in memo.pending_starts
    assert memo.terminal is None and not any(e.data["record"] == "failed" for e in memo.entries)
    receipt = json.loads((run_root / Path(tail["result_path"]).parent / "receipt.json").read_text())
    assert receipt["completion"] == "completed" and receipt["result_digest"] is None      # completion kept; proof not yet durable
    assert receipt["position_after"] is not None and receipt["pgid"] is not None
    assert len(shim_requests(tmp_path)) == 3


REGISTRY_SWAP = r'''import sys
from orchestrator.providers import registry as registry_module
from orchestrator.providers.types import ProviderTemplate
load = registry_module.ProviderRegistry._load_builtin_providers
def swapped(self):
    templates = load(self)
    codex = templates["codex"]
    templates["codex"] = ProviderTemplate(**{**codex.__dict__, "defaults": {**codex.defaults, "reasoning_effort": "low"}})
    return templates
registry_module.ProviderRegistry._load_builtin_providers = swapped
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


@pytest.mark.skipif(not __import__("importlib").util.find_spec("tests.test_workflow_evaluated_agent_turn_recovery"), reason="kill-point drivers land in Task 11")
def test_template_change_between_run_and_resume_refuses_agent_policy_mismatch(tmp_path, monkeypatch) -> None:
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECORD, _stopped
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": "settled", "STOP_TURN": "/ a1"}, "run", *fixture(tmp_path))
    run_root, *_ = memo_of(tmp_path)
    import os, subprocess, sys
    from tests.workflow_evaluated_consumer_sources import ROOT
    resumed = subprocess.run([sys.executable, "-c", REGISTRY_SWAP, "resume", run_root.name], cwd=tmp_path, capture_output=True, text=True,
                             env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})
    assert resumed.returncode == 1 and "agent_policy_mismatch" in resumed.stderr      # reviewer b1 refused before dispatch
    assert [r["tool"] for r in shim_requests(tmp_path)] == ["claude"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_evaluated_agent_turns.py -q`
Expected: FAIL — `ModuleNotFoundError: agent_turns`; the run exits 1 at the first `agent_turn` (no branch in `_resolve_effect_input`).

- [ ] **Step 3: Implement the coordinator**

```python
# orchestrator/workflow/evaluated/agent_turns.py
"""One bounded coordinator for sequential native-session turns on a run-local agent (K2/K3 shape)."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping

from orchestrator.providers.control import ProviderExecutionControl
from orchestrator.providers.native_store import NativePosition, NativeStoreError, native_store_adapter
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import ProviderSessionMode, ProviderSessionRequest
from orchestrator.workflow.evaluated.commands import workspace_relative_path
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256

from orchestrator.workflow.workspace_files import WorkspaceFiles
from pathlib import Path

from .agent_sessions import AgentBinding, Receipt, read_receipt, resolve_agent_reference, write_receipt
from .authority import _require_retained_root
from .memo import MemoError, append_record, read_memo
from .providers import ProviderPerformerError, launch_provider, provider_delivery_name_for_template, provider_result, resolve_provider_input


logger = logging.getLogger(__name__)


class AgentTurnError(RuntimeError):
    def __init__(self, code, message, *, exit_info=None, violations=None, keep_pending=False):
        super().__init__(message)
        self.code, self.exit_info, self.violations, self.keep_pending = code, exit_info, violations, keep_pending


@dataclass(frozen=True)
class ResolvedTurn:
    agent: AgentBinding
    predecessor: Any            # JournalEntry | None
    provider: Any               # ResolvedProviderInput
    provider_node: dict
    template: Any
    adapter: Any
    input_parts: dict
    delivery_name: str
    pending: Any = None         # PendingTurn | None (Task 11), set with dataclasses.replace


def leader_start_time(pid: int) -> int | None:
    """Start time (clock ticks since boot) of `pid`: field 22 of `/proc/<pid>/stat`, parsed as
    `scripts/experiments/native_session_cli_process.py::_process_table` does (split after the last `)` so a command
    name containing spaces or parentheses cannot shift the fields). `None` when the pid has no `/proc` entry (the
    process is gone, or the platform has no `/proc`), so callers fall back to process-group liveness alone."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except OSError:
        return None
    fields = raw[raw.rfind(")") + 2:].split()
    return int(fields[19]) if len(fields) >= 20 else None


class AgentTurnControl(ProviderExecutionControl):
    """Records the child's process group and its leader's start time in the receipt the moment the executor binds it
    (quiescence evidence: the pair identifies the group across a pgid reuse, R3)."""

    def __init__(self, attempt_files, receipt: Receipt) -> None:
        super().__init__()
        self._attempt_files, self._receipt = attempt_files, receipt

    def bind(self, process, pgid: int) -> None:
        update_receipt(self._attempt_files, completion="launching", pgid=pgid, leader_start_time=leader_start_time(pgid))
        super().bind(process, pgid)


def check_origins(node, agent: AgentBinding, template=None, launch_cwd=None) -> None:
    if agent.provider not in node["origins"]:
        raise AgentTurnError("agent_policy_mismatch",
                             f"agent provider {agent.provider!r} is outside the checked origins {node['origins']}")
    if template is not None:
        from .agent_sessions import pinned_config_digest
        current = pinned_config_digest(template, agent.policy, launch_cwd)
        if current != agent.config_digest:
            raise AgentTurnError("agent_policy_mismatch",
                                 f"provider template or defaults changed since allocation ({agent.config_digest} -> {current})")


def predecessor_commit(snapshot, agent_identity: str, *, before_offset: int | None = None):
    """The latest active committed turn of this agent in journal order (single writer => evaluation order).

    Replay passes `before_offset` (the replayed commit's offset): an old turn is checked against its
    historical predecessor, never against turns committed after it (the logical cursor).
    """
    turns = [c for c in snapshot.active_commits.values()
             if c.data["effect_class"] == "agent_turn" and c.data["proof"]["agent"] == agent_identity
             and (before_offset is None or c.offset < before_offset)]
    return max(turns, key=lambda c: c.offset, default=None)


def provider_view(node, agent: AgentBinding) -> dict:
    """The checked turn node seen as a provider node, so prompt/result owners stay unchanged."""
    return {**{k: v for k, v in node.items() if k not in {"agent", "origins"}}, "class": "provider",
            "provider": agent.provider, "policy": {**agent.policy, **node["policy"]}}


def resolve_turn_input(authority, node, operands, identity, workspace, reader, *, snapshot, result_path, launch_cwd,
                       committed_offset: int | None = None) -> ResolvedTurn:
    """`committed_offset` is the replayed commit's offset (replay and reuse paths): the predecessor is then the
    agent's latest turn committed *before* it, never a later one (the logical cursor)."""
    agent = resolve_agent_reference(snapshot, operands[0].json_value(), run_id=authority.header["run_id"])
    template = ProviderRegistry().get(agent.provider)
    if template is None or template.session_support is None:
        raise AgentTurnError("agent_session_unavailable", f"provider {agent.provider!r} has no session_support")
    check_origins(node, agent, template, launch_cwd)
    adapter = native_store_adapter(template.session_support.metadata_mode)
    if adapter is None:
        raise AgentTurnError("agent_session_unavailable", f"no native store adapter for {template.session_support.metadata_mode!r}")
    view = provider_view(node, agent)
    delivery = provider_delivery_name_for_template(template)
    provider = resolve_provider_input(view, operands[1:], workspace=workspace, reader=reader,
                                      result_path=workspace_relative_path(workspace, authority.run_root / result_path),
                                      delivery_name=delivery, logical_workspace=launch_cwd is not None)
    predecessor = predecessor_commit(snapshot, agent.identity, before_offset=committed_offset)
    continuation = None if predecessor is None else {"turn": predecessor.data["identity"], "proof": predecessor.data["proof"]}
    parts = {**provider.input_parts, "agent": canonical_sha256(agent.record()), "predecessor": canonical_sha256(continuation)}
    return ResolvedTurn(agent, predecessor, provider, view, template, adapter, parts, delivery)


def turn_dependencies(resolved: ResolvedTurn, operand_dependencies) -> tuple[str, ...]:
    """The predecessor is a dependency even when the prompt does not consume its result (design, Identity)."""
    extra = () if resolved.predecessor is None else (resolved.predecessor.data["identity"],)
    return tuple(sorted(set(operand_dependencies) | set(extra)))


def _head_or_refuse(resolved: ResolvedTurn):
    """D1: before an append, the native head must equal the recorded committed position of the predecessor."""
    if resolved.predecessor is None:
        return None, None
    proof = resolved.predecessor.data["proof"]
    located = resolved.adapter.locate(proof["locator"])
    if located.path is None:
        raise AgentTurnError("agent_session_unavailable",
                             f"native session {proof['locator']!r} is {'ambiguous' if located.ambiguous else 'missing'}")
    try:
        head = resolved.adapter.head(located.path)
    except NativeStoreError as exc:
        raise AgentTurnError("agent_session_unavailable", str(exc)) from exc
    expected = NativePosition.from_record(proof["position"])
    if head.open_turn or head.position != expected:
        raise AgentTurnError("agent_session_diverged",
                             f"native head {head.position} differs from the recorded position {expected} of {resolved.predecessor.data['identity']}")
    return proof["locator"], expected


def prepare_agent_attempt(authority, node, operands, identity, snapshot, *, ordinal, attempt_directory, result_path,
                          resolved: ResolvedTurn, parts, implementation_files, dependencies, context):
    """All agent-turn start decisions, behind one dispatch line in `runtime.prepare_effect`.

    Order: start-order check -> pending-turn classification (Task 11: recover / bootstrap / refuse) -> D1 head check
    -> `started` + exclusive attempt directory through `allocate_attempt` (so the kill-point hooks on
    `attempts.append_record` fire exactly as for every other class).
    """
    from .attempts import allocate_attempt
    from .effect_execution import PreparedAttempt
    import time
    if [i for i in snapshot.pending_starts if i != identity]:
        raise MemoError("memo_inconsistent", f"another effect is pending while starting {identity}")
    pending = snapshot.pending_starts.get(identity)
    if pending is not None:                                   # Task 11 fills this branch
        return _prepare_pending(authority, node, identity, snapshot, pending, resolved, context)
    _head_or_refuse(resolved)
    started = dict(record="started", identity=identity, attempt=ordinal, input_digest=canonical_sha256(parts), input_parts=parts,
                   implementation_files=implementation_files, result_path=result_path, time=time.time())
    _require_retained_root(context["run_files"])
    attempt_files = allocate_attempt(context["run_files"], authority.memo_path, started, checked_authority=authority)
    return PreparedAttempt(authority, node, identity, ordinal, result_path, started["input_digest"], parts, implementation_files,
                           turn_dependencies(resolved, dependencies), resolved, context["workspace"], context["workspace_files"],
                           context["site_classes"], context["provider_executor"], attempt_files, context.get("launch_cwd"),
                           context.get("stream_output", False), views=context.get("views"))


def _prepare_pending(authority, node, identity, snapshot, pending, resolved, context):
    raise AgentTurnError("agent_turn_unresolved", f"{identity}: pending attempt {pending.data['attempt']} awaits Task 11 reconciliation", keep_pending=True)


def perform_turn(attempt, *, views=None):
    resolved: ResolvedTurn = attempt.resolved
    locator, before = _head_or_refuse(resolved)
    receipt = Receipt(run_id=attempt.authority.header["run_id"], agent=resolved.agent.identity, turn=attempt.identity,
                      attempt=attempt.ordinal, predecessor=None if resolved.predecessor is None else resolved.predecessor.data["identity"],
                      input_digest=attempt.input_digest, adapter=resolved.adapter.metadata_mode, config_digest=resolved.agent.config_digest,
                      mode="resume" if locator else "fresh", locator=locator, pgid=None, leader_start_time=None,
                      position_before=None if before is None else before.record(), position_after=None,
                      completion="intent", result_digest=None)
    write_receipt(attempt.attempt_files, receipt)          # intent is durable before dispatch
    control = AgentTurnControl(attempt.attempt_files, receipt)   # writes `launching` + pgid + leader_start_time when the executor binds the child
    request = ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id=locator) if locator \
        else ProviderSessionRequest(mode=ProviderSessionMode.FRESH)
    path = workspace_relative_path(attempt.workspace, attempt.authority.run_root / attempt.result_path)
    handle = None if views is None else views.handle_for(resolved.agent.identity, attempt.identity, attempt.ordinal)
    from .effect_execution import ExternalOutcome
    try:
        execution = launch_provider(resolved.provider_node, resolved.provider, attempt.identity,
            executor=attempt.provider_executor, attempt_files=attempt.attempt_files, workspace_files=attempt.workspace_files,
            result_path=path, stream_output=attempt.stream_output, launch_cwd=attempt.launch_cwd,
            logical_workspace_root=attempt.workspace if attempt.launch_cwd is not None else None,
            session_request=request, observation_handle=handle, control=control)
        session_id = (execution.provider_session or {}).get("session_id") or locator
        turn = _verify_completion(attempt, resolved, session_id, before)   # reads the stored receipt (with pgid) itself
    except ProviderPerformerError as exc:
        raise _unresolved_or_failed(attempt, read_receipt(attempt.attempt_files), exc) from exc
    except AgentTurnError:
        raise                                               # already classified: unresolved (keep_pending), unavailable, diverged
    except Exception as exc:
        # Design failure table row 3: once the executor bound a child, an exception this module does not map is an
        # unknown append/completion outcome. Keep `started` pending (no `failed`, no terminal); resume classifies from
        # the receipt and the native store. Before `launching` no child was spawned, so the ordinary failure path is kept.
        stored = read_receipt(attempt.attempt_files)
        if stored is None or stored.completion == "intent":
            raise
        raise _unresolved(attempt, stored.locator or _session_from_stdout(attempt),
                          f"{type(exc).__name__} after launch: {exc}") from exc
    return ExternalOutcome(result_path=path, agent_turn=turn)


def _verify_completion(attempt, resolved, session_id, before):
    located = resolved.adapter.locate(session_id) if session_id else None
    if located is None or located.path is None:
        raise _unresolved(attempt, session_id, "native session has no unique store after dispatch")
    marker = attempt.result_path.rsplit("/", 1)[0] + "/"   # "effects/<digest>/attempt-N/": the trailing slash keeps attempt-1 from matching attempt-10
    try:
        turn = resolved.adapter.completed_turn(located.path, after=before, prompt_marker=marker)
    except NativeStoreError as exc:
        raise _unresolved(attempt, session_id, str(exc))
    if turn is None:
        raise _unresolved(attempt, session_id, "native store does not show exactly one completed turn for this attempt")
    update_receipt(attempt.attempt_files, locator=session_id, position_after=turn.position.record(), completion="completed")
    return turn


def _unresolved(attempt, locator, detail):
    update_receipt(attempt.attempt_files, locator=locator, completion="unknown")
    return AgentTurnError("agent_turn_unresolved", f"{attempt.identity}: {detail}", keep_pending=True)


def _unresolved_or_failed(attempt, receipt, exc: ProviderPerformerError):
    """Design failure table rows 3 and 4: only the adapter can prove non-dispatch; exit codes and stdout never do."""
    resolved: ResolvedTurn = attempt.resolved
    if exc.code == "provider_preparation_failed" and receipt.completion == "intent":
        update_receipt(attempt.attempt_files, completion="not_dispatched")
        return exc                                       # no child was ever spawned (no `launching`)
    if receipt.mode == "resume":
        located = resolved.adapter.locate(receipt.locator)
        if located.path is not None:
            try:
                head = resolved.adapter.head(located.path)
            except NativeStoreError as err:
                return _unresolved(attempt, receipt.locator, str(err))
            before = NativePosition.from_record(receipt.position_before)
            if not head.open_turn and head.position == before:
                update_receipt(attempt.attempt_files, completion="not_dispatched")
                return exc                               # adapter proves the existing conversation did not advance
        return _unresolved(attempt, receipt.locator, f"{exc.code}: the native head advanced, is open, or cannot be read")
    # fresh turn: a locator only exists if the CLI got far enough to create a conversation
    locator = _session_from_stdout(attempt)
    if locator is None:
        return _unresolved(attempt, None, f"{exc.code} on a fresh turn with no locator: uncertainty, not proof of non-dispatch")
    return _unresolved(attempt, locator, f"{exc.code} after a fresh conversation {locator!r} was created")


def _session_from_stdout(attempt) -> str | None:
    try:
        text = attempt.attempt_files.read("stdout.txt").decode("utf-8", "replace")
    except FileNotFoundError:
        return None
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        for key in ("session_id", "thread_id"):
            if isinstance(row.get(key), str):
                return row[key]
    return None


_COMPLETION_ORDER = {"intent": 0, "launching": 1, "not_dispatched": 2, "unknown": 2, "completed": 2, "abandoned": 3}


def update_receipt(attempt_files, **changes) -> Receipt:
    """Monotone receipt update: start from the stored receipt (never a stale in-memory copy), keep every field that is
    already set unless the change explicitly provides a value, and never move `completion` backwards."""
    from dataclasses import replace
    current = read_receipt(attempt_files)
    if current is None:
        raise MemoError("memo_inconsistent", "receipt update without a stored receipt")
    merged = {k: v for k, v in changes.items() if v is not None or getattr(current, k) is None}
    if "completion" in merged and _COMPLETION_ORDER[merged["completion"]] < _COMPLETION_ORDER[current.completion]:
        raise MemoError("memo_inconsistent", f"receipt completion cannot go from {current.completion} to {merged['completion']}")
    updated = replace(current, **merged)
    write_receipt(attempt_files, updated)
    return updated


def _replace(receipt: Receipt, **changes) -> Receipt:
    from dataclasses import replace
    return replace(receipt, **changes)


def project_turn(attempt, outcome):
    """Typed-result projection after adapter-confirmed completion (receipt `completed`).

    Only a conclusively invalid typed result closes the attempt `failed` (design: "permanently ineligible for
    same-attempt recovery"). Any other exception here is an interruption before the prepared proof (failure table
    row 6): `started` stays pending, the receipt stays `completed`, and resume recovers the same ordinal from the
    receipt and the native store without redispatch (Task 11 `recoverable`).
    """
    resolved: ResolvedTurn = attempt.resolved
    try:
        result, digest = provider_result(resolved.provider_node, resolved.provider, attempt.attempt_files,
                                         attempt.workspace_files, outcome.result_path)
        receipt = update_receipt(attempt.attempt_files, result_digest=digest)  # the prepared proof is durable here; pgid/locator kept
        proof = {"adapter": resolved.adapter.metadata_mode, "locator": receipt.locator, "position": outcome.agent_turn.position.record(),
                 "predecessor": receipt.predecessor, "agent": resolved.agent.identity, "config_digest": resolved.agent.config_digest}
    except ProviderPerformerError as exc:                   # conclusively invalid typed result: the one path that closes `failed`
        code = "provider_result_invalid" if resolved.predecessor is None else "agent_turn_result_invalid"
        raise AgentTurnError(code, str(exc), exit_info=exc.exit_info, violations=exc.violations) from exc
    except Exception as exc:                                # row 6: interrupted before the prepared proof; receipt left at `completed`
        raise AgentTurnError("agent_turn_unresolved", f"{attempt.identity}: {type(exc).__name__} during projection: {exc}",
                             keep_pending=True) from exc
    return result, digest, proof, proof


def settle_turn(authority, resolved, identity, attempt, workspace, site_classes, prepared, committed) -> None:
    """Settlement is local bookkeeping: confirm the commit is active, then append `settled`."""
    _require_retained_root(authority.run_files)
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    commit = snapshot.active_commits.get(identity)
    if commit is None or canonical_json_bytes(commit.data) != canonical_json_bytes(committed):
        raise MemoError("memo_inconsistent", "active agent turn commit disagrees before settlement")
    append_record(authority.memo_path, {"record": "settled", "identity": identity, "attempt": attempt, "by": "settle"},
                  run_files=authority.run_files, checked_authority=authority)


def validate_turn(authority, resolved: ResolvedTurn, identity, commit, *, settled) -> None:
    """Replay: the committed proof must agree with the resolved agent and recorded predecessor; no native read."""
    proof = commit.data["proof"]
    expected_predecessor = None if resolved.predecessor is None else resolved.predecessor.data["identity"]
    if proof["agent"] != resolved.agent.identity or proof["predecessor"] != expected_predecessor \
            or proof["adapter"] != resolved.adapter.metadata_mode or proof["config_digest"] != resolved.agent.config_digest:
        raise MemoError("memo_inconsistent", f"agent turn proof of {identity} disagrees with its replayed agent or predecessor")


def reconcile_turn(authority, resolved, identity, commit, site_classes) -> None:
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    if (identity, commit.data["attempt"]) in snapshot.settlements:
        return
    validate_turn(authority, resolved, identity, commit, settled=False)
    append_record(authority.memo_path, {"record": "settled", "identity": identity, "attempt": commit.data["attempt"], "by": "reconcile"},
                  run_files=authority.run_files, checked_authority=authority)
```

Runtime wiring (`runtime.py`, one line per site; the read-only helpers move to `resume_prefix.py` first so the file ends near 440 lines):
- `execute_pure_run:80-85`: gate set `{"command", "provider", "run_ref", "agent", "agent_turn"}`; executor created lazily when `node["class"] in {"provider", "agent_turn"}` (M1).
- `prepare_effect`: `_resolve_effect_input` for `agent_turn` calls `resolve_turn_input(..., snapshot=snapshot, result_path=result_path, launch_cwd=launch_cwd, committed_offset=None if commit is None else commit.offset)` (pass `snapshot` through as a new keyword, default `None`, read anew when absent). After `dependencies = effect_dependencies(...)` and the commit-reuse return: `if node['class'] == 'agent_turn': return agent_turns.prepare_agent_attempt(authority, node, operands, identity, snapshot, ordinal=ordinal, attempt_directory=attempt_directory, result_path=result_path, resolved=resolved, parts=parts, implementation_files=implementation_files, dependencies=dependencies, context=dict(run_files=run_files, workspace=workspace, workspace_files=workspace_files, site_classes=site_classes, provider_executor=provider_executor, launch_cwd=launch_cwd, stream_output=stream_output, views=views))`. `prepare_effect` itself gains no branch beyond this line, so its complexity does not grow.
- `_reuse_reached_commit`: `elif node["class"] == "agent_turn": settled = (identity, commit.data["attempt"]) in snapshot.settlements; validate_turn(authority, resolved, identity, commit, settled=settled); if not settled: reconcile_turn(authority, resolved, identity, commit, site_classes)` (the `resolved` here came from `resolve_turn_input(..., committed_offset=commit.offset)`, I6).
- `_validate_attempt_outcome`: `if attempt.node['class'] == 'agent_turn': return agent_turns.project_turn(attempt, outcome)`.
- `finish_effect`: `if prepared is not None: settle = settle_evaluated_run_ref if node['class'] == 'run_ref' else agent_turns.settle_turn; settle(authority, attempt.resolved, attempt.identity, attempt.ordinal, attempt.workspace, attempt.site_classes, prepared, committed)` (same arity for both coordinators); in the `except Exception as exc` branch: `if getattr(exc, "keep_pending", False): raise` before `_fail_started_effect` (the start stays pending; `_append_failed_terminal_if_clear` then skips the terminal because `pending_starts` is non-empty). `finish_effect` reads no receipt: `perform_turn` turns every exception raised after the receipt reached `launching` into `AgentTurnError("agent_turn_unresolved", keep_pending=True)` (receipt `unknown`), and `project_turn` does the same for every exception other than the typed-result validation failure once the receipt is `completed` (receipt left at `completed`; design row 6, resume recovers the same ordinal); only an exception before `launching` (no child bound) or a conclusively invalid typed result reaches `_fail_started_effect`, as for `provider` effects. `committed["depends_on"] = list(attempt.dependencies)` already carries the predecessor because `prepare_agent_attempt` used `turn_dependencies` (I5).
- `effect_execution.perform_external`: `if node['class'] == 'agent_turn': return perform_turn(attempt, views=attempt.views)`.
- `effect_inputs._replay_committed_effect`: `dependencies = agent_turns.turn_dependencies(resolved, effect_dependencies(...))` for `agent_turn`, then `validate_turn(...)` after `_reuse_effect_commit`.
- `replay._Discovery.__call__`: for `agent_turn` commits compute `head = self.agent_cursor.get(proof["agent"])`, require `proof["predecessor"] == head` (`memo_inconsistent` otherwise), compare `commit.data['depends_on']` against `sorted(set(dependencies) | ({head} if head else set()))`, then `self.agent_cursor[proof["agent"]] = identity`.

- [ ] **Step 4: Amend `specs/io.md` (new bullet after "Provider request and attempt files")**

"Agent turn request and attempt files (target 2.38)": the request is the ordinary provider request of the agent's pinned template with `session_request` `fresh` (first turn) or `resume <locator>` (later turns), policy = the allocation's `model`/`effort` plus the turn's `timeout_sec`; environment and working directory as for providers. Resolved input parts are the provider parts plus `agent` (digest of the Agent descriptor, which carries the pinned configuration digest) and `predecessor` (digest of `{turn, proof}` of the previous committed turn of that agent, or of `null`); a template or default change since allocation refuses `agent_policy_mismatch` before `started`. The receipt records `launching` with the child's process group and the group leader's start time (`/proc/<pid>/stat` field 22) as soon as the executor binds it; any exception after that point keeps the `started` row pending (receipt `unknown` before the adapter confirmed completion, `completed` after it; resume reconciles the same ordinal without redispatch); only a conclusively invalid typed result closes the attempt `failed`. Before dispatch the runtime reads the native store head and refuses `agent_session_diverged`/`agent_session_unavailable`; it writes `receipt.json` (intent) before launch and updates it after completion; commit requires exact native completion bound to the attempt (the user message carrying the attempt path) and the ordinary typed-result validation. A result file alone is never a result. The delivery rendering is selected structurally from the template's metadata mode (`legacy` for OMP JSON, else `file/2`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workflow_evaluated_agent_turns.py tests/test_workflow_evaluated_agent_allocation.py tests/test_workflow_evaluated_invalidate_smoke.py tests/test_workflow_evaluated_run_ref_settlement.py tests/test_workflow_evaluated_verified_drain.py tests/test_workflow_evaluated_resume_kills.py tests/test_workflow_evaluated_parallel_failures.py -q`
Expected: PASS (the last three are the existing `runtime.append_record` hook regressions); `test_unmapped_exception_after_launch_keeps_started_pending_as_unresolved` passes with the driver's run exiting 1 and `agent_turn_unresolved` on stderr, the memo tail a pending `started` for `/ a2`, no `failed`/terminal row and the receipt at `unknown` with `pgid`/`locator` kept; `test_unmapped_exception_during_projection_keeps_started_pending_with_a_completed_receipt` likewise exits 1 with `agent_turn_unresolved`, tail a pending `started` for `/ a2`, no `failed`/terminal, receipt `completed` with `result_digest` null; `wc -l orchestrator/workflow/evaluated/runtime.py orchestrator/workflow/evaluated/resume_prefix.py orchestrator/workflow/evaluated/agent_turns.py` about 440, 90, 395; the stdlib complexity check (Global Constraints) prints `complexity ok`.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow/evaluated/agent_turns.py orchestrator/workflow/evaluated/resume_prefix.py tests/test_workflow_evaluated_agent_turns.py
git commit -m "feat: coordinate sequential native-session turns on run-local agents" -- orchestrator/workflow/evaluated/agent_turns.py orchestrator/workflow/evaluated/resume_prefix.py orchestrator/workflow/evaluated/runtime.py orchestrator/workflow/evaluated/effect_inputs.py orchestrator/workflow/evaluated/effect_execution.py orchestrator/workflow/evaluated/replay.py specs/io.md tests/test_workflow_evaluated_agent_turns.py
```

---

### Task 9b: Runtime carriage proofs — factories, branch-selected aliases, reuse inside loops

**Files:**
- Create: `tests/test_workflow_evaluated_agent_composition.py`

**Interfaces:**
- Consumes: Task 10 coordinator (this task runs after Task 10; it is numbered 9b because it proves identity rules from the design's Identity table and position rows 1–4 at runtime).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_agent_composition.py
"""Factory calls with equal inputs are two agents; a branch-selected alias is one; an outside agent is reused inside a loop."""
from __future__ import annotations

import json

import pytest

from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_agent_turns import memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Note (text String))
  (defprompt ask (:fills (task :text)) -> Note "Task: {task}")
  (defproc make ((model String)) -> Agent (agent providers.codex :model model :effort "low"))
  (defproc turn ((who Agent) (task String)) -> Note (provider-result who :prompt (ask :task task) :timeout-sec 60))
  (defworkflow run ((task String) (pick Bool)) -> Note
    (let* ((one (make "m"))
           (two (make "m"))
           (chosen (if pick one two))
           (first (turn chosen task))
           (looped (loop/recur :max 3 (loop-state (i Int 0) (last String first.text))
                     (if (>= i 2) (done (Note :text last))
                         (let* ((n (turn one last))) (continue (+ i 1) n.text)))))
           (second (turn two looped.text)))
      second)))'''

PLAN = {"codex": [{"mode": "success", "result": {"text": f"t{i}"}} for i in range(5)], "claude": []}


def _run(tmp_path, monkeypatch, pick):
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    (tmp_path / "main.orc").write_text(SOURCE); (tmp_path / "providers.json").write_text(json.dumps({"providers.codex": "codex"}))
    run = _cli(tmp_path, "run", "main.orc", "--source-root", str(tmp_path), "--provider-externs-file", "providers.json",
               "--input", "task=t", "--input", f"pick={pick}")
    assert run.returncode == 0, run.stderr
    return memo_of(tmp_path)


@pytest.mark.parametrize("pick", ["true", "false"])
def test_two_factory_agents_two_sessions_and_branch_alias_selects_one(tmp_path, monkeypatch, pick) -> None:
    _root, _a, classes, memo = _run(tmp_path, monkeypatch, pick)
    allocations = sorted(i for i, c in memo.active_commits.items() if c.data["effect_class"] == "agent")
    assert len(allocations) == 2 and allocations[0] != allocations[1]          # equal inputs, two identities (frames differ)
    t = turns(memo, classes)
    agents_by_turn = {k: v["proof"]["agent"] for k, v in t.items()}
    one = next(i for i in allocations if i.endswith("/ one")); two = next(i for i in allocations if i.endswith("/ two"))
    assert agents_by_turn[next(k for k in t if k.endswith("first") or "first" in k)] == (one if pick == "true" else two)
    sessions = {r["session"] for r in shim_requests(tmp_path)}
    assert len(sessions) == 2                                                   # exactly two native conversations
    loop_turns = sorted((v for k, v in t.items() if "loop:" in v["identity"]), key=lambda v: v["proof"]["position"]["end_line"])
    assert len(loop_turns) == 2 and all(v["proof"]["agent"] == one for v in loop_turns)
    assert loop_turns[1]["proof"]["predecessor"] == loop_turns[0]["identity"]  # outside agent reused across iterations, in order
    if pick == "true":
        assert loop_turns[0]["proof"]["predecessor"].endswith("first") or loop_turns[0]["proof"]["predecessor"] in agents_by_turn
```

- [ ] **Step 2: Run the test to verify it fails before Task 10 lands and passes after** — `pytest tests/test_workflow_evaluated_agent_composition.py -q`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_workflow_evaluated_agent_composition.py
git commit -m "test: prove agent factories, branch aliases and loop reuse at runtime" -- tests/test_workflow_evaluated_agent_composition.py
```

---

### Task 11: Pending-turn recovery: `agent_turn_unresolved` keeps `started`, resume reconciles the same ordinal

**Files:**
- Modify: `orchestrator/workflow/evaluated/agent_turns.py` (add `PendingTurn`, `quiesce`, `classify_pending_turn`, `recover_pending_turn`; fill `_prepare_pending`)
- Modify: `orchestrator/workflow/evaluated/effect_inputs.py:58-90` (`_check_resume_boundary`: `agent_turn` with a pending start classifies read-only; `unresolved` refuses with `agent_turn_unresolved` at preflight)
- Modify: `orchestrator/workflow/evaluated/runtime.py` (`_start_and_perform_effect`: `outcome = agent_turns.recover_pending_turn(attempt) if attempt.recovered else perform_external(attempt)` — the only line this task adds to `runtime.py`)
- Create: `tests/test_workflow_evaluated_agent_turn_recovery.py`
- Modify (spec amendment): `specs/cli.md` "Resume preflight precedence" (`:368-400`): new step after 7 — "an agent turn with a pending start is classified from its receipt and the native store: `recoverable` (completion and intact valid result) is committed at the same ordinal without dispatch; `not_dispatched` allocates the next attempt; `unresolved` refuses `agent_turn_unresolved` after the agent's first committed turn and takes the bootstrap path (Task 12) before it; `agent_turn_result_invalid` refuses"; `docs/design/workflow_lisp_evaluated_execution.md` §8.1 table (`:1381`): add a row "A `started` agent turn with no commit | Classify from receipt and native store (Agent Sessions, Persistence); never the generic retry rule" and §9.3.1 paragraph at `:2706-2717` replace "are a later proposal, not admitted by this design's first release" with "are admitted at target 2.38 with the scoped K4 exception below".

**Interfaces:**
- Produces: `PendingTurn(disposition, receipt, native_turn, detail)`; `quiesce(receipt, *, probe_only=False) -> "quiescent" | "alive" | "unprovable"`; `classify_pending_turn(authority, node, identity, snapshot, workspace, resolved, *, probe_only=False) -> PendingTurn`; `recover_pending_turn(attempt) -> ExternalOutcome`. Classification follows the design's failure table literally: `not_dispatched` only when the receipt is absent, still `intent` (no `launching`: the executor never bound a child), or the adapter proves the predecessor head unchanged and closed; `recoverable` when the store shows exactly one completed turn bound to this attempt and `result.json` exists; otherwise uncertainty — `bootstrap` for an agent with no committed turn, `unresolved` after one. Quiescence comes first (design: "quiesce it through existing cleanup before reconciliation or append; inability to prove it stopped is `agent_turn_unresolved`"): the read-only preflight (`probe_only=True`) only probes the recorded process group and classifies a live group as `needs_quiescence` (admitted, not refused); under the writer lock `_prepare_pending` runs the real `quiesce` (probe → `SIGTERM` → grace → `SIGKILL` → empty-group check) and re-classifies; only `"unprovable"` is `unresolved`. R3 (pgid reuse): before any probe or signal, `quiesce` compares `leader_start_time(receipt.pgid)` with the start time the receipt recorded at `launching`; a live leader with a different start time is an unrelated process that received the number after our group was gone (Linux keeps a pid reserved while any member of the process group it names is alive), so the turn is `"quiescent"` and nothing is signalled. A leader with no `/proc` entry proves nothing about lingering members, so the group probe and signals proceed as before (the `linger` case). An exec-replaced leader with an identical start time is still signalled (accepted by R3).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_agent_turn_recovery.py
"""Unresolved turns keep `started` pending; resume commits a completed native turn at the same ordinal with zero redispatch."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.memo import read_memo
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


def _stopped(root, script, env, *argv):
    done = subprocess.run([sys.executable, "-c", script, *argv], cwd=root, check=False, capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", **env})
    assert done.returncode == 75, done.stderr
    return done


def _install(tmp_path, monkeypatch, plan=PLAN):
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)


SHORT = SOURCE.replace(":prompt (revise :text a1.text :notes b1.notes) :timeout-sec 60", ":prompt (revise :text a1.text :notes b1.notes) :timeout-sec 2")


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
    run = _cli(tmp_path, "run", *fixture(tmp_path, SHORT))
    assert run.returncode == 1 and "provider_timeout" in run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    (failed,) = [e.data for e in memo.entries if e.data["record"] == "failed"]
    assert failed["code"] == "provider_timeout" and failed["identity"].endswith("/ a2") and memo.terminal.data["outcome"] == "failed"
    assert json.loads((run_root / Path(memo.latest_starts[failed["identity"]].data["result_path"]).parent / "receipt.json").read_text())["completion"] == "not_dispatched"
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["a2"]["attempt"] == 2 and len(shim_requests(tmp_path)) == 5


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


def test_lingering_child_blocks_reconciliation_until_quiesced(tmp_path, monkeypatch) -> None:
    """An orphan from a crashed orchestrator must be proven stopped before reconcile or bootstrap."""
    plan = {"claude": PLAN["claude"], "codex": [{"mode": "linger", "result": {"notes": ["n"]}}, PLAN["codex"][1]]}
    _install(tmp_path, monkeypatch, plan)
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "completed", "STOP_TURN": "/ b1"}, "run", *fixture(tmp_path))
    run_root, _a, classes, memo = memo_of(tmp_path)
    receipt = json.loads((run_root / Path(memo.pending_starts[next(iter(memo.pending_starts))].data["result_path"]).parent / "receipt.json").read_text())
    assert receipt["pgid"] is not None
    os.killpg(receipt["pgid"], 0)                       # the lingering grandchild is alive when resume starts
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr      # preflight: needs_quiescence (admitted); under the lock quiesce() reaped it; then recovered
    with pytest.raises(ProcessLookupError):
        os.killpg(receipt["pgid"], 0)
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["b1"]["attempt"] == 1 and len(shim_requests(tmp_path)) == 4


def test_quiesce_never_signals_a_reused_pgid(tmp_path) -> None:
    """R3: after our group is gone its pgid can be handed to an unrelated process of the same user. A live leader whose
    start time differs from the one the receipt recorded at `launching` is that stranger: `quiescent`, no signal sent."""
    from orchestrator.workflow.evaluated.agent_sessions import Receipt
    from orchestrator.workflow.evaluated.agent_turns import leader_start_time, quiesce
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)   # a group leader we do not own
    try:
        live = leader_start_time(stranger.pid)
        assert live is not None
        receipt = Receipt(run_id="r", agent="a", turn="t", attempt=1, predecessor=None, input_digest="sha256:" + "0" * 64,
                          adapter="codex_exec_jsonl_stdout", config_digest="sha256:" + "0" * 64, mode="fresh", locator=None,
                          pgid=stranger.pid, leader_start_time=live + 1, position_before=None, position_after=None,
                          completion="launching", result_digest=None)
        assert quiesce(receipt) == "quiescent"            # full mode (SIGTERM/SIGKILL allowed), yet ...
        assert stranger.poll() is None                    # ... the stranger was never signalled
        os.killpg(stranger.pid, 0)                        # and its group is still there
    finally:
        stranger.kill()
        stranger.wait()


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
    assert json.loads((run_root / Path(pending.data["result_path"]).parent / "receipt.json").read_text())["completion"] == receipt_state
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["a2"]["attempt"] == 1 and after.terminal.data["outcome"] == "completed"
    assert len(shim_requests(tmp_path)) == 4             # a2 never redispatched


def test_kill_between_native_completion_and_commit_recovers_the_same_ordinal_with_zero_redispatch(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch)
    frontend = fixture(tmp_path)
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "completed", "STOP_TURN": "/ b1"}, "run", *frontend)
    run_root, _authority, classes, memo = memo_of(tmp_path)
    assert set(memo.pending_starts) == {next(i for i in memo.pending_starts if i.endswith("/ b1"))}
    assert len(shim_requests(tmp_path)) == 2
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _root, _authority, classes, after = memo_of(tmp_path)
    t = turns(after, classes)
    assert t["b1"]["attempt"] == 1 and after.terminal.data["outcome"] == "completed"
    assert len(shim_requests(tmp_path)) == 4   # a1, b1 before the kill; a2, b2 after; b1 never redispatched
    assert [r["tool"] for r in shim_requests(tmp_path)] == ["claude", "codex", "claude", "codex"]


@pytest.mark.parametrize("record, turn", [("committed", "/ b1"), ("settled", "/ a2")])
def test_kill_after_commit_or_settle_reconciles_without_native_append(tmp_path, monkeypatch, record, turn) -> None:
    _install(tmp_path, monkeypatch)
    frontend = fixture(tmp_path)
    _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": record, "STOP_TURN": turn}, "run", *frontend)
    run_root, *_ = memo_of(tmp_path)
    dispatched = len(shim_requests(tmp_path))
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _root, _authority, classes, after = memo_of(tmp_path)
    t = turns(after, classes)
    assert set(t) == {"a1", "b1", "a2", "b2"} and all(v["attempt"] == 1 for v in t.values())
    settled_by = {e.data["identity"].rsplit("/ ", 1)[1]: e.data["by"] for e in after.entries if e.data["record"] == "settled"}
    assert settled_by[turn.strip("/ ")] == ("reconcile" if record == "committed" else "settle")
    assert len(shim_requests(tmp_path)) == dispatched + (4 - dispatched)


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_evaluated_agent_turn_recovery.py -q`
Expected: FAIL — Task 10 keeps the uncertain starts pending but its `_prepare_pending` stub refuses every pending turn as `agent_turn_unresolved`, so the resume-based tests fail (no recovery, no next-attempt allocation); `test_quiesce_never_signals_a_reused_pgid` fails with `ImportError: quiesce`.

- [ ] **Step 3: Implement classification and recovery**

```python
# orchestrator/workflow/evaluated/agent_turns.py (additions)
@dataclass(frozen=True)
class PendingTurn:
    disposition: str                 # recoverable | not_dispatched | unresolved | bootstrap | needs_quiescence (probe_only)
    receipt: Receipt | None
    native_turn: Any                 # NativeTurn | None
    detail: str


def quiesce(receipt: Receipt, *, probe_only: bool = False) -> str:
    """Stop the recorded process group through the executor's termination shape and prove it is gone.

    Returns "quiescent" (group gone), "alive" (probe_only and the group still answers; nothing was signalled) or
    "unprovable" (we do not own the pgid, or it survives SIGTERM + grace + SIGKILL + grace).

    R3: the pgid number is reusable once every member of our group has exited. A live leader whose start time differs
    from the one recorded at `launching` is therefore an unrelated process and is never signalled. A leader with no
    `/proc` entry says nothing about lingering members (Linux keeps the number reserved while the group has any), so
    the probe and signals proceed.
    """
    import os, signal, time
    if receipt.pgid is None:
        return "quiescent" if receipt.completion in {"intent", "not_dispatched"} else "unprovable"   # launched, pgid never bound
    live = leader_start_time(receipt.pgid)
    if receipt.leader_start_time is not None and live is not None and live != receipt.leader_start_time:
        return "quiescent"                                           # reused pid: our group is gone; never signal a stranger
    steps = ((None, 0.0),) if probe_only else ((None, 0.0), (signal.SIGTERM, 2.0), (signal.SIGKILL, 2.0))
    for sig, grace in steps:
        try:
            if sig is not None:
                os.killpg(receipt.pgid, sig)
            deadline = time.monotonic() + grace
            while True:
                os.killpg(receipt.pgid, 0)
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
        except ProcessLookupError:
            return "quiescent"
        except PermissionError:
            return "unprovable"                                      # a reused pgid we do not own
    return "alive" if probe_only else "unprovable"


def classify_pending_turn(authority, node, identity, snapshot, workspace, resolved: ResolvedTurn, *, probe_only: bool = False) -> PendingTurn:
    """Reconcile a pending agent turn from its receipt and the native store; sends no prompt (design failure table).

    `probe_only=True` is the read-only resume preflight: it never signals a process and reports a live group as
    `needs_quiescence`, which the preflight admits; the writer-locked `_prepare_pending` quiesces and re-classifies.
    """
    pending = snapshot.pending_starts[identity]
    files = WorkspaceFiles(authority.run_root / Path(pending.data["result_path"]).parent)
    try:
        receipt = read_receipt(files)
        result_present = files.exists("result.json")
    finally:
        files.close()
    first_turn = resolved.predecessor is None
    if receipt is None or receipt.completion in {"intent", "not_dispatched"}:
        return PendingTurn("not_dispatched", receipt, None, "reserved; the executor never bound a child (no `launching`)")
    if receipt.input_digest != pending.data["input_digest"]:
        raise MemoError("memo_inconsistent", f"receipt of {identity} disagrees with its started reservation")
    if receipt.completion == "abandoned":
        return PendingTurn("bootstrap", receipt, None, "candidate already abandoned")
    stopped = quiesce(receipt, probe_only=probe_only)
    if stopped == "alive":
        return PendingTurn("needs_quiescence", receipt, None, "the dispatched process group is still alive; quiesce under the writer lock")
    if stopped == "unprovable":
        return PendingTurn("unresolved", receipt, None, "the dispatched process group cannot be proven stopped")
    if receipt.locator is None:
        return _pending_outcome(first_turn, receipt, None, "launched without a locator: uncertainty")
    located = resolved.adapter.locate(receipt.locator)
    if located.path is None:
        return _pending_outcome(first_turn, receipt, None, "native locator missing or ambiguous")
    before = None if receipt.position_before is None else NativePosition.from_record(receipt.position_before)
    try:
        head = resolved.adapter.head(located.path)
        turn = resolved.adapter.completed_turn(located.path, after=before, prompt_marker=pending.data["result_path"].rsplit("/", 1)[0] + "/")
    except NativeStoreError as exc:
        return _pending_outcome(first_turn, receipt, None, str(exc))
    if turn is not None and result_present:
        return PendingTurn("recoverable", receipt, turn, "native completion and result evidence intact")
    if turn is None and receipt.mode == "resume" and not head.open_turn and head.position == before:
        return PendingTurn("not_dispatched", receipt, None, "adapter proves the predecessor head unchanged")
    return _pending_outcome(first_turn, receipt, turn, "native state advanced, open or uncertain without an intact result")


def _pending_outcome(first_turn, receipt, turn, detail) -> PendingTurn:
    return PendingTurn("bootstrap" if first_turn else "unresolved", receipt, turn, detail)


def recover_pending_turn(attempt):
    """Commit the recovered pending attempt without any append: outcome from the classified native turn."""
    from .effect_execution import ExternalOutcome
    path = workspace_relative_path(attempt.workspace, attempt.authority.run_root / attempt.result_path)
    turn = attempt.resolved.pending.native_turn
    update_receipt(attempt.attempt_files, position_after=turn.position.record(), completion="completed")
    return ExternalOutcome(result_path=path, agent_turn=turn)
```

In `effect_inputs._check_resume_boundary`, for `agent_turn` with `identity in snapshot.pending_starts`: resolve the turn input, `classify_pending_turn(..., probe_only=True)` (read-only: it only probes `killpg(pgid, 0)`, signals nothing) and `raise _PreflightRefusal("agent_turn_unresolved", detail)` only for `unresolved`; `needs_quiescence`, `recoverable`, `not_dispatched` and `bootstrap` are admitted; `agent_turn_result_invalid` is refused in Task 12. `agent_turns._prepare_pending` (called by `prepare_agent_attempt`, Task 10) classifies again under the writer lock with `probe_only=False` — so a `needs_quiescence` group is terminated and reaped there (the executor's SIGTERM/SIGKILL shape) before any reconciliation or append — and then: `recoverable` → `WorkspaceFiles(authority.run_root / Path(pending.data["result_path"]).parent)` as `attempt_files` and `PreparedAttempt(..., ordinal=pending.data["attempt"], result_path=pending.data["result_path"], resolved=replace(resolved, pending=classified), recovered=True)` without a new `started`; `not_dispatched` → fall through to the ordinary next-attempt `started` in `prepare_agent_attempt`; `unresolved` → `AgentTurnError("agent_turn_unresolved", ..., keep_pending=True)`; `bootstrap` → Task 12. `_unresolved_or_failed` already returns `keep_pending=True` for every uncertain path and the plain `ProviderPerformerError` for the proven-non-dispatch paths.

- [ ] **Step 4: Amend `specs/cli.md` resume preflight and the evaluated design §8.1/§9.3.1 text (sections named in Files)**

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workflow_evaluated_agent_turn_recovery.py tests/test_workflow_evaluated_agent_turns.py tests/test_workflow_evaluated_resume_retry.py -q`
Expected: PASS. In particular `pytest tests/test_workflow_evaluated_agent_turn_recovery.py -q -k "reused_pgid or recovered_on_resume"` → `3 passed`: the stranger process is still alive after `quiesce` returned `quiescent`, and both unmapped-exception runs (verification seam, receipt `unknown`; projection seam, receipt `completed`) resume to `completed` with `a2` at attempt 1 and four dispatches.

- [ ] **Step 6: Commit**

```bash
git add tests/test_workflow_evaluated_agent_turn_recovery.py
git commit -m "feat: recover pending agent turns from receipts and native completion without redispatch" -- orchestrator/workflow/evaluated/agent_turns.py orchestrator/workflow/evaluated/effect_inputs.py orchestrator/workflow/evaluated/runtime.py orchestrator/workflow/evaluated/effect_execution.py specs/cli.md docs/design/workflow_lisp_evaluated_execution.md tests/test_workflow_evaluated_agent_turn_recovery.py
```

---

### Task 12: Explicit-resume bootstrap retry and the result-invalid rules (scoped K4 exception)

**Files:**
- Modify: `orchestrator/workflow/evaluated/agent_turns.py` (add `abandon_candidate(authority, pending_files, pending, receipt, site_classes) -> dict`; `_prepare_pending` on `bootstrap` calls it, then falls through to the ordinary next-attempt `started`; `prepare_agent_attempt` also handles the latest-attempt-`failed` case of a first turn: write `abandoned.json`/receipt `abandoned` for the previous attempt if missing and log `[agent_bootstrap_restarted]` before the new `started`)
- Modify: `orchestrator/workflow/evaluated/runtime.py` (no change)
- Modify: `orchestrator/workflow/evaluated/effect_inputs.py` (`_check_resume_boundary`: a pending or latest-failed `agent_turn_result_invalid` attempt of a later turn refuses `agent_turn_result_invalid`; `bootstrap` is admitted at preflight without writing)
- Create: `tests/test_workflow_evaluated_agent_bootstrap.py`
- Modify (spec amendment): `docs/design/workflow_lisp_evaluated_execution.md` §9.3 K4 row (`:2608`): append "Agent turns (target 2.38) are the scoped exception: a pending turn is reconciled from its receipt and native store; only an agent with no committed turn may be restarted, by explicit public `resume`, abandoning the old candidate first (Agent Sessions, Bootstrap retry policy); later turns refuse"; `specs/cli.md` resume preflight: the bootstrap sentence (admitted at preflight, executed under the lock before the next `started`).

**Interfaces:**
- Consumes: Task 11 `PendingTurn`.
- Produces: `abandon_candidate(authority, pending_files, pending, receipt, site_classes) -> dict` (the `failed` row it appended or would append); the `failed` row shape `{code: "agent_bootstrap_restarted", exit_info: {abandoned_attempt, locator}}`; the `[agent_bootstrap_restarted] <turn> abandoned attempt <n> locator=<...>` log line on every bootstrap path, including the first-turn invalid-result path.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_agent_bootstrap.py
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
    assert json.loads((attempt1 / "receipt.json").read_text())["completion"] == "abandoned"
    assert (attempt1 / "abandoned.json").exists()


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


@pytest.mark.parametrize("mode, code", [("interrupted", "agent_turn_unresolved"), ("invalid-result", "agent_turn_result_invalid")])
def test_later_turn_failures_cannot_bootstrap(tmp_path, monkeypatch, mode, code) -> None:
    plan = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": mode, "result": {"text": "d2"}}], "codex": PLAN["codex"]}
    _install(tmp_path, monkeypatch, plan)
    run = _cli(tmp_path, "run", *fixture(tmp_path))
    assert run.returncode == 1 and code in run.stderr
    run_root, _a, _c, memo = memo_of(tmp_path)
    if code == "agent_turn_result_invalid":
        (failed,) = _rows(memo, "failed", "/ a2")
        assert failed["code"] == code and failed["violations"]
    memo_bytes = (run_root / "memo.jsonl").read_bytes()
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 2 and code in resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes() == memo_bytes
    assert len(shim_requests(tmp_path)) == 3


@pytest.mark.parametrize("hook, env, failed_rows_after_kill", [
    ("receipt", {"STOP_AT_COMPLETION": "abandoned", "STOP_TURN": "/ b1"}, 0),     # between abandonment and failure closure
    ("record", {"STOP_RECORD": "failed", "STOP_TURN": "/ b1"}, 1),                 # between failure closure and the next start
])
def test_kill_between_abandonment_failure_and_next_start_keeps_ordering_valid(tmp_path, monkeypatch, hook, env, failed_rows_after_kill) -> None:
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECEIPT
    plan = {"claude": PLAN["claude"], "codex": [{"mode": "interrupted", "result": {}}, {"mode": "success", "result": {"notes": ["n"]}}, {"mode": "success", "result": {"notes": ["done"]}}]}
    _install(tmp_path, monkeypatch, plan)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 1
    run_root, *_ = memo_of(tmp_path)
    _stopped(tmp_path, STOP_AFTER_RECEIPT if hook == "receipt" else STOP_AFTER_RECORD, env, "resume", run_root.name)
    _r, _a, classes, memo = memo_of(tmp_path)
    assert len(_rows(memo, "failed", "/ b1")) == failed_rows_after_kill
    attempt1 = run_root / Path(_rows(memo, "started", "/ b1")[0]["result_path"]).parent
    assert json.loads((attempt1 / "receipt.json").read_text())["completion"] == "abandoned"
    assert len([r for r in shim_requests(tmp_path) if r["tool"] == "codex"]) == 1
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, after = memo_of(tmp_path)
    assert [r["code"] for r in _rows(after, "failed", "/ b1")] == ["agent_bootstrap_restarted"]   # not duplicated
    assert turns(after, classes)["b1"]["attempt"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_evaluated_agent_bootstrap.py -q`
Expected: FAIL — resume after an interrupted first turn refuses or redispatches at attempt 1; no `agent_bootstrap_restarted` rows.

- [ ] **Step 3: Implement bootstrap and the invalid-result refusal**

```python
# orchestrator/workflow/evaluated/agent_turns.py (addition)
def abandon_candidate(authority, pending_files, pending, receipt, site_classes) -> dict:
    """Durably mark the old native candidate abandoned, then close its attempt before any new `started`."""
    if receipt is not None and receipt.completion != "abandoned":
        update_receipt(pending_files, completion="abandoned")
    pending_files.write_atomic("abandoned.json", canonical_json_bytes({
        "schema": "agent_turn_abandoned.v1", "attempt": pending.data["attempt"],
        "locator": None if receipt is None else receipt.locator}))
    failure = {"record": "failed", "identity": pending.data["identity"], "attempt": pending.data["attempt"],
               "code": "agent_bootstrap_restarted",
               "exit_info": {"abandoned_attempt": pending.data["attempt"], "locator": None if receipt is None else receipt.locator}}
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    if snapshot.pending_starts.get(pending.data["identity"]) is not None:          # not duplicated after a crash
        append_record(authority.memo_path, failure, run_files=authority.run_files, checked_authority=authority)
    logger.warning("[agent_bootstrap_restarted] %s abandoned attempt %s locator=%s",
                   pending.data["identity"], pending.data["attempt"], failure["exit_info"]["locator"])
    return failure
```

`agent_turns._prepare_pending` on `bootstrap`: `abandon_candidate(...)` (receipt `abandoned` → `abandoned.json` → `failed` if still pending, idempotent after a crash at any of the three points), re-read the snapshot and continue to the ordinary next-attempt `started` in `prepare_agent_attempt`. `prepare_agent_attempt` with no pending start but a latest `failed` first-turn attempt (`provider_result_invalid`, or `agent_bootstrap_restarted` after a crash between `failed` and the next `started`): before the new `started`, write `abandoned.json` and the receipt `abandoned` for that attempt if absent and log `[agent_bootstrap_restarted]` — the diagnostic is emitted on every bootstrap path. `effect_inputs._check_resume_boundary`: for `agent_turn`, when the latest `failed` row's code is `agent_turn_result_invalid`, or the pending classification is `unresolved` with a predecessor, raise `_PreflightRefusal(code, detail)`; `bootstrap`/`not_dispatched`/`recoverable` are admitted without writing.

`project_turn` already raises `agent_turn_result_invalid` for later turns; the `failed` row is appended by `finish_effect` with `violations`.

- [ ] **Step 4: Amend the evaluated design K4 row and `specs/cli.md` resume preflight (sections named in Files)**

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workflow_evaluated_agent_bootstrap.py tests/test_workflow_evaluated_agent_turn_recovery.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_workflow_evaluated_agent_bootstrap.py
git commit -m "feat: bootstrap an agent's first turn only on explicit resume and refuse later-turn repair" -- orchestrator/workflow/evaluated/agent_turns.py orchestrator/workflow/evaluated/effect_inputs.py specs/cli.md docs/design/workflow_lisp_evaluated_execution.md tests/test_workflow_evaluated_agent_bootstrap.py
```

---

### Task 13: C8 whole-suffix guards for agent attempt history

**Files:**
- Create: `orchestrator/workflow/evaluated/agent_guards.py` (`check_invalidation_suffix`, `validate_prefix_receipts`; imports `memo_reducer` and `agent_sessions` only — no `memo.py` import, so no cycle)
- Modify: `orchestrator/workflow/evaluated/memo.py:159-174` (`invalidate_suffix`: after the coordinator check and before `repair_torn_tail`, `from .agent_guards import check_invalidation_suffix` locally and call it)
- Modify: `orchestrator/workflow/evaluated/resume_prefix.py` (`_validate_discovered_prefix`: after the committed replays and before the frontier checks, `agent_guards.validate_prefix_receipts(authority, snapshot, site_classes)` — the resume-time receipt guard of R1)
- Create: `tests/test_workflow_evaluated_agent_invalidate.py`
- Modify (spec amendment): `specs/cli.md` `invalidate` paragraph (`:325-336`): after "A suffix containing a committed run reference refuses whole with `invalidate_coordinator_committed`" add "or a committed agent turn; a suffix (by journal order of starts, including abandoned bootstrap attempts) containing an agent turn attempt that was dispatched, advanced its native session or is of uncertain outcome refuses `invalidate_agent_session_advanced`; an unreadable required receipt is `memo_inconsistent`; unused allocations and proven-undispatched attempts invalidate normally. All checks precede tail repair or any write"; `docs/design/workflow_lisp_evaluated_execution.md` C8 row (`:1677`): replace "`run_ref` is the only admitted coordinator in the first release" with "`run_ref` and, at target 2.38, `agent_turn` are the admitted coordinators; the agent attempt-history guard is `invalidate_agent_session_advanced` (Agent Sessions, Persistence)".

**Interfaces:**
- Produces: `check_invalidation_suffix(snapshot, chosen, run_files, site_classes) -> None` raising `MemoError("invalidate_agent_session_advanced", ...)` or `memo_inconsistent`. Agreement rule between the write preflight and the reducer's `check_invalidation_cut` (journal facts only): an `agent_turn` `started` row at or after the cut whose attempt is still pending, or closed `failed` with a dispatched-failure code, is **always** refused — by the preflight as `invalidate_agent_session_advanced` ("resume first: a pending agent turn must be reconciled before its prefix can be cancelled") and by the reducer as `memo_inconsistent`; an attempt closed `failed` with any other code (`provider_timeout`, `provider_exit_nonzero`, `effect_attempt_path_exists`, ...) may be cut by the reducer, and by the preflight **only when its receipt proves non-dispatch** (absent, `intent` or `not_dispatched`); a launched attempt (`launching`, `unknown`, `completed`) that failed through an unmapped path is uncertain and the preflight refuses it (the preflight is stricter than the reducer, never laxer, so a durable row can never be refused on read; since Task 10 keeps every post-`launching` exception of `perform_turn` and every post-`completed` exception of `project_turn` pending, no in-tree path produces such a row — the guard is defense in depth driven by receipt facts, not by the failure code, and its proof test tampers a `not_dispatched` receipt to `completed`). The preflight additionally refuses, from receipts, attempts started *before* the cut whose allocation or predecessor is in the suffix and whose receipt is not `not_dispatched`, and unreadable receipts (`memo_inconsistent`). "Proven-undispatched" therefore means: closed `failed` with a non-dispatched code, or started before the cut with a `not_dispatched`/absent receipt. A pending attempt is never cut, because the journal alone cannot prove it undispatched; `validate_prefix_receipts(authority, snapshot, site_classes) -> None`: at resume, receipts are checked only for attempts that are *not* committed — a pending `agent_turn` attempt must have either no receipt (never dispatched) or a readable receipt whose `turn`, `attempt` and `input_digest` match its `started` row and whose `completion` is one of the known states; a `failed` attempt with a dispatched-failure code (`agent_bootstrap_restarted`, `agent_turn_result_invalid`, first-turn `provider_result_invalid`) must carry a receipt in `{abandoned, completed, unknown}` and, for `agent_bootstrap_restarted`, an `abandoned.json`. Committed turns, settled or not, are never checked against receipts: the inline proof is sole continuation authority (design, Identity; verification "settled memo replay must not require old receipt sidecars"). Any disagreement is `memo_inconsistent` before the frontier is reached.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_agent_invalidate.py
"""Invalidation refuses before any write when the suffix holds a committed or advanced agent turn; unused allocations may go."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_agent_turns import PLAN, SOURCE, fixture, memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes

FILE_DEP = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Draft (text String))
  (defpath Notes :kind relpath :under "notes" :must-exist true)
  (defprompt draft (:fills (notes :doc Notes)) -> Draft "Draft from the notes")
  (defworkflow run ((task String)) -> Draft
    (let* ((designer (agent providers.claude :model "planner"))
           (written (command-result write :argv ("python" "write.py" task) :returns Notes))
           (t (provider-result designer :prompt (draft :notes written) :timeout-sec 60)))
      t)))'''

WRITE = '''import json, os, sys
from pathlib import Path
Path("notes").mkdir(exist_ok=True)
Path("notes/x.md").write_text(sys.argv[1])
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps("notes/x.md"))
'''

# A committed first turn `t0` makes `t` a resume-mode turn, so a transport failure before any append is adapter-provable
# as `not_dispatched` (design row 4: head unchanged) and closes `failed`; a fresh first turn can never be proven undispatched
# and stays pending instead. The command `written` between them is a non-agent cut point with no committed turn after it.
SEEDED_FILE_DEP = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Draft (text String))
  (defpath Notes :kind relpath :under "notes" :must-exist true)
  (defprompt seed (:fills (task :text)) -> Draft "Seed: {task}")
  (defprompt draft (:fills (notes :doc Notes)) -> Draft "Draft from the notes")
  (defworkflow run ((task String)) -> Draft
    (let* ((designer (agent providers.claude :model "planner"))
           (t0 (provider-result designer :prompt (seed :task task) :timeout-sec 60))
           (written (command-result write :argv ("python" "write.py" task) :returns Notes))
           (t (provider-result designer :prompt (draft :notes written) :timeout-sec 60)))
      t)))'''

SEEDED_NONZERO = {"claude": [{"mode": "success", "result": {"text": "d0"}}, {"mode": "nonzero-before-append", "result": {}}], "codex": []}


def _install(tmp_path, monkeypatch, plan=PLAN):
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)


def _identity(memo, suffix):
    return next(i for i in memo.latest_starts if i.endswith(suffix))


def test_suffix_with_a_committed_turn_refuses_coordinator_committed_without_writes(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    run_root, _a, _c, memo = memo_of(tmp_path)
    before = _tree_bytes(run_root)
    for target in ("/ designer", "/ a1", "/ b1"):
        refused = _cli(tmp_path, "invalidate", run_root.name, _identity(memo, target))
        assert refused.returncode == 2 and "invalidate_coordinator_committed" in refused.stderr
    assert _tree_bytes(run_root) == before


def test_unused_allocation_tail_invalidates_and_resume_reallocates(tmp_path, monkeypatch) -> None:
    source = SOURCE.replace("(b2 (provider-result reviewer :prompt (execute :text a2.text) :timeout-sec 60)))", "(spare (agent providers.codex :model \"x\")) (b2 (Feedback :notes b1.notes)))")
    _install(tmp_path, monkeypatch, {"claude": PLAN["claude"], "codex": PLAN["codex"][:1]})
    assert _cli(tmp_path, "run", *fixture(tmp_path, source)).returncode == 0
    run_root, _a, classes, memo = memo_of(tmp_path)
    done = _cli(tmp_path, "invalidate", run_root.name, _identity(memo, "/ spare"))
    assert done.returncode == 0, done.stderr
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    _r, _a, classes, after = memo_of(tmp_path)
    assert after.active_commits[_identity(after, "/ spare")].data["attempt"] == 2
    assert len(shim_requests(tmp_path)) == 3


def test_upstream_command_feeding_an_advanced_uncommitted_turn_refuses_session_advanced(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch, {"claude": [{"mode": "interrupted", "result": {}}], "codex": []})
    (tmp_path / "write.py").write_text(WRITE)
    (tmp_path / "commands.json").write_text(json.dumps({"write": {"stable_command": ["python", "write.py"], "closure": ["write.py"]}}))
    run = _cli(tmp_path, "run", *fixture(tmp_path, FILE_DEP), "--command-boundaries-file", "commands.json")
    assert run.returncode == 1 and "agent_turn_unresolved" in run.stderr
    run_root, _a, _c, memo = memo_of(tmp_path)
    assert memo.pending_starts and memo.terminal is None
    before = _tree_bytes(run_root)
    refused = _cli(tmp_path, "invalidate", run_root.name, _identity(memo, "/ written"))
    assert refused.returncode == 2 and "invalidate_agent_session_advanced" in refused.stderr
    assert _tree_bytes(run_root) == before
    # the allocation predates the command and the turn declares no value dependency on it: still refused (start order)
    refused_alloc = _cli(tmp_path, "invalidate", run_root.name, _identity(memo, "/ designer"))
    assert refused_alloc.returncode == 2 and "invalidate_agent_session_advanced" in refused_alloc.stderr


def test_committed_turns_after_a_bootstrap_still_protect_the_suffix(tmp_path, monkeypatch) -> None:
    plan = {"claude": PLAN["claude"], "codex": [{"mode": "interrupted", "result": {}}, {"mode": "success", "result": {"notes": ["n"]}}, {"mode": "success", "result": {"notes": ["done"]}}]}
    _install(tmp_path, monkeypatch, plan)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 1
    run_root, *_ = memo_of(tmp_path)
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    _r, _a, _c, memo = memo_of(tmp_path)
    refused = _cli(tmp_path, "invalidate", run_root.name, _identity(memo, "/ reviewer"))
    assert refused.returncode == 2 and "invalidate_coordinator_committed" in refused.stderr


def test_resume_refuses_a_pending_receipt_that_disagrees_with_its_started_row(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch, {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": "interrupted", "result": {}}], "codex": PLAN["codex"]})
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 1
    run_root, _a, classes, memo = memo_of(tmp_path)
    (pending,) = memo.pending_starts.values()
    receipt_path = run_root / Path(pending.data["result_path"]).parent / "receipt.json"
    receipt = json.loads(receipt_path.read_text()); receipt["input_digest"] = "sha256:" + "f" * 64
    receipt_path.write_text(json.dumps(receipt))
    before = _tree_bytes(run_root, omit_memo=None)
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 2 and "memo_inconsistent" in resumed.stderr
    assert _tree_bytes(run_root, omit_memo=None) == before and len(shim_requests(tmp_path)) == 3


def test_committed_turns_never_need_their_receipts_on_resume(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    run_root, *_ = memo_of(tmp_path)
    for receipt in run_root.rglob("receipt.json"):
        receipt.write_text("{garbage")                  # unreadable sidecars beside committed turns are ignored
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0 and len(shim_requests(tmp_path)) == 4


def test_pending_turn_after_a_kill_is_refused_by_preflight_and_the_row_would_not_reduce(tmp_path, monkeypatch) -> None:
    """NEW-I2 agreement proof: the preflight refuses; a forged `invalidated` row over the same journal is memo_inconsistent on read."""
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECORD, _stopped
    from orchestrator.workflow.evaluated.memo import MemoError, read_memo
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    _install(tmp_path, monkeypatch)
    _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": "started", "STOP_TURN": "/ b1"}, "run", *fixture(tmp_path))
    run_root, _a, classes, memo = memo_of(tmp_path)
    assert next(iter(memo.pending_starts)).endswith("/ b1")
    before = _tree_bytes(run_root)
    refused = _cli(tmp_path, "invalidate", run_root.name, _identity(memo, "/ reviewer"))
    assert refused.returncode == 2 and "invalidate_agent_session_advanced" in refused.stderr and "resume first" in refused.stderr
    assert _tree_bytes(run_root) == before
    # forge the row the preflight refused: the reducer rejects it too, so preflight and reducer agree
    forged = run_root / "forged.jsonl"
    anchor = memo.active_commits[_identity(memo, "/ reviewer")].offset
    forged.write_bytes((run_root / "memo.jsonl").read_bytes() + json.dumps({"record": "invalidated", "from_commit": anchor, "time": 1.0}).encode() + b"\n")
    with pytest.raises(MemoError, match="memo_inconsistent"):
        read_memo(forged, site_classes(load_run_authority(run_root).program))
    forged.unlink()
    # resume reconciles the pending reviewer turn (bootstrap: it was never dispatched -> not_dispatched -> next attempt)
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0


def test_failed_row_with_a_receipt_past_intent_refuses_cut(tmp_path, monkeypatch) -> None:
    """Defense in depth for the receipt guard (NEW-I4). Task 10 keeps every post-`launching` exception of `perform_turn`
    and every post-`completed` exception of `project_turn` pending, so no in-tree path closes `failed` with a receipt past
    `intent`; the row is produced through the normal `nonzero-before-append` path (receipt `not_dispatched`) and the receipt
    is then tampered to `completed` on disk. The guard is driven by receipt facts, not by the failure code alone: the same
    journal is refused with the tampered receipt and cut with the original one.
    Expected: `invalidate <written>` exits 2 with `invalidate_agent_session_advanced` and "after launch", tree unchanged."""
    _install(tmp_path, monkeypatch, SEEDED_NONZERO)
    (tmp_path / "write.py").write_text(WRITE)
    (tmp_path / "commands.json").write_text(json.dumps({"write": {"stable_command": ["python", "write.py"], "closure": ["write.py"]}}))
    assert _cli(tmp_path, "run", *fixture(tmp_path, SEEDED_FILE_DEP), "--command-boundaries-file", "commands.json").returncode == 1
    run_root, _a, _c, memo = memo_of(tmp_path)
    (failed,) = [e.data for e in memo.entries if e.data["record"] == "failed"]
    assert failed["code"] == "provider_exit_nonzero" and failed["identity"].endswith("/ t")
    receipt_path = run_root / Path(memo.latest_starts[failed["identity"]].data["result_path"]).parent / "receipt.json"
    original = receipt_path.read_bytes()
    receipt = json.loads(original)
    assert receipt["completion"] == "not_dispatched"
    receipt_path.write_text(json.dumps({**receipt, "completion": "completed"}))        # tamper: launched and advanced
    before = _tree_bytes(run_root)
    refused = _cli(tmp_path, "invalidate", run_root.name, _identity(memo, "/ written"))
    assert refused.returncode == 2 and "invalidate_agent_session_advanced" in refused.stderr and "after launch" in refused.stderr
    assert _tree_bytes(run_root) == before
    receipt_path.write_bytes(original)                                                  # same journal, original receipt: the cut is allowed
    assert _cli(tmp_path, "invalidate", run_root.name, _identity(memo, "/ written")).returncode == 0


def test_failed_before_dispatch_turn_may_be_cut_by_preflight_and_reducer_alike(tmp_path, monkeypatch) -> None:
    """Design row 4 at the cut: `t` (resume mode after `t0`) fails before any append, the adapter proves the head unchanged,
    so the attempt closes `failed` (`provider_exit_nonzero`) with receipt `not_dispatched`; preflight and reducer both let
    the cut at `written` through, and resume reruns `written` and `t` at the next attempt."""
    from orchestrator.workflow.evaluated.memo import read_memo
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    _install(tmp_path, monkeypatch, {"claude": [*SEEDED_NONZERO["claude"], {"mode": "success", "result": {"text": "d1"}}], "codex": []})
    (tmp_path / "write.py").write_text(WRITE)
    (tmp_path / "commands.json").write_text(json.dumps({"write": {"stable_command": ["python", "write.py"], "closure": ["write.py"]}}))
    run = _cli(tmp_path, "run", *fixture(tmp_path, SEEDED_FILE_DEP), "--command-boundaries-file", "commands.json")
    assert run.returncode == 1 and "provider_exit_nonzero" in run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    (failed,) = [e.data for e in memo.entries if e.data["record"] == "failed"]
    assert failed["identity"].endswith("/ t") and memo.terminal.data["outcome"] == "failed"
    assert json.loads((run_root / Path(memo.latest_starts[failed["identity"]].data["result_path"]).parent / "receipt.json").read_text())["completion"] == "not_dispatched"
    done = _cli(tmp_path, "invalidate", run_root.name, _identity(memo, "/ written"))
    assert done.returncode == 0, done.stderr
    authority = load_run_authority(run_root)
    assert read_memo(authority.memo_path, site_classes(authority.program)).active_commits.keys() >= {_identity(memo, "/ designer"), _identity(memo, "/ t0")}   # the reducer accepts the cut
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    _r, _a, classes, after = memo_of(tmp_path)
    assert turns(after, classes)["t"]["attempt"] == 2 and len(shim_requests(tmp_path)) == 3


def test_unreadable_required_receipt_is_memo_inconsistent(tmp_path, monkeypatch) -> None:
    """A turn started before the cut whose allocation is in the suffix needs its receipt; unreadable -> memo_inconsistent."""
    _install(tmp_path, monkeypatch, {"claude": [{"mode": "interrupted", "result": {}}], "codex": []})
    (tmp_path / "write.py").write_text(WRITE)
    (tmp_path / "commands.json").write_text(json.dumps({"write": {"stable_command": ["python", "write.py"], "closure": ["write.py"]}}))
    assert _cli(tmp_path, "run", *fixture(tmp_path, FILE_DEP), "--command-boundaries-file", "commands.json").returncode == 1
    run_root, _a, _c, memo = memo_of(tmp_path)
    for receipt in run_root.rglob("receipt.json"):
        receipt.write_text("{not json")
    refused = _cli(tmp_path, "invalidate", run_root.name, _identity(memo, "/ designer"))
    assert refused.returncode == 2 and "memo_inconsistent" in refused.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_evaluated_agent_invalidate.py -q`
Expected: the first two tests pass from Task 8; the command/receipt tests FAIL (invalidation succeeds).

- [ ] **Step 3: Implement the guard**

```python
# orchestrator/workflow/evaluated/agent_guards.py
"""Receipt-based agent guards: C8 write preflight and resume-time prefix validation (R1)."""
from __future__ import annotations

import json
from pathlib import Path

from .agent_sessions import Receipt
from .memo_reducer import MemoError, _DYNAMIC_INDEX


DISPATCHED_FAILURE_CODES = {"agent_bootstrap_restarted", "agent_turn_result_invalid", "provider_result_invalid"}


def validate_prefix_receipts(authority, snapshot, site_classes) -> None:
    """Receipts of uncommitted agent attempts must agree with the journal; committed turns rely on their inline proof only."""
    for entry in snapshot.entries:
        row = entry.data
        if row.get("record") != "started" or _site_class(site_classes, row["identity"]) != "agent_turn":
            continue
        closing = next((e.data for e in snapshot.entries if e.offset > entry.offset and e.data.get("identity") == row["identity"]
                        and e.data.get("attempt") == row["attempt"] and e.data["record"] in {"committed", "failed"}), None)
        if closing is not None and closing["record"] == "committed":
            continue                                                     # inline proof is sole authority; no sidecar needed
        receipt = _read_attempt_receipt(authority.run_files, row["result_path"])   # unreadable -> memo_inconsistent
        if receipt is None:
            if closing is not None and closing["code"] in DISPATCHED_FAILURE_CODES:
                raise MemoError("memo_inconsistent", f"dispatched agent attempt {row['identity']} #{row['attempt']} has no receipt")
            continue                                                     # reserved and never dispatched
        if (receipt.turn, receipt.attempt, receipt.input_digest) != (row["identity"], row["attempt"], row["input_digest"]):
            raise MemoError("memo_inconsistent", f"receipt of {row['identity']} #{row['attempt']} disagrees with its started row")
        if closing is not None and closing["code"] in DISPATCHED_FAILURE_CODES and receipt.completion not in {"abandoned", "completed", "unknown"}:
            raise MemoError("memo_inconsistent", f"failed agent attempt {row['identity']} #{row['attempt']} carries an undispatched receipt")


def check_invalidation_suffix(snapshot, chosen, run_files, site_classes) -> None:
    """Inspect all agent attempt history affected by the cut; refuse before any write (C8, Agent Sessions)."""
    cut = chosen.offset
    suffix_identities = {i for i, c in snapshot.active_commits.items() if c.offset >= cut}
    for entry in snapshot.entries:
        row = entry.data
        if row.get("record") != "started":
            continue
        identity = row["identity"]
        if _site_class(site_classes, identity) != "agent_turn":
            continue
        committed_here = snapshot.active_commits.get(identity)
        if committed_here is not None and committed_here.offset < cut and committed_here.data["attempt"] == row["attempt"]:
            continue                                   # a settled earlier turn is untouched by the cut
        closing = next((e.data for e in snapshot.entries if e.offset > entry.offset and e.data.get("identity") == identity
                        and e.data.get("attempt") == row["attempt"] and e.data["record"] in {"committed", "failed"}), None)
        if entry.offset >= cut:                        # journal rule, identical to memo_reducer_agents.check_invalidation_cut
            if closing is None:
                raise MemoError("invalidate_agent_session_advanced",
                                f"agent turn {identity} attempt {row['attempt']} is pending; resume first so it is reconciled or bootstrapped")
            if closing["record"] == "failed" and closing["code"] in DISPATCHED_FAILURE_CODES:
                raise MemoError("invalidate_agent_session_advanced",
                                f"agent turn {identity} attempt {row['attempt']} dispatched and failed ({closing['code']})")
            receipt = _read_attempt_receipt(run_files, row["result_path"])   # unreadable -> memo_inconsistent
            if receipt is None or receipt.completion in {"intent", "not_dispatched"}:
                continue                               # proven undispatched (never launched, or adapter-proven no advance): ordinary C8
            raise MemoError("invalidate_agent_session_advanced",             # launched, then failed through an unmapped path: uncertain
                            f"agent turn {identity} attempt {row['attempt']} failed ({closing['code']}) after launch; receipt {receipt.completion}")
        receipt = _read_attempt_receipt(run_files, row["result_path"])          # started before the cut: receipt facts decide
        if not _depends_on_suffix(receipt, suffix_identities):
            continue                                   # independent of the cut
        if receipt is None or receipt.completion == "not_dispatched":
            continue                                   # reserved or proven undispatched: ordinary C8
        raise MemoError("invalidate_agent_session_advanced",
                        f"agent turn {identity} attempt {row['attempt']} is {receipt.completion}; its native session advanced or is uncertain")


def _depends_on_suffix(receipt, suffix_identities) -> bool:
    """A turn started before the cut is affected when its allocation or recorded predecessor is cancelled by it."""
    if receipt is None:
        return False
    return receipt.agent in suffix_identities or receipt.predecessor in suffix_identities


def _read_attempt_receipt(run_files, result_path):
    directory = Path(result_path).parent
    if not run_files.exists(directory / "receipt.json"):
        return None
    try:
        return Receipt(**{k: v for k, v in json.loads(run_files.read(directory / "receipt.json")).items() if k != "schema"})
    except (ValueError, TypeError) as exc:
        raise MemoError("memo_inconsistent", f"agent turn receipt under {directory} is unreadable: {exc}") from exc


def _site_class(site_classes, identity):
    return site_classes.get(identity) or site_classes.get(_DYNAMIC_INDEX.sub("[*]", identity))
```

The rule is the design's: a turn attempt started at or after the cut is affected (start order, protecting undeclared file dependencies); one started before the cut is affected when its allocation or recorded predecessor is in the suffix. For a closed `failed` attempt with a non-dispatched code the decision is driven by receipt facts, not by the failure code alone: an absent, `intent` or `not_dispatched` receipt is proven undispatched; anything else is uncertain and refused, whatever produced the row. `memo.invalidate_suffix`: `check_invalidation_suffix(snapshot, chosen, run_files, site_classes)` (local import) between the coordinator check and `repair_torn_tail`. The journal-only part of the same rule is mirrored by the reducer (Task 8, `check_invalidation_cut`), so a write that slipped past the preflight is still refused on replay.

- [ ] **Step 4: Amend `specs/cli.md` and the evaluated design C8 row (sections named in Files)**

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workflow_evaluated_agent_invalidate.py tests/test_workflow_evaluated_invalidate.py tests/test_workflow_evaluated_invalidate_smoke.py -q`
Expected: PASS (the ordinary invalidate suite is the regression control). `pytest tests/test_workflow_evaluated_agent_invalidate.py -q -k "receipt_past_intent or failed_before_dispatch"` → `2 passed`: the seeded run exits 1 with a `failed` row for `/ t` (`provider_exit_nonzero`, receipt `not_dispatched`); with the receipt tampered to `completed`, `invalidate <written>` exits 2 with `invalidate_agent_session_advanced` and "after launch" on stderr and the run-root tree is byte-identical; with the original receipt the same cut exits 0, the reducer re-reads the journal, and resume commits `t` at attempt 2 with three dispatches.

- [ ] **Step 6: Commit**

```bash
git add tests/test_workflow_evaluated_agent_invalidate.py orchestrator/workflow/evaluated/agent_guards.py
git commit -m "feat: refuse invalidation across advanced or committed agent turns before any write" -- orchestrator/workflow/evaluated/agent_guards.py orchestrator/workflow/evaluated/memo.py orchestrator/workflow/evaluated/resume_prefix.py specs/cli.md docs/design/workflow_lisp_evaluated_execution.md tests/test_workflow_evaluated_agent_invalidate.py
```

---

### Task 14: Views and readers show logical identities and continuation status

**Files:**
- Modify: `orchestrator/workflow/evaluated/views.py:156-186` (`_update_effect_row`: for `agent_turn` commits add `agent`, `predecessor`, `continuation` ∈ `initial`/`continued`, `locator_present: true`; never the locator or position; for `agent` commits add `agent: identity`)
- Modify: `orchestrator/cli/commands/report.py` only if its markdown renderer drops unknown row keys (keep them)
- Create: `tests/test_workflow_evaluated_agent_views.py`
- Modify (spec amendment): `specs/state.md` "Derived view" `steps` row (`:503`): "an `agent_turn` row adds `agent` (allocation identity), `predecessor` (turn identity or `null`) and `continuation` (`initial`/`continued`) from its proof; an `agent` row adds `agent`; no locator, position or tmux target ever enters the view"

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_agent_views.py
"""Readers show agent identity and continuation without locators; a pending unresolved turn is `running`."""
from __future__ import annotations

import json

from orchestrator.workflow.evaluated.views import load_evaluated_view
from tests.agent_session_shims import install_agent_shims
from tests.test_workflow_evaluated_agent_turns import PLAN, fixture, memo_of
from tests.test_workflow_evaluated_invalidate import _cli


def test_view_rows_carry_agent_identity_and_continuation_only(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 0
    run_root, *_ = memo_of(tmp_path)
    view = load_evaluated_view(run_root)
    rows = {k.rsplit("/ ", 1)[1]: v for k, v in view["steps"].items()}
    assert rows["a1"]["continuation"] == "initial" and rows["a2"]["continuation"] == "continued"
    assert rows["a2"]["predecessor"].endswith("/ a1") and rows["a2"]["agent"].endswith("/ designer")
    assert rows["designer"]["effect_class"] == "agent" and rows["designer"]["status"] == "completed"
    assert all(v["status"] == "completed" for v in rows.values())
    dumped = json.dumps(view)
    for forbidden in ("locator", "end_line", "turn_id", "%pane", "tmux"):
        assert forbidden not in dumped
    assert json.loads((run_root / "state.json").read_text())["steps"] == view["steps"]


def test_pending_unresolved_turn_is_running_and_report_succeeds(tmp_path, monkeypatch, capsys) -> None:
    plan = {"claude": [{"mode": "success", "result": {"text": "d1"}}, {"mode": "interrupted", "result": {}}], "codex": PLAN["codex"]}
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 1
    run_root, *_ = memo_of(tmp_path)
    view = load_evaluated_view(run_root)
    row = next(v for k, v in view["steps"].items() if k.endswith("/ a2"))
    assert row["status"] == "running" and view["status"] == "interrupted" and view["current_step"]["identity"].endswith("/ a2")
    report = _cli(tmp_path, "report", "--run-id", run_root.name, "--format", "json")
    assert report.returncode == 0, report.stderr
    assert json.loads(report.stdout)["progress"]["running"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_evaluated_agent_views.py -q`
Expected: FAIL — `KeyError: 'continuation'`.

- [ ] **Step 3: Implement**

```python
# orchestrator/workflow/evaluated/views.py (_update_effect_row, committed branch)
        if row["effect_class"] == "agent_turn":
            proof = row["proof"]
            target.update(agent=proof["agent"], predecessor=proof["predecessor"],
                          continuation="initial" if proof["predecessor"] is None else "continued")
        elif row["effect_class"] == "agent":
            target["agent"] = row["identity"]
```

- [ ] **Step 4: Amend `specs/state.md` derived view row (section named in Files)**

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workflow_evaluated_agent_views.py tests/test_workflow_evaluated_views.py tests/test_workflow_evaluated_readers.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_workflow_evaluated_agent_views.py
git commit -m "feat: show agent identity and continuation status in evaluated views" -- orchestrator/workflow/evaluated/views.py specs/state.md tests/test_workflow_evaluated_agent_views.py
```

---

### Task 15: One read-only tmux view per agent instance (D6) and observation wiring for evaluated runs

**Files:**
- Modify: `orchestrator/workflow/evaluated/runtime.py:80-85` (replace the inline `ProviderExecutor(workspace, ProviderRegistry(), provider_observation_enabled=False)` with `provider_executor_for_run(workspace, authority.run_root, agents_present=any(kind in {"agent", "agent_turn"} for kind in checked_site_classes.values()))`; close the manager and the agent views in the `finally`); `views` already reaches `PreparedAttempt` through the Task 10 context
- Modify: `orchestrator/workflow/evaluated/agent_turns.py` (add `AgentViews`)
- `orchestrator/providers/observation.py` is not modified (584 lines; the backend is injected through the existing `ProviderObservationManager(run_root, backend=...)` parameter)
- Modify: `orchestrator/workflow/evaluated/parallel.py:286-287` unchanged (workers cannot host agents; ordinary observation stays disabled there and is recorded as a limit in the spec amendment)
- Create: `tests/test_workflow_evaluated_agent_observation.py`
- Modify (spec amendment): `specs/observability.md:19-38` ("Provider observation (v2.16)"): new bullets — "An evaluated run whose checked program contains `agent`/`agent_turn` effects constructs the run-scoped observation manager best-effort; evaluated runs of programs without agents keep observation disabled as before, so 2.35–2.37 behaviour is unchanged (R2). Within an agent-bearing run, ordinary `provider-result` effects keep the one-invocation/one-pane contract. Each agent instance owns one logical read-only view: every turn of that agent appends to the same pane and transcript, with `--- turn <identity> attempt <n> ---` and `--- idle ---` boundary lines; invoking the agent again never opens a second pane. Attach is read-only (`tmux -S <socket> attach -r -t <session>`); the current socket and pane target are logged once per run at manager creation and are transient: a runtime restart may allocate a different pane/socket for the same logical agent, and targets never enter `Agent`, the memo or `state.json`. The view is derived from invocation-local streams and can never authorize, reconcile or dispatch a turn; every observation failure is best-effort. Parallel workers keep observation disabled."

**Interfaces:**
- Produces: `AgentViews(manager).handle_for(agent_identity, turn_identity, ordinal) -> ProviderObservationHandle | None`, `.idle(agent_identity)`, `.close()`; `runtime.provider_executor_for_run(workspace, run_root, *, agents_present) -> tuple[ProviderExecutor, ProviderObservationManager | None]`; `runtime.observation_backend() -> None` (module-level factory; `None` selects the tmux backend inside the manager; the tests' driver script replaces `runtime.observation_backend` with a file-only fake, the same in-process patching pattern as the kill-point hooks — no environment seam).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_agent_observation.py
"""Two logical views across four turns; ordinary calls keep one pane each; crash/resume may change targets, never redispatch."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.providers import observation as observation_module
from orchestrator.workflow.evaluated import runtime
from orchestrator.workflow.evaluated.agent_turns import AgentViews
from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_agent_turns import PLAN, SOURCE, fixture, memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli

# Driver: replaces the backend factory in-process (same pattern as the kill-point hooks); FAKE_BACKEND appends
# display bytes to the display file and hands out `%pane-N` targets; BROKEN_BACKEND raises on server start.
OBSERVE = r'''import os, sys
from orchestrator.workflow.evaluated import runtime
from tests.test_provider_observation import _FakeObservationBackend
backend = _FakeObservationBackend()
if os.environ["OBSERVATION_BACKEND"] == "broken":
    backend.start_error = RuntimeError("no tmux here")
runtime.observation_backend = lambda: backend
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


def _observed(root, backend, *argv):
    import os, subprocess, sys
    from tests.workflow_evaluated_consumer_sources import ROOT
    return subprocess.run([sys.executable, "-c", OBSERVE, *argv], cwd=root, capture_output=True, text=True, check=False,
                          env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "OBSERVATION_BACKEND": backend})


MIXED = SOURCE.replace("(b2 (provider-result reviewer :prompt (execute :text a2.text) :timeout-sec 60)))",
                       "(b2 (provider-result reviewer :prompt (execute :text a2.text) :timeout-sec 60))"
                       " (plain (provider-result providers.codex :prompt (execute :text a2.text) :timeout-sec 60)))").replace("b2)))", "plain)))")


def _views(run_root: Path):
    display = sorted((run_root / "provider-observation" / "display").glob("*.display"))
    return {p.name: p.read_bytes() for p in display}


def test_each_agent_has_one_view_across_its_turns_and_ordinary_calls_keep_one_pane(tmp_path, monkeypatch) -> None:
    plan = {"claude": PLAN["claude"], "codex": [*PLAN["codex"], {"mode": "success", "result": {"notes": ["plain"]}}]}
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)
    run = _observed(tmp_path, "fake", "run", *fixture(tmp_path, MIXED))
    assert run.returncode == 0, run.stderr
    run_root, *_ = memo_of(tmp_path)
    views = _views(run_root)
    assert len(views) == 3                                # designer view, reviewer view, one pane for `plain`
    agent_views = [v for v in views.values() if b"--- turn" in v]
    assert len(agent_views) == 2
    assert all(v.count(b"--- turn") == 2 and v.count(b"--- idle ---") == 2 for v in agent_views)   # boundaries and idle states
    assert len(shim_requests(tmp_path)) == 5
    assert "orc-observe-" in run.stderr                   # transient attach coordinates logged once, never persisted


def test_agent_free_evaluated_run_keeps_observation_disabled(tmp_path, monkeypatch) -> None:
    """R2: 2.35–2.37 behaviour unchanged — a program without agents constructs no manager."""
    from tests.test_workflow_evaluated_providers import SOURCE as PLAIN_SOURCE, _fixture
    _fixture(tmp_path, PLAIN_SOURCE)
    run = _observed(tmp_path, "fake", "run", "main.orc", "--source-root", str(tmp_path), "--provider-externs-file", "providers.json",
                    "--prompt-externs-file", "prompts.json", "--input", "message=typed input")
    assert run.returncode == 0, run.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    assert not (run_root / "provider-observation").exists()


def test_crash_and_resume_rebuilds_views_without_redispatch(tmp_path, monkeypatch) -> None:
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECORD, _stopped
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": "settled", "STOP_TURN": "/ b1"}, "run", *fixture(tmp_path))   # tmux absent or present: best effort
    run_root, *_ = memo_of(tmp_path)
    first = _views(run_root)
    assert _observed(tmp_path, "fake", "resume", run_root.name).returncode == 0
    after = _views(run_root)
    assert set(first) <= set(after) and len(after) == len(first) + 2   # two new views for the resumed process; old streams retained
    assert len(shim_requests(tmp_path)) == 4
    _r, _a, classes, memo = memo_of(tmp_path)
    assert all(v["attempt"] == 1 for v in turns(memo, classes).values())


def test_observation_failure_never_changes_execution(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    run = _observed(tmp_path, "broken", "run", *fixture(tmp_path))
    assert run.returncode == 0, run.stderr
    _r, _a, classes, memo = memo_of(tmp_path)
    assert set(turns(memo, classes)) == {"a1", "b1", "a2", "b2"}


def test_views_never_enter_memo_or_state(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=PLAN)
    assert _observed(tmp_path, "fake", "run", *fixture(tmp_path)).returncode == 0
    run_root, *_ = memo_of(tmp_path)
    text = (run_root / "memo.jsonl").read_text() + (run_root / "state.json").read_text()
    assert "%pane" not in text and "orc-observe" not in text
```

`_FakeObservationBackend` (`tests/test_provider_observation.py:21`) already records `open_pane` calls and keeps the display file as the pane's content; no production seam exists beyond the module-level `runtime.observation_backend` factory that returns `None` (tmux default).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_evaluated_agent_observation.py -q`
Expected: FAIL — no `provider-observation` directory under the run root (observation disabled).

- [ ] **Step 3: Implement**

```python
# orchestrator/workflow/evaluated/runtime.py
def observation_backend():
    """`None` selects the tmux backend inside the manager; test drivers replace this attribute in-process."""
    return None


def provider_executor_for_run(workspace, run_root, *, agents_present: bool):
    """One executor per run; observation only for agent-bearing programs (R2), best-effort, never changing execution."""
    manager = None
    if agents_present:
        from orchestrator.providers.observation import ProviderObservationManager
        try:
            manager = ProviderObservationManager(run_root, backend=observation_backend())
            logger.info("[provider_observation] session %s (socket under /tmp/orc-observe-*/tmux.sock; attach read-only with tmux -S <socket> attach -r -t %s)", manager.session_name, manager.session_name)
        except Exception:
            manager = None
    return ProviderExecutor(workspace, ProviderRegistry(), provider_observation_enabled=manager is not None,
                            observation_manager=manager), manager
```

```python
# orchestrator/workflow/evaluated/agent_turns.py
class AgentViews:
    """One pre-opened observation handle per agent instance for the life of this process."""

    def __init__(self, manager):
        self._manager, self._handles = manager, {}

    def handle_for(self, agent_identity, turn_identity, ordinal):
        if self._manager is None:
            return None
        handle = self._handles.get(agent_identity)
        if handle is None:
            try:
                digest = hashlib.sha256(agent_identity.encode("utf-8")).hexdigest()[:16]
                handle = self._manager.open_observation(invocation_id=f"agent-{digest}", member_id="agent", turn_id="all")
            except Exception:
                return None
            self._handles[agent_identity] = handle
        try:
            handle.append_display(f"\n--- turn {turn_identity} attempt {ordinal} ---\n".encode("utf-8"))
        except Exception:
            pass
        return handle

    def idle(self, agent_identity):
        handle = self._handles.get(agent_identity)
        if handle is not None:
            try:
                handle.append_display(b"\n--- idle ---\n")
            except Exception:
                pass

    def close(self):
        for handle in self._handles.values():
            try:
                handle.finalize()
            except Exception:
                pass
        self._handles.clear()
```

`execute_pure_run`: `provider_executor, manager = provider_executor_for_run(workspace, authority.run_root, agents_present=...)` lazily on the first provider/agent_turn effect (keep the lazy shape); `views = AgentViews(manager)`; `views` enters `PreparedAttempt` through the Task 10 context; `perform_turn` calls `views.idle(agent)` after the turn's result is read; in the `finally`: `views.close()` then `manager.close()` if not None. `wc -l orchestrator/workflow/evaluated/runtime.py` about 455 after this task.

- [ ] **Step 4: Amend `specs/observability.md` (section named in Files)**

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workflow_evaluated_agent_observation.py tests/test_provider_observation.py tests/test_provider_observation_execution.py tests/test_workflow_evaluated_providers.py -q`
Expected: PASS; ordinary evaluated provider tests still pass with observation enabled best-effort (tmux absent → manager None).

- [ ] **Step 6: Commit**

```bash
git add tests/test_workflow_evaluated_agent_observation.py
git commit -m "feat: give each agent instance one read-only tmux view and wire observation into agent-bearing evaluated runs" -- orchestrator/workflow/evaluated/runtime.py orchestrator/workflow/evaluated/agent_turns.py specs/observability.md tests/test_workflow_evaluated_agent_observation.py
```

---

### Task 16: The opt-in `design_review_execute` two-agent variant and its documentation rows

**Files:**
- Create: `workflows/examples/design_review_execute_agents.orc` (target `2.38`; same `defpath`/`defrecord`/`defprompt` declarations as `workflows/examples/design_review_execute.orc:21-50`, copied verbatim; workflow body below), `workflows/examples/inputs/design_review_execute_agents/inputs.json` (copy of `../design_review_execute/inputs.json`), `workflows/examples/inputs/design_review_execute_agents/providers.json` (same mapping: `providers.claude` → `claude_unrestricted_workspace`, `providers.codex` → `codex`)
- Create: `tests/test_workflow_lisp_design_review_execute_agents_example.py` (documented compile command → `sites == 6`)
- Modify: `tests/workflow_lisp_closed_program_corpus.py:81` (add `"workflows/examples/design_review_execute_agents.orc::run": Built(6)`)
- Modify: `workflows/README.md:61` (paragraph: name the variant) and the registry table at `:159-169` (new row)
- Modify: `docs/lisp_workflow_drafting_guide.md` (new subsection "### Agent sessions (target 2.38)" after "### Portable Provider Context" at `:1457`; the §2 availability table row at `:312-313` gains `agent`), `docs/capability_status_matrix.md:65` (status "Implemented at 2.38; qualification pending under PQ-1a", example column names the variant), `docs/index.md:52` and `docs/design/README.md:91` (status text), `docs/lisp_library_reference.md` (one task row "Keep one conversation across review and revise" pointing at the variant)

**Interfaces:**
- Consumes: everything above.
- Produces: the consumer used by Tasks 17–21.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_workflow_lisp_design_review_execute_agents_example.py
"""`design_review_execute_agents.orc`: the two-agent opt-in variant compiles with two allocations and four turns."""
from __future__ import annotations

import json, os, shlex, subprocess, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "workflows" / "examples" / "design_review_execute_agents.orc"
BASELINE = REPO_ROOT / "workflows" / "examples" / "design_review_execute.orc"


def test_documented_command_compiles_two_agents_and_four_turns() -> None:
    header = EXAMPLE.read_text(encoding="utf-8").split("python -m orchestrator compile", 1)[1].split("\n\n", 1)[0]
    argv = shlex.split("python -m orchestrator compile " + " ".join(line.strip(" ;\\") for line in header.splitlines()))
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, *argv[1:]], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    built = json.loads(result.stdout)
    assert (built["entry_workflow"], built["sites"], built["target"]) == ("design_review_execute_agents::run", 6, "2.38")


def test_variant_keeps_the_baseline_declarations_models_effort_and_timeouts() -> None:
    variant, baseline = EXAMPLE.read_text(), BASELINE.read_text()
    for declaration in ("(defpath DraftDocPath", "(defpath DesignDocPath", "(defrecord Draft", "(defrecord Design", "(defrecord Feedback", "(defrecord Execution"):
        assert declaration in variant
    for prompt in ("draft-design", "review-design", "revise-design", "execute-design"):
        start = baseline.index(f"(defprompt {prompt}"); end = baseline.index("\n\n", start)
        assert baseline[start:end] in variant
    assert '(planner_model String :default "claude-fable-5-1")' in variant and '(reviewer_model String :default "gpt-6.1-sol")' in variant
    assert variant.count(":timeout-sec 3600") == 3 and ":timeout-sec 14400" in variant
    assert ':effort "high"' in variant
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_workflow_lisp_design_review_execute_agents_example.py -q`
Expected: FAIL — file not found.

- [ ] **Step 3: Write the variant**

Header comment: the same explanation as the baseline plus "Opt-in variant: the designer and the reviewer each keep one native conversation (Agent Sessions, target 2.38); invalidating `feedback` is refused once `revised` committed (C8). The baseline `design_review_execute.orc` keeps four independent calls." and the documented command `python -m orchestrator compile workflows/examples/design_review_execute_agents.orc --provider-externs-file workflows/examples/inputs/design_review_execute_agents/providers.json`. Workflow body:

```lisp
  (defworkflow run
    ((task String)
     (planner_model String :default "claude-fable-5-1")
     (reviewer_model String :default "gpt-6.1-sol"))
    -> Execution
    (let* ((designer (agent providers.claude :model planner_model :effort "high"))
           (reviewer (agent providers.codex :model reviewer_model :effort "high"))
           (draft (provider-result designer :timeout-sec 3600
                    :prompt (draft-design :task task)))
           (feedback (provider-result reviewer :timeout-sec 3600
                       :prompt (review-design :task task :design draft.doc)))
           (revised (provider-result designer :timeout-sec 3600
                      :prompt (revise-design :task task :design draft.doc :draft_path draft.doc
                                             :blocking feedback.blocking :notes feedback.notes))))
      (provider-result reviewer :timeout-sec 14400
        :prompt (execute-design :task task :design revised.doc))))
```

- [ ] **Step 4: Documentation rows (design-spec-drafting: each names its section)**

- `workflows/README.md` registry table row: `| `workflows/examples/design_review_execute_agents.orc` | Workflow Lisp agent-sessions example; input-required; qualification pending (PQ-1a) | `2.38` | `design_review_execute_agents::run` | Opt-in variant of `design_review_execute.orc`: designer `Agent` on `claude_unrestricted_workspace` (draft, revise) and reviewer `Agent` on `codex` (review, execute), four typed committed turns, two tmux views. Same models, effort and timeouts as the baseline. Real execution needs both CLIs authenticated in the default home. |`
- Drafting guide "### Agent sessions (target 2.38)": when to choose an agent over artifact handoff (retained context across review/revise; cost: no invalidation after a committed turn, first-turn at-least-once); the constructor and turn surface; what is refused (overrides, escapes); link to the variant and to `specs/state.md` records; one sentence that `prompt-queue` is superseded.
- Capability matrix row `:65`: Status "Implemented at 2.38 (admission, runtime, C8 guards, views); PQ-1a qualification pending in `docs/plans/2026-10-14-agent-sessions-implementation-plan-b.md`"; Example "`workflows/examples/design_review_execute_agents.orc`".
- `docs/index.md:52`, `docs/design/README.md:91`: "implemented at 2.38; qualification gate pending".

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workflow_lisp_design_review_execute_agents_example.py tests/test_workflow_lisp_design_review_execute_example.py tests/test_workflow_lisp_closed_program_corpus.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add workflows/examples/design_review_execute_agents.orc workflows/examples/inputs/design_review_execute_agents tests/test_workflow_lisp_design_review_execute_agents_example.py
git commit -m "feat: add the opt-in two-agent design_review_execute variant at target 2.38" -- workflows/examples/design_review_execute_agents.orc workflows/examples/inputs/design_review_execute_agents tests/test_workflow_lisp_design_review_execute_agents_example.py tests/workflow_lisp_closed_program_corpus.py workflows/README.md docs/lisp_workflow_drafting_guide.md docs/capability_status_matrix.md docs/index.md docs/design/README.md docs/lisp_library_reference.md
```

---

### Task 17: Public compile → run → resume → invalidate smoke on the consumer with every failure-table row

**Files:**
- Create: `tests/test_workflow_evaluated_agent_consumer_smoke.py`
- Modify: `tests/workflow_evaluated_consumer_sources.py:130-160` (add `PROGRAMS["design_review_execute_agents"]` with `manifests={"providers": "workflows/examples/inputs/design_review_execute_agents/providers.json"}`, `prepare=` a function creating `docs/templates/design_template.md` and `AGENTS.md` stubs in the workspace)

**Interfaces:**
- Consumes: Plan A shims (`install_agent_shims`), `STOP_AFTER_RECORD`/`STOP_AFTER_RECEIPT`, Task 16 consumer.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_agent_consumer_smoke.py
"""PQ-1a deterministic gate: the real consumer through the public CLI with fake CLIs, every failure-table row and kill point."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECEIPT, STOP_AFTER_RECORD, _stopped
from tests.test_workflow_evaluated_agent_turns import memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes
from tests.workflow_evaluated_consumer_sources import PROGRAMS, install

DOC = "artifacts/design/slug.md"; FINAL = "docs/design/slug.md"
RESULTS = {
    "claude": [{"mode": "success", "result": {"doc": DOC}, "files": {DOC: "# draft\n"}},
               {"mode": "success", "result": {"doc": FINAL}, "files": {FINAL: "# final\n"}}],
    "codex": [{"mode": "success", "result": {"blocking": ["b1"], "notes": []}},
              {"mode": "success", "result": {"summary": "done", "commits": ["abc"], "checks_run": ["pytest"], "left_undone": []}}],
}


def _setup(tmp_path, monkeypatch, plan=RESULTS):
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)
    return install(tmp_path, PROGRAMS["design_review_execute_agents"], {"task": "t"}, current=True)


def test_clean_consumer_run_four_turns_two_sessions_lineage_and_readonly_resume(tmp_path, monkeypatch) -> None:
    frontend = _setup(tmp_path, monkeypatch)
    compiled = _cli(tmp_path, "compile", *frontend)
    assert compiled.returncode == 0 and json.loads(compiled.stdout)["sites"] == 6
    run = _cli(tmp_path, "run", *frontend, "--input-file", "inputs.json")
    assert run.returncode == 0, run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    t = turns(memo, classes)
    assert len(t) == 4 and {"draft", "feedback", "revised"} <= set(t)   # the final execute turn is the anonymous binding
    draft, revised = t["draft"], t["revised"]
    assert draft["value"] == {"doc": DOC} and revised["value"] == {"doc": FINAL}
    assert revised["proof"]["predecessor"] == draft["identity"] and draft["identity"] in revised["depends_on"]
    assert (tmp_path / DOC).read_text() == "# draft\n" and (tmp_path / FINAL).read_text() == "# final\n"
    requests = shim_requests(tmp_path)
    assert [r["tool"] for r in requests] == ["claude", "codex", "claude", "codex"] and len({r["session"] for r in requests}) == 2
    before = _tree_bytes(run_root)
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0 and _tree_bytes(run_root) == before


@pytest.mark.parametrize("tool, index, mode, expected", [
    ("codex", 0, "interrupted", "bootstrap"),          # reviewer first turn: unknown outcome -> bootstrap on resume
    ("codex", 0, "invalid-result", "bootstrap"),       # reviewer first turn: invalid typed result -> bootstrap on resume
    ("claude", 1, "interrupted", "agent_turn_unresolved"),       # designer second turn: refuse on resume
    ("claude", 1, "invalid-result", "agent_turn_result_invalid"),
    ("claude", 1, "overlap", "agent_session_diverged"),          # external advancement before revise -> refuse before dispatch
    ("claude", 1, "lose-locator", "agent_session_unavailable"),
    ("codex", 1, "nonzero-before-append", "resume_retries"),    # adapter proves the head unchanged: ordinary next attempt
    ("codex", 1, "nonzero", "agent_turn_unresolved"),           # open head after a nonzero exit: uncertainty, refuse
])
def test_failure_table_rows_through_the_public_cli(tmp_path, monkeypatch, tool, index, mode, expected) -> None:
    plan = {k: [dict(s) for s in v] for k, v in RESULTS.items()}
    plan[tool][index] = {**plan[tool][index], "mode": mode}
    if expected in {"bootstrap", "resume_retries"}:
        plan[tool].insert(index + 1, dict(RESULTS[tool][index]))      # the retry answers correctly
    if mode == "overlap":
        plan[tool][index]["mode"] = "success"
        # external advancement: run a foreign turn on the designer's session between draft and revise via a kill point
    frontend = _setup(tmp_path, monkeypatch, plan)
    if mode == "overlap":
        _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": "settled", "STOP_TURN": "/ feedback"}, "run", *frontend, "--input-file", "inputs.json")
        run_root, _a, classes, memo = memo_of(tmp_path)
        _foreign_append(tmp_path, turns(memo, classes)["draft"]["proof"]["locator"])
        resumed = _cli(tmp_path, "resume", run_root.name)
        assert resumed.returncode == 1 and "agent_session_diverged" in resumed.stderr
        assert len(shim_requests(tmp_path)) == 2
        return
    if mode == "lose-locator":
        _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": "settled", "STOP_TURN": "/ feedback"}, "run", *frontend, "--input-file", "inputs.json")
        run_root, _a, classes, memo = memo_of(tmp_path)
        _delete_store(tmp_path, turns(memo, classes)["draft"]["proof"]["locator"])
        resumed = _cli(tmp_path, "resume", run_root.name)
        assert resumed.returncode == 1 and "agent_session_unavailable" in resumed.stderr
        return
    run = _cli(tmp_path, "run", *frontend, "--input-file", "inputs.json")
    assert run.returncode == 1
    run_root, *_ = memo_of(tmp_path)
    resumed = _cli(tmp_path, "resume", run_root.name)
    if expected in {"bootstrap", "resume_retries"}:
        assert resumed.returncode == 0, resumed.stderr
        _r, _a, classes, memo = memo_of(tmp_path)
        assert memo.terminal.data["outcome"] == "completed" and len(turns(memo, classes)) == 4
        if expected == "bootstrap":
            assert "agent_bootstrap_restarted" in resumed.stderr or mode == "invalid-result"
    else:
        assert resumed.returncode == 2 and expected in resumed.stderr


def _foreign_append(root: Path, locator: str) -> None:
    path = next((root / "claude" / "projects").rglob(f"{locator}.jsonl"))
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    parent = rows[-1]["uuid"]
    rows += [{"type": "user", "uuid": "ext-u", "parentUuid": parent, "sessionId": locator, "promptId": "ext", "isSidechain": False, "message": {"role": "user", "content": "operator"}},
             {"type": "assistant", "uuid": "ext-a", "parentUuid": "ext-u", "sessionId": locator, "promptId": "ext", "isSidechain": False, "message": {"role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}}]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _delete_store(root: Path, locator: str) -> None:
    next((root / "claude" / "projects").rglob(f"{locator}.jsonl")).unlink()


@pytest.mark.parametrize("hook, env", [
    (STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "intent", "STOP_TURN": "/ feedback"}),
    (STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "completed", "STOP_TURN": "/ revised"}),
    (STOP_AFTER_RECORD, {"STOP_RECORD": "started", "STOP_TURN": "/ draft"}),
    (STOP_AFTER_RECORD, {"STOP_RECORD": "committed", "STOP_TURN": "/ revised"}),
    (STOP_AFTER_RECORD, {"STOP_RECORD": "settled", "STOP_TURN": "/ draft"}),
])
def test_every_kill_point_resumes_to_the_same_value_without_a_committed_turn_running_twice(tmp_path, monkeypatch, hook, env) -> None:
    frontend = _setup(tmp_path, monkeypatch)
    _stopped(tmp_path, hook, env, "run", *frontend, "--input-file", "inputs.json")
    run_root, *_ = memo_of(tmp_path)
    dispatched_before = shim_requests(tmp_path)
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _r, _a, classes, memo = memo_of(tmp_path)
    assert memo.terminal.data["value"]["summary"] == "done"
    assert len(shim_requests(tmp_path)) == 4          # no committed or completed turn ever runs twice
    t = turns(memo, classes)
    assert len(t) == 4 and all(v["attempt"] <= 2 for v in t.values())   # attempt 2 only for the pre-dispatch `started` stop


def test_invalidate_feedback_is_refused_after_revised_committed_but_baseline_consumer_can(tmp_path, monkeypatch) -> None:
    frontend = _setup(tmp_path, monkeypatch)
    assert _cli(tmp_path, "run", *frontend, "--input-file", "inputs.json").returncode == 0
    run_root, _a, classes, memo = memo_of(tmp_path)
    feedback = next(i for i in memo.active_commits if i.endswith("/ feedback"))
    refused = _cli(tmp_path, "invalidate", run_root.name, feedback)
    assert refused.returncode == 2 and "invalidate_coordinator_committed" in refused.stderr
```

`install(...)` for the new program must also install the stub files the prompts reference (`AGENTS.md`, `docs/index.md`, `docs/templates/design_template.md`) through `prepare`; the shims never read them, but path-typed results `DraftDocPath`/`DesignDocPath` have `:must-exist true`, so the plan writes the documents (`files` in the plan step, already supported by the shim `COMMON` block — add the `files` loop from `tests/workflow_evaluated_consumer_sources.py:SHIM` to `tests/agent_session_shims.py:COMMON` in this task).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_evaluated_agent_consumer_smoke.py -q -x`
Expected: FAIL — `KeyError: 'design_review_execute_agents'` until the PROGRAMS row exists; then the `files` support in the shim.

- [ ] **Step 3: Implement the fixtures** (PROGRAMS row, `prepare`, shim `files` support) and run again.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_evaluated_agent_consumer_smoke.py tests/test_workflow_evaluated_consumers.py tests/test_workflow_evaluated_invalidate_smoke.py -q` then `pytest --collect-only tests/test_workflow_evaluated_agent_consumer_smoke.py -q`.
Expected: PASS (17 items); the ordinary consumer and invalidate smokes are regression controls.

- [ ] **Step 5: Commit**

```bash
git add tests/test_workflow_evaluated_agent_consumer_smoke.py
git commit -m "test: prove the two-agent consumer through the public lifecycle with every failure row and kill point" -- tests/test_workflow_evaluated_agent_consumer_smoke.py tests/workflow_evaluated_consumer_sources.py tests/agent_session_shims.py
```

---

### Task 18: Broad verification and the deterministic PQ-1a record

**Files:**
- Create: `docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md`

- [ ] **Step 1:** In tmux: `pytest -q -n 16 --dist=worksteal` on the full suite; record counts versus the Plan A closeout baseline. Any new failure outside the agent modules is a regression to fix in the task that introduced it, not to skip.
- [ ] **Step 2:** Write the qualification record: per design failure-table row and per kill point, the test id that pins it (from Tasks 10–17), the adapter dispositions proved deterministically (lazy creation, sequential append, completion identification, turn-local contracts, compatible policy, locator-loss rejection, quiescence after timeout/cancel via the executor reap and `quiesce` on resume), what remains real-provider evidence (Tasks 19–20), the operator limit of the check-then-append window (D1), and the quiescence limit (R3): `quiesce` identifies the group by `pgid` plus the leader's recorded start time and never signals a live leader with a different start time; the residual limit is a leader that exec-replaced itself with an identical start time (still signalled, accepted by R3), and a platform without `/proc` falls back to process-group liveness alone. State explicitly: "deterministic proofs are mechanism proofs, not consumer proofs; no acceptance comparison has run".
- [ ] **Step 3:** Commit: `git add docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md && git commit -m "docs: record deterministic PQ-1a mechanism proofs for agent sessions" -- docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md`.

---

### Task 19: Bounded real-provider smoke — Claude adapter (paid, opt-in; authorized by D8)

**Files:**
- Create: `tests/e2e/test_agent_session_real_claude.py` (marker `e2e`, skipped unless `AGENT_SESSION_REAL_SMOKE=claude` or `both`)
- Modify: `docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md` (append the receipt-backed result)

- [ ] **Step 1: Write the gated test**

```python
# tests/e2e/test_agent_session_real_claude.py
"""One real Claude agent, two short turns; receipts and proofs from the real native store. Paid; opt-in."""
from __future__ import annotations

import json, os
from pathlib import Path

import pytest

from tests.test_workflow_evaluated_agent_turns import memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get("AGENT_SESSION_REAL_SMOKE") not in {"claude", "both"},
                                                   reason="set AGENT_SESSION_REAL_SMOKE=claude to spend one bounded real smoke")]

SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule main) (export run)
  (defrecord Word (word String))
  (defprompt first (:fills (seed :text)) -> Word "Remember the secret word {seed}. Reply with the word `ready` as `word`.")
  (defprompt second (:fills (again :text)) -> Word "What was the secret word I gave you earlier in this conversation? Return it as `word`. ({again})")
  (defworkflow run ((seed String)) -> Word
    (let* ((a (agent providers.claude :model "haiku" :effort "low"))
           (r1 (provider-result a :prompt (first :seed seed) :timeout-sec 300)))
      (provider-result a :prompt (second :again "no hints") :timeout-sec 300))))'''


def test_real_claude_agent_keeps_context_across_two_turns(tmp_path: Path) -> None:
    (tmp_path / "main.orc").write_text(SOURCE)
    (tmp_path / "providers.json").write_text(json.dumps({"providers.claude": "claude_unrestricted_workspace"}))
    run = _cli(tmp_path, "run", "main.orc", "--source-root", str(tmp_path), "--provider-externs-file", "providers.json", "--input", "seed=marmalade-7")
    assert run.returncode == 0, run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    t = turns(memo, classes)
    assert len(t) == 2 and "marmalade-7" in json.dumps(next(v for k, v in t.items() if not k.endswith("/ r1"))["value"]).lower()
    first, second = sorted(t.values(), key=lambda v: v["proof"]["position"]["end_line"])
    assert first["proof"]["locator"] == second["proof"]["locator"] and second["proof"]["predecessor"] == first["identity"]
    assert Path.home().joinpath(".claude", "projects").exists()
    for row in t.values():
        receipt = json.loads((run_root / Path(row["result_path"]).parent / "receipt.json").read_text())
        assert receipt["completion"] == "completed" and receipt["locator"] == row["proof"]["locator"]
```

- [ ] **Step 2:** Run in tmux: `AGENT_SESSION_REAL_SMOKE=claude pytest tests/e2e/test_agent_session_real_claude.py -q -m e2e` (two short turns on `haiku`). Expected: PASS; copy the run root's `memo.jsonl` proofs and receipts (locator redacted to its first 8 characters) into the qualification record with the CLI version (`claude --version`).
- [ ] **Step 3:** Commit: `git add tests/e2e/test_agent_session_real_claude.py && git commit -m "test: add the opt-in bounded real Claude agent-session smoke" -- tests/e2e/test_agent_session_real_claude.py docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md`.

---

### Task 20: Bounded real-provider smoke — Codex adapter (paid, opt-in; authorized by D8)

**Files:**
- Create: `tests/e2e/test_agent_session_real_codex.py` (code in Step 1; gate value `codex`/`both`)
- Modify: the qualification record

- [ ] **Step 1:** Write the test:

```python
# tests/e2e/test_agent_session_real_codex.py
"""One real Codex agent, two short turns; receipts and proofs from the real native store. Paid; opt-in."""
from __future__ import annotations

import json, os
from pathlib import Path

import pytest

from tests.test_workflow_evaluated_agent_turns import memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli
from tests.e2e.test_agent_session_real_claude import SOURCE as CLAUDE_SOURCE

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get("AGENT_SESSION_REAL_SMOKE") not in {"codex", "both"},
                                                   reason="set AGENT_SESSION_REAL_SMOKE=codex to spend one bounded real smoke")]

SOURCE = CLAUDE_SOURCE.replace('(agent providers.claude :model "haiku" :effort "low")', '(agent providers.codex :model "gpt-5.5" :effort "low")')


def test_real_codex_agent_keeps_context_across_two_turns(tmp_path: Path) -> None:
    (tmp_path / "main.orc").write_text(SOURCE)
    (tmp_path / "providers.json").write_text(json.dumps({"providers.codex": "codex"}))
    run = _cli(tmp_path, "run", "main.orc", "--source-root", str(tmp_path), "--provider-externs-file", "providers.json", "--input", "seed=marmalade-7")
    assert run.returncode == 0, run.stderr
    run_root, _a, classes, memo = memo_of(tmp_path)
    t = turns(memo, classes)
    assert len(t) == 2 and "marmalade-7" in json.dumps(next(v for k, v in t.items() if not k.endswith("/ r1"))["value"]).lower()
    first, second = sorted(t.values(), key=lambda v: v["proof"]["position"]["end_line"])
    assert first["proof"]["locator"] == second["proof"]["locator"] and second["proof"]["predecessor"] == first["identity"]
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    assert any(first["proof"]["locator"] in p.name for p in (home / "sessions").rglob("rollout-*.jsonl"))
    for row in t.values():
        receipt = json.loads((run_root / Path(row["result_path"]).parent / "receipt.json").read_text())
        assert receipt["completion"] == "completed" and receipt["locator"] == row["proof"]["locator"] and receipt["pgid"] is not None
```
- [ ] **Step 2:** Run in tmux: `AGENT_SESSION_REAL_SMOKE=codex pytest tests/e2e/test_agent_session_real_codex.py -q -m e2e`. Expected: PASS; record proofs/receipts and `codex --version`.
- [ ] **Step 3:** Commit: `git add tests/e2e/test_agent_session_real_codex.py && git commit -m "test: add the opt-in bounded real Codex agent-session smoke" -- tests/e2e/test_agent_session_real_codex.py docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md`.

---

### Task 21: Name the acceptance-comparison gate, close routing, and stop

**Files:**
- Modify: `docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md` PQ-1 (`:614-660`): status "first slice implemented; PQ-1a deterministic proofs and adapter smokes recorded in the qualification report; acceptance comparison (PQ-1c) not run"
- Modify: `docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md` (final section "Acceptance comparison gate — not authorized by this plan")
- Modify: `specs/versioning.md` 2.38 rows (Task 1) to point at the qualification record; `docs/capability_status_matrix.md:65` evidence column
- Modify (design and doc leftovers, M9): `docs/design/workflow_lisp_agent_sessions.md` — Context And Authority: "the built-in Claude template has no `session_support`" becomes "`claude_unrestricted_workspace` carries `session_support` (plain `claude` templates do not)"; Authoring position table: add the row "Loop state (`loop-state` fields, `loop/recur` outputs) | Refused in the first slice; an outside handle is reused lexically inside the loop body"; Architecture: add "The adapters honour `CODEX_HOME`/`CLAUDE_CONFIG_DIR` only when already present in the orchestrator's environment; the orchestrator never sets them (D7)"; Persistence: add "Replay validation performs every journal-only guard; receipt-based guards run at write preflight and at resume-time prefix validation (R1). The journal cannot bind a `started` row to its agent, so the reducer's allocation guard requires only some active allocation; the receipt and the committed proof carry the binding"; `docs/design/workflow_lisp_evaluated_execution.md:1025` "only `run_ref` is a coordinator in the first release" → "`run_ref`, and at target 2.38 `agent_turn`, are coordinators"; `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md:113` follow-on paragraph: first slice implemented, gate pending

- [ ] **Step 1: Write the gate** in the qualification record, verbatim contract:
  - Runs required: the variant `design_review_execute_agents.orc` and the baseline `design_review_execute.orc` on the same task input, same models/effort/timeouts, (a) one clean run each, (b) one failed/resumed run each (kill after the first reviewer turn commits; resume), both with real providers.
  - Evidence per run: run root (memo, receipts, attempt files), elapsed time per turn, provider usage from each CLI's native accounting, the produced documents, the four typed results, dispatch counts, any `agent_bootstrap_restarted`/`effect_rerun` rows, and for the variant the refusal of `invalidate <feedback>`.
  - Axes judged (PQ-1c): retained useful context, repeated investigation, friction, elapsed time, total provider usage (first-turn repeats included), inability to invalidate feedback after session commits.
  - Decision rule: acceptance requires both clean and failed/resumed evidence plus an explicit owner judgment that retained context justifies lost suffix recoverability and any repeated paid work; a clean success alone is insufficient. Outcomes: retain, improve, or retire (PQ-1c).
  - Authorization: the owner authorizes these runs separately (D8). This plan stops here.
- [ ] **Step 2:** Update the PQ-1 status paragraph, the matrix/versioning evidence pointers and the design/doc leftovers listed in Files.
- [ ] **Step 3:** Final inspection: `git diff --stat <plan A first commit>..HEAD -- orchestrator tests specs docs workflows`, `wc -l` on every touched module (every module this plan created or that was under 500 before stays <= 500; modules already over 500 grew by their dispatch lines only), the stdlib complexity check (Global Constraints) on `runtime.py`, `agent_turns.py`, `agent_guards.py`, `memo_reducer.py`; then commit: `git commit -m "docs: name the agent-sessions acceptance gate and record first-slice delivery status" -- docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md specs/versioning.md docs/capability_status_matrix.md docs/design/workflow_lisp_agent_sessions.md docs/design/workflow_lisp_evaluated_execution.md docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`.

Follow-on (not in this plan): second slice, the `reviewed_change` coder variant (coder `Agent` on Claude, independent reviewer unchanged, turn shape selected then).

---

## Conflicts surfaced

1. Resolved by coordinator ruling R1: the pure reducer performs every journal-only guard (Task 8: K8 for both classes, same-agent predecessor without forks, `started` only against an active allocation, invalidation cuts over pending/dispatched-failed agent attempts); receipt-based guards run at write preflight (`invalidate_suffix`) and at resume-time prefix validation (`validate_prefix_receipts`), both in Task 13. Task 21 records this in the design.
2. `specs/cli.md` "Resume preflight precedence" promises a read-only preflight, while the design's bootstrap policy says "Resume completes this ordering after a crash" (abandon → `failed` → `started`). Plan B keeps preflight read-only (classification only) and performs the bootstrap writes under the same writer lock inside `prepare_effect`, before the next `started` (Tasks 11–12). Spec amended accordingly.
3. The design's position table does not list loop-state carriage of an `Agent`; Plan A refuses it (conservative, first slice). Task 21 adds the row to the design.
4. D7 says no per-run `CODEX_HOME`/`CLAUDE_CONFIG_DIR`; deterministic tests need an isolated store, so the adapters honor those variables when already present in the orchestrator's environment (never set per run). Task 21 records this in the design.
5. The design (Context And Authority) says the built-in Claude template has no `session_support`; the consumer maps `providers.claude` to `claude_unrestricted_workspace`, so that template receives `session_support` (Plan A Task 4); the plain `claude` templates stay without it. Task 21 updates the sentence.
6. Observation scope (reviewer I13) resolved by coordinator ruling R2: the manager is constructed only for agent-bearing programs (Task 15).
7. Claude completion marker for the plain `stream-json` form (reviewer I11) resolved by owner decision D8a: Plan A Task 6a observes it before Plan B starts; the adapter treats `end_turn` as a hypothesis until then.
