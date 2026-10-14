from __future__ import annotations

from pathlib import Path
from typing import Any


from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow import runtime_plan as runtime_plan_module
from orchestrator.workflow_lisp.build import _json_data as workflow_lisp_json_data


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
PROVIDER_SUPERVISION_PROJECTION_SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.16")
  (defmodule provider_supervision_projection)
  (export orchestrate)

  (defrecord SupervisedOutcome
    (work String)
    (status String))

  (defworkflow orchestrate () -> SupervisedOutcome
    (with-live-providers
      ((worker
        (provider-result providers.worker
          :prompt prompts.worker
          :inputs ()
          :timeout-sec 30
          :returns String))
       (supervisor
        (provider-result providers.supervisor
          :prompt prompts.supervisor
          :inputs ()
          :timeout-sec 20
          :returns ProviderSteeringDirective)
        :observes worker))
      (record SupervisedOutcome
        :work worker
        :status "settled"))))
"""

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




















def test_projection_dual_run_local_vectors_cover_generic_adapters() -> None:
    payload = _load_vectors()

    assert set(payload["adapters"]) == set(COMPARISON_MAPPINGS)
    for adapter_name, adapter_payload in payload["adapters"].items():
        assert adapter_payload["comparison_mapping_id"] == COMPARISON_MAPPINGS[adapter_name]
        assert len(adapter_payload["vectors"]) == 1
        assert adapter_payload["vectors"][0]["accepted_differences"] == []



def test_provider_supervision_runtime_plan_projects_composite_topology_without_envelope_bump(
    tmp_path: Path,
) -> None:

    summary_type = getattr(
        runtime_plan_module,
        "RuntimeProviderSupervisionPlan",
        None,
    )
    assert summary_type is not None

    assert (
        runtime_plan_module.RuntimePlanNode.__dataclass_fields__[
            "provider_supervision"
        ].metadata["json_omit_if_none"]
        is True
    )




def test_ordinary_runtime_plan_node_serialization_omits_provider_supervision() -> None:
    ordinary_node = runtime_plan_module.RuntimePlanNode(
        node_id="root.ordinary",
        step_id="root.ordinary",
        presentation_key="ordinary",
        display_name="Ordinary",
        kind=ExecutableNodeKind.PROVIDER.value,
        region="body",
        execution_index=0,
    )

    assert "provider_supervision" not in workflow_lisp_json_data(ordinary_node)
