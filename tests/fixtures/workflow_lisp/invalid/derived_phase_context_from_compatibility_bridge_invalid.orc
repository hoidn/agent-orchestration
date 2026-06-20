(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule derived_phase_context_from_compatibility_bridge_invalid)
  (import std/context :only (ItemCtx PhaseCtx))
  (import std/phase :only (with-phase))
  (import std/resource :only (StateExisting))
  (import lisp_frontend_design_delta/bootstrap :only (project-work-item-inputs))
  (import lisp_frontend_design_delta/plan_phase :only (run-plan-phase))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc ProgressLedger SteeringDoc TargetDesignDoc WorkItemBootstrapSeed))
  (export run-entry)

  (defrecord WorkItemSelectionPayload
    (work_item_bootstrap WorkItemBootstrapSeed)
    (steering_path SteeringDoc)
    (target_design_path TargetDesignDoc)
    (baseline_design_path BaselineDesignDoc)
    (progress_ledger_path ProgressLedger))

  (defunion FixtureResult
    (BLOCKED
      (reason String)))

  (defworkflow run-entry
    ((work_item_bootstrap WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger)
     (run_state_path StateExisting))
    -> FixtureResult
    (call bootstrap-run-state-bridge
      :work_item_bootstrap work_item_bootstrap
      :steering_path steering_path
      :target_design_path target_design_path
      :baseline_design_path baseline_design_path
      :progress_ledger_path progress_ledger_path
      :run_state_path run_state_path))

  (defworkflow bootstrap-run-state-bridge
    ((phase-ctx PhaseCtx)
     (work_item_bootstrap WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger)
     (run_state_path StateExisting))
    -> FixtureResult
    (with-phase phase-ctx work-item
      (let* ((item-ctx
               (record ItemCtx
                 :run phase-ctx.run
                 :item-id work_item_bootstrap.work_item_id
                 :state-root phase-ctx.state-root
                 :artifact-root phase-ctx.artifact-root
                 :ledger phase-ctx.state-root))
             (selection
               (record WorkItemSelectionPayload
                 :work_item_bootstrap work_item_bootstrap
                 :steering_path steering_path
                 :target_design_path target_design_path
                 :baseline_design_path baseline_design_path
                 :progress_ledger_path progress_ledger_path)))
        (call run-with-run-state-bridge
          :item-ctx item-ctx
          :selection selection
          :run_state_path run_state_path))))

  (defworkflow run-with-run-state-bridge
    ((item-ctx ItemCtx)
     (selection WorkItemSelectionPayload)
     (run_state_path StateExisting))
    -> FixtureResult
    (let* ((selection-ctx
             (record lisp_frontend_design_delta/types/SelectionCtx
               :state_root item-ctx.state-root
               :artifact_root item-ctx.artifact-root))
           (design-delta-item-ctx
             (record lisp_frontend_design_delta/types/ItemCtx
               :selection selection-ctx
               :work_item_id item-ctx.item-id
               :state_root item-ctx.state-root
               :artifact_root item-ctx.artifact-root))
           (resolved
             (call project-work-item-inputs
               :item_ctx design-delta-item-ctx
               :work_item_bootstrap selection.work_item_bootstrap))
           (plan
             (call run-plan-phase
               :steering selection.steering_path
               :target_design selection.target_design_path
               :baseline_design selection.baseline_design_path
               :work_item_context resolved.work_item_context
               :progress_ledger selection.progress_ledger_path
               :plan_target_path resolved.plan_target_path
               :plan_review_report_target_path resolved.plan_review_report_target_path)))
      (match plan
        ((APPROVED approved)
         (variant FixtureResult BLOCKED
           :reason "approved"))
        ((BLOCKED blocked)
         (variant FixtureResult BLOCKED
           :reason "blocked"))
        ((EXHAUSTED exhausted)
         (variant FixtureResult BLOCKED
           :reason "exhausted"))))))
