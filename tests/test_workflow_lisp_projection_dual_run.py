from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_ROOT = REPO_ROOT / "workflows" / "library"
DESIGN_DELTA_PROJECTION_RUNTIME_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "design_delta_projection_runtime.orc"
)
REPORT_SCHEMA_VERSION = "workflow_lisp_projection_dual_run_report.v1"

ADAPTER_SCRIPTS = {
    "project_lisp_frontend_selector_action": (
        REPO_ROOT / "workflows" / "library" / "scripts" / "project_lisp_frontend_selector_action.py"
    ),
    "classify_lisp_frontend_work_item_terminal": (
        REPO_ROOT / "workflows" / "library" / "scripts" / "classify_lisp_frontend_work_item_terminal.py"
    ),
    "select_lisp_frontend_blocked_recovery_route": (
        REPO_ROOT / "workflows" / "library" / "scripts" / "select_lisp_frontend_blocked_recovery_route.py"
    ),
}
REPLACEMENT_ENTRY_WORKFLOWS = {
    "project_lisp_frontend_selector_action": "projection_dual_run/runtime::run-selector-projection",
    "classify_lisp_frontend_work_item_terminal": "projection_dual_run/runtime::run-terminal-projection",
    "select_lisp_frontend_blocked_recovery_route": "projection_dual_run/runtime::run-blocked-recovery-projection",
}
COMPARISON_MAPPINGS = {
    "project_lisp_frontend_selector_action": "selector_action_projection.v1",
    "classify_lisp_frontend_work_item_terminal": "work_item_terminal_projection.v1",
    "select_lisp_frontend_blocked_recovery_route": "blocked_recovery_projection.v1",
}

WRAPPER_SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule projection_dual_run/runtime)
  (import lisp_frontend_design_delta/projections :only
    (classify-work-item-terminal normalize-blocked-recovery-route project-selector-action))
  (import lisp_frontend_design_delta/types :only
    (BlockedRecoveryDecision BlockedRecoveryReason BlockedRecoveryRoute DesignDeltaDrainAction
      ImplementationReviewDecision ImplementationState PlanReviewDecision SelectionBundlePath
      SelectionStatus WorkItemBootstrapSeed WorkItemSource WorkItemTerminalDecision))
  (export run-blocked-recovery-projection run-selector-projection run-terminal-projection)

  (defrecord SelectorProjectionOutcome
    (variant String)
    (selection_bundle_path SelectionBundlePath)
    (reason String))

  (defrecord TerminalProjectionOutcome
    (variant String))

  (defrecord BlockedRecoveryProjectionOutcome
    (variant String)
    (reason BlockedRecoveryReason))

  (defproc project-selector-variant
    ((decision DesignDeltaDrainAction))
    -> String
    :effects ()
    :lowering inline
    (match decision
      ((SELECTED_ITEM selected)
       "SELECTED_ITEM")
      ((DRAFT_DESIGN_GAP gap)
       "DRAFT_DESIGN_GAP")
      ((BLOCKED_RECOVERY blocked_recovery)
       "BLOCKED_RECOVERY")
      ((DONE done)
       "DONE")
      ((BLOCKED blocked)
       "BLOCKED")
      ((EXHAUSTED exhausted)
       "EXHAUSTED")))

  (defproc project-selector-bundle
    ((decision DesignDeltaDrainAction)
     (fallback_bundle SelectionBundlePath))
    -> SelectionBundlePath
    :effects ()
    :lowering inline
    (match decision
      ((SELECTED_ITEM selected)
       fallback_bundle)
      ((DRAFT_DESIGN_GAP gap)
       fallback_bundle)
      ((BLOCKED_RECOVERY blocked_recovery)
       blocked_recovery.blocked_recovery_selection_bundle)
      ((DONE done)
       fallback_bundle)
      ((BLOCKED blocked)
       fallback_bundle)
      ((EXHAUSTED exhausted)
       fallback_bundle)))

  (defproc project-selector-reason
    ((decision DesignDeltaDrainAction))
    -> String
    :effects ()
    :lowering inline
    (match decision
      ((SELECTED_ITEM selected)
       "")
      ((DRAFT_DESIGN_GAP gap)
       "")
      ((BLOCKED_RECOVERY blocked_recovery)
       blocked_recovery.blocked_recovery_reason)
      ((DONE done)
       "")
      ((BLOCKED blocked)
       blocked.blocked_reason)
      ((EXHAUSTED exhausted)
       exhausted.exhausted_reason)))

  (defproc project-terminal-variant
    ((decision WorkItemTerminalDecision))
    -> String
    :effects ()
    :lowering inline
    (match decision
      ((COMPLETE complete)
       "COMPLETE")
      ((PLAN_REVIEW_EXHAUSTED plan_review_exhausted)
       "PLAN_REVIEW_EXHAUSTED")
      ((IMPLEMENTATION_BLOCKED implementation_blocked)
       "IMPLEMENTATION_BLOCKED")
      ((IMPLEMENTATION_REVIEW_EXHAUSTED implementation_review_exhausted)
       "IMPLEMENTATION_REVIEW_EXHAUSTED")))

  (defproc project-blocked-recovery-variant
    ((decision BlockedRecoveryDecision))
    -> String
    :effects ()
    :lowering inline
    (match decision
      ((GAP_DESIGN_REVISION_REQUIRED gap)
       "GAP_DESIGN_REVISION_REQUIRED")
      ((TARGET_DESIGN_REVISION_REQUIRED target)
       "TARGET_DESIGN_REVISION_REQUIRED")
      ((PREREQUISITE_GAP_REQUIRED prerequisite)
       "PREREQUISITE_GAP_REQUIRED")
      ((TERMINAL_BLOCKED terminal)
       "TERMINAL_BLOCKED")))

  (defproc project-blocked-recovery-reason
    ((decision BlockedRecoveryDecision))
    -> BlockedRecoveryReason
    :effects ()
    :lowering inline
    (match decision
      ((GAP_DESIGN_REVISION_REQUIRED gap)
       gap.reason)
      ((TARGET_DESIGN_REVISION_REQUIRED target)
       target.reason)
      ((PREREQUISITE_GAP_REQUIRED prerequisite)
       prerequisite.reason)
      ((TERMINAL_BLOCKED terminal)
       terminal.reason)))

  (defworkflow run-selector-projection
    ((selection_status SelectionStatus)
     (selection_bundle_path SelectionBundlePath)
     (work_item_bootstrap WorkItemBootstrapSeed)
     (blocked_reason String))
    -> SelectorProjectionOutcome
      (let* ((decision
             (call project-selector-action
               :selection_status selection_status
               :work_item_bootstrap work_item_bootstrap
               :blocked_reason blocked_reason))
           (variant_name
             (project-selector-variant decision))
           (bundle_path
             (project-selector-bundle decision selection_bundle_path))
           (reason_text
             (project-selector-reason decision)))
      (record SelectorProjectionOutcome
        :variant variant_name
        :selection_bundle_path bundle_path
        :reason reason_text)))

  (defworkflow run-terminal-projection
    ((plan_review_decision PlanReviewDecision)
     (implementation_state ImplementationState)
     (implementation_review_decision ImplementationReviewDecision)
     (work_item_source WorkItemSource))
    -> TerminalProjectionOutcome
      (let* ((decision
             (call classify-work-item-terminal
               :plan_review_decision plan_review_decision
               :implementation_state implementation_state
               :implementation_review_decision implementation_review_decision
               :work_item_source work_item_source))
           (variant_name
             (project-terminal-variant decision)))
      (record TerminalProjectionOutcome
        :variant variant_name)))

  (defworkflow run-blocked-recovery-projection
    ((work_item_source WorkItemSource)
     (blocked_recovery_route BlockedRecoveryRoute)
     (reason BlockedRecoveryReason))
    -> BlockedRecoveryProjectionOutcome
      (let* ((decision
             (normalize-blocked-recovery-route
               work_item_source
               blocked_recovery_route
               reason))
           (variant_name
             (project-blocked-recovery-variant decision))
           (decision_reason
             (project-blocked-recovery-reason decision)))
      (record BlockedRecoveryProjectionOutcome
        :variant variant_name
        :reason decision_reason))))
"""


def _load_vectors() -> dict[str, Any]:
    return {
        "adapters": {
            "project_lisp_frontend_selector_action": {
                "comparison_mapping_id": "selector_action_projection.v1",
                "vectors": [
                    {
                        "id": "selector_selected_backlog_item",
                        "replacement_inputs": {
                            "selection_status": "SELECT_BACKLOG_ITEM",
                            "selection_bundle_path": "state/selector_selected.json",
                            "work_item_bootstrap__work_item_source": "BACKLOG_ITEM",
                            "work_item_bootstrap__work_item_id": "selector-selected-backlog-item",
                            "work_item_bootstrap__plan_target_path": "docs/plans/projection-plan.md",
                            "work_item_bootstrap__check_commands__commands": [],
                            "work_item_bootstrap__architecture_path": "docs/plans/projection-architecture.md",
                            "blocked_reason": "",
                        },
                        "incumbent_inputs": {
                            "selection_status": "SELECT_BACKLOG_ITEM",
                            "selection_bundle_path": "state/selector_selected.json",
                            "is_selected": True,
                            "is_design_gap": False,
                            "is_done": False,
                            "is_blocked": False,
                            "blocked_reason": "",
                        },
                        "expected_result": {
                            "variant": "SELECTED_ITEM",
                            "selection_bundle_path": "state/selector_selected.json",
                            "reason": "",
                        },
                        "accepted_differences": [],
                    }
                ],
            },
            "classify_lisp_frontend_work_item_terminal": {
                "comparison_mapping_id": "work_item_terminal_projection.v1",
                "vectors": [
                    {
                        "id": "terminal_implementation_blocked",
                        "replacement_inputs": {
                            "plan_review_decision": "APPROVE",
                            "implementation_state": "BLOCKED",
                            "implementation_review_decision": "NOT_APPLICABLE",
                            "work_item_source": "DESIGN_GAP",
                        },
                        "incumbent_inputs": {
                            "plan_review_decision": "APPROVE",
                            "implementation_state": "BLOCKED",
                            "implementation_review_decision": "NOT_APPLICABLE",
                            "work_item_source": "DESIGN_GAP",
                        },
                        "expected_result": {"variant": "IMPLEMENTATION_BLOCKED"},
                        "accepted_differences": [],
                    }
                ],
            },
            "select_lisp_frontend_blocked_recovery_route": {
                "comparison_mapping_id": "blocked_recovery_projection.v1",
                "vectors": [
                    {
                        "id": "blocked_recovery_target_design_revision_required",
                        "replacement_inputs": {
                            "work_item_source": "DESIGN_GAP",
                            "blocked_recovery_route": "TARGET_DESIGN_REVISION_REQUIRED",
                            "reason": "target_design_contract_gap",
                        },
                        "incumbent_inputs": {
                            "terminal_route": "IMPLEMENTATION_BLOCKED",
                            "work_item_source": "DESIGN_GAP",
                            "blocked_recovery_route": "TARGET_DESIGN_REVISION_REQUIRED",
                            "reason": "target_design_contract_gap",
                        },
                        "expected_result": {
                            "variant": "TARGET_DESIGN_REVISION_REQUIRED",
                            "reason": "target_design_contract_gap",
                        },
                        "accepted_differences": [],
                    }
                ],
            },
        }
    }


def _write_wrapper_module(workspace: Path) -> Path:
    module_path = workspace / "projection_dual_run" / "runtime.orc"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(WRAPPER_SOURCE, encoding="utf-8")
    return module_path


def _ensure_workspace_relpath(workspace: Path, relpath: str) -> None:
    target = workspace / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text("{}\n", encoding="utf-8")


def _prepare_workspace_inputs(workspace: Path, vector_payload: dict[str, Any]) -> None:
    for adapter_payload in vector_payload["adapters"].values():
        for vector in adapter_payload["vectors"]:
            for key in ("replacement_inputs", "incumbent_inputs", "expected_result"):
                values = vector.get(key, {})
                if not isinstance(values, dict):
                    continue
                relpath = values.get("selection_bundle_path")
                if isinstance(relpath, str) and relpath:
                    _ensure_workspace_relpath(workspace, relpath)


def _compile_replacement_bundle(workspace: Path, adapter_name: str):
    module_path = _write_wrapper_module(workspace)
    entry_workflow = REPLACEMENT_ENTRY_WORKFLOWS[adapter_name]
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(LIBRARY_ROOT, workspace),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=workspace,
    )
    return module_path, result.validated_bundles_by_name[entry_workflow]


def _execute_replacement(adapter_name: str, inputs: dict[str, Any], workspace: Path) -> dict[str, Any]:
    module_path, bundle = _compile_replacement_bundle(workspace, adapter_name)
    runtime_inputs = {
        input_name: contract
        for input_name, contract in workflow_runtime_input_contracts(bundle).items()
        if not input_name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(runtime_inputs, inputs, workspace)
    run_suffix = abs(hash(json.dumps(inputs, sort_keys=True)))
    state_manager = StateManager(
        workspace=workspace,
        run_id=f"projection-dual-run-{adapter_name}-{run_suffix}",
    )
    state_manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    state = WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(on_error="stop")
    assert state["status"] == "completed"
    outputs = state["workflow_outputs"]
    if adapter_name == "project_lisp_frontend_selector_action":
        return {
            "variant": outputs["return__variant"],
            "selection_bundle_path": outputs["return__selection_bundle_path"],
            "reason": outputs["return__reason"],
        }
    if adapter_name == "classify_lisp_frontend_work_item_terminal":
        return {"variant": outputs["return__variant"]}
    if adapter_name == "select_lisp_frontend_blocked_recovery_route":
        return {
            "variant": outputs["return__variant"],
            "reason": outputs["return__reason"],
        }
    raise AssertionError(f"unknown replacement adapter `{adapter_name}`")


def _run_incumbent(adapter_name: str, inputs: dict[str, Any], workspace: Path) -> dict[str, Any]:
    output_path = workspace / "artifacts" / "work" / f"{adapter_name}_bundle.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] = str(output_path)
    result = subprocess.run(
        ["python", str(ADAPTER_SCRIPTS[adapter_name]), json.dumps(inputs)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if adapter_name == "project_lisp_frontend_selector_action":
        variant = payload["variant"]
        selection_bundle_path = payload.get("selected_item_selection_bundle") or payload.get(
            "design_gap_selection_bundle"
        ) or inputs["selection_bundle_path"]
        reason = payload.get("blocked_reason") or payload.get("blocked_recovery_reason") or payload.get(
            "exhausted_reason"
        ) or ""
        return {
            "variant": variant,
            "selection_bundle_path": selection_bundle_path,
            "reason": reason,
        }
    if adapter_name == "classify_lisp_frontend_work_item_terminal":
        return {"variant": payload["terminal_route"]}
    if adapter_name == "select_lisp_frontend_blocked_recovery_route":
        return {
            "variant": payload["blocked_recovery_route"],
            "reason": payload["reason"],
        }
    raise AssertionError(f"unknown incumbent adapter `{adapter_name}`")


def _compare_results(
    *,
    adapter_name: str,
    comparison_mapping_id: str,
    vector: dict[str, Any],
    incumbent_result: dict[str, Any],
    replacement_result: dict[str, Any],
) -> None:
    expected_mapping_id = COMPARISON_MAPPINGS[adapter_name]
    assert comparison_mapping_id == expected_mapping_id, (
        f"comparison mapping mismatch for `{adapter_name}`: "
        f"{comparison_mapping_id!r} != {expected_mapping_id!r}"
    )
    expected_result = vector["expected_result"]
    assert replacement_result == expected_result
    assert incumbent_result == expected_result


def _emit_dual_run_report(workspace: Path) -> dict[str, Any]:
    vectors_payload = _load_vectors()
    _prepare_workspace_inputs(workspace, vectors_payload)
    adapters_report: dict[str, Any] = {}
    overall_pass = True
    for adapter_name, adapter_payload in vectors_payload["adapters"].items():
        comparison_mapping_id = adapter_payload["comparison_mapping_id"]
        case_reports = []
        adapter_pass = True
        for vector in adapter_payload["vectors"]:
            case_workspace = workspace / adapter_name / vector["id"]
            _prepare_workspace_inputs(case_workspace, vectors_payload)
            incumbent_result = _run_incumbent(adapter_name, vector["incumbent_inputs"], case_workspace)
            replacement_result = _execute_replacement(
                adapter_name,
                vector["replacement_inputs"],
                case_workspace,
            )
            _compare_results(
                adapter_name=adapter_name,
                comparison_mapping_id=comparison_mapping_id,
                vector=vector,
                incumbent_result=incumbent_result,
                replacement_result=replacement_result,
            )
            case_reports.append(
                {
                    "id": vector["id"],
                    "status": "pass",
                    "accepted_differences": vector["accepted_differences"],
                    "expected_result": vector["expected_result"],
                    "incumbent_result": incumbent_result,
                    "replacement_result": replacement_result,
                }
            )
        adapters_report[adapter_name] = {
            "status": "pass" if adapter_pass else "fail",
            "comparison_mapping_id": comparison_mapping_id,
            "cases": case_reports,
        }
        overall_pass = overall_pass and adapter_pass
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "artifact_id": "projection_dual_run_report",
        "workflow_family": "generic_projection_dual_run",
        "overall_status": "pass" if overall_pass else "fail",
        "all_passed": overall_pass,
        "adapters": adapters_report,
    }


def test_projection_dual_run_local_vectors_cover_generic_adapters() -> None:
    payload = _load_vectors()

    assert set(payload["adapters"]) == set(COMPARISON_MAPPINGS)
    for adapter_name, adapter_payload in payload["adapters"].items():
        assert adapter_payload["comparison_mapping_id"] == COMPARISON_MAPPINGS[adapter_name]
        assert len(adapter_payload["vectors"]) == 1
        assert adapter_payload["vectors"][0]["accepted_differences"] == []

def test_projection_dual_run_emits_declared_report_and_passes_all_vectors(tmp_path: Path) -> None:
    report = _emit_dual_run_report(tmp_path)

    assert report["schema_version"] == REPORT_SCHEMA_VERSION
    assert report["artifact_id"] == "projection_dual_run_report"
    assert report["workflow_family"] == "generic_projection_dual_run"
    assert report["overall_status"] == "pass"
    assert report["all_passed"] is True
    assert set(report["adapters"]) == set(COMPARISON_MAPPINGS)


def test_design_delta_projection_runtime_fixture_executes_directly(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        DESIGN_DELTA_PROJECTION_RUNTIME_FIXTURE,
        source_roots=(DESIGN_DELTA_PROJECTION_RUNTIME_FIXTURE.parent,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles_by_name[
        "design_delta_projection_runtime::run-projection"
    ]
    selection_bundle = tmp_path / "state" / "selection.json"
    selection_bundle.parent.mkdir(parents=True, exist_ok=True)
    selection_bundle.write_text(
        json.dumps({"selection": "runtime"}) + "\n",
        encoding="utf-8",
    )

    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        binding_inputs,
        {
            "selection_bundle": "state/selection.json",
            "selection_status": "SELECT_BACKLOG_ITEM",
            "blocked_reason": "gap",
            "implementation_state": "COMPLETED",
            "implementation_review_decision": "APPROVE",
            "work_item_source": "DESIGN_GAP",
            "blocked_recovery_route": "TERMINAL_BLOCKED",
            "blocked_recovery_reason": "user_decision_required",
        },
        tmp_path,
    )
    state_manager = StateManager(
        workspace=tmp_path,
        run_id="design-delta-projection-runtime",
    )
    state_manager.initialize(
        DESIGN_DELTA_PROJECTION_RUNTIME_FIXTURE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )

    state = WorkflowExecutor(
        bundle,
        tmp_path,
        state_manager,
        retry_delay_ms=0,
    ).execute(on_error="stop")

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__selector_route": "SELECTED_ITEM",
        "return__terminal_route": "COMPLETE",
        "return__blocked_recovery_route": "TERMINAL_BLOCKED",
        "return__blocked_recovery_reason": "user_decision_required",
        "return__selection_bundle": "state/selection.json",
    }


def test_projection_dual_run_detects_expected_result_mismatch(tmp_path: Path) -> None:
    payload = _load_vectors()
    case_workspace = tmp_path / "expected-mismatch"
    _prepare_workspace_inputs(case_workspace, payload)
    adapter_name = "project_lisp_frontend_selector_action"
    adapter_payload = payload["adapters"][adapter_name]
    vector = json.loads(json.dumps(adapter_payload["vectors"][0]))
    vector["expected_result"]["variant"] = "WRONG"

    incumbent_result = _run_incumbent(adapter_name, vector["incumbent_inputs"], case_workspace)
    replacement_result = _execute_replacement(
        adapter_name,
        vector["replacement_inputs"],
        case_workspace,
    )

    with pytest.raises(AssertionError):
        _compare_results(
            adapter_name=adapter_name,
            comparison_mapping_id=adapter_payload["comparison_mapping_id"],
            vector=vector,
            incumbent_result=incumbent_result,
            replacement_result=replacement_result,
        )


def test_projection_dual_run_detects_mapping_mismatch(tmp_path: Path) -> None:
    payload = _load_vectors()
    case_workspace = tmp_path / "mapping-mismatch"
    _prepare_workspace_inputs(case_workspace, payload)
    adapter_name = "classify_lisp_frontend_work_item_terminal"
    adapter_payload = payload["adapters"][adapter_name]
    vector = adapter_payload["vectors"][0]

    incumbent_result = _run_incumbent(adapter_name, vector["incumbent_inputs"], case_workspace)
    replacement_result = _execute_replacement(
        adapter_name,
        vector["replacement_inputs"],
        case_workspace,
    )

    with pytest.raises(AssertionError):
        _compare_results(
            adapter_name=adapter_name,
            comparison_mapping_id="wrong_mapping.v1",
            vector=vector,
            incumbent_result=incumbent_result,
            replacement_result=replacement_result,
        )
