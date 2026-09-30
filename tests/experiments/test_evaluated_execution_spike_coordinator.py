"""Spike of evaluated execution, iteration 2, item D1: an effect that wraps a coordinator with its own ledger.

Throwaway. The coordinator is the run reference (`run-ref`) runtime, unchanged: its
ledger `run-ref-attempts.jsonl`, its pending commit `completed_pending_parent_commit`
and its final commit `committed` after the parent's own commit. The child run is the
stand-in of the runtime's tests (`_RuntimeHarness`: a materializer and a child
launcher that count launches). The run-ref form is not compiled: no program reaches it
with stand-ins in the spike, so the closed program is written by hand, one run-ref
effect whose value is the workflow's value.

The evaluator drives the coordinator through three calls: `prepare` (the coordinator
runs the child and writes its pending commit), the memo's `committed`, then `settle`
(the coordinator's final commit). On resume, a memo hit calls `reconcile`. The visit
key of the coordinator is derived from the effect's identity.

The process stops (in-process, by raising from the evaluator's hook) at each moment;
both the ledger and the memo are synchronized files, so what they hold is what a kill
would leave.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.evaluated_execution_spike.evaluator import evaluate
from experiments.evaluated_execution_spike.memo import read_records
from experiments.evaluated_execution_spike.sites import ClosedProgram, canonical_digest
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey, load_attempt_ledger
from orchestrator.workflow.run_ref.runtime import (
    finalize_run_ref_parent_commit,
    prepare_run_ref_settlement,
    validate_completed_run_ref_authority,
)
from tests.experiments.test_evaluated_execution_spike_resume import Interrupt, stop_at
from tests.test_workflow_run_ref_runtime import _runtime_request, _RuntimeHarness

SITE = "coord::run / child"
TREE = {
    "schema": "evaluated-execution-spike/closed-program/1",
    "entry": "coord::run",
    "params": [],
    "defaults": {},
    "result": {"kind": "primitive", "name": "String"},
    "body": {
        "k": "let",
        "name": "child",
        "value": {"k": "perform", "class": "run_ref", "result": {"kind": "primitive", "name": "String"},
                  "site": SITE, "repeat": "rerun"},
        "body": {"k": "halt", "value": {"k": "name", "n": "child"}},
    },
}
PROGRAM = ClosedProgram(tree=TREE, sites=(SITE,), digest=canonical_digest(TREE))


_MKDIR = Path.mkdir


def _mkdir_existing(path: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False) -> None:
    _MKDIR(path, mode, parents, True)


class RunRefCoordinator:
    """The run-ref runtime behind the evaluator's coordinator calls.

    `settle_first`: the other order, the coordinator's final commit before the memo's `committed`.
    `reconcile_on_hit`: whether a memo hit reconciles a pending ledger row, as the flat route's resume does.
    """

    def __init__(self, root: Path, *, settle_first: bool = False, reconcile_on_hit: bool = True) -> None:
        root.mkdir(parents=True, exist_ok=True)
        with patch.object(Path, "mkdir", _mkdir_existing):  # a new process builds the same request again
            self.base = _runtime_request(root)
        self.harness = _RuntimeHarness()
        self.settle_first, self.reconcile_on_hit = settle_first, reconcile_on_hit
        self.prepared = {}

    def request(self, identity: str):
        step_id = "root." + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        visit = RunRefVisitKey(parent_run_id="parent-run", execution_frame_id="root", call_frame_id=None,
                               step_id=step_id, visit_count=1)
        return replace(self.base, visit=visit)

    def prepare(self, node, resolved, identity, attempt):
        request = self.request(identity)
        prepared = prepare_run_ref_settlement(request, dependencies=self.harness.dependencies())
        self.prepared[identity] = (request, prepared)
        proof = {"settled_result": prepared.settled_result.record, "artifacts": dict(prepared.artifacts)}
        if self.settle_first:
            self.settle(node, identity, proof)
        return prepared.envelope["value"], None, proof

    def settle(self, node, identity, proof):
        request, prepared = self.prepared[identity]
        if load_attempt_ledger(request.ledger_path).rows[-1].stage != "committed":
            finalize_run_ref_parent_commit(request, prepared, persisted_settled_result=proof["settled_result"])

    def reconcile(self, node, resolved, identity, proof):
        if self.reconcile_on_hit:
            validate_completed_run_ref_authority(self.request(identity), settled_result=proof["settled_result"],
                                                 artifacts=proof["artifacts"], reconcile_pending=True)

    def ledger(self, identity: str) -> list[tuple[int, str]]:
        rows = load_attempt_ledger(self.request(identity).ledger_path).rows
        return [(row.attempt_ordinal, row.stage) for row in rows if row.stage in (
            "launched", "completed_pending_parent_commit", "committed") or row.status == "discarded"]


def run(root: Path, coordinator: RunRefCoordinator, *, hook=None):
    return evaluate(PROGRAM, inputs={}, workspace=root, run_root=root / "run", hook=hook,
                    coordinators={"run_ref": coordinator})


def memo(root: Path) -> list[tuple[str, int]]:
    return [(r["record"], r.get("attempt")) for r in read_records(root / "run")]


def test_uninterrupted_the_memo_commit_sits_between_the_coordinators_two_commits(tmp_path: Path) -> None:
    coordinator = RunRefCoordinator(tmp_path / "coordinator")

    result = run(tmp_path, coordinator)

    assert (result.value, len(coordinator.harness.launches)) == ("artifacts/work/result.txt", 1)
    assert coordinator.ledger(SITE) == [(1, "launched"), (1, "completed_pending_parent_commit"), (1, "committed")]
    assert memo(tmp_path) == [("started", 1), ("committed", 1), ("settled", 1), ("terminal", None)]


def test_stopped_after_the_coordinators_pending_commit_the_child_runs_again_and_both_sides_agree(tmp_path: Path) -> None:
    """The memo has no commit, the ledger a pending one: resume discards the pending attempt and starts a child."""

    coordinator = RunRefCoordinator(tmp_path / "coordinator")
    with pytest.raises(Interrupt):
        run(tmp_path, coordinator, hook=stop_at("finished"))
    assert coordinator.ledger(SITE)[-1] == (1, "completed_pending_parent_commit")

    result = run(tmp_path, coordinator)

    assert (result.value, len(coordinator.harness.launches)) == ("artifacts/work/result.txt", 2)
    assert coordinator.ledger(SITE)[-4:] == [
        (1, "completed_pending_parent_commit"), (2, "launched"), (2, "completed_pending_parent_commit"), (2, "committed")
    ]
    assert [row for row in coordinator.ledger(SITE) if row[1] not in ("launched", "completed_pending_parent_commit",
                                                                       "committed")] == []
    assert memo(tmp_path) == [("started", 1), ("started", 2), ("committed", 2), ("settled", 2), ("terminal", None)]


@pytest.mark.parametrize("reconcile", [True, False], ids=["reconciled", "not-reconciled"])
def test_stopped_after_the_memo_commit_no_child_runs_again_and_the_ledger_agrees_only_when_reconciled(
    tmp_path: Path, reconcile: bool
) -> None:
    coordinator = RunRefCoordinator(tmp_path / "coordinator", reconcile_on_hit=reconcile)
    with pytest.raises(Interrupt):
        run(tmp_path, coordinator, hook=stop_at("committed"))
    assert coordinator.ledger(SITE)[-1] == (1, "completed_pending_parent_commit")

    result = run(tmp_path, coordinator)

    assert (result.value, len(coordinator.harness.launches)) == ("artifacts/work/result.txt", 1)
    assert coordinator.ledger(SITE)[-1] == ((1, "committed") if reconcile else (1, "completed_pending_parent_commit"))


def test_in_the_other_order_the_coordinator_refuses_the_rerun_that_the_memo_asks_for(tmp_path: Path) -> None:
    """The coordinator commits before the memo. Stopped between them, the memo has no commit and asks for a new
    attempt; the coordinator refuses a second attempt of a committed visit. The run cannot go on: they disagree,
    the coordinator's refusal wins, and no child runs twice."""

    from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError

    coordinator = RunRefCoordinator(tmp_path / "coordinator", settle_first=True)
    with pytest.raises(Interrupt):
        run(tmp_path, coordinator, hook=stop_at("finished"))
    assert coordinator.ledger(SITE)[-1] == (1, "committed")

    with pytest.raises(RunRefRuntimeError, match="an attempt is already active or committed for this visit"):
        run(tmp_path, coordinator)

    assert (len(coordinator.harness.launches), memo(tmp_path)) == (1, [("started", 1), ("started", 2)])
