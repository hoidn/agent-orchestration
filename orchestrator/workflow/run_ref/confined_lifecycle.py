"""Confined children through the ordinary parent-owned, acknowledged E1 lifecycle.

V2 reservation opens the visit budget before admission. Recovery quiesces exact
scopes and resolves terminality/budget before retaining progress or applying K4.
A child failure closes its budget and acknowledges a boundary proof before its
memo failure/terminal. The ordinary prepare/parent-commit/settle chain owns both
outcomes; v1 path attempts continue through the legacy driver.
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
from .contracts import RUN_REF_CONFINED_MATERIALIZER_VERSION, canonical_json_bytes, canonical_sha256
from .delta import build_workspace_delta, validate_workspace_delta, validate_retained_workspace_delta
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
                   status: str, direct_value: Any, image=None) -> tuple[dict[str, Any], str]:
    """The child result document and terminal digest from the control root's witness."""
    config = request.step_config.run_ref
    from .confined_evidence import evidence_usage
    evidence_usage(layout, ledger_path=request.ledger_path, visit=request.visit)
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
                direct_value=direct_value, image=image)
            return {**document, "value": value}, digest
        from .confined_recovery import validate_failed_terminal_evidence
        validate_failed_terminal_evidence(request, layout)
        code, detail, _path, digest = validate_confined_child_failure(**common)
        return {**document, "code": code, "detail": detail}, digest
    except _WITNESS_ERRORS as exc:
        raise _invalid("confined_child_terminal_invalid") from exc


def _outcome(request, document, delta_record, accounting, *, value=None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The site's union value and its artifact projection."""
    if document["status"] == "failed":
        return {"variant": "FAILED", "code": document["code"], "detail": document["detail"],
                "accounting": dict(accounting)}, {}
    envelope = {"value": document["value"] if value is None else value, "workspace_delta": dict(delta_record), "accounting": dict(accounting)}
    artifacts = flatten_run_ref_result_artifacts(envelope, request.step_config.run_ref.result_descriptor["envelope"])
    return {"variant": "COMPLETED", "result": envelope}, artifacts


def _declared(request, document):
    if document["status"] != "completed":
        return ()
    descriptor = request.step_config.run_ref.result_descriptor["envelope"]["fields"][0]["type"]
    return declared_artifacts_from_value(document["value"], descriptor, pointer_locations=True)


def _evidence(request, ordinal: int, bindings: RunRefAttemptBindings, layout, *,
              envelope_digest: str, final_digest: str) -> dict[str, Any]:
    attempt_root = layout.workspace.parent
    record = bindings.record
    from .confined_provider import provider_allowance
    from .ledger import load_attempt_ledger
    provider = provider_allowance(load_attempt_ledger(request.ledger_path, run_files=request.run_files).rows,
                                  request.visit)
    return {
        "schema_version": EVIDENCE_SCHEMA, "visit": request.visit.record, "attempt_ordinal": ordinal,
        "mode": "confined",
        **({'provider_authority_digest': canonical_sha256(provider)} if provider is not None else {}),
        **{name: record[name] for name in record if name not in ("evidence_manifest_digest", "disposition_digest")},
        "result_envelope_digest": envelope_digest, "final_workspace_digest": final_digest,
        "paths": {"workspace": layout.workspace.as_posix(), "control_root": layout.child_root.as_posix(),
                  **{name: (attempt_root / filename).as_posix() for name, filename in (
                      ("baseline", _BASELINE_DIRECTORY), ("child_request", _REQUEST_FILENAME),
                      ("child_result", _CHILD_RESULT_FILENAME), ("workspace_delta", _WORKSPACE_DELTA_FILENAME),
                      ("accounting", _ACCOUNTING_FILENAME))}},
    }


def prepare_confined_recovery_allocation(request, effects):
    """Resolve budget/terminality under the parent writer before selecting K4 or continuation."""
    from .ledger import load_attempt_ledger, identify_incomplete_attempt, confined_budget
    from .holder_scope import recover_holder_scopes
    from .confined_budget import boottime_ns, remaining_ns
    from .runtime import (select_run_ref_lifecycle_allocation, _discard_incomplete_attempt,
                          persist_run_ref_lifecycle_event, RunRefLifecycleEvent)
    head = identify_incomplete_attempt(request.ledger_path, visit=request.visit,
        current_step_config_digest=request.step_config.step_config_digest, run_files=request.run_files)
    if head is None:
        return select_run_ref_lifecycle_allocation(request)
    rows = load_attempt_ledger(request.ledger_path, run_files=request.run_files).rows
    state = confined_budget(rows, request.visit)
    if state is None:
        raise _invalid("confined_attempt_requires_v2_ledger")
    if state["limit_ns"] != dict(request.step_config.run_ref.policy.limits)["wall-seconds"] * 1_000_000_000:
        raise _invalid("confined_budget_limit_disagrees")
    remaining_ns(state)  # an open old-boot interval refuses before scope-name reuse
    layout = _layout(request, head.attempt_ordinal)
    expected = confined_attempt_bindings(request, attempt_ordinal=head.attempt_ordinal,
        workspace=layout.workspace, parent_values=resolve_run_ref_parent_input_values(request))
    if any(getattr(head.bindings, name) != getattr(expected, name) for name in _STATIC_BINDINGS):
        raise _invalid("retained_attempt_bindings_disagree")
    recipe = None
    if (layout.child_root / RECIPE_FILENAME).exists():
        from .confinement import _read_recipe, require_owned_roots
        recipe = _read_recipe(layout)
        if head.bindings.setup_evidence_digest is not None and canonical_sha256(recipe) != head.bindings.setup_evidence_digest:
            raise _invalid('retained_recipe_digest_disagrees')
        if head.bindings.setup_evidence_digest is None and (layout.child_root / 'holder').exists():
            raise _invalid('holder_before_bound_provisioning')
        require_owned_roots(layout, request.run_ref_root, recipe)
    recover_holder_scopes(layout.child_root / "holder")  # before every checkpoint/clone reader
    if state['active'] is not None:
        active = state['active']
        event = RunRefLifecycleEvent.build(sequence=1, event_kind='budget_close', stage=head.stage,
            visit=request.visit, attempt_ordinal=head.attempt_ordinal, effect_instance_root=request.parent_run_root,
            payload={'event': dict(opening_sequence=active['opening_sequence'], boot_id=active['boot_id'], until_ns=boottime_ns())})
        persist_run_ref_lifecycle_event(request, event)
        rows = load_attempt_ledger(request.ledger_path, run_files=request.run_files).rows
        head = next(row for row in reversed(rows) if row.visit == request.visit)
        state = confined_budget(rows, request.visit)
    # Terminal evidence is checked before reopening execution accounting, including pure zero-commit children.
    terminal = None
    commits = False
    if (layout.child_root / 'run.json').exists():
        from orchestrator.workflow.evaluated.authority import load_run_authority
        from orchestrator.workflow.evaluated.memo import read_memo
        from orchestrator.workflow.evaluated.machine import site_classes
        authority = load_run_authority(layout.child_root)
        if recipe is None:
            raise _invalid('child_authority_without_recipe')
        from .confined_recovery import _require_child_authority
        _require_child_authority(request, layout, authority, canonical_json_bytes(recipe))
        memo = read_memo(authority.memo_path, site_classes(authority.program))
        commits = bool(memo.active_commits)
        terminal = memo.terminal
    from .confinement import CHECKPOINT_HEADER, validate_checkpoint_identity
    if head.bindings.post_setup_baseline_digest is not None and not os.path.lexists(layout.child_root / CHECKPOINT_HEADER):
        raise _invalid('checkpoint_header_missing_after_setup')
    validate_checkpoint_identity(layout)  # read-only, after quiescence and before K4
    failure = next((row for row in reversed(rows) if row.visit == request.visit
                    and row.attempt_ordinal == head.attempt_ordinal and row.event_kind == 'failed_terminal'), None)
    if terminal is None and failure is None and not commits and remaining_ns(state) > 0:
        _discard_incomplete_attempt(request, effects)
        return select_run_ref_lifecycle_allocation(request)
    fresh = select_run_ref_lifecycle_allocation(request)
    return replace(fresh, attempt_ordinal=head.attempt_ordinal, bindings=head.bindings, retained=head)


def drive_confined_lifecycle(request, *, allocation, emit: Callable[..., Any], effects):
    """The same E1 driver reserves accounting before admission and retains committed child progress."""
    from .confined_budget import VisitBudget, boot_id, boottime_ns
    from .confined_provider import VisitProviderAllowance, provider_allowance
    from .ledger import confined_budget, load_attempt_ledger
    ordinal, bindings = allocation.attempt_ordinal, allocation.bindings
    stage = 'allocated' if allocation.retained is None else allocation.retained.stage

    def side(kind, event):
        return emit(stage=stage, event_kind=kind, attempt_ordinal=ordinal, payload={'event': event})

    def advance(target, updates, *, kind='progress', extra=None):
        nonlocal bindings, stage
        bindings = replace(bindings, **updates)
        ack = emit(stage=target, event_kind=kind, attempt_ordinal=ordinal,
                   payload=(dict(extra) if kind == 'export_prepared' else {'binding_updates': dict(updates), **(extra or {})}))
        stage = target
        return ack

    rows = load_attempt_ledger(allocation.ledger_path, run_files=request.run_files).rows
    if (len(rows) + 1 != allocation.expected_ledger_sequence
            or (rows[-1].row_digest if rows else None) != allocation.expected_previous_row_digest):
        raise _invalid('confined_allocation_head_changed')
    if allocation.retained is not None and next((row for row in reversed(rows) if row.visit == request.visit), None) != allocation.retained:
        raise _invalid('confined_retained_head_changed')
    prior = confined_budget(rows, request.visit)
    if allocation.retained is None:
        opening = dict(limit_ns=dict(request.step_config.run_ref.policy.limits)['wall-seconds'] * 1_000_000_000,
                       boot_id=boot_id(), since_ns=boottime_ns())
        ack = emit(stage='allocated', event_kind='allocation', attempt_ordinal=ordinal,
                   payload={'bindings': bindings.record, 'confined_opening': opening})
        state = dict(limit_ns=opening['limit_ns'], charged_ns=0 if prior is None else prior['charged_ns'],
                     active={**{k:v for k,v in opening.items() if k != 'limit_ns'},
                             'attempt_ordinal': ordinal, 'opening_sequence': ack.authority.sequence},
                     closure_digest=None if prior is None else prior['closure_digest'])
        effects.crash_hook('allocation')
    else:
        state = prior
    budget = VisitBudget(state, side)
    layout = _layout(request, ordinal)
    # A retained terminal never opens another execution interval or starts a holder.
    from .confined_recovery import retained_terminal, record_failure
    terminal = retained_terminal(request, layout, rows, state) if allocation.retained is not None else None
    if terminal is None and budget.state['active'] is None:
        if budget.remaining <= 0:
            from .confined_recovery import fail_exhausted_retained
            terminal = fail_exhausted_retained(request, layout, rows, budget, side)
        else:
            opening = dict(boot_id=boot_id(), since_ns=boottime_ns())
            ack = side('budget_open', opening)
            budget.state = dict(budget.state, active={**opening, 'attempt_ordinal': ordinal,
                                                     'opening_sequence': ack.authority.sequence})
    if terminal is not None:
        document, state_digest = terminal
        return _finish_confined(request, allocation, bindings, stage, advance, document, state_digest,
                                budget.state['charged_ns'] // 1_000_000, effects)
    if budget.remaining <= 0:
        budget.close()
        raise RunRefRuntimeError('run_ref_budget_exhausted', 'child wall budget exhausted before release')
    parent_values = resolve_run_ref_parent_input_values(request)
    record = _request_record(request, parent_values)
    admission = None
    session = None
    try:
        admission = admit_confined_child(request.step_config.run_ref, record, commit=request.parent_state['commit'],
            inputs=parent_values, parent_program=request.parent_program,
            image_store=request.run_ref_root / IMAGES_DIRNAME, host=probe_host())
        if budget.remaining <= 0:
            raise RunRefRuntimeError('run_ref_budget_exhausted', 'child wall budget exhausted before release')
        provisioned = provision_confined_child(admission, layout, run_ref_root=request.run_ref_root,
            parent_run_root=request.parent_run_root, parent_workspace=request.parent_workspace)
        attempt_root = layout.workspace.parent
        if allocation.retained is None:
            advance('materialized', {'verified_git_tree_id': provisioned.source.verified_git_tree.value})
            baseline = _snapshot_baseline(layout.workspace, attempt_root / _BASELINE_DIRECTORY)
            ensure_checkpoint_header(layout.child_root, baseline.digest)
            advance('setup_completed', {'setup_evidence_digest': canonical_sha256(provisioned.recipe),
                                       'post_setup_baseline_digest': baseline.digest})
            _write_canonical_document(attempt_root / _REQUEST_FILENAME, record)
            advance('program_prepared', {'program_preparation_digest': _preparation_digest(request, record)})
            advance('launched', {'child_launch_digest': canonical_sha256(record)})
            effects.crash_hook('launch')
        session = ConfinedChildSession(admission, provisioned, budget_context=budget,
            evidence_ledger=request.ledger_path, evidence_visit=request.visit,
            provider_allowance=VisitProviderAllowance(provider_allowance(rows, request.visit), request.visit, ordinal, side),
            failure_callback=lambda authority, exc: record_failure(request, provisioned, authority, exc, budget, side))
        status, value = 'completed', None
        try:
            value = execute_confined_child(admission, provisioned, run_ref_root=request.run_ref_root, session=session)
        except RunRefRuntimeError as exc:
            if session.prerelease_error is not None:
                raise session.prerelease_error from exc
            if exc.detail != 'workflow_execution_failed':
                raise
            status = 'failed'
        finally:
            session.stop()
        document, state_digest = _checked_child(request, layout, provisioned.recipe_bytes, admission.inputs,
                                               status, value, image=admission.image)
        return _finish_confined(request, allocation, bindings, stage, advance, document, state_digest,
                                budget.state['charged_ns'] // 1_000_000, effects)
    except RunRefRuntimeError as exc:
        if session is None and exc.code == 'run_ref_budget_exhausted' and budget.remaining <= 0:
            budget.close()
            from .confined_recovery import _released, fail_exhausted_retained
            if allocation.retained is not None and _released(layout):
                document, state_digest = fail_exhausted_retained(request, layout, rows, budget, side)
                return _finish_confined(request, allocation, bindings, stage, advance, document, state_digest,
                                        budget.state['charged_ns'] // 1_000_000, effects)
        raise
    finally:
        if session is None:
            budget.close()
        if admission is not None:
            admission.close()


def _finish_confined(request, allocation, bindings, stage, advance, document, state_digest, elapsed_ms, effects):
    ordinal = allocation.attempt_ordinal
    layout = _layout(request, ordinal)
    attempt_root = layout.workspace.parent
    baseline = freeze_tree(attempt_root / _BASELINE_DIRECTORY)
    status = document['status']
    from .confinement import _recover_checkpoint
    _recover_checkpoint(layout)
    if bindings.child_terminal_state_digest is not None and (bindings.child_terminal_state_digest != state_digest
            or bindings.result_payload_digest != canonical_sha256(document)):
        raise _invalid('retained_child_terminal_binding_disagrees')
    _write_canonical_document(attempt_root / _CHILD_RESULT_FILENAME, document)
    if bindings.child_terminal_state_digest is None:
        advance("child_completed", {"child_terminal_state_digest": state_digest,
                                    "result_payload_digest": canonical_sha256(document)})
        bindings = replace(bindings, child_terminal_state_digest=state_digest, result_payload_digest=canonical_sha256(document))
    effects.crash_hook("child_completion")

    delta = build_workspace_delta(base=confined_revision(request.step_config.run_ref.repo, request.parent_state["commit"])[1],
                                  baseline_root=attempt_root / _BASELINE_DIRECTORY, baseline_manifest=baseline,
                                  workspace_root=layout.workspace, declared_artifacts=_declared(request, document), allow_aliases=True)
    validate_workspace_delta(delta.record, expected_digest=delta.digest,
        base=confined_revision(request.step_config.run_ref.repo, request.parent_state["commit"])[1],
        baseline_root=attempt_root / _BASELINE_DIRECTORY, baseline_manifest=baseline,
        workspace_root=layout.workspace, declared_artifacts=_declared(request, document), allow_aliases=True)
    accounting = confined_child_accounting(layout, attempt_ordinal=ordinal, terminal_status=status,
                                           elapsed_ms=elapsed_ms)
    _write_canonical_document(attempt_root / _WORKSPACE_DELTA_FILENAME, delta.record)
    _write_canonical_document(attempt_root / _ACCOUNTING_FILENAME, accounting)
    from .confined_exports import export_value
    from .ledger import load_attempt_ledger
    rows = load_attempt_ledger(request.ledger_path, run_files=request.run_files).rows
    events = [dict(row.event) for row in rows if row.visit == request.visit and row.attempt_ordinal == ordinal
              and row.event_kind == 'export_prepared']
    if document['status'] == 'completed':
        exported, export_proof = export_value(document['value'],
            request.step_config.run_ref.result_descriptor['envelope']['fields'][0]['type'],
            clone=layout.workspace, parent=request.parent_workspace, parent_run=request.visit.parent_run_id,
            activation=canonical_sha256(request.visit.record).removeprefix('sha256:'), attempt=ordinal,
            max_bytes=dict(request.step_config.run_ref.policy.limits)['output-mib'] << 20,
            prepared_events=events,
            persist=lambda event: advance('child_completed', {}, kind='export_prepared', extra={'event': event}),
            crash_hook=effects.crash_hook)
    else:
        exported, export_proof = None, None
    envelope, artifacts = _outcome(request, document, delta.record, accounting, value=exported)
    updates = {"workspace_delta_digest": delta.digest, "accounting_digest": canonical_sha256(accounting)}
    evidence = _evidence(request, ordinal, replace(bindings, **updates), layout,
                         envelope_digest=canonical_sha256(envelope), final_digest=delta.final_manifest.digest)
    from .confined_evidence import retain_trees, evidence_usage, authority_inventory
    evidence['retained_trees_digest'] = retain_trees(layout, baseline, delta.final_manifest, delta.digest)
    evidence['authority_inventory'] = authority_inventory(layout)
    evidence['exports'] = export_proof
    from .confined_cleanup import checkpoint_binding
    evidence['cleanup_checkpoint'] = checkpoint_binding(layout)
    _write_canonical_document(attempt_root / _EVIDENCE_FILENAME, evidence)
    evidence_usage(layout, ledger_path=request.ledger_path, visit=request.visit)
    if bindings.evidence_manifest_digest is None:
        advance("delta_captured", {**updates, "evidence_manifest_digest": canonical_sha256(evidence)})
        bindings = replace(bindings, **updates, evidence_manifest_digest=canonical_sha256(evidence))
    effects.crash_hook("delta")
    if stage == "completed_pending_parent_commit":
        pending_digest = allocation.retained.row_digest
    else:
        pending = advance("completed_pending_parent_commit", {}, kind="prepared", extra={
            "result_envelope_digest": canonical_sha256(envelope),
            "artifact_projection_digest": canonical_sha256(artifacts),
            "evidence_manifest_digest": bindings.evidence_manifest_digest})
        pending_digest = pending.authority_digest
    return PreparedRunRefSettlement(
        envelope=envelope, artifacts=artifacts,
        settled_result=SettledRunRefResultBinding(
            visit=request.visit, attempt_ordinal=ordinal, step_config_digest=bindings.step_config_digest,
            run_ref_root=bindings.run_ref_root, workspace_path=bindings.workspace_path,
            child_run_id=bindings.child_run_id, pending_row_digest=pending_digest,
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
    from .confinement import _read_recipe
    recipe = _read_recipe(layout)
    if canonical_sha256(recipe) != bindings.setup_evidence_digest:
        raise _invalid('setup_evidence_binding_invalid')
    from .confinement import _owned_root_identity
    # The retained control/parents stay authoritative after the disposable clone is retired.
    for name, path in (('control', layout.child_root), ('clone_parent', layout.workspace.parent),
                       ('run_ref_root', request.run_ref_root), ('control_parent', layout.child_root.parent),
                       ('run_ref_parent', request.run_ref_root.parent)):
        if name in recipe['owned_roots'] and _owned_root_identity(path) != recipe['owned_roots'][name]:
            raise _invalid('retained_root_identity_changed')
    from .holder_scope import validate_holder_scopes_quiescent
    validate_holder_scopes_quiescent(layout.child_root / 'holder')
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
    evidence = _read_canonical_document(attempt_root / _EVIDENCE_FILENAME, label="evidence_manifest")
    if not isinstance(evidence, dict) or canonical_sha256(evidence) != bindings.evidence_manifest_digest:
        raise _invalid('evidence_manifest_binding_invalid')
    delta_record = _read_canonical_document(attempt_root / _WORKSPACE_DELTA_FILENAME, label="workspace_delta")
    if canonical_sha256(delta_record) != bindings.workspace_delta_digest:
        raise _invalid('workspace_delta_binding_invalid')
    from .confined_evidence import retained_trees, evidence_usage
    baseline, final = retained_trees(layout, expected_digest=evidence.get('retained_trees_digest'),
        baseline_digest=bindings.post_setup_baseline_digest, final_digest=evidence.get('final_workspace_digest'),
        delta_digest=bindings.workspace_delta_digest)
    validate_retained_workspace_delta(delta_record, expected_digest=bindings.workspace_delta_digest,
        base=confined_revision(request.step_config.run_ref.repo, request.parent_state["commit"])[1],
        baseline_manifest=baseline, final_manifest=final,
        declared_artifacts=_declared(request, document), allow_aliases=True)
    evidence_usage(layout, ledger_path=request.ledger_path, visit=request.visit)
    accounting = _read_canonical_document(attempt_root / _ACCOUNTING_FILENAME, label="accounting")
    if (not isinstance(accounting, Mapping) or canonical_sha256(accounting) != bindings.accounting_digest
            or build_run_ref_accounting(**accounting) != accounting
            or (accounting["child_run_id"], accounting["attempt_ordinal"], accounting["terminal_status"])
            != (bindings.child_run_id, row.attempt_ordinal, document["status"])):
        raise _invalid("accounting_binding_invalid")
    from .ledger import confined_budget, load_attempt_ledger
    state = confined_budget(load_attempt_ledger(request.ledger_path, run_files=request.run_files).rows, request.visit)
    if state is None or state['active'] is not None or accounting['elapsed_ms'] != state['charged_ns'] // 1_000_000:
        raise _invalid('accounting_budget_binding_invalid')
    from .confined_exports import validate_exports
    exported = None if document['status'] == 'failed' else validate_exports(document['value'],
        request.step_config.run_ref.result_descriptor['envelope']['fields'][0]['type'],
        evidence.get('exports'), parent=request.parent_workspace)
    if document['status'] == 'failed' and evidence.get('exports') is not None:
        raise _invalid('failed_result_has_exports')
    envelope, artifacts = _outcome(request, document, delta_record, accounting, value=exported)
    expected_evidence = _evidence(request, row.attempt_ordinal, bindings, layout,
        envelope_digest=canonical_sha256(envelope), final_digest=final.digest)
    expected_evidence['retained_trees_digest'] = evidence['retained_trees_digest']
    from .confined_evidence import authority_inventory
    expected_evidence['authority_inventory'] = authority_inventory(layout)
    expected_evidence['exports'] = evidence['exports']
    expected_evidence['cleanup_checkpoint'] = evidence['cleanup_checkpoint']
    if (evidence != expected_evidence
            or canonical_sha256(evidence) != bindings.evidence_manifest_digest):
        raise _invalid("evidence_manifest_binding_invalid")
    return envelope, artifacts


__all__ = ["IMAGES_DIRNAME", "confined_attempt_bindings", "drive_confined_lifecycle",
           "validate_confined_bound_authority"]
