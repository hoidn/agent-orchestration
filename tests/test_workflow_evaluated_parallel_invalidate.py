"""Public `orchestrator invalidate` over a parallel map keeps C8 whole-suffix semantics."""

from __future__ import annotations

from collections import Counter

from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes
from tests.workflow_evaluated_parallel_kill_helpers import Batch, committed, item_of
from tests.workflow_evaluated_recovery_helpers import resume


TWO_BY_TWO = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule main) (export run)
  (defworkflow worker ((repo String)) -> Int
    (let* ((first (command-result step :argv ("python" "step.py" repo "first") :returns Int)))
      (command-result step :argv ("python" "step.py" repo "second" first) :returns Int)))
  (defworkflow run () -> List[Int]
    (list/map-effect ((repo (list "a" "b"))) :max 2 :parallel 2 :workspace repo
      (call worker :repo repo))))
'''
# Each step waits for this many earlier commits, so the journal interleaves a1, b1, a2, b2.
WAITS = {("a", "first"): 0, ("b", "first"): 1, ("a", "second"): 2, ("b", "second"): 3}


def test_invalidate_cancels_the_whole_suffix_across_interleaved_items(tmp_path):
    batch = Batch(tmp_path, source=TWO_BY_TWO, items=("a", "b"), waits=WAITS)
    result = batch.run()
    assert result.returncode == 0, result.stderr
    rows = committed(batch.snapshot())
    assert [(item_of(row["identity"]), row["value"]) for row in rows] == [("a", 1), ("b", 20), ("a", 2), ("b", 21)]
    anchor = rows[2]["identity"]

    invalidated = _cli(batch.ws, "invalidate", batch.run_root().name, anchor)

    assert invalidated.returncode == 0, invalidated.stderr
    after = batch.snapshot()
    assert set(after.active_commits) == {rows[0]["identity"], rows[1]["identity"]}
    assert after.terminal is None
    resumed = resume(batch.ws, batch.run_root().name)
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert batch.snapshot().terminal.data["value"] == [2, 21]
    assert Counter(batch.dispatches()) == {
        ("a", "first"): 1, ("b", "first"): 1, ("a", "second"): 2, ("b", "second"): 2}


def test_invalidate_refuses_a_committed_run_reference_suffix(tmp_path):
    from tests.test_workflow_evaluated_cli import _run_cli
    from tests.test_workflow_evaluated_parallel_run_ref import _parallel_e1_fixture
    from tests.test_workflow_evaluated_run_ref import _authority
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, snapshot = _authority(parent)
    identities = [row["identity"] for row in committed(snapshot)]
    assert len(identities) == 2
    before = _tree_bytes(parent), _tree_bytes(refs)
    for anchor in identities:
        refused = _cli(parent, "invalidate", authority.run_root.name, anchor)
        assert refused.returncode == 2 and "invalidate_coordinator_committed" in refused.stderr
        assert (_tree_bytes(parent), _tree_bytes(refs)) == before
