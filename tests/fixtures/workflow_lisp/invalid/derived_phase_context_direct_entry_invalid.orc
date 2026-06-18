(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule derived_phase_context_direct_entry_invalid)
  (import lisp_frontend_design_delta/plan_phase :only
    (DesignDeltaPlanPhaseResult run-plan-phase))
  (import lisp_frontend_design_delta/types :only
    (ArtifactReviewTargetPath BaselineDesignDoc PlanDocTarget ProgressLedger
      SteeringDoc TargetDesignDoc WorkItemContextValue))
  (export run-entry)

  (defworkflow run-entry
    ((steering SteeringDoc)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (work_item_context WorkItemContextValue)
     (progress_ledger ProgressLedger)
     (plan_target_path PlanDocTarget)
     (plan_review_report_target_path ArtifactReviewTargetPath))
    -> DesignDeltaPlanPhaseResult
    (call run-plan-phase
      :steering steering
      :target_design target_design
      :baseline_design baseline_design
      :work_item_context work_item_context
      :progress_ledger progress_ledger
      :plan_target_path plan_target_path
      :plan_review_report_target_path plan_review_report_target_path)))
