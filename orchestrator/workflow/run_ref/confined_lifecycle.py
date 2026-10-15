"""Confined (`run_ref_static_config.v2`) attempts through the ordinary E1 lifecycle.

`drive_run_ref_lifecycle` hands a confined site here after allocation; the same
acknowledged ledger stages are emitted with confined evidence:

* `allocated`: bindings from the v2 config, the evaluated `:commit` and the inputs,
  with the child run id and clone of `confinement.confined_attempt_layout`; the
  child is admitted before (a refusal leaves no ledger row and aborts the parent
  effect under ordinary EE rules).
* `materialized` / `setup_completed`: the sanitized clone and control root
  (`provision_confined_child`), the baseline snapshot beside the clone, the
  initial `committed` checkpoint header; setup evidence is the child recipe.
* `program_prepared` / `launched`: the durable confined request
  (`run_ref_confined_child_request.v1`) written as `child-request.json`.
* `child_completed`: the child run under a `ConfinedChildSession` (one holder per
  attempt, stopped at the child terminal), then its terminal witness: a completed
  memo replayed over its committed effects, or the child's failed terminal. A
  failure after release settles as `FAILED (code, detail, accounting)` (P32); a
  launch refused before release aborts the parent effect.
* `delta_captured` / `completed_pending_parent_commit`: delta from the baseline to
  the clone after its last checkpoint, accounting (`elapsed_ms` is the wall time
  charged to `:wall-seconds`, host work included) and the evidence manifest; the
  envelope is the site's outcome union.

`validate_confined_bound_authority` rebuilds the same envelope from the durable
evidence for settlement, reconciliation and reuse. The durable failed terminal
row, crash recovery and K4 changes are Task 7's. Dependencies: `confinement.py`,
`confined_session.py`, `evaluated_child.py`, `delta.py`, `runtime.py` documents.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
from typing import Any

from .confined_session import ConfinedChildSession, ensure_checkpoint_header
from .confined_source import confined_revision
from .confinement import (
    RECIPE_FILENAME,
    admit_confined_child,
    checked_child_program,
    confined_attempt_layout,
    confined_child_accounting,
    probe_host,
    provision_confined_child,
)
from .contracts import RUN_REF_CONFINED_MATERIALIZER_VERSION, canonical_sha256
from .delta import build_workspace_delta, validate_workspace_delta
from .evaluated_child import (
    confined_child_header,
    execute_confined_child,
    validate_confined_child_failure,
    validate_confined_child_terminal,
)
from .ledger import RunRefAttemptBindings, SettledRunRefResultBinding
from .runtime import (
    _ACCOUNTING_FILENAME,
    _BASELINE_DIRECTORY,
    _CHILD_RESULT_FILENAME,
    _EVIDENCE_FILENAME,
    _REQUEST_FILENAME,
    _WORKSPACE_DELTA_FILENAME,
    PreparedRunRefSettlement,
    RunRefRuntimeError,
    build_run_ref_accounting,
    declared_artifacts_from_value,
    flatten_run_ref_result_artifacts,
    resolve_run_ref_parent_input_values,
    _read_canonical_document,
    _write_canonical_document,
)
from .wire import confined_child_request
from .workspace import TreeManifest, freeze_tree

IMAGES_DIRNAME = "images"  # the sealed image store beneath the run-reference root
CHILD_RESULT_SCHEMA = "run_ref_confined_child_result.v1"
EVIDENCE_SCHEMA = "run_ref_confined_evidence_manifest.v1"
_STATIC_BINDINGS = ("run_ref_root", "workspace_path", "source_digest", "program_digest", "input_digest",
                    "policy_digest", "step_config_digest", "capsule_or_compiler_digest", "child_run_id",
                    "result_contract_digest")
_WITNESS_ERRORS = (KeyError, TypeError, ValueError, OSError)


def _invalid(detail: str) -> RunRefRuntimeError:
    return RunRefRuntimeError("run_ref_evidence_invalid", detail)


def _layout(request, attempt_ordinal: int):
    return confined_attempt_layout(run_ref_root=request.run_ref_root, parent_run_root=request.parent_run_root,
                                   visit=request.visit, attempt_ordinal=attempt_ordinal,
                                   config=request.step_config.run_ref)


def _request_record(request, parent_values: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return confined_child_request(request.step_config.run_ref, commit=request.parent_state["commit"],
                                      inputs=parent_values)
    except (KeyError, TypeError, ValueError) as exc:
        raise RunRefRuntimeError("run_ref_environment_escape_rejected", "confined_child_request_invalid") from exc


def confined_attempt_bindings(request, *, attempt_ordinal: int, workspace: Path,
                              parent_values: Mapping[str, Any]) -> RunRefAttemptBindings:
    """Static ledger bindings of one confined attempt; the commit is part of the input digest."""
    config = request.step_config.run_ref
    return RunRefAttemptBindings(
        run_ref_root=request.run_ref_root,
        workspace_path=workspace,
        source_digest=canonical_sha256({"schema_version": "run_ref_confined_source.v1",
                                        "normalized_locator": config.repo,
                                        "materializer_version": RUN_REF_CONFINED_MATERIALIZER_VERSION}),
        program_digest=canonical_sha256(config.program.record),
        input_digest=canonical_sha256({"schema_version": "run_ref_confined_input_binding.v1",
                                       "commit": request.parent_state.get("commit"),
                                       "inputs": [row.record for row in config.inputs],
                                       "resolved_parent_values": dict(parent_values)}),
        policy_digest=canonical_sha256(config.policy.record),
        step_config_digest=request.step_config.step_config_digest,
        capsule_or_compiler_digest=config.compiler_runtime_identity_digest,
        child_run_id=_layout(request, attempt_ordinal).child_run_id,
        result_contract_digest=config.result_digest,
    )


def _preparation_digest(request, record: Mapping[str, Any]) -> str:
    return canonical_sha256({"schema_version": "run_ref_program_preparation.v1", "mode": "confined",
                             "step_config_digest": request.step_config.step_config_digest,
                             "child_request_digest": canonical_sha256(dict(record))})


def _snapshot_baseline(workspace: Path, baseline: Path) -> TreeManifest:
    """Copy the provisioned clone (no `.git`) beside it: the delta's baseline."""
    if os.path.lexists(baseline):
        raise RunRefRuntimeError("run_ref_delta_capture_failed", "baseline_snapshot_preexisting")
    manifest = freeze_tree(workspace, excluded_roots=(".git", ".orchestrate"))
    shutil.copytree(workspace, baseline, symlinks=True, copy_function=shutil.copy2,
                    ignore=lambda directory, names: {".git"} & set(names) if Path(directory) == workspace else set())
    if freeze_tree(baseline) != manifest:
        raise RunRefRuntimeError("run_ref_delta_capture_failed", "baseline_snapshot_mismatch")
    return manifest


def _checked_child(request, layout, recipe_bytes: bytes, inputs: Mapping[str, Any],
                   status: str, direct_value: Any) -> tuple[dict[str, Any], str]:
    """The child result document and terminal digest from the control root's witness."""
    config = request.step_config.run_ref
    try:
        recipe = json.loads(recipe_bytes)
        image_digest = recipe["admission"]["image"]["tree_digest"]
        program = checked_child_program(request.parent_program, config)
        header = confined_child_header(program=program, child_run_id=layout.child_run_id,
                                       child_root=layout.child_root, clone_root=layout.workspace,
                                       run_ref_root=request.run_ref_root, inputs=inputs)
        common = dict(child_root=layout.child_root, clone_root=layout.workspace, expected_header=header,
                      recipe_bytes=recipe_bytes, image_digest=image_digest)
        document = {"schema_version": CHILD_RESULT_SCHEMA, "child_run_id": layout.child_run_id, "status": status}
        if status == "completed":
            value, _path, digest = validate_confined_child_terminal(
                **common, value_descriptor=config.result_descriptor["envelope"]["fields"][0]["type"],
                direct_value=direct_value)
            return {**document, "value": value}, digest
        code, detail, _path, digest = validate_confined_child_failure(**common)
        return {**document, "code": code, "detail": detail}, digest
    except _WITNESS_ERRORS as exc:
        raise _invalid("confined_child_terminal_invalid") from exc


def _outcome(request, document, delta_record, accounting) -> tuple[dict[str, Any], dict[str, Any]]:
    """The site's union value and its artifact projection."""
    if document["status"] == "failed":
        return {"variant": "FAILED", "code": document["code"], "detail": document["detail"],
                "accounting": dict(accounting)}, {}
    envelope = {"value": document["value"], "workspace_delta": dict(delta_record), "accounting": dict(accounting)}
    artifacts = flatten_run_ref_result_artifacts(envelope, request.step_config.run_ref.result_descriptor["envelope"])
    return {"variant": "COMPLETED", "result": envelope}, artifacts


def _declared(request, document):
    if document["status"] != "completed":
        return ()
    descriptor = request.step_config.run_ref.result_descriptor["envelope"]["fields"][0]["type"]
    return declared_artifacts_from_value(document["value"], descriptor)


def _evidence(request, ordinal: int, bindings: RunRefAttemptBindings, layout, *,
              envelope_digest: str, final_digest: str) -> dict[str, Any]:
    attempt_root = layout.workspace.parent
    record = bindings.record
    return {
        "schema_version": EVIDENCE_SCHEMA, "visit": request.visit.record, "attempt_ordinal": ordinal,
        "mode": "confined",
        **{name: record[name] for name in record if name not in ("evidence_manifest_digest", "disposition_digest")},
        "result_envelope_digest": envelope_digest, "final_workspace_digest": final_digest,
        "paths": {"workspace": layout.workspace.as_posix(), "control_root": layout.child_root.as_posix(),
                  **{name: (attempt_root / filename).as_posix() for name, filename in (
                      ("baseline", _BASELINE_DIRECTORY), ("child_request", _REQUEST_FILENAME),
                      ("child_result", _CHILD_RESULT_FILENAME), ("workspace_delta", _WORKSPACE_DELTA_FILENAME),
                      ("accounting", _ACCOUNTING_FILENAME))}},
    }


def drive_confined_lifecycle(request, *, allocation, emit: Callable[..., Any], effects):
    """Admit, provision, run and witness one confined child attempt (see the module docstring)."""
    parent_values = resolve_run_ref_parent_input_values(request)
    record = _request_record(request, parent_values)
    admission = admit_confined_child(request.step_config.run_ref, record, commit=request.parent_state["commit"],
                                     inputs=parent_values, parent_program=request.parent_program,
                                     image_store=request.run_ref_root / IMAGES_DIRNAME, host=probe_host())
    try:
        return _drive(request, admission, record, parent_values, allocation, emit, effects)
    finally:
        admission.close()


def _drive(request, admission, record, parent_values, allocation, emit, effects):
    ordinal, bindings = allocation.attempt_ordinal, allocation.bindings

    def advance(stage: str, updates: Mapping[str, Any], *, kind: str = "progress", extra=None):
        nonlocal bindings
        bindings = replace(bindings, **updates)
        return emit(stage=stage, event_kind=kind, attempt_ordinal=ordinal,
                    payload={"binding_updates": dict(updates), **(extra or {})})

    emit(stage="allocated", event_kind="allocation", attempt_ordinal=ordinal, payload={"bindings": bindings.record})
    effects.crash_hook("allocation")
    layout = _layout(request, ordinal)
    provisioned = provision_confined_child(admission, layout, run_ref_root=request.run_ref_root,
                                           parent_run_root=request.parent_run_root,
                                           parent_workspace=request.parent_workspace)
    advance("materialized", {"verified_git_tree_id": provisioned.source.verified_git_tree.value})
    attempt_root = layout.workspace.parent
    baseline = _snapshot_baseline(layout.workspace, attempt_root / _BASELINE_DIRECTORY)
    ensure_checkpoint_header(layout.child_root, baseline.digest)
    advance("setup_completed", {"setup_evidence_digest": canonical_sha256(provisioned.recipe),
                                "post_setup_baseline_digest": baseline.digest})
    _write_canonical_document(attempt_root / _REQUEST_FILENAME, record)
    advance("program_prepared", {"program_preparation_digest": _preparation_digest(request, record)})
    advance("launched", {"child_launch_digest": canonical_sha256(record)})
    effects.crash_hook("launch")

    session = ConfinedChildSession(admission, provisioned)
    status, value = "completed", None
    try:
        value = execute_confined_child(admission, provisioned, run_ref_root=request.run_ref_root, session=session)
    except RunRefRuntimeError as exc:
        if session.prerelease_error is not None:
            raise session.prerelease_error from exc
        if exc.detail != "workflow_execution_failed":
            raise
        status = "failed"
    finally:
        budget = session.stop()
    document, state_digest = _checked_child(request, layout, provisioned.recipe_bytes, admission.inputs,
                                            status, value)
    _write_canonical_document(attempt_root / _CHILD_RESULT_FILENAME, document)
    advance("child_completed", {"child_terminal_state_digest": state_digest,
                                "result_payload_digest": canonical_sha256(document)})
    effects.crash_hook("child_completion")

    delta = build_workspace_delta(base=provisioned.source.repository_revision_id,
                                  baseline_root=attempt_root / _BASELINE_DIRECTORY, baseline_manifest=baseline,
                                  workspace_root=layout.workspace, declared_artifacts=_declared(request, document))
    accounting = confined_child_accounting(layout, attempt_ordinal=ordinal, terminal_status=status,
                                           elapsed_ms=budget["charged_ms"])
    _write_canonical_document(attempt_root / _WORKSPACE_DELTA_FILENAME, delta.record)
    _write_canonical_document(attempt_root / _ACCOUNTING_FILENAME, accounting)
    envelope, artifacts = _outcome(request, document, delta.record, accounting)
    updates = {"workspace_delta_digest": delta.digest, "accounting_digest": canonical_sha256(accounting)}
    evidence = _evidence(request, ordinal, replace(bindings, **updates), layout,
                         envelope_digest=canonical_sha256(envelope), final_digest=delta.final_manifest.digest)
    _write_canonical_document(attempt_root / _EVIDENCE_FILENAME, evidence)
    advance("delta_captured", {**updates, "evidence_manifest_digest": canonical_sha256(evidence)})
    effects.crash_hook("delta")
    pending = advance("completed_pending_parent_commit", {}, kind="prepared", extra={
        "result_envelope_digest": canonical_sha256(envelope),
        "artifact_projection_digest": canonical_sha256(artifacts),
        "evidence_manifest_digest": bindings.evidence_manifest_digest})
    return PreparedRunRefSettlement(
        envelope=envelope, artifacts=artifacts,
        settled_result=SettledRunRefResultBinding(
            visit=request.visit, attempt_ordinal=ordinal, step_config_digest=bindings.step_config_digest,
            run_ref_root=bindings.run_ref_root, workspace_path=bindings.workspace_path,
            child_run_id=bindings.child_run_id, pending_row_digest=pending.authority_digest,
            child_terminal_state_digest=bindings.child_terminal_state_digest,
            result_contract_digest=bindings.result_contract_digest,
            result_payload_digest=bindings.result_payload_digest,
            workspace_delta_digest=bindings.workspace_delta_digest, accounting_digest=bindings.accounting_digest,
            evidence_manifest_digest=bindings.evidence_manifest_digest),
        ledger_path=allocation.ledger_path,
        evidence_manifest_path=attempt_root / _EVIDENCE_FILENAME,
    )


def validate_confined_bound_authority(request, row) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rebuild a confined attempt's envelope and artifacts from its durable evidence."""
    if row.visit != request.visit:
        raise _invalid("visit_binding_invalid")
    layout = _layout(request, row.attempt_ordinal)
    parent_values = resolve_run_ref_parent_input_values(request)
    expected = confined_attempt_bindings(request, attempt_ordinal=row.attempt_ordinal,
                                         workspace=layout.workspace, parent_values=parent_values)
    for name in _STATIC_BINDINGS:
        if getattr(row.bindings, name) != getattr(expected, name):
            raise _invalid(f"{name}_binding_invalid")
    bindings, attempt_root = row.bindings, layout.workspace.parent
    record = _request_record(request, parent_values)
    stored = _read_canonical_document(attempt_root / _REQUEST_FILENAME, label="child_request")
    if (stored != record or canonical_sha256(record) != bindings.child_launch_digest
            or _preparation_digest(request, record) != bindings.program_preparation_digest):
        raise _invalid("child_request_binding_invalid")
    try:
        recipe_bytes = (layout.child_root / RECIPE_FILENAME).read_bytes()
        recipe_digest = canonical_sha256(json.loads(recipe_bytes))
    except (OSError, ValueError) as exc:
        raise _invalid("setup_evidence_binding_invalid") from exc
    if recipe_digest != bindings.setup_evidence_digest:
        raise _invalid("setup_evidence_binding_invalid")
    document = _read_canonical_document(attempt_root / _CHILD_RESULT_FILENAME, label="child_result")
    if not isinstance(document, Mapping) or canonical_sha256(document) != bindings.result_payload_digest:
        raise _invalid("result_payload_digest_invalid")
    checked, state_digest = _checked_child(request, layout, recipe_bytes, parent_values,
                                           document.get("status"), document.get("value"))
    if checked != document or state_digest != bindings.child_terminal_state_digest:
        raise _invalid("child_terminal_state_digest_invalid")
    baseline_root = attempt_root / _BASELINE_DIRECTORY
    baseline = freeze_tree(baseline_root)
    if baseline.digest != bindings.post_setup_baseline_digest:
        raise _invalid("baseline_digest_invalid")
    delta_record = _read_canonical_document(attempt_root / _WORKSPACE_DELTA_FILENAME, label="workspace_delta")
    final = validate_workspace_delta(delta_record, expected_digest=bindings.workspace_delta_digest,
                                     base=confined_revision(request.step_config.run_ref.repo,
                                                            request.parent_state["commit"])[1],
                                     baseline_root=baseline_root, baseline_manifest=baseline,
                                     workspace_root=layout.workspace, declared_artifacts=_declared(request, document))
    accounting = _read_canonical_document(attempt_root / _ACCOUNTING_FILENAME, label="accounting")
    if (not isinstance(accounting, Mapping) or canonical_sha256(accounting) != bindings.accounting_digest
            or build_run_ref_accounting(**accounting) != accounting
            or (accounting["child_run_id"], accounting["attempt_ordinal"], accounting["terminal_status"])
            != (bindings.child_run_id, row.attempt_ordinal, document["status"])):
        raise _invalid("accounting_binding_invalid")
    envelope, artifacts = _outcome(request, document, delta_record, accounting)
    evidence = _read_canonical_document(attempt_root / _EVIDENCE_FILENAME, label="evidence_manifest")
    if (evidence != _evidence(request, row.attempt_ordinal, bindings, layout,
                              envelope_digest=canonical_sha256(envelope), final_digest=final.digest)
            or canonical_sha256(evidence) != bindings.evidence_manifest_digest):
        raise _invalid("evidence_manifest_binding_invalid")
    return envelope, artifacts


__all__ = ["IMAGES_DIRNAME", "confined_attempt_bindings", "drive_confined_lifecycle",
           "validate_confined_bound_authority"]
