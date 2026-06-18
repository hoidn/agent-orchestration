(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule design_delta_parent_calls_work_item)
  (import lisp_frontend_design_delta/work_item :only (run-work-item))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc PlanDraftResult ProgressLedger SteeringDoc TargetDesignDoc
      WorkItemBootstrapSeed WorkItemResult))
  (export run-parent-work-item)

  (defworkflow run-parent-work-item
    ((work_item_bootstrap WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> WorkItemResult
    (call run-work-item
      :work_item_bootstrap work_item_bootstrap
      :steering_path steering_path
      :target_design_path target_design_path
      :baseline_design_path baseline_design_path
      :progress_ledger_path progress_ledger_path)))
