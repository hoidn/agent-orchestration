"""External SIGKILL at real run-ref parent settlement gaps."""

import hashlib
import json
import os
from pathlib import Path
import signal

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_run_ref import _authority, _repeated_fixture
from tests.workflow_evaluated_run_ref_helpers import (
    _assert_no_child_resume, _json_lines, _kill_own_group, _run_to_exit,
    _start_cli, _wait_for_marker,
)


def _assert_child_terminal(request, child_result, expected_input, child_target):
    version = "v1" if child_target == "2.24" else "v2"
    assert child_result["schema_version"] == f"run_ref_path_child_result.{version}"
    assert child_result["workflow_outputs"] == {"__result__": expected_input}
    child_root = Path(request["child_state_dir"]) / request["child_run_id"]
    if child_target == "2.24":
        assert json.loads((child_root / "state.json").read_bytes())["status"] == "completed"
    else:
        child_authority = load_run_authority(child_root)
        child_memo = read_memo(child_authority.memo_path, site_classes(child_authority.program))
        assert child_memo.terminal.data == {
            "record": "terminal", "outcome": "completed", "value": expected_input,
        }


def _assert_attempt_manifest(attempt_root, manifest, bindings, request):
    delta = json.loads((attempt_root / "workspace-delta.json").read_bytes())
    accounting = json.loads((attempt_root / "accounting.json").read_bytes())
    assert canonical_sha256(manifest) == bindings.evidence_manifest_digest
    assert manifest["workspace_delta_digest"] == bindings.workspace_delta_digest
    assert delta["base"]["resolved_commit_sha"] == request["materialized_source"]["resolved_commit_sha"]
    assert accounting["provider_attempts"] == "UNKNOWN"
    assert accounting["token_usage"] == "UNKNOWN"
    assert accounting["cost"] == "UNKNOWN"
    assert not (attempt_root / "disposition.json").exists()


def _assert_attempt_evidence(row, *, identity, expected_input, child_target):
    attempt_root = row.bindings.workspace_path.parent
    request_bytes = (attempt_root / "child-request.json").read_bytes()
    request = json.loads(request_bytes)
    child_result = json.loads((attempt_root / "child-result.json").read_bytes())
    manifest = json.loads((attempt_root / "evidence-manifest.json").read_bytes())
    assert request["parent_authority"]["identity"] == identity
    assert request["parent_authority"]["attempt"] == 1
    assert request["inputs"]["flag"] is expected_input
    assert request["child_run_id"] == row.bindings.child_run_id
    _assert_child_terminal(request, child_result, expected_input, child_target)
    _assert_attempt_manifest(attempt_root, manifest, row.bindings, request)
    return {"attempt_root": attempt_root, "request": request,
            "request_sha256": hashlib.sha256(request_bytes).hexdigest()}


def _assert_committed_prefix(memo, gap, identity):
    assert memo.terminal is None
    commits = [entry.data for entry in memo.entries if entry.data["record"] == "committed"]
    assert len(commits) == (1 if gap == "pending" else 2)
    first = commits[0]
    assert first["identity"] != identity
    assert (first["identity"], first["attempt"]) in memo.settlements
    starts = [entry.data for entry in memo.entries if entry.data["record"] == "started"]
    assert {row["identity"] for row in starts} == {first["identity"], identity}
    return first, commits


def _assert_second_memo_window(memo, commits, marker, gap):
    identity = marker["identity"]
    second = next((row for row in commits if row["identity"] == identity), None)
    assert (second is None) == (gap == "pending")
    if second is not None:
        assert (identity, second["attempt"]) not in memo.settlements
        assert second["proof"]["settled_result"]["visit"] == marker["visit"]
    assert marker["gap"] == gap
    assert marker["attempt_ordinal"] == 1
    assert marker["visit"]["visit_count"] == 1
    return second


def _assert_ledger_window(authority, first, marker):
    ledger = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    first_visit = first["proof"]["settled_result"]["visit"]
    first_rows = [row for row in ledger.rows if row.visit.record == first_visit]
    pending_rows = [row for row in ledger.rows if row.visit.record == marker["visit"]]
    assert first_rows[-1].stage == "committed" and first_rows[-1].status == "committed"
    assert pending_rows[-1].stage == "completed_pending_parent_commit"
    assert pending_rows[-1].attempt_ordinal == marker["attempt_ordinal"]
    assert pending_rows[-1].status == "pending_parent_commit"
    return first_rows, pending_rows


def _assert_launch_binding(launch, info, pgid, identities):
    assert launch["pid"] > 0 and launch["pgid"] == launch["runner_pgid"] == pgid
    assert "--path-request" in launch["argv"]
    assert launch["request_path"] == str(info["attempt_root"] / "child-request.json")
    assert launch["request_sha256"] == info["request_sha256"]
    assert launch["parent_authority"]["identity"] in identities


def _assert_launch_window(control, pgid, first_rows, pending_rows, first_info, pending_info):
    launches = _json_lines(control / "launches.jsonl")
    assert len(launches) == 2
    assert [row["child_run_id"] for row in launches] == [
        first_rows[-1].bindings.child_run_id, pending_rows[-1].bindings.child_run_id,
    ]
    identities = {first_info["request"]["parent_authority"]["identity"], pending_info["request"]["parent_authority"]["identity"]}
    for launch, info in zip(launches, (first_info, pending_info), strict=True):
        _assert_launch_binding(launch, info, pgid, identities)
    assert len(_json_lines(control / "finalize.jsonl")) == 1
    assert not _json_lines(control / "reconcile.jsonl")


def _assert_kill_window(parent, control, marker, pgid, gap, child_target):
    authority, memo = _authority(parent)
    assert len(site_classes(authority.program)) == 1
    first, commits = _assert_committed_prefix(memo, gap, marker["identity"])
    second = _assert_second_memo_window(memo, commits, marker, gap)
    first_rows, pending_rows = _assert_ledger_window(authority, first, marker)
    assert pending_rows[-1].visit != first_rows[-1].visit
    assert first_rows[-1].visit.record["step_id"] != marker["visit"]["step_id"]
    assert first_rows[-1].visit.record["visit_count"] == marker["visit"]["visit_count"] == 1
    first_info = _assert_attempt_evidence(first_rows[-1], identity=first["identity"],
                                          expected_input=False, child_target=child_target)
    pending_info = _assert_attempt_evidence(pending_rows[-1], identity=marker["identity"],
                                            expected_input=True, child_target=child_target)
    _assert_launch_window(control, pgid, first_rows, pending_rows, first_info, pending_info)
    return authority, first, first_rows, pending_rows, second, first_info


def _baseline(root, child_target):
    root.mkdir()
    parent, source, refs = _repeated_fixture(root, child_target=child_target, forwarding=True)
    baseline = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert baseline.returncode == 0, baseline.stderr
    _, memo = _authority(parent)
    assert memo.terminal.data["value"] is True
    assert len(memo.active_commits) == len(memo.settlements) == 2
    first = next(iter(memo.active_commits.values())).data
    attempt = Path(first["proof"]["settled_result"]["workspace_path"]).parent
    return source, memo, json.loads((attempt / "child-request.json").read_bytes())


def _assert_same_source(first_info, baseline_request):
    request = first_info["request"]
    assert request["materialized_source"]["normalized_locator"] == baseline_request["materialized_source"]["normalized_locator"]
    assert request["materialized_source"]["resolved_commit_sha"] == baseline_request["materialized_source"]["resolved_commit_sha"]
    assert request["inputs"] == baseline_request["inputs"] == {"flag": False}


def _protocol_counts(control):
    return tuple(len(_json_lines(control / name)) for name in
                 ("launches.jsonl", "reconcile.jsonl", "finalize.jsonl"))


def _assert_recovered_memo(parent, marker, first, second, baseline_memo, gap):
    authority, recovered = _authority(parent)
    assert recovered.terminal.data["outcome"] == "completed"
    assert recovered.terminal.data["value"] == baseline_memo.terminal.data["value"]
    assert len(recovered.active_commits) == len(recovered.settlements) == 2
    assert recovered.active_commits[first["identity"]].data == first
    commit = recovered.active_commits[marker["identity"]].data
    assert (commit["identity"], commit["attempt"]) in recovered.settlements
    assert commit["value"]["value"] is True
    assert commit["value"]["accounting"]["attempt_ordinal"] == (2 if gap == "pending" else 1)
    if gap == "memo":
        assert commit == second
    return authority


def _assert_recovery_counts(control, before, gap):
    launches, reconciles, finalizes = before
    assert _protocol_counts(control) == (
        launches + (gap == "pending"), reconciles + (gap == "memo"), finalizes + (gap == "pending"),
    )


def _assert_disposition_binding(disposition, pending):
    assert disposition["attempt_ordinal"] == pending.attempt_ordinal
    assert disposition["visit"] == pending.visit.record
    assert disposition["workspace_path"] == str(pending.bindings.workspace_path)
    assert disposition["incomplete_row_digest"] == pending.row_digest
    assert disposition["workspace_deletion"] == {
        "status": "deleted_or_confirmed_absent", "workspace_absent": True,
    }


def _assert_pending_disposition(rows, pending):
    interrupted_workspace = pending.bindings.workspace_path
    discarded = [row for row in rows if row.attempt_ordinal == 1 and row.status == "discarded"]
    replacement = [row for row in rows if row.attempt_ordinal == 2 and row.stage == "committed" and row.status == "committed"]
    assert len(discarded) == len(replacement) == 1
    assert not interrupted_workspace.exists()
    disposition = json.loads((interrupted_workspace.parent / "disposition.json").read_bytes())
    assert disposition["disposition"] == "discard_incomplete_attempt_and_rerun_fresh"
    _assert_disposition_binding(disposition, pending)
    return replacement[0]


def _assert_replacement_binding(replacement, pending, launches, marker):
    assert replacement.bindings.workspace_path != pending.bindings.workspace_path
    assert replacement.bindings.child_run_id != pending.bindings.child_run_id
    assert launches[-1]["child_run_id"] == replacement.bindings.child_run_id
    assert launches[-1]["parent_authority"]["identity"] == marker["identity"]


def _assert_memo_ledger_reconcile(rows, pending_rows, second):
    assert second is not None
    assert tuple(rows[:len(pending_rows)]) == tuple(pending_rows)
    assert len(rows) == len(pending_rows) + 1
    assert rows[-1].stage == rows[-1].status == "committed"
    assert rows[-1].attempt_ordinal == 1
    assert rows[-1].bindings.child_run_id == pending_rows[-1].bindings.child_run_id
    assert rows[-1].bindings.workspace_path == pending_rows[-1].bindings.workspace_path


def _assert_reconcile_binding(control, pending, second, marker):
    assert pending.bindings.workspace_path.exists()
    assert not (pending.bindings.workspace_path.parent / "disposition.json").exists()
    assert _json_lines(control / "launches.jsonl")[-1]["child_run_id"] == pending.bindings.child_run_id
    reconcile = _json_lines(control / "reconcile.jsonl")[-1]
    assert reconcile["identity"] == marker["identity"]
    assert reconcile["parent_attempt"] == second["attempt"]
    assert reconcile["visit"] == marker["visit"] and reconcile["reconcile_pending"] is True


def _assert_recovery_ledger(authority, control, first_rows, pending_rows, second, marker, gap):
    after = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    assert tuple(row for row in after.rows if row.visit == first_rows[-1].visit) == tuple(first_rows)
    rows = [row for row in after.rows if row.visit.record == marker["visit"]]
    if gap == "pending":
        replacement = _assert_pending_disposition(rows, pending_rows[-1])
        _assert_replacement_binding(replacement, pending_rows[-1], _json_lines(control / "launches.jsonl"), marker)
    else:
        _assert_memo_ledger_reconcile(rows, pending_rows, second)
        _assert_reconcile_binding(control, pending_rows[-1], second, marker)


def _assert_completed_readonly(parent, refs, control, authority, orphan):
    before = _tree_bytes(parent), _tree_bytes(refs)
    counts = _protocol_counts(control)
    for _ in range(2):
        _run_to_exit(parent, control, ["resume", authority.run_root.name])
        assert (_tree_bytes(parent), _tree_bytes(refs)) == before
        assert _protocol_counts(control) == counts
        _assert_no_child_resume(control, {orphan})


@pytest.mark.parametrize("child_target", ["2.24", "2.35"], ids=["legacy", "evaluated"])
@pytest.mark.parametrize("gap", ["pending", "memo"], ids=["pending-before-memo", "memo-before-finalize"])
def test_kill_at_parent_settlement_gap_recovers(tmp_path, gap, child_target):
    baseline_source, baseline_memo, baseline_request = _baseline(tmp_path / "baseline", child_target)
    parent = tmp_path / "interrupted" / "parent"
    parent.mkdir(parents=True)
    source = parent / "controller.orc"
    source.write_bytes(baseline_source.read_bytes())
    refs, control = tmp_path / "interrupted" / "refs", tmp_path / "control"
    assert source.read_bytes() == baseline_source.read_bytes()
    process, pgid, stdout, stderr = _start_cli(parent, control,
        ["run", str(source), "--run-ref-root", str(refs)], gate=gap)
    try:
        marker = _wait_for_marker(process, stdout, stderr, control)
        authority, first, first_rows, pending_rows, second, first_info = _assert_kill_window(
            parent, control, marker, pgid, gap, child_target)
        _assert_same_source(first_info, baseline_request)
        pending_attempt_root = pending_rows[-1].bindings.workspace_path.parent
        incident_before = {path.name: _tree_bytes(path) for path in pending_attempt_root.iterdir()
                           if path.name != "workspace"}
        first_attempt_tree = _tree_bytes(first_info["attempt_root"])
        first_child_root = Path(first_info["request"]["child_state_dir"]) / first_info["request"]["child_run_id"]
        first_child_tree = _tree_bytes(first_child_root)
        os.killpg(pgid, signal.SIGKILL)
        process.wait(timeout=5)
        assert process.returncode == -signal.SIGKILL
    finally:
        _kill_own_group(process, pgid)
    counts = _protocol_counts(control)
    _run_to_exit(parent, control, ["resume", authority.run_root.name])
    recovered = _assert_recovered_memo(parent, marker, first, second, baseline_memo, gap)
    _assert_recovery_counts(control, counts, gap)
    _assert_recovery_ledger(recovered, control, first_rows, pending_rows, second, marker, gap)
    assert _tree_bytes(first_info["attempt_root"]) == first_attempt_tree
    assert _tree_bytes(first_child_root) == first_child_tree
    assert {name: _tree_bytes(pending_attempt_root / name) for name in incident_before} == incident_before
    orphan = pending_rows[-1].bindings.child_run_id
    _assert_no_child_resume(control, {orphan})
    _assert_completed_readonly(parent, refs, control, recovered, orphan)
