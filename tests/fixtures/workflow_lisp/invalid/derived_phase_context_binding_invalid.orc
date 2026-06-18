(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule derived_phase_context_binding_invalid)
  (import std/context :only (ItemCtx PhaseCtx))
  (import std/phase :only (with-phase))
  (import lisp_frontend_design_delta/bootstrap :only (project-work-item-inputs))
  (import lisp_frontend_design_delta/plan_phase :only (run-plan-phase))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc ProgressLedger ResolvedWorkItemInputs SteeringDoc
      TargetDesignDoc WorkItemBootstrapSeed))
  (export run-entry)

  (defrecord WorkItemSelectionPayload
    (resolved_inputs ResolvedWorkItemInputs)
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
     (progress_ledger_path ProgressLedger))
    -> FixtureResult
    (call bootstrap-without-derived-source
      :work_item_bootstrap work_item_bootstrap
      :steering_path steering_path
      :target_design_path target_design_path
      :baseline_design_path baseline_design_path
      :progress_ledger_path progress_ledger_path))

  (defworkflow bootstrap-without-derived-source
    ((phase-ctx PhaseCtx)
     (work_item_bootstrap WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> FixtureResult
    (with-phase phase-ctx work-item
      (let* ((item-ctx
               (record ItemCtx
                 :run phase-ctx.run
                 :item-id work_item_bootstrap.work_item_id
                 :state-root phase-ctx.state-root
                 :artifact-root phase-ctx.artifact-root
                 :ledger phase-ctx.state-root))
             (selection-ctx
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
                 :work_item_bootstrap work_item_bootstrap))
             (selection
               (record WorkItemSelectionPayload
                 :resolved_inputs resolved
                 :steering_path steering_path
                 :target_design_path target_design_path
                 :baseline_design_path baseline_design_path
                 :progress_ledger_path progress_ledger_path)))
        (call run-without-derived-source
          :selection selection))))

  (defworkflow run-without-derived-source
    ((selection WorkItemSelectionPayload))
    -> FixtureResult
    (let* ((plan
             (call run-plan-phase
               :steering selection.steering_path
               :target_design selection.target_design_path
               :baseline_design selection.baseline_design_path
               :work_item_context selection.resolved_inputs.work_item_context
               :progress_ledger selection.progress_ledger_path
               :plan_target_path selection.resolved_inputs.plan_target_path
               :plan_review_report_target_path
                 selection.resolved_inputs.plan_review_report_target_path)))
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
