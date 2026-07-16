from __future__ import annotations

import importlib
import json
import multiprocessing
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
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


def _default_resume_module():
    return importlib.import_module(
        "orchestrator.workflow_lisp.lexical_checkpoint_default_resume"
    )


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
    state_manager.state = state
    state_manager._write_state()
    _assert_projection_valid_resume_state(state_manager, bundle)


def _force_active_loop_frame_resume_state(state_manager: StateManager, bundle) -> None:
    state = state_manager.load()
    loop_name = "lexical_checkpoint_restore_regions::orchestrate__loop_result__loop"
    progress = {
        "current_iteration": 0,
        "completed_iterations": [],
        "condition_evaluated_for_iteration": 0,
        "last_condition_result": False,
    }
    state.current_step = {
        "name": loop_name,
        "index": 12,
        "step_id": "root.lexical_checkpoint_restore_regions_orchestrate__loop_result__loop",
        "status": "running",
    }
    frame_result = state.steps[loop_name]
    frame_result["status"] = "running"
    frame_result.pop("outcome", None)
    frame_result["debug"]["structured_repeat_until"].update(
        {
            **progress,
            "exhausted": False,
        }
    )
    for key in list(state.steps):
        if key == "lexical_checkpoint_restore_regions::orchestrate__loop_result__result":
            state.steps.pop(key, None)
            continue
        if key.startswith(f"{loop_name}["):
            state.steps.pop(key, None)
    state.repeat_until[loop_name] = progress
    state_manager.state = state
    state_manager._write_state()
    _assert_projection_valid_resume_state(state_manager, bundle)


def _assert_projection_valid_resume_state(
    state_manager: StateManager,
    bundle,
) -> None:
    from orchestrator.workflow.resume_projection_integrity import ResumeScopePath, audit_scope

    assert (
        audit_scope(
            bundle,
            state_manager.load().to_dict(),
            ResumeScopePath.root(str(bundle.provenance.workflow_path)),
        )
        is None
    )


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
    _force_active_loop_frame_resume_state(state_manager, bundle)
    interrupted_state = state_manager.load()
    loop_name = "lexical_checkpoint_restore_regions::orchestrate__loop_result__loop"
    assert interrupted_state.repeat_until[loop_name] == {
        "current_iteration": 0,
        "completed_iterations": [],
        "condition_evaluated_for_iteration": 0,
        "last_condition_result": False,
    }
    assert interrupted_state.steps[loop_name]["status"] == "running"

    resumed = WorkflowExecutor(bundle, tmp_path, state_manager).execute(resume=True)

    assert resumed["status"] == "completed"
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    payload = json.loads(restore_report.read_text(encoding="utf-8"))
    assert payload["decision_kind"] == "RESTORED"
    assert payload["restored_loop_frames"] >= 1
    loaded_state = state_manager.load()
    assert loaded_state.steps[loop_name]["status"] == "completed"


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
    assert resumed["error"]["type"] == "resume_projection_integrity_error"
    assert resumed["error"]["context"]["reason"] == "invalid_loop_progress"
    assert resumed["error"]["context"]["field"] == (
        "repeat_until."
        "lexical_checkpoint_restore_regions::orchestrate__loop_result__loop."
        "condition_evaluated_for_iteration"
    )
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    assert not restore_report.exists()


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


def _generic_resume_point(
    checkpoint_id: str,
    node_id: str,
    *,
    point_kind: str = "effect_boundary",
) -> SimpleNamespace:
    return SimpleNamespace(
        checkpoint_id=checkpoint_id,
        node_id=node_id,
        step_id=node_id,
        point_kind=point_kind,
        workflow_name="generic::workflow",
        origin_key=f"source:{node_id}",
        details={
            "restore": {"eligibility": ["pure_binding"]},
            "effect_boundary": {"effect_kind": "provider"},
        },
    )


def _generic_default_resume_plan(
    *,
    ordered_node_ids: tuple[str, ...],
    points: tuple[SimpleNamespace, ...],
) -> SimpleNamespace:
    return SimpleNamespace(
        workflow_name="generic::workflow",
        ordered_node_ids=ordered_node_ids,
        lexical_checkpoint_points=points,
    )


def _generic_restore_decision(
    kind: str,
    *,
    checkpoint_id: str | None = None,
    selection_observation: str | None = None,
    diagnostics: tuple[str, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind,
        checkpoint_id=checkpoint_id,
        record_id="record:prior" if kind == "RESTORED" else None,
        source_map_origin_key="source:prior" if kind == "RESTORED" else None,
        restore_payload={"bindings": []} if kind == "RESTORED" else None,
        policy_decision="REUSABLE" if kind == "RESTORED" else None,
        diagnostics=diagnostics,
        transition_resume=None,
        selection_observation=selection_observation,
    )


def test_default_resume_restores_unique_nearest_prior_effect_boundary_after_record_absence() -> None:
    default_resume = _default_resume_module()
    prior = _generic_resume_point("checkpoint:prior", "root.prior")
    restart = _generic_resume_point("checkpoint:restart", "root.restart")
    runtime_plan = _generic_default_resume_plan(
        ordered_node_ids=("root.prior", "root.restart"),
        points=(prior, restart),
    )
    calls: list[dict[str, object]] = []

    def selector(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _generic_restore_decision(
                "NOT_RESTORABLE",
                selection_observation="record_absent",
            )
        return _generic_restore_decision(
            "RESTORED",
            checkpoint_id="checkpoint:prior",
            selection_observation="record_present",
        )

    decision = default_resume.determine_runtime_default_resume_decision(
        state={"context": {"workflow_lisp": {"lowering_schema_version": 2}}},
        runtime_plan=runtime_plan,
        restart_node_id="root.restart",
        restore_selector=selector,
        is_workflow_lisp=True,
    )

    assert decision["mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert decision["restore_decision"] == "RESTORED"
    assert decision["restart_node_id"] == "root.restart"
    assert decision["checkpoint_id"] == "checkpoint:prior"
    assert decision["restore_candidate"]["selection_reason"] == "validated_prior_boundary"
    assert len(calls) == 2
    assert calls[0]["restart_node_id"] == "root.restart"
    assert calls[1]["checkpoint_id"] == "checkpoint:prior"
    assert "restart_node_id" not in calls[1]


def test_default_resume_validates_and_restores_materialized_nearest_prior_boundary(
    tmp_path: Path,
) -> None:
    default_resume = _default_resume_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id="restore-materialized-nearest-prior",
    )
    order = {
        node_id: index
        for index, node_id in enumerate(bundle.runtime_plan.ordered_node_ids)
    }
    effect_points = sorted(
        (
            point
            for point in bundle.runtime_plan.lexical_checkpoint_points
            if point.point_kind == "effect_boundary"
        ),
        key=lambda point: order[point.node_id],
    )
    prior, restart = effect_points[-2:]
    restart_index = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=restart.workflow_name,
        checkpoint_id=restart.checkpoint_id,
    )
    restart_index.unlink()

    decision = default_resume.determine_runtime_default_resume_decision(
        state=state_manager.load().to_dict(),
        runtime_plan=bundle.runtime_plan,
        restart_node_id=restart.node_id,
        state_manager=state_manager,
        loaded_workflow=bundle,
        executable_workflow=bundle.ir,
        is_workflow_lisp=True,
    )

    assert decision["mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert decision["restore_decision"] == "RESTORED"
    assert decision["restart_node_id"] == restart.node_id
    assert decision["checkpoint_id"] == prior.checkpoint_id
    assert decision["selection_reason"] == "validated_prior_boundary"


@pytest.mark.parametrize(
    ("ordered_node_ids", "points", "expected_diagnostic"),
    (
        (
            ("root.restart",),
            (_generic_resume_point("checkpoint:restart", "root.restart"),),
            "lexical_default_resume_prior_boundary_missing",
        ),
        (
            ("root.prior", "root.restart"),
            (
                _generic_resume_point("checkpoint:prior-a", "root.prior"),
                _generic_resume_point("checkpoint:prior-b", "root.prior"),
                _generic_resume_point("checkpoint:restart", "root.restart"),
            ),
            "lexical_default_resume_prior_boundary_ambiguous",
        ),
        (
            ("root.prior",),
            (
                _generic_resume_point("checkpoint:prior", "root.prior"),
                _generic_resume_point("checkpoint:restart", "root.restart"),
            ),
            "lexical_default_resume_prior_boundary_unordered",
        ),
        (
            ("root.prior", "root.restart", "root.restart"),
            (
                _generic_resume_point("checkpoint:prior", "root.prior"),
                _generic_resume_point("checkpoint:restart", "root.restart"),
            ),
            "lexical_default_resume_prior_boundary_duplicate_order",
        ),
    ),
)
def test_default_resume_fails_closed_when_unique_prior_boundary_cannot_be_derived(
    ordered_node_ids: tuple[str, ...],
    points: tuple[SimpleNamespace, ...],
    expected_diagnostic: str,
) -> None:
    default_resume = _default_resume_module()
    calls = 0

    def selector(**_kwargs):
        nonlocal calls
        calls += 1
        return _generic_restore_decision(
            "NOT_RESTORABLE",
            selection_observation="record_absent",
        )

    decision = default_resume.determine_runtime_default_resume_decision(
        state={"context": {"workflow_lisp": {"lowering_schema_version": 2}}},
        runtime_plan=_generic_default_resume_plan(
            ordered_node_ids=ordered_node_ids,
            points=points,
        ),
        restart_node_id="root.restart",
        restore_selector=selector,
        is_workflow_lisp=True,
    )

    assert decision["mode"] == "FAIL_CLOSED"
    assert expected_diagnostic in decision["diagnostics"]
    assert calls == 1


@pytest.mark.parametrize(
    ("duplicate_node_id", "duplicate_point_kind", "ordered_node_ids"),
    (
        (
            "root.older",
            "effect_boundary",
            ("root.older", "root.prior", "root.restart"),
        ),
        (
            "root.later",
            "binding",
            ("root.prior", "root.restart", "root.later"),
        ),
    ),
)
def test_default_resume_fails_closed_when_selected_prior_checkpoint_id_is_duplicated_anywhere(
    duplicate_node_id: str,
    duplicate_point_kind: str,
    ordered_node_ids: tuple[str, ...],
) -> None:
    default_resume = _default_resume_module()
    selected = _generic_resume_point("checkpoint:prior", "root.prior")
    restart = _generic_resume_point("checkpoint:restart", "root.restart")
    duplicate = _generic_resume_point(
        "checkpoint:prior",
        duplicate_node_id,
        point_kind=duplicate_point_kind,
    )
    points = (
        (duplicate, selected, restart)
        if duplicate_node_id == "root.older"
        else (selected, restart, duplicate)
    )
    calls: list[dict[str, object]] = []

    def selector(**kwargs):
        calls.append(kwargs)
        if "checkpoint_id" in kwargs:
            return _generic_restore_decision(
                "RESTORED",
                checkpoint_id="checkpoint:prior",
                selection_observation="record_present",
            )
        return _generic_restore_decision(
            "NOT_RESTORABLE",
            selection_observation="record_absent",
        )

    decision = default_resume.determine_runtime_default_resume_decision(
        state={"context": {"workflow_lisp": {"lowering_schema_version": 2}}},
        runtime_plan=_generic_default_resume_plan(
            ordered_node_ids=ordered_node_ids,
            points=points,
        ),
        restart_node_id="root.restart",
        restore_selector=selector,
        is_workflow_lisp=True,
    )

    assert decision["mode"] == "FAIL_CLOSED"
    assert decision["diagnostics"] == [
        "lexical_default_resume_prior_boundary_duplicate"
    ]
    assert len(calls) == 1
    assert "checkpoint_id" not in calls[0]


@pytest.mark.parametrize(
    ("node_local", "prior", "expected_diagnostic"),
    (
        (
            _generic_restore_decision(
                "INVALID",
                selection_observation="record_present_unusable",
                diagnostics=("lexical_restore_checkpoint_index_unreadable",),
            ),
            None,
            "lexical_restore_checkpoint_index_unreadable",
        ),
        (
            _generic_restore_decision(
                "NOT_RESTORABLE",
                selection_observation="record_present",
                diagnostics=("lexical_restore_pending_effect_unsafe",),
            ),
            None,
            "lexical_restore_pending_effect_unsafe",
        ),
        (
            _generic_restore_decision(
                "NOT_RESTORABLE",
                selection_observation="record_absent",
            ),
            _generic_restore_decision(
                "NOT_RESTORABLE",
                checkpoint_id="checkpoint:prior",
                selection_observation="record_absent",
            ),
            "lexical_default_resume_prior_boundary_not_restorable",
        ),
        (
            _generic_restore_decision(
                "NOT_RESTORABLE",
                selection_observation="record_absent",
            ),
            _generic_restore_decision(
                "INVALID",
                checkpoint_id="checkpoint:prior",
                selection_observation="record_present_unusable",
                diagnostics=("lexical_restore_program_identity_mismatch",),
            ),
            "lexical_restore_program_identity_mismatch",
        ),
    ),
)
def test_default_resume_never_searches_past_unusable_node_local_or_nearest_prior_record(
    node_local: SimpleNamespace,
    prior: SimpleNamespace | None,
    expected_diagnostic: str,
) -> None:
    default_resume = _default_resume_module()
    older = _generic_resume_point("checkpoint:older", "root.older")
    nearest = _generic_resume_point("checkpoint:prior", "root.prior")
    restart = _generic_resume_point("checkpoint:restart", "root.restart")
    calls: list[dict[str, object]] = []

    def selector(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return node_local
        if len(calls) == 2 and prior is not None:
            return prior
        raise AssertionError("default resume searched past the nearest prior boundary")

    decision = default_resume.determine_runtime_default_resume_decision(
        state={"context": {"workflow_lisp": {"lowering_schema_version": 2}}},
        runtime_plan=_generic_default_resume_plan(
            ordered_node_ids=("root.older", "root.prior", "root.restart"),
            points=(older, nearest, restart),
        ),
        restart_node_id="root.restart",
        restore_selector=selector,
        is_workflow_lisp=True,
    )

    assert decision["mode"] == "FAIL_CLOSED"
    assert expected_diagnostic in decision["diagnostics"]
    assert len(calls) == (1 if prior is None else 2)
    assert all(call.get("checkpoint_id") != "checkpoint:older" for call in calls)


@pytest.mark.parametrize(
    ("index_mutation", "expected_diagnostic"),
    (
        ("unreadable", "lexical_restore_checkpoint_index_unreadable"),
        ("dangling_symlink", "lexical_restore_checkpoint_index_unreadable"),
        ("symlink_to_file", "lexical_restore_checkpoint_index_unreadable"),
        ("malformed", "lexical_restore_checkpoint_index_malformed"),
        ("incomplete", "lexical_restore_checkpoint_record_reference_invalid"),
    ),
)
def test_restore_selector_treats_present_unusable_index_as_invalid_not_absent(
    tmp_path: Path,
    index_mutation: str,
    expected_diagnostic: str,
) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id=f"restore-present-unusable-{index_mutation}",
    )
    point = next(
        candidate
        for candidate in bundle.runtime_plan.lexical_checkpoint_points
        if candidate.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    if index_mutation == "unreadable":
        index_path.unlink()
        index_path.mkdir()
    elif index_mutation == "dangling_symlink":
        index_path.unlink()
        index_path.symlink_to(index_path.with_name("missing-index.json"))
    elif index_mutation == "symlink_to_file":
        symlink_target = index_path.with_name("symlink-target-index.json")
        symlink_target.write_text(json.dumps(index_payload), encoding="utf-8")
        index_path.unlink()
        index_path.symlink_to(symlink_target)
    elif index_mutation == "malformed":
        index_path.write_text("{", encoding="utf-8")
    else:
        index_payload["records"] = [{"record_id": "record:incomplete"}]
        index_path.write_text(
            json.dumps(index_payload),
            encoding="utf-8",
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
    assert decision.selection_observation == "record_present_unusable"
    assert expected_diagnostic in decision.diagnostics


def test_restore_selector_rejects_index_reached_through_symlinked_parent(
    tmp_path: Path,
) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id="restore-index-symlinked-parent",
    )
    point = next(
        candidate
        for candidate in bundle.runtime_plan.lexical_checkpoint_points
        if candidate.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_parent = index_path.parent
    target_parent = index_parent.with_name(f"{index_parent.name}-target")
    index_parent.rename(target_parent)
    index_parent.symlink_to(target_parent.name, target_is_directory=True)

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "INVALID"
    assert decision.selection_observation == "record_present_unusable"
    assert decision.diagnostics == (
        "lexical_restore_checkpoint_index_unreadable",
    )


@pytest.mark.filterwarnings(
    r"ignore:This process .* is multi-threaded, use of fork\(\) may lead to "
    r"deadlocks in the child\.:DeprecationWarning"
)
@pytest.mark.parametrize(
    ("fifo_target", "expected_diagnostics"),
    (
        ("index", {("lexical_restore_checkpoint_index_unreadable",)}),
        (
            "record",
            {
                ("lexical_restore_checkpoint_record_reference_invalid",),
                ("lexical_restore_checkpoint_record_unreadable",),
            },
        ),
    ),
)
def test_restore_selector_rejects_fifo_without_blocking(
    tmp_path: Path,
    fifo_target: str,
    expected_diagnostics: set[tuple[str, ...]],
) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable on this platform")
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("forked process isolation is unavailable on this platform")

    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id=f"restore-{fifo_target}-fifo",
    )
    point = next(
        candidate
        for candidate in bundle.runtime_plan.lexical_checkpoint_points
        if candidate.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    if fifo_target == "index":
        fifo_path = index_path
    else:
        index_payload = json.loads(index_path.read_text(encoding="utf-8"))
        fifo_path = tmp_path / index_payload["records"][-1]["record_path"]
    fifo_path.unlink()
    os.mkfifo(fifo_path)
    state = state_manager.load().to_dict()

    context = multiprocessing.get_context("fork")
    parent_connection, child_connection = context.Pipe(duplex=False)

    def select_in_child() -> None:
        try:
            decision = restore.select_restore_candidate(
                state_manager=state_manager,
                runtime_plan=bundle.runtime_plan,
                state=state,
                checkpoint_id=point.checkpoint_id,
                executable_workflow=bundle.ir,
                loaded_workflow=bundle,
            )
            child_connection.send(
                (
                    decision.kind,
                    decision.selection_observation,
                    decision.diagnostics,
                )
            )
        except BaseException as exc:
            child_connection.send(("ERROR", type(exc).__name__, str(exc)))
        finally:
            child_connection.close()

    process = context.Process(target=select_in_child)
    process.start()
    child_connection.close()
    process.join(timeout=2.0)
    timed_out = process.is_alive()
    if timed_out:
        process.terminate()
        process.join(timeout=1.0)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=1.0)

    try:
        assert not timed_out, f"restore selector blocked while opening {fifo_target} FIFO"
        assert process.exitcode == 0
        assert parent_connection.poll(0.5), "child exited without a selector result"
        kind, observation, diagnostics = parent_connection.recv()
    finally:
        parent_connection.close()

    assert kind == "INVALID"
    assert observation == "record_present_unusable"
    assert diagnostics in expected_diagnostics


@pytest.mark.parametrize(
    ("record_mutation", "expected_diagnostic"),
    (
        ("unreadable", "lexical_restore_checkpoint_record_unreadable"),
        ("malformed", "lexical_restore_checkpoint_record_malformed"),
        ("incomplete", "lexical_restore_checkpoint_record_reference_invalid"),
    ),
)
def test_restore_selector_treats_referenced_unusable_record_as_invalid_not_absent(
    tmp_path: Path,
    record_mutation: str,
    expected_diagnostic: str,
) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id=f"restore-referenced-unusable-{record_mutation}",
    )
    point = next(
        candidate
        for candidate in bundle.runtime_plan.lexical_checkpoint_points
        if candidate.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = tmp_path / index_payload["records"][-1]["record_path"]
    if record_mutation == "unreadable":
        record_path.unlink()
        record_path.mkdir()
    elif record_mutation == "malformed":
        record_path.write_text("{", encoding="utf-8")
    else:
        record_path.write_text("{}", encoding="utf-8")

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "INVALID"
    assert decision.selection_observation == "record_present_unusable"
    assert expected_diagnostic in decision.diagnostics


@pytest.mark.parametrize("index_state", ("missing", "empty"))
def test_restore_selector_positively_reports_record_absent_only_for_missing_or_empty_index(
    tmp_path: Path,
    index_state: str,
) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id=f"restore-record-absent-{index_state}",
    )
    point = next(
        candidate
        for candidate in bundle.runtime_plan.lexical_checkpoint_points
        if candidate.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    if index_state == "missing":
        index_path.unlink()
    else:
        index_payload["records"] = []
        index_path.write_text(json.dumps(index_payload), encoding="utf-8")

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "NOT_RESTORABLE"
    assert decision.selection_observation == "record_absent"


@pytest.mark.parametrize(
    "foreign_index_field",
    ("program_point_id", "storage_allocation_id"),
)
def test_default_resume_rejects_foreign_empty_index_before_prior_checkpoint_selection(
    tmp_path: Path,
    foreign_index_field: str,
) -> None:
    default_resume = _default_resume_module()
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id=f"restore-foreign-empty-index-{foreign_index_field}",
    )
    order = {
        node_id: index
        for index, node_id in enumerate(bundle.runtime_plan.ordered_node_ids)
    }
    effect_points = sorted(
        (
            point
            for point in bundle.runtime_plan.lexical_checkpoint_points
            if point.point_kind == "effect_boundary"
        ),
        key=lambda point: order[point.node_id],
    )
    _prior, restart = effect_points[-2:]
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=restart.workflow_name,
        checkpoint_id=restart.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    index_payload[foreign_index_field] = f"foreign:{foreign_index_field}"
    index_payload["records"] = []
    state_manager.write_runtime_sidecar_json(index_path, index_payload)
    calls: list[dict[str, object]] = []

    def selector(**kwargs):
        calls.append(kwargs)
        return restore.select_restore_candidate(**kwargs)

    decision = default_resume.determine_runtime_default_resume_decision(
        state=state_manager.load().to_dict(),
        runtime_plan=bundle.runtime_plan,
        restart_node_id=restart.node_id,
        state_manager=state_manager,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
        restore_selector=selector,
        is_workflow_lisp=True,
    )

    assert decision["mode"] == "FAIL_CLOSED"
    assert decision["restore_decision"] == "INVALID"
    assert decision["diagnostics"] == [
        "lexical_default_resume_invalid_checkpoint",
        "lexical_restore_checkpoint_index_identity_mismatch",
    ]
    assert len(calls) == 1
    assert "checkpoint_id" not in calls[0]


@pytest.mark.parametrize(
    "record_reference",
    ("canonical", "absolute", "parent_escape", "record_symlink", "parent_symlink"),
)
def test_restore_selector_requires_canonical_non_symlink_record_reference(
    tmp_path: Path,
    record_reference: str,
) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id=f"restore-record-reference-{record_reference}",
    )
    point = next(
        candidate
        for candidate in bundle.runtime_plan.lexical_checkpoint_points
        if candidate.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    entry = index_payload["records"][-1]
    record_path = tmp_path / entry["record_path"]
    if record_reference == "absolute":
        entry["record_path"] = record_path.as_posix()
    elif record_reference == "parent_escape":
        entry["record_path"] = f"../{tmp_path.name}/{entry['record_path']}"
    elif record_reference == "record_symlink":
        target = record_path.with_name(f"{record_path.stem}-target.json")
        record_path.rename(target)
        record_path.symlink_to(target.name)
    elif record_reference == "parent_symlink":
        record_family = record_path.parent
        target_family = record_family.with_name(f"{record_family.name}-target")
        record_family.rename(target_family)
        record_family.symlink_to(target_family.name, target_is_directory=True)
    if record_reference in {"absolute", "parent_escape"}:
        state_manager.write_runtime_sidecar_json(index_path, index_payload)

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    if record_reference == "canonical":
        assert decision.kind == "RESTORED"
        assert decision.selection_observation == "record_present"
    else:
        assert decision.kind == "INVALID"
        assert decision.selection_observation == "record_present_unusable"
        assert decision.diagnostics == (
            "lexical_restore_checkpoint_record_reference_invalid",
        )


def test_restore_selector_rejects_traversal_record_id_before_crafted_record_read(
    tmp_path: Path,
) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id="restore-traversal-record-id",
    )
    point = next(
        candidate
        for candidate in bundle.runtime_plan.lexical_checkpoint_points
        if candidate.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    entry = index_payload["records"][-1]
    original_record_path = tmp_path / entry["record_path"]
    crafted_record = json.loads(original_record_path.read_text(encoding="utf-8"))
    traversal_record_id = "../../../../../crafted"
    crafted_record_path = checkpoints.resolve_checkpoint_record_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
        record_id=traversal_record_id,
        storage_scope=point.details["storage"]["resume_scope"],
    )
    crafted_record["record_id"] = traversal_record_id
    state_manager.write_runtime_sidecar_json(crafted_record_path, crafted_record)
    entry["record_id"] = traversal_record_id
    entry["record_path"] = crafted_record_path.relative_to(tmp_path).as_posix()
    state_manager.write_runtime_sidecar_json(index_path, index_payload)
    original_reader = state_manager.read_runtime_sidecar_json
    read_paths: list[Path] = []

    def recording_reader(path: Path):
        read_paths.append(Path(path))
        return original_reader(path)

    with patch.object(
        state_manager,
        "read_runtime_sidecar_json",
        side_effect=recording_reader,
    ):
        decision = restore.select_restore_candidate(
            state_manager=state_manager,
            runtime_plan=bundle.runtime_plan,
            state=state_manager.load().to_dict(),
            checkpoint_id=point.checkpoint_id,
            executable_workflow=bundle.ir,
            loaded_workflow=bundle,
        )

    assert decision.kind == "INVALID"
    assert decision.selection_observation == "record_present_unusable"
    assert decision.diagnostics == (
        "lexical_restore_checkpoint_record_reference_invalid",
    )
    crafted_target = crafted_record_path.resolve()
    assert all(path.resolve() != crafted_target for path in read_paths)


def test_restore_selector_rejects_record_symlink_swapped_at_final_open(
    tmp_path: Path,
) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id="restore-record-final-open-swap",
    )
    point = next(
        candidate
        for candidate in bundle.runtime_plan.lexical_checkpoint_points
        if candidate.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    record_path = tmp_path / index_payload["records"][-1]["record_path"]
    target_path = record_path.with_name(f"{record_path.stem}-target.json")
    real_os_open = os.open
    swapped = False

    def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if (
            not swapped
            and dir_fd is not None
            and Path(path).name == record_path.name
            and not flags & getattr(os, "O_DIRECTORY", 0)
        ):
            record_path.rename(target_path)
            record_path.symlink_to(target_path.name)
            swapped = True
        return real_os_open(path, flags, mode, dir_fd=dir_fd)

    with patch("os.open", side_effect=swapping_open):
        decision = restore.select_restore_candidate(
            state_manager=state_manager,
            runtime_plan=bundle.runtime_plan,
            state=state_manager.load().to_dict(),
            checkpoint_id=point.checkpoint_id,
            executable_workflow=bundle.ir,
            loaded_workflow=bundle,
        )

    assert swapped
    assert decision.kind == "INVALID"
    assert decision.selection_observation == "record_present_unusable"
    assert decision.diagnostics in {
        ("lexical_restore_checkpoint_record_reference_invalid",),
        ("lexical_restore_checkpoint_record_unreadable",),
    }


@pytest.mark.parametrize(
    "identity_mismatch",
    ("record_id", "program_point_id", "point_kind", "frame_identity"),
)
def test_restore_selector_rejects_checkpoint_index_entry_identity_mismatch(
    tmp_path: Path,
    identity_mismatch: str,
) -> None:
    restore = _restore_module()
    checkpoints = _checkpoints_module()
    bundle, state_manager, _ = _materialize_restore_sidecars(
        tmp_path,
        run_id=f"restore-entry-identity-{identity_mismatch}",
    )
    point = next(
        candidate
        for candidate in bundle.runtime_plan.lexical_checkpoint_points
        if candidate.details.get("restore", {}).get("eligibility")
    )
    index_path = checkpoints.resolve_checkpoint_index_path(
        state_manager=state_manager,
        workflow_name=point.workflow_name,
        checkpoint_id=point.checkpoint_id,
    )
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    entry = index_payload["records"][-1]
    record_path = tmp_path / entry["record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if identity_mismatch == "record_id":
        record["record_id"] = "record:foreign"
        state_manager.write_runtime_sidecar_json(record_path, record)
    elif identity_mismatch == "program_point_id":
        entry["program_point_id"] = "pp:foreign"
        state_manager.write_runtime_sidecar_json(index_path, index_payload)
    elif identity_mismatch == "point_kind":
        entry["point_kind"] = (
            "loop_back_edge"
            if point.point_kind == "effect_boundary"
            else "effect_boundary"
        )
        state_manager.write_runtime_sidecar_json(index_path, index_payload)
    else:
        entry["frame_identity"] = {
            **entry["frame_identity"],
            "visit_count": entry["frame_identity"]["visit_count"] + 1,
        }
        state_manager.write_runtime_sidecar_json(index_path, index_payload)

    decision = restore.select_restore_candidate(
        state_manager=state_manager,
        runtime_plan=bundle.runtime_plan,
        state=state_manager.load().to_dict(),
        checkpoint_id=point.checkpoint_id,
        executable_workflow=bundle.ir,
        loaded_workflow=bundle,
    )

    assert decision.kind == "INVALID"
    assert decision.selection_observation == "record_present_unusable"
    assert decision.diagnostics == (
        "lexical_restore_checkpoint_record_reference_invalid",
    )
