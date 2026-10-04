"""Checked evaluated inputs and memo authority for the existing E1 coordinator."""

from __future__ import annotations

import base64
from pathlib import Path

from orchestrator.workflow.executable_ir import RunRefStepConfig, StepCommonConfig
from orchestrator.workflow.run_ref.config import decode_run_ref_static_config
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.run_ref.runtime import (
    RunRefRuntimeRequest,
    finalize_run_ref_parent_commit,
    prepare_run_ref_settlement,
    recover_run_ref_settlement,
    resolve_run_ref_parent_input_values_for_config,
    validate_run_ref_memo_authority,
)

from .authority import _require_retained_root
from .memo import MemoError, append_record, read_memo
from .values import coerce_evaluated_value


class RunRefRootMissing(RuntimeError):
    code = "resume_run_ref_root_missing"


def require_run_ref_root(authority):
    root = authority.header.get("run_ref_root")
    if root is None:
        raise RunRefRootMissing("reached run reference has no recorded run_ref_root")
    return Path(root)


def resolve_run_ref_input(node, operands):
    config = RunRefStepConfig(common=StepCommonConfig(), run_ref=decode_run_ref_static_config(
        base64.b64decode(node["config"], validate=True)))
    rows = config.run_ref.inputs
    if len(operands) != len(rows) or [name for name, _ in node["inputs"]] != [row.name for row in rows]:
        raise MemoError("memo_inconsistent", "checked run-ref input order disagrees")
    parent_state = {"bound_inputs": {
        row.name: coerce_evaluated_value(value.json_value(), row.type_descriptor,
            context=f"run-ref input {row.name}").json_value()
        for row, value in zip(rows, operands, strict=True)
    }}
    values = resolve_run_ref_parent_input_values_for_config(config, parent_state)
    parts = {"config": config.step_config_digest, "inputs": canonical_sha256(values)}
    return (config, parent_state), parts


def _request(authority, resolved, identity, attempt, workspace):
    config, parent_state = resolved
    visit = RunRefVisitKey(parent_run_id=authority.run_root.name,
        execution_frame_id="root", call_frame_id=None,
        step_id="root." + canonical_sha256(identity).removeprefix("sha256:"), visit_count=1)
    return RunRefRuntimeRequest(step_config=config, visit=visit, parent_state=parent_state,
        parent_workspace=workspace, parent_run_root=authority.run_root,
        run_ref_root=require_run_ref_root(authority), run_files=authority.run_files,
        parent_identity=identity, parent_attempt=attempt)


def validate_evaluated_run_ref_start(authority, resolved, identity, attempt, workspace):
    """Apply the shared request guard before reserving a new memo attempt."""
    _require_retained_root(authority.run_files)
    _request(authority, resolved, identity, attempt, workspace)


def prepare_evaluated_run_ref(authority, node, resolved, identity, attempt, workspace, attempt_files):
    request = _request(authority, resolved, identity, attempt, workspace)
    prepared = prepare_run_ref_settlement(request)
    result = coerce_evaluated_value(prepared.envelope, node["result"], context="run-ref result")
    payload = canonical_json_bytes(result.json_value())
    attempt_files.write_atomic("result.json", payload)
    proof = {"settled_result": prepared.settled_result.record, "artifacts": dict(prepared.artifacts)}
    return result, canonical_sha256(result.json_value()), proof, prepared


def settle_evaluated_run_ref(authority, resolved, identity, attempt, workspace, site_classes, prepared, expected_commit):
    _require_retained_root(authority.run_files)
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    commit = snapshot.active_commits.get(identity)
    if commit is None or canonical_json_bytes(commit.data) != canonical_json_bytes(expected_commit):
        raise MemoError("memo_inconsistent", "active run-ref commit disagrees before settlement")
    request = _request(authority, resolved, identity, attempt, workspace)
    finalize_run_ref_parent_commit(request, prepared,
        persisted_settled_result=commit.data["proof"]["settled_result"])
    _require_retained_root(authority.run_files)
    append_record(authority.memo_path, {"record": "settled", "identity": identity,
        "attempt": attempt, "by": "settle"}, run_files=authority.run_files)


def validate_evaluated_run_ref(authority, resolved, identity, workspace, commit, *, settled):
    request = _request(authority, resolved, identity, commit.data["attempt"], workspace)
    proof = commit.data["proof"]
    envelope, artifacts = validate_run_ref_memo_authority(request,
        settled_result=proof["settled_result"], artifacts=proof["artifacts"], allow_pending=not settled)
    if (canonical_json_bytes(envelope) != canonical_json_bytes(commit.data["value"])
            or canonical_json_bytes(artifacts) != canonical_json_bytes(proof["artifacts"])):
        raise MemoError("memo_inconsistent", "run-ref memo value differs from its proof")


def reconcile_evaluated_run_ref(authority, resolved, identity, workspace, expected, site_classes):
    _require_retained_root(authority.run_files)
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    commit = snapshot.active_commits.get(identity)
    if commit is None or canonical_json_bytes(commit.data) != canonical_json_bytes(expected.data):
        raise MemoError("memo_inconsistent", "active run-ref commit changed before reconciliation")
    attempt = commit.data["attempt"]
    if (identity, attempt) in snapshot.settlements:
        return
    validate_evaluated_run_ref(authority, resolved, identity, workspace, commit, settled=False)
    request = _request(authority, resolved, identity, attempt, workspace)
    recover_run_ref_settlement(request, settled_result=commit.data["proof"]["settled_result"],
        reconcile_pending=True)
    _require_retained_root(authority.run_files)
    append_record(authority.memo_path, {"record": "settled", "identity": identity,
        "attempt": attempt, "by": "reconcile"}, run_files=authority.run_files)
