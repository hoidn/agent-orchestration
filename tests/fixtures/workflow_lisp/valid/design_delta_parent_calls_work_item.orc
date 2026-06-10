(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule design_delta_parent_calls_work_item)
  (import lisp_frontend_design_delta/work_item :only (run-work-item))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc PlanDraftResult ProgressLedger RunStatePath SelectionBundlePath StateFile
      StateFileExisting SteeringDoc TargetDesignDoc WorkItemResult))
  (export run-parent-work-item)

  (defworkflow run-parent-work-item
    ((selection_bundle_path SelectionBundlePath)
     (manifest_path StateFileExisting)
     (architecture_bundle_path StateFile)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger)
     (run_state_path RunStatePath)
     (implementation_execute_provider String)
     (implementation_review_provider String))
    -> WorkItemResult
    (call run-work-item
      :selection_bundle_path selection_bundle_path
      :manifest_path manifest_path
      :architecture_bundle_path architecture_bundle_path
      :steering_path steering_path
      :target_design_path target_design_path
      :baseline_design_path baseline_design_path
      :progress_ledger_path progress_ledger_path
      :run_state_path run_state_path
      :implementation_execute_provider implementation_execute_provider
      :implementation_review_provider implementation_review_provider)))
