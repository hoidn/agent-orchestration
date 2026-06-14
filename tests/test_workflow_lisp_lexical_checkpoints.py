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
RESTORE_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_restore_regions.orc")


def _module():
    return importlib.import_module("orchestrator.workflow_lisp.lexical_checkpoints")


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
