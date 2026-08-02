from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.state import StateManager, StepResult
from orchestrator.workflow.executable_ir import derive_unbound_trial_step_config
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.trial.adjudication import evaluate_trial_execution
from orchestrator.workflow.trial.contracts import derive_trial_cell_effect_scopes
from orchestrator.workflow.trial.ledger import load_trial_event_ledger
from orchestrator.workflow.trial.settlement import (
    commit_trial_parent_settlement,
    prepare_trial_parent_settlement,
)
from orchestrator.workflow_lisp import lexical_checkpoints as checkpoints
from orchestrator.workflow_lisp.lexical_checkpoint_effect_policies import (
    derive_effect_resume_policy_digest,
)
from tests.test_workflow_trial_adjudication import (
    _Executor,
    _blinded_cell_harnesses,
    _dependencies,
)
from tests.test_workflow_trial_runtime import _execute, _runtime_fixture


def _trial_point(request):
    policy = {
        "schema_version": "workflow_lisp_effect_resume_policy.v1",
        "policy_kind": "reuse_validated_trial_result",
        "effect_kind": "trial",
        "boundary_kind": "trial",
        "step_id": request.visit.step_id,
        "source_map_origin_key": "source:trial",
        "evidence_requirements": {
            "trial_result": {
                "trial_static_config_digest": request.static_config_digest,
                "result_contract_digest": request.result_contract_digest,
            }
        },
        "unsafe_pending_behavior": "fail_closed",
    }
    policy["policy_digest"] = derive_effect_resume_policy_digest(policy)
    return SimpleNamespace(
        checkpoint_id="checkpoint:trial",
        program_point_id="program-point:trial",
        point_kind="effect_boundary",
        workflow_name="parent",
        step_id=request.visit.step_id,
        node_id="node.trial",
        presentation_key="Compare",
        origin_key="source:trial",
        details={
            "step_kind": "trial",
            "executable_identity": {
                "step_id": request.visit.step_id,
                "identity_component_digest": request.static_config_digest,
                "trial_result_contract_digest": request.result_contract_digest,
            },
            "effect_boundary": {
                "effect_kind": "trial",
                "boundary_kind": "trial",
                "policy": policy,
            },
        },
    )


def _committed_trial_checkpoint_fixture(tmp_path: Path):
    fixture = _runtime_fixture(tmp_path / "fixture")
    request = fixture["request"]
    workspace = fixture["parent_workspace"]
    workflow_path = workspace / "parent.orc"
    workflow_path.write_text('(workflow-lisp (:target-dsl "2.25"))\n')
    state_manager = StateManager(workspace, run_id=request.visit.parent_run_id)
    state_manager.initialize(
        str(workflow_path),
        bound_inputs={"payload": "fixed"},
    )
    state_manager.bind_run_ref_root(fixture["run_ref_root"])
    fixture["parent_run_root"] = state_manager.run_root.resolve()
    fixture["scopes"] = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=fixture["parent_run_root"],
        run_ref_root=fixture["run_ref_root"],
    )

    execution = _execute(fixture, _blinded_cell_harnesses())
    dependencies, _ = _dependencies(_Executor())
    adjudicated = evaluate_trial_execution(
        request,
        execution,
        parent_workspace=workspace,
        dependencies=dependencies,
    )
    envelope = {
        "outcomes": list(adjudicated.authored_outcomes),
        "verdict": adjudicated.verdict,
        "verdict_artifact": adjudicated.verdict_artifact.relpath,
    }
    artifacts = {"verdict": adjudicated.verdict_artifact.relpath}
    prepared = prepare_trial_parent_settlement(
        execution.ledger_path,
        request=request,
        parent_workspace=workspace,
        result_envelope=envelope,
    )
    state_manager.state.step_visits["Compare"] = request.visit.visit_count
    state_manager.update_step(
        "Compare",
        StepResult(
            status="completed",
            exit_code=0,
            name="Compare",
            step_id=request.visit.step_id,
            visit_count=request.visit.visit_count,
            trial=envelope,
            artifacts=artifacts,
        ),
    )
    state = state_manager.load().to_dict()
    committed = commit_trial_parent_settlement(
        execution.ledger_path,
        request=request,
        prepared=prepared,
        step_name="Compare",
        expected_artifacts=artifacts,
        read_parent_state=lambda: state,
    )
    point = _trial_point(request)
    runtime_step = SimpleNamespace(
        node=SimpleNamespace(execution_config=request.step_config),
        name=point.presentation_key,
        step_id=point.step_id,
    )
    executor = SimpleNamespace(
        state_manager=state_manager,
        workspace=workspace,
        _runtime_step_for_node_id=lambda *_args, **_kwargs: runtime_step,
    )
    runtime_node = SimpleNamespace(
        kind="trial",
        node_id=point.node_id,
        step_id=point.step_id,
        trial_config_digest=request.static_config_digest,
        trial_result_contract_digest=request.result_contract_digest,
    )
    runtime_plan = SimpleNamespace(
        workflow_name="parent",
        ordered_node_ids=(point.node_id,),
        nodes={point.node_id: runtime_node},
        lexical_checkpoint_points=(point,),
        resume_checkpoints=(),
    )
    executable_workflow = SimpleNamespace(
        version="2.25",
        nodes={
            point.node_id: SimpleNamespace(
                execution_config=request.step_config,
            )
        },
    )
    return SimpleNamespace(
        fixture=fixture,
        request=request,
        execution=execution,
        envelope=envelope,
        artifacts=artifacts,
        prepared=prepared,
        committed=committed,
        state_manager=state_manager,
        state=state,
        point=point,
        executor=executor,
        runtime_plan=runtime_plan,
        executable_workflow=executable_workflow,
    )


def _record(ref):
    return {
        "completed_effect_refs": [ref],
        "validity_envelope": {
            "completed_effect_refs_digest": checkpoints._completed_effect_refs_digest(
                (ref,)
            )
        },
        "frame_identity": {
            "execution_index": 0,
            "visit_count": 1,
            "loop_iteration": None,
            "call_frame_id": None,
        },
    }


def test_trial_completed_effect_ref_is_closed_digest_only_authority(
    tmp_path: Path,
) -> None:
    authority = _committed_trial_checkpoint_fixture(tmp_path)

    refs = checkpoints.collect_completed_effect_refs(
        authority.executor,
        point=authority.point,
        committed_step_state=authority.state["steps"]["Compare"],
    )

    ledger = load_trial_event_ledger(authority.execution.ledger_path)
    assert refs == [
        {
            "effect_ref_schema_version": "workflow_lisp_completed_effect_ref.v1",
            "effect_kind": "trial",
            "step_id": authority.request.visit.step_id,
            "status": "completed",
            "source_map_origin_key": authority.point.origin_key,
            "evidence_kind": "trial_result",
            "trial_static_config_digest": authority.request.static_config_digest,
            "trial_step_config_digest": authority.request.trial_step_config_digest,
            "trial_request_digest": authority.request.digest,
            "trial_visit_digest": canonical_sha256(authority.request.visit.record),
            "result_contract_digest": authority.request.result_contract_digest,
            "result_envelope_digest": canonical_sha256(authority.envelope),
            "trial_prepared_row_digest": authority.prepared.row.row_digest,
            "trial_parent_committed_row_digest": authority.committed.row_digest,
            "parent_state_settlement_digest": ledger.rows[-1].payload[
                "parent_state_settlement_digest"
            ],
        }
    ]
    assert "result_envelope" not in refs[0]
    checkpoints._validate_completed_effect_refs(
        _record(refs[0]),
        expected_point=checkpoints._point_payload(authority.point),
    )


def test_trial_completed_effect_ref_rejects_resealed_shape_or_digest_drift(
    tmp_path: Path,
) -> None:
    authority = _committed_trial_checkpoint_fixture(tmp_path)
    [original] = checkpoints.collect_completed_effect_refs(
        authority.executor,
        point=authority.point,
        committed_step_state=authority.state["steps"]["Compare"],
    )
    variants = []
    extra = deepcopy(dict(original))
    extra["result_envelope"] = authority.envelope
    variants.append(extra)
    missing = deepcopy(dict(original))
    missing.pop("trial_parent_committed_row_digest")
    variants.append(missing)
    malformed = deepcopy(dict(original))
    malformed["trial_request_digest"] = "sha256:invalid"
    variants.append(malformed)
    stale = deepcopy(dict(original))
    stale["trial_static_config_digest"] = "sha256:" + "0" * 64
    variants.append(stale)

    for ref in variants:
        with pytest.raises(
            ValueError,
            match="lexical_checkpoint_effect_policy_trial_result_invalid",
        ):
            checkpoints._validate_completed_effect_refs(
                _record(ref),
                expected_point=checkpoints._point_payload(authority.point),
            )

    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_effect_policy_trial_result_invalid",
    ):
        checkpoints._validate_completed_effect_refs(
            {
                "completed_effect_refs": [original, original],
                "validity_envelope": {
                    "completed_effect_refs_digest": (
                        checkpoints._completed_effect_refs_digest(
                            (original, original)
                        )
                    )
                },
            },
            expected_point=checkpoints._point_payload(authority.point),
        )


def test_trial_completed_effect_ref_revalidates_exact_terminal_authority(
    tmp_path: Path,
) -> None:
    authority = _committed_trial_checkpoint_fixture(tmp_path)
    [ref] = checkpoints.collect_completed_effect_refs(
        authority.executor,
        point=authority.point,
        committed_step_state=authority.state["steps"]["Compare"],
    )
    record = _record(ref)

    checkpoints.validate_completed_effect_refs_against_authoritative_state(
        record,
        expected_point=checkpoints._point_payload(authority.point),
        state=authority.state,
        state_manager=authority.state_manager,
        workspace=authority.fixture["parent_workspace"],
        executable_workflow=authority.executable_workflow,
        runtime_plan=authority.runtime_plan,
    )

    later_state = deepcopy(authority.state)
    later_state["current_step"] = {
        "name": "Later",
        "step_id": "root.later",
        "type": "provider",
        "status": "failed",
        "visit_count": 1,
    }
    checkpoints.validate_completed_effect_refs_against_authoritative_state(
        record,
        expected_point=checkpoints._point_payload(authority.point),
        state=later_state,
        state_manager=authority.state_manager,
        workspace=authority.fixture["parent_workspace"],
        executable_workflow=authority.executable_workflow,
        runtime_plan=authority.runtime_plan,
    )

    unsettled_current_state = deepcopy(authority.state)
    unsettled_current_state["current_step"] = {
        "name": "Compare",
        "step_id": authority.request.visit.step_id,
        "type": "trial",
        "status": "running",
        "visit_count": authority.request.visit.visit_count,
    }
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_effect_policy_trial_result_invalid",
    ):
        checkpoints.validate_completed_effect_refs_against_authoritative_state(
            record,
            expected_point=checkpoints._point_payload(authority.point),
            state=unsettled_current_state,
            state_manager=authority.state_manager,
            workspace=authority.fixture["parent_workspace"],
            executable_workflow=authority.executable_workflow,
            runtime_plan=authority.runtime_plan,
        )

    tampered_state = deepcopy(authority.state)
    tampered_state["steps"]["Compare"]["trial"]["verdict"][
        "selected_arm"
    ] = "not-the-committed-result"
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_effect_policy_trial_result_invalid",
    ):
        checkpoints.validate_completed_effect_refs_against_authoritative_state(
            record,
            expected_point=checkpoints._point_payload(authority.point),
            state=tampered_state,
            state_manager=authority.state_manager,
            workspace=authority.fixture["parent_workspace"],
            executable_workflow=authority.executable_workflow,
            runtime_plan=authority.runtime_plan,
        )

    unbound_config = derive_unbound_trial_step_config(
        authority.request.static_config
    )
    assert (
        unbound_config.step_config_digest
        != authority.request.trial_step_config_digest
    )
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_effect_policy_trial_result_invalid",
    ):
        checkpoints.validate_completed_effect_refs_against_authoritative_state(
            record,
            expected_point=checkpoints._point_payload(authority.point),
            state=authority.state,
            state_manager=authority.state_manager,
            workspace=authority.fixture["parent_workspace"],
            executable_workflow=SimpleNamespace(
                version="2.25",
                nodes={
                    authority.point.node_id: SimpleNamespace(
                        execution_config=unbound_config,
                    )
                },
            ),
            runtime_plan=authority.runtime_plan,
        )

    resealed = deepcopy(dict(ref))
    resealed["trial_parent_committed_row_digest"] = "sha256:" + "9" * 64
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_effect_policy_trial_result_invalid",
    ):
        checkpoints.validate_completed_effect_refs_against_authoritative_state(
            _record(resealed),
            expected_point=checkpoints._point_payload(authority.point),
            state=authority.state,
            state_manager=authority.state_manager,
            workspace=authority.fixture["parent_workspace"],
            executable_workflow=authority.executable_workflow,
            runtime_plan=authority.runtime_plan,
        )


def test_completed_trial_checkpoint_rejects_missing_prepared_only_or_extra_authority(
    tmp_path: Path,
) -> None:
    authority = _committed_trial_checkpoint_fixture(tmp_path)
    ledger_path = authority.execution.ledger_path
    original = ledger_path.read_bytes()
    rows = original.splitlines(keepends=True)
    variants = (
        b"".join(rows[:-1]),
        None,
        original + rows[-1],
    )
    for payload in variants:
        if payload is None:
            ledger_path.unlink()
        else:
            ledger_path.write_bytes(payload)
        with pytest.raises(
            ValueError,
            match="lexical_checkpoint_effect_policy_trial_result_invalid",
        ):
            checkpoints.collect_completed_effect_refs(
                authority.executor,
                point=authority.point,
                committed_step_state=authority.state["steps"]["Compare"],
            )
        ledger_path.write_bytes(original)


def test_trial_checkpoint_authority_preserves_root_frame_and_checkpoint_guards(
    tmp_path: Path,
) -> None:
    authority = _committed_trial_checkpoint_fixture(tmp_path)
    [ref] = checkpoints.collect_completed_effect_refs(
        authority.executor,
        point=authority.point,
        committed_step_state=authority.state["steps"]["Compare"],
    )
    record = _record(ref)

    wrong_frame = deepcopy(record)
    wrong_frame["frame_identity"]["call_frame_id"] = "frame:other"
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_effect_policy_trial_result_invalid",
    ):
        checkpoints.validate_completed_effect_refs_against_authoritative_state(
            wrong_frame,
            expected_point=checkpoints._point_payload(authority.point),
            state=authority.state,
            state_manager=authority.state_manager,
            workspace=authority.fixture["parent_workspace"],
            executable_workflow=authority.executable_workflow,
            runtime_plan=authority.runtime_plan,
        )

    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_effect_policy_trial_result_invalid",
    ):
        checkpoints.validate_completed_effect_refs_against_authoritative_state(
            record,
            expected_point=checkpoints._point_payload(authority.point),
            state=authority.state,
            state_manager=authority.state_manager,
            workspace=tmp_path.resolve(),
            executable_workflow=authority.executable_workflow,
            runtime_plan=authority.runtime_plan,
        )

    stale_point = deepcopy(checkpoints._point_payload(authority.point))
    stale_point["effect_boundary"]["policy"]["evidence_requirements"][
        "trial_result"
    ]["trial_static_config_digest"] = "sha256:" + "0" * 64
    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_effect_policy_trial_result_invalid",
    ):
        checkpoints.validate_completed_effect_refs_against_authoritative_state(
            record,
            expected_point=stale_point,
            state=authority.state,
            state_manager=authority.state_manager,
            workspace=authority.fixture["parent_workspace"],
            executable_workflow=authority.executable_workflow,
            runtime_plan=authority.runtime_plan,
        )


def test_trial_runtime_program_identity_requires_exact_point_and_config(
    tmp_path: Path,
) -> None:
    authority = _committed_trial_checkpoint_fixture(tmp_path)

    identity = checkpoints.checkpoint_runtime_program_identity(
        state_manager=authority.state_manager,
        runtime_plan=authority.runtime_plan,
        executable_ir=authority.executable_workflow,
    )
    assert identity["executable_ir_digest"].startswith("sha256:")

    with pytest.raises(
        ValueError,
        match="lexical_checkpoint_program_identity_mismatch",
    ):
        checkpoints.checkpoint_runtime_program_identity(
            state_manager=authority.state_manager,
            runtime_plan=SimpleNamespace(
                **{
                    **vars(authority.runtime_plan),
                    "lexical_checkpoint_points": (),
                }
            ),
            executable_ir=authority.executable_workflow,
        )

    runtime_node = authority.runtime_plan.nodes[authority.point.node_id]
    for field in (
        "trial_config_digest",
        "trial_result_contract_digest",
    ):
        stale_node = SimpleNamespace(
            **{
                **vars(runtime_node),
                field: "sha256:" + "0" * 64,
            }
        )
        stale_plan = SimpleNamespace(
            **{
                **vars(authority.runtime_plan),
                "nodes": {authority.point.node_id: stale_node},
            }
        )
        with pytest.raises(
            ValueError,
            match="lexical_checkpoint_program_identity_mismatch",
        ):
            checkpoints.checkpoint_runtime_program_identity(
                state_manager=authority.state_manager,
                runtime_plan=stale_plan,
                executable_ir=authority.executable_workflow,
            )
