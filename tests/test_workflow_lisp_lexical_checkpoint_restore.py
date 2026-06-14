from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_restore_regions.orc")
POLICY_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_effect_policies.orc")
CERTIFIED_ADAPTER_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/certified_adapter_call.orc")
PLAIN_PURE_BINDING_FIXTURE_SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lexical_checkpoint_restore_plain_binding)
  (export orchestrate)
  (defpath MaterializedSummaryPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord Output
    (summary_path MaterializedSummaryPath))
  (defworkflow orchestrate
    ((summary_target MaterializedSummaryPath))
    -> Output
    (let* ((plain_status "ready")
           (summary_path
             (materialize-view runtime-summary
               :value plain_status
               :renderer canonical-json
               :renderer-version 1
               :target summary_target
               :returns MaterializedSummaryPath)))
       (record Output
        :summary_path summary_path))))\n"""
TRANSITION_RESUME_FIXTURE_SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lexical_checkpoint_transition_resume)
  (export orchestrate)
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
  (defpath MaterializedSummaryPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord DrainRunState
    (drain_status String))
  (defrecord DrainStatusRequest
    (status String))
  (defrecord DrainStatusResult
    (status String))
  (defrecord DrainStatusAudit
    (status String))
  (defrecord Output
    (summary_path MaterializedSummaryPath)
    (transition_status String))
  (defresource drain-run-state
    :state-type DrainRunState
    :backing (bridge run_state_path))
  (deftransition write-drain-status
    :resource drain-run-state
    :request-type DrainStatusRequest
    :result-type DrainStatusResult
    :preconditions ((!= request.status ""))
    :updates ((set-field drain_status request.status))
    :write-set (drain_status)
    :idempotency-fields (status)
    :result (record DrainStatusResult
      :status request.status)
    :audit (record DrainStatusAudit
      :status request.status)
    :conflict-policy fail_closed
    :backend runtime_native)
  (defworkflow orchestrate
    ((run_state_path StateFile)
     (summary_target MaterializedSummaryPath))
    -> Output
    (let* ((transition
             (resource-transition
               :transition write-drain-status
               :resource drain-run-state
               :request (record DrainStatusRequest
                 :status "BLOCKED")))
           (summary_path
             (materialize-view runtime-summary
               :value transition
               :renderer canonical-json
               :renderer-version 1
               :target summary_target
               :returns MaterializedSummaryPath)))
      (record Output
        :summary_path summary_path
        :transition_status transition.status))))\n"""


def _checkpoints_module():
    return importlib.import_module("orchestrator.workflow_lisp.lexical_checkpoints")


def _restore_module():
    return importlib.import_module("orchestrator.workflow_lisp.lexical_checkpoint_restore")


def _compile_fixture(tmp_path: Path):
    local_fixture = tmp_path / FIXTURE.name
    local_fixture.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )


def _compile_source_fixture(tmp_path: Path, *, filename: str, source: str):
    local_fixture = tmp_path / filename
    local_fixture.write_text(source, encoding="utf-8")
    result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return local_fixture, next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )


def _compile_policy_fixture(tmp_path: Path, *, prompt_binding_path: str = "prompts/implementation/execute.md"):
    local_fixture = tmp_path / POLICY_FIXTURE.name
    local_fixture.write_text(POLICY_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    prompt_path = tmp_path / prompt_binding_path
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("Execute the plan.\n", encoding="utf-8")
    result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.implementation.execute": prompt_binding_path},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return local_fixture, next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )


def _certified_adapter_command_boundaries():
    return _parse_command_boundaries_manifest(
        {
            "normalize_result": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_result.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "ImplementationSummary",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_result_ok"],
                "negative_fixture_ids": ["normalize_result_bad"],
                "behavior_class": "structured_result",
                "input_signature": [
                    {
                        "name": "execution_report",
                        "type_name": "WorkReport",
                        "required": True,
                        "transport_key": "execution_report",
                    },
                    {
                        "name": "review_report",
                        "type_name": "WorkReport",
                        "required": True,
                        "transport_key": "review_report",
                    },
                ],
                "artifact_contracts": ["implementation_summary_report"],
                "state_writes": [],
                "error_codes": ["normalize_result_invalid_payload"],
                "owner_module": "std/phase",
                "replacement_path": "typed review findings validation bridge",
                "invocation_protocol": "json_object_positional_arg",
            }
        },
        manifest_path=None,
    )


def _compile_certified_adapter_fixture(tmp_path: Path):
    local_fixture = tmp_path / "certified_adapter_checkpoint_restore.orc"
    source = CERTIFIED_ADAPTER_FIXTURE.read_text(encoding="utf-8")
    if "(defmodule" not in source:
        source = source.replace(
            '(:target-dsl "2.14")\n',
            '(:target-dsl "2.14")\n  (defmodule certified_adapter_checkpoint_restore)\n  (export normalize-summary)\n',
            1,
        )
    local_fixture.write_text(source, encoding="utf-8")
    result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        command_boundaries=_certified_adapter_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return local_fixture, next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "normalize-summary" or name.endswith("::normalize-summary")
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
    }


def _plain_binding_execution_inputs(tmp_path: Path) -> dict[str, object]:
    summary_path = tmp_path / "artifacts" / "work" / "plain-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{}\n", encoding="utf-8")
    return {
        "summary_target": "artifacts/work/plain-summary.json",
    }


def _transition_resume_execution_inputs(tmp_path: Path) -> dict[str, object]:
    summary_path = tmp_path / "artifacts" / "work" / "transition-summary.json"
    run_state_path = tmp_path / "state" / "transition-run-state.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{}\n", encoding="utf-8")
    run_state_path.write_text('{"drain_status":"READY"}\n', encoding="utf-8")
    return {
        "run_state_path": "state/transition-run-state.json",
        "summary_target": "artifacts/work/transition-summary.json",
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


def _certified_adapter_execution_inputs(tmp_path: Path) -> dict[str, object]:
    execution_report = tmp_path / "artifacts" / "work" / "execution.md"
    review_report = tmp_path / "artifacts" / "work" / "review.md"
    execution_report.parent.mkdir(parents=True, exist_ok=True)
    execution_report.write_text("execution\n", encoding="utf-8")
    review_report.write_text("review\n", encoding="utf-8")
    return {
        "completed": {"execution_report": "artifacts/work/execution.md"},
        "approved": {"review_report": "artifacts/work/review.md"},
    }


def _materialize_policy_sidecars(tmp_path: Path, *, run_id: str):
    from orchestrator.contracts.output_contract import validate_output_bundle

    workflow_path, bundle = _compile_policy_fixture(tmp_path)
    state_manager = StateManager(tmp_path, run_id=run_id)
    state_manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
        bound_inputs=_policy_execution_inputs(tmp_path),
    )

    def _write_bundle(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _fake_command(self, step, state):
        _, resolved_output_bundle, path_error = self._resolve_output_contract_paths(step, state)
        assert path_error is None and resolved_output_bundle is not None
        _write_bundle(self.workspace / resolved_output_bundle["path"], {"status": "READY", "report": "artifacts/work/report.md"})
        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": validate_output_bundle(resolved_output_bundle, workspace=self.workspace),
        }

    def _fake_provider(self, step, state):
        _, resolved_output_bundle, path_error = self._resolve_output_contract_paths(step, state)
        assert path_error is None and resolved_output_bundle is not None
        _write_bundle(self.workspace / resolved_output_bundle["path"], {"status": "COMPLETED", "report": "artifacts/work/report.md"})
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
        final_state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")

    return bundle, state_manager, final_state


def _compile_imported_call_fixture(tmp_path: Path, *, helper_status: str = "ok"):
    source_root = tmp_path / "imported_call"
    entry_path = source_root / "demo" / "entry.orc"
    helper_path = source_root / "demo" / "helper.orc"
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    helper_path.parent.mkdir(parents=True, exist_ok=True)
    helper_path.write_text(
        "\n".join(
                [
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    "  (defmodule demo/helper)",
                "  (export CallSummary run)",
                "  (defrecord CallSummary",
                "    (status String))",
                "  (defworkflow run",
                "    ()",
                "    -> CallSummary",
                "    (record CallSummary",
                f'      :status "{helper_status}")))',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    entry_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/helper :only (CallSummary run))",
                "  (export orchestrate)",
                "  (defworkflow orchestrate",
                "    ()",
                "    -> CallSummary",
                "    (call run)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(source_root,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        bundle
        for name, bundle in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )
    return entry_path, helper_path, bundle


def _materialize_imported_call_sidecars(tmp_path: Path, *, run_id: str):
    workflow_path, helper_path, bundle = _compile_imported_call_fixture(tmp_path)
    state_manager = StateManager(tmp_path, run_id=run_id)
    state_manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
    )
    final_state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")
    return workflow_path, helper_path, bundle, state_manager, final_state


def _materialize_certified_adapter_sidecars(tmp_path: Path, *, run_id: str):
    from orchestrator.contracts.output_contract import validate_output_bundle

    workflow_path, bundle = _compile_certified_adapter_fixture(tmp_path)
    state_manager = StateManager(tmp_path, run_id=run_id)
    state_manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
        bound_inputs=_certified_adapter_execution_inputs(tmp_path),
    )

    def _write_bundle(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _fake_command(self, step, state):
        _, resolved_output_bundle, path_error = self._resolve_output_contract_paths(step, state)
        assert path_error is None and resolved_output_bundle is not None
        _write_bundle(self.workspace / resolved_output_bundle["path"], {"report": "artifacts/work/review.md"})
        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": validate_output_bundle(resolved_output_bundle, workspace=self.workspace),
        }

    with patch.object(WorkflowExecutor, "_execute_command", _fake_command):
        final_state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="stop")

    return bundle, state_manager, final_state


def _restore_payload(*, record_id: str, program_point_id: str, origin_key: str) -> dict[str, object]:
    restore = _restore_module()
    selected_label = {
        "binding_name": "selected_label",
        "binding_kind": "pure_binding",
        "type_ref": "String",
        "transport": "inline_json",
        "value": "ready",
        "source_map_origin_key": origin_key,
        "source_step_name": "lexical_checkpoint_restore_regions::orchestrate__selected_label__match_decision",
        "source_step_id": "root.lexical_checkpoint_restore_regions_orchestrate__selected_label__match_decision",
    }
    selected_label["schema_digest"] = restore._binding_schema_digest(selected_label)
    selected_label["value_digest"] = restore._binding_value_digest(selected_label)
    selected_report = {
        "binding_name": "selected_report",
        "binding_kind": "pure_binding",
        "type_ref": "WorkReport",
        "transport": "inline_json",
        "value": "artifacts/work/report.md",
        "source_map_origin_key": origin_key,
        "source_step_name": "lexical_checkpoint_restore_regions::orchestrate__selected_report__match_decision",
        "source_step_id": "root.lexical_checkpoint_restore_regions_orchestrate__selected_report__match_decision",
    }
    selected_report["schema_digest"] = restore._binding_schema_digest(selected_report)
    selected_report["value_digest"] = restore._binding_value_digest(selected_report)
    proof = {
        "proof_id": "proof:lexical_checkpoint_restore_regions::orchestrate:root.lexical_checkpoint_restore_regions_orchestrate__selected_label__match_decision",
        "proof_kind": "match_branch",
        "subject_binding": "decision",
        "union_type": "BranchDecision",
        "variant": "READY",
        "variant_name": "READY",
        "proof_source": "root.lexical_checkpoint_restore_regions_orchestrate__selected_label__match_decision",
        "source_map_origin_key": origin_key,
    }
    proof["discriminant_digest"] = restore._proof_discriminant_digest(proof)
    loop_frame = {
        "loop_id": "lexical_checkpoint_restore_regions::orchestrate__loop_result__loop",
        "loop_name": "lexical_checkpoint_restore_regions::orchestrate__loop_result__loop",
        "loop_site_id": "loop:test",
        "iteration": 0,
        "current_iteration": 0,
        "next_iteration": 1,
        "frame_state_digest": "",
        "state_binding": "state",
        "state_binding_name": "state",
        "type_ref": "LoopState",
        "state_type_ref": "LoopState",
        "state_value": {
            "count": 1,
            "label": "tick",
        },
        "proofs": [],
        "proofs_carried": [],
    }
    loop_frame["frame_digest"] = restore._loop_frame_digest(loop_frame)
    loop_frame["frame_state_digest"] = loop_frame["frame_digest"]
    return {
        "schema_version": "workflow_lisp_lexical_restore_payload.v1",
        "eligibility": ["pure_binding", "let_continuation", "match_branch", "loop_frame"],
        "restorable": True,
        "resume_after": {
            "program_point_id": program_point_id,
            "step_id": "lexical_checkpoint_restore_regions::orchestrate__materialize-view__runtime-summary",
            "execution_index": 14,
            "continuation_kind": "after_effect_boundary",
        },
        "bindings": [selected_label, selected_report],
        "active_variant_proofs": [proof],
        "loop_frame": loop_frame,
        "completed_effect_barrier": None,
        "resource_observations": [],
    }


def _resource_observation(*, checkpoint_id: str, program_point_id: str, origin_key: str) -> dict[str, object]:
    helper = importlib.import_module("orchestrator.workflow_lisp.lexical_checkpoint_transition_resume")
    return helper.build_resource_observation(
        resource_id="drain-run-state",
        resource_kind="DrainRunState",
        observed_version="sha256:resource-version",
        transition_identity="write-drain-status",
        checkpoint_id=checkpoint_id,
        program_point_id=program_point_id,
        source_step_id="root.lexical_checkpoint_effect_policies_orchestrate__transition",
        source_map_origin_key=origin_key,
        audit_path="state/workflow_lisp/lexical-checkpoint-effect-policies--orchestrate/write-drain-status-audit.jsonl",
        audit_digest="sha256:audit-digest",
    )


def _prepare_failed_run(tmp_path: Path, *, run_id: str):
    bundle = _compile_fixture(tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize(
        str(tmp_path / FIXTURE.name),
        context=bundle_context_dict(bundle),
        bound_inputs=_execution_inputs(tmp_path),
    )

    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic restore-boundary failure")
        return real_render_view(*args, **kwargs)

    with patch("orchestrator.workflow.executor.render_view", side_effect=_fail_render_once):
        first_run = WorkflowExecutor(bundle, tmp_path, state_manager).execute()

    return bundle, state_manager, first_run


def _prepare_failed_plain_binding_run(tmp_path: Path, *, run_id: str):
    workflow_path, bundle = _compile_source_fixture(
        tmp_path,
        filename="lexical_checkpoint_restore_plain_binding.orc",
        source=PLAIN_PURE_BINDING_FIXTURE_SOURCE,
    )
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
        bound_inputs=_plain_binding_execution_inputs(tmp_path),
    )

    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic restore-boundary failure")
        return real_render_view(*args, **kwargs)

    with patch("orchestrator.workflow.executor.render_view", side_effect=_fail_render_once):
        first_run = WorkflowExecutor(bundle, tmp_path, state_manager).execute()

    return workflow_path, bundle, state_manager, first_run


def _prepare_failed_transition_resume_run(tmp_path: Path, *, run_id: str):
    workflow_path, bundle = _compile_source_fixture(
        tmp_path,
        filename="lexical_checkpoint_transition_resume.orc",
        source=TRANSITION_RESUME_FIXTURE_SOURCE,
    )
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
        bound_inputs=_transition_resume_execution_inputs(tmp_path),
    )

    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic transition restore-boundary failure")
        return real_render_view(*args, **kwargs)

    with patch("orchestrator.workflow.executor.render_view", side_effect=_fail_render_once):
        first_run = WorkflowExecutor(bundle, tmp_path, state_manager).execute()

    return workflow_path, bundle, state_manager, first_run


def _materialize_restore_sidecars(tmp_path: Path, *, run_id: str):
    return _prepare_failed_run(tmp_path, run_id=run_id)


def _checkpoint_point_by_node_id(bundle, node_id: str):
    return next(point for point in bundle.runtime_plan.lexical_checkpoint_points if point.node_id == node_id)


def _rewrite_checkpoint_record(
    *,
    tmp_path: Path,
    state_manager: StateManager,
    point,
    mutate,
) -> dict[str, object]:
    checkpoints = _checkpoints_module()
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = tmp_path / index_payload["records"][-1]["record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    mutate(record)
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def _latest_checkpoint_record(
    *,
    tmp_path: Path,
    state_manager: StateManager,
    point,
) -> dict[str, object]:
    checkpoints = _checkpoints_module()
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = tmp_path / index_payload["records"][-1]["record_path"]
    return json.loads(record_path.read_text(encoding="utf-8"))


def _append_checkpoint_record(
    *,
    tmp_path: Path,
    state_manager: StateManager,
    point,
    record_id: str,
    mutate,
) -> dict[str, object]:
    checkpoints = _checkpoints_module()
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    latest_entry = deepcopy(index_payload["records"][-1])
    latest_record_path = tmp_path / latest_entry["record_path"]
    record = json.loads(latest_record_path.read_text(encoding="utf-8"))
    record["record_id"] = record_id
    mutate(record)

    record_path = checkpoints.resolve_checkpoint_record_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
        record_id=record_id,
    )
    state_manager.write_runtime_sidecar_json(record_path, record)

    latest_entry["record_id"] = record_id
    latest_entry["record_path"] = record_path.relative_to(tmp_path).as_posix()
    index_payload["records"].append(latest_entry)
    state_manager.write_runtime_sidecar_json(index_path, index_payload)
    return record


def _checkpoint_point_by_step_suffix(bundle, suffix: str):
    return next(point for point in bundle.runtime_plan.lexical_checkpoint_points if point.step_id.endswith(suffix))


def _force_materialize_view_resume_state(state_manager: StateManager, bundle) -> None:
    state = state_manager.load()
    step_id = "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary"
    execution_index = bundle.projection.execution_index_for_step_id(step_id)
    state.current_step = {
        "name": "lexical_checkpoint_restore_regions::orchestrate__materialize-view__runtime-summary",
        "index": execution_index if isinstance(execution_index, int) else 14,
        "step_id": step_id,
        "status": "running",
    }
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__summary_status", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__selected_label__match_decision", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__selected_report__match_decision", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__loop_result__result", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__loop_result__loop", None)
    state_manager.state = state
    state_manager._write_state()


def _force_loop_frame_resume_state(state_manager: StateManager) -> None:
    state = state_manager.load()
    loop_name = "lexical_checkpoint_restore_regions::orchestrate__loop_result__loop"
    state.current_step = {
        "name": loop_name,
        "index": 12,
        "step_id": "root.lexical_checkpoint_restore_regions_orchestrate__loop_result__loop",
        "status": "running",
    }
    for key in list(state.steps):
        if key == "lexical_checkpoint_restore_regions::orchestrate__loop_result__result":
            state.steps.pop(key, None)
            continue
        if key.startswith(f"{loop_name}["):
            state.steps.pop(key, None)
            continue
        if key == loop_name:
            state.steps.pop(key, None)
    state_manager.state = state
    state_manager._write_state()


def _force_plain_binding_resume_state(state_manager: StateManager, bundle) -> None:
    state = state_manager.load()
    step_id = "root.lexical_checkpoint_restore_plain_binding_orchestrate__materialize_view__runtime_summary"
    execution_index = bundle.projection.execution_index_for_step_id(step_id)
    state.current_step = {
        "name": "lexical_checkpoint_restore_plain_binding::orchestrate__materialize-view__runtime-summary",
        "index": execution_index if isinstance(execution_index, int) else 0,
        "step_id": step_id,
        "status": "running",
    }
    state_manager.state = state
    state_manager._write_state()


def _mutate_restore_proof_variant(record: dict[str, object], *, variant_name: str) -> None:
    restore = _restore_module()
    proof = record["restore_payload"]["active_variant_proofs"][0]
    proof["variant"] = variant_name
    proof["variant_name"] = variant_name
    proof["discriminant_digest"] = restore._proof_discriminant_digest(proof)


def _mutate_restore_binding_type_ref(
    record: dict[str, object],
    *,
    type_ref: str,
) -> None:
    restore = _restore_module()
    binding = record["restore_payload"]["bindings"][0]
    binding["type_ref"] = type_ref
    binding["schema_digest"] = restore._binding_schema_digest(binding)


def _force_transition_resume_state(state_manager: StateManager, bundle) -> None:
    state = state_manager.load()
    step_id = "root.lexical_checkpoint_transition_resume_orchestrate__materialize_view__runtime_summary"
    execution_index = bundle.projection.execution_index_for_step_id(step_id)
    state.current_step = {
        "name": "lexical_checkpoint_transition_resume::orchestrate__materialize-view__runtime-summary",
        "index": execution_index if isinstance(execution_index, int) else 1,
        "step_id": step_id,
        "status": "running",
    }
    state.steps.pop("lexical_checkpoint_transition_resume::orchestrate__transition", None)
    state_manager.state = state
    state_manager._write_state()


def _private_artifact_ref_for_generated_bundle(
    tmp_path: Path,
    state_manager: StateManager,
    *,
    bundle_fragment: str,
) -> tuple[dict[str, object], object]:
    bundle_root = tmp_path / ".orchestrate" / "workflow_lisp" / "entry" / state_manager.run_id
    bundle_path = next(bundle_root.rglob(f"*{bundle_fragment}*result_bundle.json"))
    bundle_record = json.loads(bundle_path.read_text(encoding="utf-8"))
    return (
        {
            "bundle_kind": "pure_projection_result",
            "path": bundle_path.relative_to(tmp_path).as_posix(),
            "payload_digest": bundle_record["payload_digest"],
            "pure_expr_schema_version": bundle_record["pure_expr_schema_version"],
        },
        bundle_record["result"],
    )


def _mutate_binding_to_private_artifact_ref(
    record: dict[str, object],
    *,
    binding_name: str,
    private_artifact_ref: dict[str, object],
    restored_value: object,
) -> None:
    restore = _restore_module()
    binding = next(
        candidate
        for candidate in record["restore_payload"]["bindings"]
        if candidate["binding_name"] == binding_name
    )
    binding["transport"] = "private_artifact_ref"
    binding["value"] = None
    binding["private_artifact_ref"] = private_artifact_ref
    binding["value_digest"] = restore._sha256_json(restored_value)


def test_restore_payload_validation_requires_stable_schema_and_binding_metadata() -> None:
    restore = _restore_module()
    payload = _restore_payload(record_id="record:1", program_point_id="pp:1", origin_key="source:test")

    restore.validate_restore_payload(payload)

    invalid = deepcopy(payload)
    invalid["schema_version"] = "workflow_lisp_lexical_restore_payload.v0"
    with pytest.raises(ValueError, match="lexical_restore_payload_schema_invalid"):
        restore.validate_restore_payload(invalid)

    missing_binding_digest = deepcopy(payload)
    missing_binding_digest["bindings"][0]["value_digest"] = ""
    with pytest.raises(ValueError, match="lexical_restore_value_digest_mismatch"):
        restore.validate_restore_payload(missing_binding_digest)


def test_restore_payload_validation_accepts_r4_resource_observation_schema() -> None:
    restore = _restore_module()
    payload = _restore_payload(record_id="record:1", program_point_id="pp:1", origin_key="source:test")
    payload["resource_observations"] = [
        _resource_observation(
            checkpoint_id="ckpt:test",
            program_point_id="pp:1",
            origin_key="source:test",
        )
    ]

    restore.validate_restore_payload(payload)


def test_restore_payload_validation_requires_existing_private_artifact_bundle(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, first_run = _materialize_restore_sidecars(
        tmp_path,
        run_id="restore-private-artifact-validate",
    )

    assert first_run["status"] == "failed"
    point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary",
    )
    record = _latest_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=point,
    )
    private_artifact_ref, restored_value = _private_artifact_ref_for_generated_bundle(
        tmp_path,
        state_manager,
        bundle_fragment="summary_status",
    )
    _mutate_binding_to_private_artifact_ref(
        record,
        binding_name="summary_status",
        private_artifact_ref=private_artifact_ref,
        restored_value=restored_value,
    )

    restore.validate_restore_payload(
        record["restore_payload"],
        expected_origin_key=point.origin_key,
        state_manager=state_manager,
    )

    invalid = deepcopy(record["restore_payload"])
    invalid_binding = next(
        candidate
        for candidate in invalid["bindings"]
        if candidate["binding_name"] == "summary_status"
    )
    invalid_binding["private_artifact_ref"] = {
        **invalid_binding["private_artifact_ref"],
        "path": "missing/private-bundle.json",
    }
    with pytest.raises(ValueError, match="lexical_restore_used_as_semantic_authority"):
        restore.validate_restore_payload(
            invalid,
            expected_origin_key=point.origin_key,
            state_manager=state_manager,
        )


def test_plain_pure_binding_restore_metadata_survives_compile_for_effect_boundary(tmp_path: Path) -> None:
    _, bundle = _compile_source_fixture(
        tmp_path,
        filename="lexical_checkpoint_restore_plain_binding.orc",
        source=PLAIN_PURE_BINDING_FIXTURE_SOURCE,
    )

    point = _checkpoint_point_by_step_suffix(bundle, "__materialize_view__runtime_summary")
    restore = point.details.get("restore", {})
    binding_names = {
        descriptor["binding_name"]
        for descriptor in restore.get("binding_descriptors", ())
    }

    assert {"pure_binding", "let_continuation"} <= set(restore.get("eligibility", ()))
    assert "plain_status" in binding_names


def test_runtime_shadow_emission_records_distinct_match_proof_identity(tmp_path: Path) -> None:
    bundle, state_manager, first_run = _prepare_failed_run(tmp_path, run_id="restore-proof-identity")

    assert first_run["status"] == "failed"
    point = _checkpoint_point_by_step_suffix(bundle, "__materialize_view__runtime_summary")
    record = _latest_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=point,
    )

    proofs = record["restore_payload"]["active_variant_proofs"]
    assert len(proofs) == 2
    assert len({proof["proof_id"] for proof in proofs}) == 2
    assert len({proof["proof_source"] for proof in proofs}) == 2
    assert {proof["subject_binding"] for proof in proofs} == {"decision"}


def test_restore_selector_prefers_latest_valid_record_for_one_checkpoint_family(tmp_path: Path) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(tmp_path, run_id="restore-selector-ordering")

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    latest_entry = index_payload["records"][-1]

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
    )

    assert decision.kind == "RESTORED"
    assert decision.record_id == latest_entry["record_id"]


def test_restore_selector_fails_closed_when_newest_record_is_invalid(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(tmp_path, run_id="restore-selector-newest-invalid")

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.details.get("restore", {}).get("eligibility")
    )
    prior_record = _latest_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=point,
    )
    _append_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=point,
        record_id="record:newest-invalid",
        mutate=lambda record: record["restore_payload"]["bindings"][0].__setitem__("value_digest", "sha256:drifted"),
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "INVALID"
    assert decision.record_id == "record:newest-invalid"
    assert "lexical_restore_value_digest_mismatch" in decision.diagnostics
    assert decision.record_id != prior_record["record_id"]


def test_restore_selector_treats_r1_records_without_restore_payload_as_not_restorable(tmp_path: Path) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _prepare_failed_run(tmp_path, run_id="restore-selector-r1")

    point = bundle.runtime_plan.lexical_checkpoint_points[0]
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    assert index_path.is_file()

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
    )

    assert decision.kind == "NOT_RESTORABLE"


def test_restore_selector_rejects_self_consistent_binding_schema_drift(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path, run_id="restore-binding-schema-self-consistent"
    )
    point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary",
    )

    _rewrite_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=point,
        mutate=lambda record: _mutate_restore_binding_type_ref(record, type_ref="WorkReport"),
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "INVALID"
    assert "lexical_restore_binding_schema_mismatch" in decision.diagnostics


def test_restore_selector_rejects_self_consistent_proof_variant_drift(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path, run_id="restore-proof-self-consistent"
    )
    point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary",
    )

    _rewrite_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=point,
        mutate=lambda record: _mutate_restore_proof_variant(record, variant_name="RETRY"),
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "INVALID"
    assert "lexical_restore_proof_mismatch" in decision.diagnostics


def test_restore_selector_accepts_private_artifact_ref_binding_with_validated_bundle(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id="restore-private-artifact-selector",
    )
    point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary",
    )
    record = _rewrite_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=point,
        mutate=lambda candidate: _mutate_binding_to_private_artifact_ref(
            candidate,
            binding_name="summary_status",
            private_artifact_ref=_private_artifact_ref_for_generated_bundle(
                tmp_path,
                state_manager,
                bundle_fragment="summary_status",
            )[0],
            restored_value=_private_artifact_ref_for_generated_bundle(
                tmp_path,
                state_manager,
                bundle_fragment="summary_status",
            )[1],
        ),
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "RESTORED"
    assert decision.record_id == record["record_id"]


def test_restore_selector_rejects_private_artifact_ref_without_validated_bundle(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id="restore-private-artifact-invalid",
    )
    point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary",
    )
    private_artifact_ref, restored_value = _private_artifact_ref_for_generated_bundle(
        tmp_path,
        state_manager,
        bundle_fragment="summary_status",
    )
    _rewrite_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=point,
        mutate=lambda record: _mutate_binding_to_private_artifact_ref(
            record,
            binding_name="summary_status",
            private_artifact_ref=private_artifact_ref,
            restored_value=restored_value,
        ),
    )
    (tmp_path / private_artifact_ref["path"]).unlink()

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "INVALID"
    assert "lexical_restore_used_as_semantic_authority" in decision.diagnostics


def test_restore_selector_scopes_candidates_to_restart_node(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(tmp_path, run_id="restore-scope")
    restart_point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary",
    )

    _rewrite_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=restart_point,
        mutate=lambda record: record["restore_payload"]["bindings"][0].__setitem__("value_digest", "sha256:drifted"),
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        restart_node_id=restart_point.node_id,
        executable_workflow=bundle.ir,
    )

    assert decision.kind == "INVALID"
    assert "lexical_restore_value_digest_mismatch" in decision.diagnostics


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("program_identity", "lexical_restore_program_identity_mismatch"),
        ("semantic_digest", "lexical_restore_semantic_digest_mismatch"),
        ("source_origin", "lexical_restore_source_lineage_mismatch"),
        ("binding_schema", "lexical_restore_binding_schema_mismatch"),
        ("value_digest", "lexical_restore_value_digest_mismatch"),
        ("proof", "lexical_restore_proof_mismatch"),
        ("loop_frame", "lexical_restore_loop_frame_mismatch"),
        ("pending_effect", "lexical_restore_pending_effect_unsafe"),
        ("resource_observation", "lexical_restore_resource_observation_mismatch"),
        ("semantic_authority", "lexical_restore_used_as_semantic_authority"),
    ),
)
def test_restore_selector_rejects_invalid_restore_candidates(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(tmp_path, run_id=f"restore-invalid-{mutation}")
    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = tmp_path / index_payload["records"][-1]["record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))

    if mutation == "program_identity":
        record["program_identity"]["workflow_name"] = "drifted::workflow"
    elif mutation == "semantic_digest":
        record["program_identity"]["semantic_ir_digest"] = "sha256:drifted"
    elif mutation == "source_origin":
        record["restore_payload"]["bindings"][0]["source_map_origin_key"] = "source:drifted"
    elif mutation == "binding_schema":
        record["restore_payload"]["bindings"][0]["schema_digest"] = "sha256:drifted"
    elif mutation == "value_digest":
        record["restore_payload"]["bindings"][0]["value_digest"] = "sha256:drifted"
    elif mutation == "proof":
        _mutate_restore_proof_variant(record, variant_name="RETRY")
    elif mutation == "loop_frame":
        record["restore_payload"]["loop_frame"]["frame_digest"] = "sha256:drifted"
    elif mutation == "pending_effect":
        record["pending_effect_policy"]["policy_status"] = "replay_required"
    elif mutation == "resource_observation":
        record["restore_payload"]["resource_observations"] = [{"resource_name": "review_queue", "version": "v2"}]
    elif mutation == "semantic_authority":
        record["restore_payload"]["bindings"][0]["transport"] = "rendered_report"

    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
    )

    assert decision.kind == "INVALID"
    assert expected_code in decision.diagnostics


def test_restore_selector_rejects_loop_frame_state_drift_with_stable_bookkeeping(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path, run_id="restore-loop-frame-state-self-consistent"
    )
    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "loop_back_edge"
    )
    state = state_manager.load()
    loop_name = "lexical_checkpoint_restore_regions::orchestrate__loop_result__loop"
    loop_step = state.steps[loop_name]
    loop_step["artifacts"]["state__count"] = 7
    loop_step["artifacts"]["state__label"] = "drifted"
    state_manager.state = state
    state_manager._write_state()
    _rewrite_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=point,
        mutate=lambda record: (
            record["restore_payload"].__setitem__("bindings", []),
            record["restore_payload"].__setitem__("active_variant_proofs", []),
            record["restore_payload"].__setitem__("eligibility", ["loop_frame"]),
        ),
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
    )

    assert decision.kind == "INVALID"
    assert "lexical_restore_loop_frame_mismatch" in decision.diagnostics


def test_restore_selector_records_private_r3_policy_decision_for_preserved_materialized_view(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, final_state = _materialize_policy_sidecars(tmp_path, run_id="restore-policy-view")

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "materialize_view"
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
    )

    assert decision.kind == "RESTORED"
    assert decision.policy_decision == "REUSABLE"


def test_restore_selector_rejects_preserved_materialized_view_without_completed_effect_evidence(tmp_path: Path) -> None:
    checkpoints = _checkpoints_module()
    restore = _restore_module()
    bundle, state_manager, final_state = _materialize_policy_sidecars(
        tmp_path,
        run_id="restore-policy-view-missing-evidence",
    )

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("policy", {}).get("policy_kind")
        == "preserve_durable_view"
    )
    _rewrite_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=point,
        mutate=lambda record: (
            record.__setitem__("completed_effect_refs", []),
            record["validity_envelope"].__setitem__(
                "completed_effect_refs_digest",
                checkpoints._completed_effect_refs_digest(()),
            ),
        ),
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
    )

    assert decision.kind == "INVALID"
    assert decision.policy_decision == "INVALID"
    assert "lexical_checkpoint_effect_policy_materialized_view_mismatch" in decision.diagnostics


def test_restore_selector_reuses_completed_command_boundary_when_validated_bundle_matches(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, final_state = _materialize_policy_sidecars(tmp_path, run_id="restore-policy-command")

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "command"
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
    )

    assert decision.kind == "RESTORED"
    assert decision.policy_decision == "REUSABLE"


def test_restore_selector_reuses_completed_certified_adapter_boundary_when_protocol_matches(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, final_state = _materialize_certified_adapter_sidecars(
        tmp_path,
        run_id="restore-policy-certified-adapter",
    )

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "command"
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
    )

    assert decision.kind == "RESTORED"
    assert decision.policy_decision == "REUSABLE"


def test_restore_selector_reuses_completed_transition_policy_when_audit_and_resource_match(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, final_state = _materialize_policy_sidecars(tmp_path, run_id="restore-policy-transition")

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "resource_transition"
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "RESTORED"
    assert decision.policy_decision == "REUSABLE"


def test_restore_selector_ignores_checkpoint_bridge_path_when_live_resource_has_drifted(tmp_path: Path) -> None:
    checkpoints = _checkpoints_module()
    restore = _restore_module()
    bundle, state_manager, final_state = _materialize_policy_sidecars(
        tmp_path,
        run_id="restore-transition-live-resource-authority",
    )

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "resource_transition"
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = tmp_path / index_payload["records"][-1]["record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    effect_ref = record["completed_effect_refs"][0]

    live_bridge_path = tmp_path / effect_ref["bridge_path"]
    backup_bridge_path = tmp_path / "state" / "drain-run-state-backup.json"
    backup_bridge_path.parent.mkdir(parents=True, exist_ok=True)
    backup_bridge_path.write_text(live_bridge_path.read_text(encoding="utf-8"), encoding="utf-8")
    live_bridge_path.write_text('{"drain_status":"DRIFTED"}\n', encoding="utf-8")

    effect_ref["bridge_path"] = str(backup_bridge_path.relative_to(tmp_path))
    record["validity_envelope"]["completed_effect_refs_digest"] = checkpoints._completed_effect_refs_digest(
        tuple(record["completed_effect_refs"])
    )
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "INVALID"
    assert "lexical_checkpoint_transition_used_as_semantic_authority" in decision.diagnostics


@pytest.mark.parametrize(
    ("mutation", "expected_kind", "expected_diagnostic"),
        (
            ("audit_row_digest", "INVALID", "lexical_checkpoint_transition_audit_row_digest_mismatch"),
            ("request_digest", "INVALID", "lexical_checkpoint_transition_request_digest_mismatch"),
            ("idempotency_key", "INVALID", "lexical_checkpoint_transition_idempotency_mismatch"),
            ("result_digest", "INVALID", "lexical_checkpoint_transition_result_digest_mismatch"),
            ("legacy_record", "NOT_RESTORABLE", "lexical_restore_effect_policy_barrier"),
            ("resource_observation_invalid", "INVALID", "lexical_checkpoint_transition_resource_observation_invalid"),
    ),
)
def test_restore_selector_fails_closed_for_transition_evidence_drift(
    tmp_path: Path,
    mutation: str,
    expected_kind: str,
    expected_diagnostic: str,
) -> None:
    checkpoints = _checkpoints_module()
    restore = _restore_module()
    bundle, state_manager, final_state = _materialize_policy_sidecars(tmp_path, run_id=f"restore-transition-{mutation}")

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "resource_transition"
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = tmp_path / index_payload["records"][-1]["record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    effect_ref = record["completed_effect_refs"][0]

    if mutation == "audit_row_digest":
        effect_ref["audit_row_digest"] = "sha256:drifted"
    elif mutation == "request_digest":
        effect_ref["request_digest"] = "sha256:drifted"
    elif mutation == "idempotency_key":
        effect_ref["idempotency_key"] = "sha256:drifted"
    elif mutation == "result_digest":
        effect_ref["result_digest"] = "sha256:drifted"
    elif mutation == "legacy_record":
        for key in (
            "evidence_schema_version",
            "resource_kind",
            "audit_row_index",
            "audit_row_digest",
            "audit_outcome_code",
            "request_digest",
            "result_digest",
            "backend_kind",
            "bridge_path",
        ):
            effect_ref.pop(key, None)
    elif mutation == "resource_observation_invalid":
        record["restore_payload"] = _restore_payload(
            record_id="record:test",
            program_point_id=point.program_point_id,
            origin_key=point.origin_key,
        )
        observation = _resource_observation(
            checkpoint_id=point.checkpoint_id,
            program_point_id=point.program_point_id,
            origin_key=point.origin_key,
        )
        observation["resource_id"] = "drifted-resource"
        record["restore_payload"]["resource_observations"] = [observation]

    if mutation != "resource_observation_invalid":
        record["validity_envelope"]["completed_effect_refs_digest"] = checkpoints._completed_effect_refs_digest(
            tuple(record["completed_effect_refs"])
        )

    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == expected_kind
    assert expected_diagnostic in decision.diagnostics


@pytest.mark.parametrize(
    ("mutation", "expected_diagnostic"),
    (
        ("resource_conflict", "lexical_checkpoint_transition_resource_version_conflict"),
        ("pending_replay", "lexical_checkpoint_transition_pending_replay_unresolved"),
        ("audit_row_missing", "lexical_checkpoint_transition_audit_row_missing"),
    ),
)
def test_restore_selector_detects_authoritative_transition_conflicts(
    tmp_path: Path,
    mutation: str,
    expected_diagnostic: str,
) -> None:
    checkpoints = _checkpoints_module()
    restore = _restore_module()
    transition_executor = importlib.import_module("orchestrator.workflow.transition_executor")
    bundle, state_manager, final_state = _materialize_policy_sidecars(tmp_path, run_id=f"restore-transition-authority-{mutation}")

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "resource_transition"
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = tmp_path / index_payload["records"][-1]["record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    effect_ref = record["completed_effect_refs"][0]
    audit_path = tmp_path / effect_ref["audit_path"]

    if mutation == "resource_conflict":
        bridge_path = tmp_path / effect_ref["bridge_path"]
        bridge_path.write_text('{"drain_status":"DRIFTED"}\n', encoding="utf-8")
    elif mutation == "pending_replay":
        audit_rows = transition_executor.read_transition_audit_rows(audit_path)
        transition_executor._write_pending_replay(audit_path, audit_rows[-1])
    elif mutation == "audit_row_missing":
        effect_ref["audit_row_index"] = 9
        record["validity_envelope"]["completed_effect_refs_digest"] = checkpoints._completed_effect_refs_digest(
            tuple(record["completed_effect_refs"])
        )
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "INVALID"
    assert expected_diagnostic in decision.diagnostics


def test_restore_selector_rejects_r3_completed_effect_ref_drift(tmp_path: Path) -> None:
    checkpoints = _checkpoints_module()
    restore = _restore_module()
    bundle, state_manager, final_state = _materialize_policy_sidecars(tmp_path, run_id="restore-policy-drift")

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "materialize_view"
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = tmp_path / index_payload["records"][-1]["record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["completed_effect_refs"][0]["view_digest"] = "sha256:drifted"
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
    )

    assert decision.kind == "INVALID"
    assert decision.policy_decision == "INVALID"
    assert "lexical_checkpoint_effect_policy_materialized_view_mismatch" in decision.diagnostics


def test_restore_selector_rejects_r3_authoritative_bundle_drift_on_disk(tmp_path: Path) -> None:
    checkpoints = _checkpoints_module()
    restore = _restore_module()
    bundle, state_manager, final_state = _materialize_policy_sidecars(tmp_path, run_id="restore-policy-provider-drift")

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "provider"
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = tmp_path / index_payload["records"][-1]["record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    bundle_path = tmp_path / record["completed_effect_refs"][0]["bundle_path"]
    bundle_path.write_text(
        json.dumps({"report": "artifacts/work/report.md", "status": "DRIFTED"}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
    )

    assert decision.kind == "INVALID"
    assert decision.policy_decision == "INVALID"
    assert "lexical_checkpoint_effect_policy_structured_output_invalid" in decision.diagnostics


def test_restore_selector_rejects_r3_provider_prompt_drift_on_disk(tmp_path: Path) -> None:
    restore = _restore_module()
    bundle, state_manager, final_state = _materialize_policy_sidecars(tmp_path, run_id="restore-policy-provider-prompt-drift")

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "provider"
    )
    recompiled_bundle = _compile_policy_fixture(
        tmp_path,
        prompt_binding_path="prompts/implementation/execute_v2.md",
    )[1]

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=recompiled_bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=recompiled_bundle.ir,
    )

    assert decision.kind == "INVALID"
    assert decision.policy_decision == "INVALID"
    assert "lexical_checkpoint_effect_policy_structured_output_invalid" in decision.diagnostics


def test_restore_selector_rejects_r3_imported_workflow_call_callee_drift(tmp_path: Path) -> None:
    restore = _restore_module()
    _, _, bundle, state_manager, final_state = _materialize_imported_call_sidecars(
        tmp_path,
        run_id="restore-policy-imported-call-drift",
    )

    assert final_state["status"] == "completed"

    point = next(
        checkpoint_point
        for checkpoint_point in bundle.runtime_plan.lexical_checkpoint_points
        if checkpoint_point.point_kind == "effect_boundary"
        and checkpoint_point.details.get("effect_boundary", {}).get("effect_kind") == "call"
    )
    recompiled_bundle = _compile_imported_call_fixture(tmp_path, helper_status="changed")[2]

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=recompiled_bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=recompiled_bundle.ir,
    )

    assert decision.kind == "INVALID"
    assert decision.policy_decision == "INVALID"
    assert "lexical_checkpoint_completed_effect_invalid" in decision.diagnostics


def test_runtime_resume_restores_private_bindings_and_loop_frame_from_checkpoint_sidecars(tmp_path: Path) -> None:
    bundle, state_manager, first_run = _materialize_restore_sidecars(tmp_path, run_id="restore-runtime")
    assert first_run["status"] == "failed"
    restart_point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary",
    )
    checkpoint_record = _latest_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=restart_point,
    )
    restored_binding_names = {
        binding["binding_name"]
        for binding in checkpoint_record["restore_payload"]["bindings"]
    }
    assert {"selected_label", "selected_report", "summary_status"} <= restored_binding_names
    _force_materialize_view_resume_state(state_manager, bundle)

    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["status"] == "completed"
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    payload = json.loads(restore_report.read_text(encoding="utf-8"))
    assert payload["decision_kind"] == "RESTORED"
    assert payload["restored_bindings"] >= 3
    assert payload["restored_loop_frames"] >= 1


def test_runtime_resume_restores_repeat_until_restart_from_checkpoint_sidecars(tmp_path: Path) -> None:
    bundle, state_manager, first_run = _materialize_restore_sidecars(tmp_path, run_id="restore-loop-restart")
    assert first_run["status"] == "failed"
    _force_loop_frame_resume_state(state_manager)

    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["status"] == "completed"
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    payload = json.loads(restore_report.read_text(encoding="utf-8"))
    assert payload["decision_kind"] == "RESTORED"
    assert payload["restored_loop_frames"] >= 1
    loaded_state = state_manager.load()
    assert loaded_state.steps["lexical_checkpoint_restore_regions::orchestrate__loop_result__loop"]["status"] == "completed"


def test_runtime_resume_fails_closed_when_restart_restore_candidate_is_invalid(tmp_path: Path) -> None:
    bundle, state_manager, first_run = _materialize_restore_sidecars(tmp_path, run_id="restore-invalid-runtime")
    assert first_run["status"] == "failed"
    restart_point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary",
    )
    _force_materialize_view_resume_state(state_manager, bundle)
    _rewrite_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=restart_point,
        mutate=lambda record: record["restore_payload"]["bindings"][0].__setitem__("value_digest", "sha256:drifted"),
    )

    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["status"] == "failed"
    assert resumed["error"]["type"] == "lexical_restore_invalid"
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    payload = json.loads(restore_report.read_text(encoding="utf-8"))
    assert payload["decision_kind"] == "INVALID"
    assert payload["source_map_origin_key"] == restart_point.origin_key
    assert "lexical_restore_value_digest_mismatch" in payload["diagnostics"]


def test_runtime_resume_rejects_loop_frame_when_persisted_repeat_until_bookkeeping_drifts(tmp_path: Path) -> None:
    bundle, state_manager, first_run = _materialize_restore_sidecars(tmp_path, run_id="restore-loop-drift")
    assert first_run["status"] == "failed"
    _force_materialize_view_resume_state(state_manager, bundle)

    state = state_manager.load()
    loop_name = "lexical_checkpoint_restore_regions::orchestrate__loop_result__loop"
    state.repeat_until[loop_name]["condition_evaluated_for_iteration"] = 99
    state_manager.state = state
    state_manager._write_state()

    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["status"] == "failed"
    assert resumed["error"]["type"] == "lexical_restore_invalid"
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    payload = json.loads(restore_report.read_text(encoding="utf-8"))
    assert payload["decision_kind"] == "INVALID"
    assert "lexical_restore_loop_frame_mismatch" in payload["diagnostics"]


def test_runtime_resume_requires_restored_match_proof_for_missing_join_results(tmp_path: Path) -> None:
    bundle, state_manager, first_run = _materialize_restore_sidecars(tmp_path, run_id="restore-proof-runtime")
    assert first_run["status"] == "failed"
    restart_point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary",
    )
    _force_materialize_view_resume_state(state_manager, bundle)
    _rewrite_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=restart_point,
        mutate=lambda record: _mutate_restore_proof_variant(record, variant_name="RETRY"),
    )

    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["status"] == "failed"
    assert resumed["error"]["type"] == "lexical_restore_invalid"
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    payload = json.loads(restore_report.read_text(encoding="utf-8"))
    assert payload["decision_kind"] == "INVALID"
    assert "lexical_restore_proof_mismatch" in payload["diagnostics"]


def test_runtime_resume_restores_plain_pure_binding_before_effect_boundary(tmp_path: Path) -> None:
    _, bundle, state_manager, first_run = _prepare_failed_plain_binding_run(
        tmp_path,
        run_id="restore-plain-binding-runtime",
    )
    assert first_run["status"] == "failed"
    restart_point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_plain_binding_orchestrate__materialize_view__runtime_summary",
    )
    checkpoint_record = _latest_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=restart_point,
    )

    restored_binding_names = {
        binding["binding_name"]
        for binding in checkpoint_record["restore_payload"]["bindings"]
    }
    assert "plain_status" in restored_binding_names
    _force_plain_binding_resume_state(state_manager, bundle)

    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["status"] == "completed"
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    payload = json.loads(restore_report.read_text(encoding="utf-8"))
    assert payload["decision_kind"] == "RESTORED"
    assert payload["restored_bindings"] >= 1


def test_runtime_resume_reuses_committed_transition_result_from_audit_evidence(tmp_path: Path) -> None:
    _, bundle, state_manager, first_run = _prepare_failed_transition_resume_run(
        tmp_path,
        run_id="restore-transition-runtime",
    )
    assert first_run["status"] == "failed"
    transition_point = _checkpoint_point_by_step_suffix(
        bundle,
        "lexical_checkpoint_transition_resume_orchestrate__transition",
    )
    checkpoint_record = _latest_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=transition_point,
    )
    assert checkpoint_record["completed_effect_refs"][0]["transition_identity"] == "write-drain-status"

    transition_ref = checkpoint_record["completed_effect_refs"][0]
    audit_path = tmp_path / transition_ref["audit_path"]
    _force_transition_resume_state(state_manager, bundle)

    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["status"] == "completed"
    assert [row["outcome_code"] for row in json.loads("[" + ",".join(audit_path.read_text(encoding="utf-8").splitlines()) + "]")] == ["committed"]
    summary_path = tmp_path / "artifacts" / "work" / "transition-summary.json"
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "BLOCKED"
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    payload = json.loads(restore_report.read_text(encoding="utf-8"))
    assert payload["decision_kind"] == "RESTORED"
    assert payload["policy_decision"] == "REGENERATE"
    assert payload["transition_identity"] == "write-drain-status"
    assert payload["transition_decision"] == "COMMITTED_RESULT_REUSED"


def test_runtime_resume_restores_private_artifact_ref_binding_before_effect_boundary(tmp_path: Path) -> None:
    bundle, state_manager, first_run = _materialize_restore_sidecars(
        tmp_path,
        run_id="restore-private-artifact-runtime",
    )
    assert first_run["status"] == "failed"
    restart_point = _checkpoint_point_by_node_id(
        bundle,
        "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary",
    )
    private_artifact_ref, restored_value = _private_artifact_ref_for_generated_bundle(
        tmp_path,
        state_manager,
        bundle_fragment="summary_status",
    )
    _rewrite_checkpoint_record(
        tmp_path=tmp_path,
        state_manager=state_manager,
        point=restart_point,
        mutate=lambda record: _mutate_binding_to_private_artifact_ref(
            record,
            binding_name="summary_status",
            private_artifact_ref=private_artifact_ref,
            restored_value=restored_value,
        ),
    )
    _force_materialize_view_resume_state(state_manager, bundle)

    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["status"] == "completed"
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    payload = json.loads(restore_report.read_text(encoding="utf-8"))
    assert payload["decision_kind"] == "RESTORED"
    assert payload["restored_bindings"] >= 3
