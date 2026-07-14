from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_shadow_points.orc")
POLICY_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_effect_policies.orc")
RESTORE_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_restore_regions.orc")
PROCEDURE_FIXTURE = Path(
    "tests/fixtures/workflow_lisp/valid/procedure_lowering_identity_modes.orc"
)


def _module():
    return importlib.import_module("orchestrator.workflow_lisp.lexical_checkpoints")


def _policy_module():
    return importlib.import_module("orchestrator.workflow_lisp.lexical_checkpoint_effect_policies")


def _compile_fixture(tmp_path: Path):
    local_fixture = tmp_path / FIXTURE.name
    local_fixture.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )


def _compile_restore_fixture(tmp_path: Path):
    local_fixture = tmp_path / RESTORE_FIXTURE.name
    local_fixture.write_text(RESTORE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )


def _compile_policy_fixture(tmp_path: Path):
    local_fixture = tmp_path / POLICY_FIXTURE.name
    local_fixture.write_text(POLICY_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )


def _compile_wcc_procedure_fixture(tmp_path: Path):
    providers = json.loads(
        PROCEDURE_FIXTURE.with_suffix(".providers.json").read_text(encoding="utf-8")
    )
    prompts = json.loads(
        PROCEDURE_FIXTURE.with_suffix(".prompts.json").read_text(encoding="utf-8")
    )
    command_payload = json.loads(
        PROCEDURE_FIXTURE.with_suffix(".commands.json").read_text(encoding="utf-8")
    )
    commands = {
        name: ExternalToolBinding(
            name=name,
            stable_command=tuple(payload["stable_command"]),
        )
        for name, payload in command_payload.items()
    }
    result = compile_stage3_entrypoint(
        PROCEDURE_FIXTURE,
        source_roots=(PROCEDURE_FIXTURE.parent,),
        entry_workflow="orchestrate",
        provider_externs=providers,
        prompt_externs=prompts,
        command_boundaries=commands,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    return next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )


def _effect_policy(point) -> dict[str, object]:
    return point.details["effect_boundary"]["policy"]


def _execution_inputs(tmp_path: Path) -> dict[str, object]:
    report_path = tmp_path / "artifacts" / "work" / "report.md"
    summary_path = tmp_path / "artifacts" / "work" / "summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("report\n", encoding="utf-8")
    summary_path.write_text("{}\n", encoding="utf-8")
    return {
        "report_path": "artifacts/work/report.md",
        "summary_target": "artifacts/work/summary.json",
        "run_checks_now": False,
    }


def _policy_execution_inputs(tmp_path: Path) -> dict[str, object]:
    report_path = tmp_path / "artifacts" / "work" / "report.md"
    summary_path = tmp_path / "artifacts" / "work" / "summary.json"
    run_state_path = tmp_path / "state" / "run_state.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("report\n", encoding="utf-8")
    summary_path.write_text("{}\n", encoding="utf-8")
    run_state_path.write_text('{"drain_status":"READY"}\n', encoding="utf-8")
    return {
        "run_state_path": "state/run_state.json",
        "report_path": "artifacts/work/report.md",
        "summary_target": "artifacts/work/summary.json",
        "run_checks_now": True,
    }


def _execute_policy_fixture_with_stubbed_effects(tmp_path: Path):
    from orchestrator.contracts.output_contract import validate_output_bundle

    bundle = _compile_policy_fixture(tmp_path)
    state_manager = StateManager(tmp_path, run_id="lexical-checkpoint-policy")
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)
    inputs = _policy_execution_inputs(tmp_path)
    state_manager.initialize(str(bundle.provenance.workflow_path), bound_inputs=inputs)

    def _write_bundle(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _fake_command(self, step, state):
        _, resolved_output_bundle, path_error = self._resolve_output_contract_paths(step, state)
        assert path_error is None
        assert resolved_output_bundle is not None
        bundle_path = self.workspace / resolved_output_bundle["path"]
        _write_bundle(bundle_path, {"status": "READY", "report": "artifacts/work/report.md"})
        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": validate_output_bundle(resolved_output_bundle, workspace=self.workspace),
        }

    def _fake_provider(self, step, state):
        _, resolved_output_bundle, path_error = self._resolve_output_contract_paths(step, state)
        assert path_error is None
        assert resolved_output_bundle is not None
        bundle_path = self.workspace / resolved_output_bundle["path"]
        _write_bundle(bundle_path, {"status": "COMPLETED", "report": "artifacts/work/report.md"})
        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": validate_output_bundle(resolved_output_bundle, workspace=self.workspace),
        }

    with patch.object(WorkflowExecutor, "_execute_command", _fake_command), patch.object(
        WorkflowExecutor,
        "_execute_provider",
        _fake_provider,
    ):
        final_state = executor.execute(on_error="stop")

    return executor, state_manager, bundle, final_state


def _latest_checkpoint_records_by_effect_kind(executor: WorkflowExecutor, state_manager: StateManager) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    checkpoints = _module()
    for point in executor.runtime_plan.lexical_checkpoint_points:
        if point.point_kind != "effect_boundary":
            continue
        index_path = checkpoints.resolve_checkpoint_index_path(
            state_manager=state_manager,
            workflow_name=point.workflow_name,
            checkpoint_id=point.checkpoint_id,
        )
        index_payload = json.loads(index_path.read_text(encoding="utf-8"))
        last_entry = index_payload["records"][-1]
        record_path = state_manager.workspace / last_entry["record_path"]
        records[point.details["effect_boundary"]["effect_kind"]] = json.loads(record_path.read_text(encoding="utf-8"))
    return records


def test_wcc_inline_procedure_has_no_synthetic_workflow_call_checkpoint(
    tmp_path: Path,
) -> None:
    bundle = _compile_wcc_procedure_fixture(tmp_path)

    inline_call_points = [
        point
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if "inline_plan" in point.step_id
        and point.details.get("step_kind") == "call"
        and _effect_policy(point)["policy_kind"]
        == "reuse_validated_workflow_call"
    ]

    assert inline_call_points == []


def test_wcc_inline_procedure_keeps_inner_provider_and_command_policies(
    tmp_path: Path,
) -> None:
    bundle = _compile_wcc_procedure_fixture(tmp_path)

    inline_effect_policies = {
        point.details["step_kind"]: _effect_policy(point)["policy_kind"]
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if "inline_plan" in point.step_id
        and point.details.get("step_kind") in {"provider", "command"}
    }

    assert inline_effect_policies == {
        "provider": "reuse_validated_structured_output",
        "command": "reuse_validated_structured_output",
    }


def test_wcc_real_workflow_and_private_procedure_calls_keep_workflow_call_policy(
    tmp_path: Path,
) -> None:
    workflow_workspace = tmp_path / "workflow-call"
    procedure_workspace = tmp_path / "private-procedure"
    workflow_workspace.mkdir()
    procedure_workspace.mkdir()
    workflow_bundle = _compile_fixture(workflow_workspace)
    procedure_bundle = _compile_wcc_procedure_fixture(procedure_workspace)

    real_workflow_call = next(
        point
        for point in workflow_bundle.runtime_plan.lexical_checkpoint_points
        if "pure_helper" in point.step_id
        and point.details.get("step_kind") == "call"
    )
    private_procedure_call = next(
        point
        for point in procedure_bundle.runtime_plan.lexical_checkpoint_points
        if "private_helper" in point.step_id
        and point.details.get("step_kind") == "call"
    )

    for point in (real_workflow_call, private_procedure_call):
        assert point.details["effect_boundary"]["effect_kind"] == "call"
        assert point.details["effect_boundary"]["boundary_kind"] == "call"
        assert _effect_policy(point)["policy_kind"] == "reuse_validated_workflow_call"


def test_checkpoint_id_derivation_is_deterministic() -> None:
    checkpoints = _module()

    first = checkpoints.derive_checkpoint_id(
        workflow_name="lexical_checkpoint_shadow_points::orchestrate",
        program_point_id="pp:effect_boundary:run_checks",
        executable_identity="root.command_boundary",
        lowering_schema_version="wcc_m4",
        checkpoint_schema_version="workflow_lisp_lexical_checkpoint.v1",
        storage_scope="step_visit",
    )
    second = checkpoints.derive_checkpoint_id(
        workflow_name="lexical_checkpoint_shadow_points::orchestrate",
        program_point_id="pp:effect_boundary:run_checks",
        executable_identity="root.command_boundary",
        lowering_schema_version="wcc_m4",
        checkpoint_schema_version="workflow_lisp_lexical_checkpoint.v1",
        storage_scope="step_visit",
    )
    different_scope = checkpoints.derive_checkpoint_id(
        workflow_name="lexical_checkpoint_shadow_points::orchestrate",
        program_point_id="pp:effect_boundary:run_checks",
        executable_identity="root.command_boundary",
        lowering_schema_version="wcc_m4",
        checkpoint_schema_version="workflow_lisp_lexical_checkpoint.v1",
        storage_scope="call_frame",
    )

    assert first == second
    assert first != different_scope


def test_record_id_derivation_includes_frame_identity() -> None:
    checkpoints = _module()

    base = checkpoints.derive_record_id(
        checkpoint_id="ckpt:test",
        run_id="20260613T120000Z-abcdef",
        execution_index=3,
        visit_count=1,
        loop_iteration=None,
        call_frame_id=None,
    )
    call_frame = checkpoints.derive_record_id(
        checkpoint_id="ckpt:test",
        run_id="20260613T120000Z-abcdef",
        execution_index=3,
        visit_count=1,
        loop_iteration=None,
        call_frame_id="call-frame-1",
    )
    loop_iteration = checkpoints.derive_record_id(
        checkpoint_id="ckpt:test",
        run_id="20260613T120000Z-abcdef",
        execution_index=3,
        visit_count=1,
        loop_iteration=1,
        call_frame_id=None,
    )

    assert len({base, call_frame, loop_iteration}) == 3


def test_program_point_ids_distinguish_effect_boundaries_and_loop_back_edges() -> None:
    checkpoints = _module()

    effect_boundary = checkpoints.derive_program_point_id(
        workflow_name="lexical_checkpoint_shadow_points::orchestrate",
        point_kind="effect_boundary",
        origin_key="source:effect",
        identity_digest="sha256:effect",
    )
    loop_back_edge = checkpoints.derive_program_point_id(
        workflow_name="lexical_checkpoint_shadow_points::orchestrate",
        point_kind="loop_back_edge",
        origin_key="source:loop",
        identity_digest="sha256:loop",
    )

    assert effect_boundary != loop_back_edge


def test_effect_resume_policy_digest_is_canonical_and_source_lineage_sensitive() -> None:
    policies = _policy_module()

    first = policies.build_effect_resume_policy(
        policy_kind="reuse_validated_structured_output",
        effect_kind="provider_call",
        boundary_kind="provider",
        step_id="root.provider",
        source_map_origin_key="source:provider",
        evidence_requirements={
            "structured_output": {
                "contract_digest": "sha256:contract",
                "payload_digest_required": True,
                "declared_target_only": True,
                "bundle_path_ref": "generated:provider_bundle",
            }
        },
    )
    same_meaning = policies.build_effect_resume_policy(
        policy_kind="reuse_validated_structured_output",
        effect_kind="provider_call",
        boundary_kind="provider",
        step_id="root.provider",
        source_map_origin_key="source:provider",
        evidence_requirements={
            "structured_output": {
                "bundle_path_ref": "generated:provider_bundle",
                "declared_target_only": True,
                "payload_digest_required": True,
                "contract_digest": "sha256:contract",
            }
        },
    )
    changed_origin = policies.build_effect_resume_policy(
        policy_kind="reuse_validated_structured_output",
        effect_kind="provider_call",
        boundary_kind="provider",
        step_id="root.provider",
        source_map_origin_key="source:other-provider",
        evidence_requirements={
            "structured_output": {
                "bundle_path_ref": "generated:provider_bundle",
                "declared_target_only": True,
                "payload_digest_required": True,
                "contract_digest": "sha256:contract",
            }
        },
    )

    assert first["schema_version"] == "workflow_lisp_effect_resume_policy.v1"
    assert first["policy_digest"] == same_meaning["policy_digest"]
    assert first["policy_digest"] != changed_origin["policy_digest"]


def test_effect_resume_policy_validation_rejects_unknown_policy_kind() -> None:
    policies = _policy_module()
    invalid = {
        "schema_version": "workflow_lisp_effect_resume_policy.v1",
        "policy_kind": "unknown_policy",
        "effect_kind": "provider_call",
        "boundary_kind": "provider",
        "step_id": "root.provider",
        "source_map_origin_key": "source:provider",
        "evidence_requirements": {
            "structured_output": {
                "bundle_path_ref": "generated:provider_bundle",
                "contract_digest": "sha256:contract",
                "payload_digest_required": True,
                "declared_target_only": True,
            }
        },
        "unsafe_pending_behavior": "fail_closed",
        "policy_digest": "sha256:placeholder",
    }

    with pytest.raises(ValueError, match="lexical_checkpoint_effect_policy_unknown_kind"):
        policies.validate_effect_resume_policy(invalid)


def test_effect_resume_policy_validation_rejects_policy_digest_drift() -> None:
    policies = _policy_module()
    invalid = policies.build_effect_resume_policy(
        policy_kind="reuse_validated_structured_output",
        effect_kind="provider_call",
        boundary_kind="provider",
        step_id="root.provider",
        source_map_origin_key="source:provider",
        evidence_requirements={
            "structured_output": {
                "bundle_path_ref": "generated:provider_bundle",
                "contract_digest": "sha256:contract",
                "payload_digest_required": True,
                "declared_target_only": True,
            }
        },
    )
    invalid["policy_digest"] = "sha256:drifted"

    with pytest.raises(ValueError, match="lexical_checkpoint_effect_policy_digest_mismatch"):
        policies.validate_effect_resume_policy(invalid)


def test_effect_resume_policy_validation_rejects_missing_certified_adapter_protocol() -> None:
    policies = _policy_module()
    invalid = {
        "schema_version": "workflow_lisp_effect_resume_policy.v1",
        "policy_kind": "certified_resume_protocol_required",
        "effect_kind": "command",
        "boundary_kind": "certified_adapter",
        "step_id": "root.normalize_result",
        "source_map_origin_key": "source:normalize-result",
        "evidence_requirements": {
            "structured_output": {
                "bundle_path_ref": "generated:command_bundle",
                "contract_digest": "sha256:contract",
                "payload_digest_required": True,
                "declared_target_only": True,
            }
        },
        "unsafe_pending_behavior": "requires_certified_resume_protocol",
    }
    invalid["policy_digest"] = policies.derive_effect_resume_policy_digest(invalid)

    with pytest.raises(ValueError, match="lexical_checkpoint_effect_policy_command_uncertified"):
        policies.validate_effect_resume_policy(invalid)


def test_legacy_provisional_record_remains_valid_but_non_reusable_against_r3_policy_point() -> None:
    checkpoints = _module()
    policies = _policy_module()
    point = {
        "checkpoint_id": "ckpt:test",
        "program_point_id": "pp:test",
        "point_kind": "effect_boundary",
        "workflow_name": "demo::workflow",
        "step_id": "root.provider",
        "node_id": "node.provider",
        "presentation_key": "provider",
        "origin_key": "source:provider",
        "step_kind": "provider",
        "wcc_identity": {
            "node_id_digest": checkpoints._sha256_text("wcc-node"),
            "scope_id_digest": checkpoints._sha256_text("wcc-scope"),
        },
        "runtime_program_identity": {
            "wcc_node_id": "wcc-node",
            "wcc_scope_id": "wcc-scope",
            "lowering_schema_version": "wcc_m4",
        },
        "binding_schema": {"schema_digest": "sha256:bindings"},
        "storage": {
            "semantic_role": "lexical_checkpoint_record",
            "privacy": "runtime_sidecar",
            "resume_scope": "step_visit",
            "allocation_id": "alloc:checkpoint",
        },
        "effect_boundary": {
            "effect_kind": "provider_call",
            "boundary_kind": "provider",
            "policy": policies.build_effect_resume_policy(
                policy_kind="reuse_validated_structured_output",
                effect_kind="provider_call",
                boundary_kind="provider",
                step_id="root.provider",
                source_map_origin_key="source:provider",
                evidence_requirements={
                    "structured_output": {
                        "bundle_path_ref": "generated:provider_bundle",
                        "contract_digest": "sha256:contract",
                        "payload_digest_required": True,
                        "declared_target_only": True,
                    }
                },
            ),
        },
    }
    record = {
        "schema_version": "workflow_lisp_lexical_checkpoint.v1",
        "checkpoint_id": "ckpt:test",
        "program_point_id": "pp:test",
        "point_kind": "effect_boundary",
        "record_id": "record:test",
        "binding_schema_digest": "sha256:bindings",
        "storage_allocation_id": "alloc:checkpoint",
        "origin_key": "source:provider",
        "provisional_policy": "shadow_record_only",
        "validity_envelope": {
            "binding_schema_digest": "sha256:bindings",
            "effect_policy_digest": checkpoints._sha256_json(
                {
                    "point_kind": "effect_boundary",
                    "policy_status": "shadow_record_only",
                    "step_kind": "provider",
                    "effect_kind": "provider_call",
                    "boundary_kind": "provider",
                    "loop_name": None,
                }
            ),
            "source_map_origin_key": "source:provider",
            "storage_allocation_id": "alloc:checkpoint",
        },
    }

    checkpoints.validate_checkpoint_record(record, expected_point=point)

    summary = checkpoints.describe_checkpoint_record_policy(record, expected_point=point)
    assert summary["record_policy_status"] == "historical_shadow_only"
    assert summary["restore_authorized"] is False


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("schema_version", "workflow_lisp_lexical_checkpoint.v0"),
        ("binding_schema_digest", ""),
        ("storage_allocation_id", ""),
        ("origin_key", ""),
        ("provisional_policy", "unknown"),
    ),
)
def test_checkpoint_record_validation_rejects_mismatched_identity_and_unknown_policy_metadata(
    field_name: str,
    value: object,
) -> None:
    checkpoints = _module()
    record = {
        "schema_version": "workflow_lisp_lexical_checkpoint.v1",
        "checkpoint_id": "ckpt:test",
        "program_point_id": "pp:test",
        "record_id": "record:test",
        "binding_schema_digest": "sha256:bindings",
        "storage_allocation_id": "alloc:test",
        "origin_key": "source:test",
        "provisional_policy": "shadow_record_only",
    }
    record[field_name] = value

    with pytest.raises(ValueError):
        checkpoints.validate_checkpoint_record(record)


def test_checkpoint_storage_roles_allocate_runtime_sidecars_and_reject_duplicate_frame_identity() -> None:
    checkpoints = _module()

    record_role = checkpoints.allocate_checkpoint_storage(
        workflow_name="lexical_checkpoint_shadow_points::orchestrate",
        checkpoint_id="ckpt:test",
        semantic_role="lexical_checkpoint_record",
    )
    index_role = checkpoints.allocate_checkpoint_storage(
        workflow_name="lexical_checkpoint_shadow_points::orchestrate",
        checkpoint_id="ckpt:test",
        semantic_role="lexical_checkpoint_index",
    )

    assert record_role.privacy == "runtime_sidecar"
    assert index_role.privacy == "runtime_sidecar"

    with pytest.raises(ValueError):
        checkpoints.validate_checkpoint_index_update(
            checkpoint_id="ckpt:test",
            existing_records=(
                {
                    "record_id": "record:test",
                    "frame_identity": {"execution_index": 1, "visit_count": 1, "call_frame_id": "frame-a"},
                },
            ),
            candidate_record={
                "record_id": "record:test",
                "frame_identity": {"execution_index": 1, "visit_count": 1, "call_frame_id": "frame-b"},
            },
        )


def test_runtime_shadow_emission_writes_record_and_index_after_authoritative_state_commit(tmp_path: Path) -> None:
    checkpoints = _module()
    bundle = _compile_fixture(tmp_path)
    state_manager = StateManager(tmp_path, run_id="lexical-checkpoint-red")
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)
    checkpoints.assert_runtime_shadow_emission(
        executor=executor,
        state_manager=state_manager,
        inputs=_execution_inputs(tmp_path),
        expected_record_kinds={"effect_boundary", "loop_back_edge"},
    )


def test_runtime_shadow_emission_call_frame_record_ids_include_durable_call_frame_identity(tmp_path: Path) -> None:
    checkpoints = _module()
    bundle = _compile_fixture(tmp_path)
    state_manager = StateManager(tmp_path, run_id="lexical-checkpoint-call-frame")
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)

    checkpoints.assert_runtime_shadow_emission(
        executor=executor,
        state_manager=state_manager,
        inputs=_execution_inputs(tmp_path),
        expected_record_kinds={"effect_boundary", "loop_back_edge"},
    )

    call_point = next(
        point
        for point in executor.runtime_plan.lexical_checkpoint_points
        if point.details.get("step_kind") == "call"
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=call_point.workflow_name,
        checkpoint_id=call_point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    call_record_entry = next(
        entry
        for entry in index_payload["records"]
        if entry["frame_identity"].get("call_frame_id")
    )
    record_path = tmp_path / call_record_entry["record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))

    assert record["frame_identity"]["call_frame_id"]
    assert record["record_id"] == checkpoints.derive_record_id(
        checkpoint_id=call_point.checkpoint_id,
        run_id=state_manager.run_id,
        execution_index=record["frame_identity"]["execution_index"],
        visit_count=record["frame_identity"]["visit_count"],
        loop_iteration=record["frame_identity"]["loop_iteration"],
        call_frame_id=record["frame_identity"]["call_frame_id"],
    )


def test_runtime_shadow_emission_may_attach_restore_payload_while_preserving_r1_validation(tmp_path: Path) -> None:
    checkpoints = _module()
    bundle = _compile_restore_fixture(tmp_path)
    state_manager = StateManager(tmp_path, run_id="lexical-checkpoint-restore-payload")
    state_manager.initialize(
        str(tmp_path / RESTORE_FIXTURE.name),
        bound_inputs={
            "report_path": "artifacts/work/report.md",
            "summary_target": "artifacts/work/summary.json",
        },
    )
    report_path = tmp_path / "artifacts" / "work" / "report.md"
    summary_path = tmp_path / "artifacts" / "work" / "summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("report\n", encoding="utf-8")
    summary_path.write_text("{}\n", encoding="utf-8")

    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic restore payload failure")
        return real_render_view(*args, **kwargs)

    with patch("orchestrator.workflow.executor.render_view", side_effect=_fail_render_once):
        result = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert result["status"] == "failed"

    observed_restore_payloads = []
    for point in bundle.runtime_plan.lexical_checkpoint_points:
        index_path = checkpoints.resolve_checkpoint_index_path(
            state_manager=state_manager,
            workflow_name=point.workflow_name,
            checkpoint_id=point.checkpoint_id,
        )
        if not index_path.is_file():
            continue
        index_payload = json.loads(index_path.read_text(encoding="utf-8"))
        for entry in index_payload.get("records", []):
            record_path = tmp_path / entry["record_path"]
            record = json.loads(record_path.read_text(encoding="utf-8"))
            checkpoints.validate_checkpoint_record(record, expected_point=checkpoints._point_payload(point))
            observed_restore_payloads.append(record.get("restore_payload"))

    assert any(isinstance(payload, dict) for payload in observed_restore_payloads)


def test_runtime_shadow_emission_fail_closed_for_invalid_point_metadata(tmp_path: Path) -> None:
    bundle = _compile_fixture(tmp_path)
    state_manager = StateManager(tmp_path, run_id="lexical-checkpoint-fail-closed")
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)
    call_point = next(
        point for point in executor.runtime_plan.lexical_checkpoint_points if point.details.get("step_kind") == "call"
    )
    tampered_point = replace(call_point, origin_key="")
    executor.runtime_plan = replace(
        executor.runtime_plan,
        lexical_checkpoint_points=tuple(
            tampered_point if point.checkpoint_id == call_point.checkpoint_id else point
            for point in executor.runtime_plan.lexical_checkpoint_points
        ),
    )
    state_manager.initialize(str(bundle.provenance.workflow_path), bound_inputs=_execution_inputs(tmp_path))

    with pytest.raises(ValueError, match="lexical_checkpoint_source_lineage_mismatch"):
        executor.execute(on_error="stop")


def test_runtime_shadow_emission_fail_closed_for_program_identity_mismatch(tmp_path: Path) -> None:
    bundle = _compile_fixture(tmp_path)
    state_manager = StateManager(tmp_path, run_id="lexical-checkpoint-program-identity")
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)
    call_point = next(
        point for point in executor.runtime_plan.lexical_checkpoint_points if point.details.get("step_kind") == "call"
    )
    tampered_details = {
        **dict(call_point.details),
        "wcc_identity": {
            **dict(call_point.details.get("wcc_identity", {})),
            "node_id_digest": "sha256:tampered",
        },
    }
    executor.runtime_plan = replace(
        executor.runtime_plan,
        lexical_checkpoint_points=tuple(
            replace(point, details=tampered_details)
            if point.checkpoint_id == call_point.checkpoint_id
            else point
            for point in executor.runtime_plan.lexical_checkpoint_points
        ),
    )
    state_manager.initialize(str(bundle.provenance.workflow_path), bound_inputs=_execution_inputs(tmp_path))

    with pytest.raises(ValueError, match="lexical_checkpoint_program_identity_mismatch"):
        executor.execute(on_error="stop")


def test_runtime_shadow_emission_preserves_authoritative_state_when_sidecar_write_fails_closed(tmp_path: Path) -> None:
    bundle = _compile_fixture(tmp_path)
    state_manager = StateManager(tmp_path, run_id="lexical-checkpoint-sidecar-failure")
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)
    state_manager.initialize(str(bundle.provenance.workflow_path), bound_inputs=_execution_inputs(tmp_path))

    original_write = state_manager.write_runtime_sidecar_json

    def _failing_write(path, payload):
        if "workflow_lisp/checkpoints/records" in str(path):
            raise OSError("synthetic checkpoint-sidecar failure")
        return original_write(path, payload)

    with patch.object(state_manager, "write_runtime_sidecar_json", side_effect=_failing_write):
        with pytest.raises(OSError, match="synthetic checkpoint-sidecar failure"):
            executor.execute(on_error="stop")

    persisted = state_manager.load().to_dict()
    assert any(
        "pure-helper" in step_name and isinstance(value, dict) and value.get("status") == "completed"
        for step_name, value in persisted["steps"].items()
    )


def test_runtime_shadow_emission_records_completed_effect_refs_for_command_provider_call_materialize_view_and_transition(
    tmp_path: Path,
) -> None:
    checkpoints = _module()
    executor, state_manager, bundle, final_state = _execute_policy_fixture_with_stubbed_effects(tmp_path)

    assert final_state["status"] == "completed"

    records_by_effect = _latest_checkpoint_records_by_effect_kind(executor, state_manager)
    points_by_effect = {
        point.details["effect_boundary"]["effect_kind"]: checkpoints._point_payload(point)
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.point_kind == "effect_boundary"
    }

    assert records_by_effect["pure_projection"]["completed_effect_refs"] == []
    command_ref = records_by_effect["command"]["completed_effect_refs"][0]
    assert command_ref["effect_ref_schema_version"] == "workflow_lisp_completed_effect_ref.v1"
    assert command_ref["evidence_kind"] == "structured_output_bundle"
    assert command_ref["status"] == "completed"
    provider_ref = records_by_effect["provider"]["completed_effect_refs"][0]
    assert provider_ref["prompt_input_contract_digest"].startswith("sha256:")
    call_ref = records_by_effect["call"]["completed_effect_refs"][0]
    assert call_ref["target_dsl_version"] == "2.14"
    assert call_ref["callee_checksum"].startswith("sha256:")
    materialized_view_ref = records_by_effect["materialize_view"]["completed_effect_refs"][0]
    assert materialized_view_ref["renderer_id"] == "canonical-json"
    assert materialized_view_ref["renderer_version"] == 1
    assert materialized_view_ref["value_digest"].startswith("sha256:")
    assert materialized_view_ref["durability_mode"] == "preserve"
    transition_ref = records_by_effect["resource_transition"]["completed_effect_refs"][0]
    assert transition_ref["audit_digest"].startswith("sha256:")
    assert transition_ref["request_digest"].startswith("sha256:")
    assert transition_ref["audit_row_index"] == 0
    assert transition_ref["audit_row_digest"].startswith("sha256:")
    assert transition_ref["audit_outcome_code"] == "committed"
    assert transition_ref["result_digest"].startswith("sha256:")
    assert transition_ref["backend_kind"] == "runtime_native"
    for effect_kind in ("command", "provider", "call", "materialize_view", "resource_transition"):
        record = records_by_effect[effect_kind]
        assert record["completed_effect_refs"]
        assert record["validity_envelope"]["completed_effect_refs_digest"].startswith("sha256:")
        checkpoints.validate_checkpoint_record(record, expected_point=points_by_effect[effect_kind])


@pytest.mark.parametrize(
    ("effect_kind", "field_name", "replacement", "expected_code"),
    (
        ("command", "contract_digest", "sha256:tampered", "lexical_checkpoint_effect_policy_structured_output_invalid"),
        ("provider", "payload_digest", "sha256:tampered", "lexical_checkpoint_effect_policy_structured_output_invalid"),
        ("materialize_view", "value_digest", "sha256:tampered", "lexical_checkpoint_effect_policy_materialized_view_mismatch"),
        ("resource_transition", "audit_path", "", "lexical_checkpoint_effect_policy_transition_audit_missing"),
    ),
)
def test_checkpoint_record_validation_fails_closed_for_mutated_completed_effect_refs(
    tmp_path: Path,
    effect_kind: str,
    field_name: str,
    replacement: object,
    expected_code: str,
) -> None:
    checkpoints = _module()
    executor, state_manager, bundle, final_state = _execute_policy_fixture_with_stubbed_effects(tmp_path)

    assert final_state["status"] == "completed"

    records_by_effect = _latest_checkpoint_records_by_effect_kind(executor, state_manager)
    points_by_effect = {
        point.details["effect_boundary"]["effect_kind"]: checkpoints._point_payload(point)
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.point_kind == "effect_boundary"
    }
    record = records_by_effect[effect_kind]
    record["completed_effect_refs"][0][field_name] = replacement

    with pytest.raises(ValueError, match=expected_code):
        checkpoints.validate_checkpoint_record(record, expected_point=points_by_effect[effect_kind])
