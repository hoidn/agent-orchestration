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
    (let* ((designer (agent providers.claude :model "planner" :effort "high"))
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
    (let* ((designer (agent providers.claude :model "planner" :effort "high"))
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
    source = SOURCE.replace("(b2 (provider-result reviewer :prompt (execute :text a2.text) :timeout-sec 60)))", "(spare (agent providers.codex :model \"x\" :effort \"high\")) (b2 b1))")
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
        receipt.unlink()                                # settled replay needs no receipt sidecar (the inline proof decides)
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0 and len(shim_requests(tmp_path)) == 4


def test_pending_turn_after_a_kill_is_refused_by_preflight_and_the_row_would_not_reduce(tmp_path, monkeypatch) -> None:
    """NEW-I2 agreement proof: the preflight refuses; a forged `invalidated` row over the same journal is memo_inconsistent on read."""
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECEIPT, _stopped
    from orchestrator.workflow.evaluated.memo import MemoError, read_memo
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    _install(tmp_path, monkeypatch)
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "intent", "STOP_TURN": "/ a1"}, "run", *fixture(tmp_path))
    run_root, _a, classes, memo = memo_of(tmp_path)
    assert next(iter(memo.pending_starts)).endswith("/ a1")       # no committed turn after the reviewer allocation
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
    # resume reconciles the pending designer turn (`intent` receipt: never dispatched -> closed failed -> next attempt)
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
    assert turns(after, classes)["t"]["attempt"] == 2
    assert len((tmp_path / "bin" / ".claude.calls").read_text()) == 3     # nonzero-before-append exits before the request log


def test_unreadable_required_receipt_is_memo_inconsistent(tmp_path, monkeypatch) -> None:
    """A turn failed with a non-dispatched code inside the suffix is cut only on receipt proof; unreadable -> memo_inconsistent."""
    _install(tmp_path, monkeypatch, SEEDED_NONZERO)
    (tmp_path / "write.py").write_text(WRITE)
    (tmp_path / "commands.json").write_text(json.dumps({"write": {"stable_command": ["python", "write.py"], "closure": ["write.py"]}}))
    assert _cli(tmp_path, "run", *fixture(tmp_path, SEEDED_FILE_DEP), "--command-boundaries-file", "commands.json").returncode == 1
    run_root, _a, _c, memo = memo_of(tmp_path)
    (failed,) = [e.data for e in memo.entries if e.data["record"] == "failed"]
    (run_root / Path(memo.latest_starts[failed["identity"]].data["result_path"]).parent / "receipt.json").write_text("{not json")
    before = _tree_bytes(run_root)
    refused = _cli(tmp_path, "invalidate", run_root.name, _identity(memo, "/ written"))
    assert refused.returncode == 2 and "memo_inconsistent" in refused.stderr
    assert _tree_bytes(run_root) == before



def test_resume_refuses_a_bootstrap_restart_without_its_abandoned_marker(tmp_path, monkeypatch) -> None:
    """A `failed agent_bootstrap_restarted` attempt must carry `abandoned.json` and a dispatched receipt; resume refuses
    `memo_inconsistent` before any write (the bootstrap would otherwise recreate the marker)."""
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECORD, _stopped
    _install(tmp_path, monkeypatch, {"claude": [{"mode": "interrupted", "result": {}}, *PLAN["claude"]], "codex": PLAN["codex"]})
    assert _cli(tmp_path, "run", *fixture(tmp_path)).returncode == 1
    run_root, *_ = memo_of(tmp_path)
    _stopped(tmp_path, STOP_AFTER_RECORD, {"STOP_RECORD": "failed", "STOP_TURN": "/ a1"}, "resume", run_root.name)
    _r, _a, _c, memo = memo_of(tmp_path)
    (failed,) = [e.data for e in memo.entries if e.data["record"] == "failed"]
    assert failed["code"] == "agent_bootstrap_restarted" and not memo.pending_starts
    (marker,) = run_root.rglob("abandoned.json")
    marker.unlink()
    before = _tree_bytes(run_root)
    resumed = _cli(tmp_path, "resume", run_root.name)
    assert resumed.returncode == 2 and "memo_inconsistent" in resumed.stderr
    assert _tree_bytes(run_root) == before
