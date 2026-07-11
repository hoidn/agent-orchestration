(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule design_delta_item_ctx_child_phase_reuse_proc_ref)
  (import std/context :only (ItemCtx PhaseCtx))
  (import std/resource :only
    (BlockerClass SelectedItemResult WorkReport finalize-selected-item))
  (import std/phase :only (with-phase))
  (import lisp_frontend_design_delta/branching_terminal_reprojection_support :only
    (project-selected-compat))
  (import lisp_frontend_design_delta/bootstrap :only (project-work-item-inputs))
  (import lisp_frontend_design_delta/implementation_phase :only (implementation-phase))
  (import lisp_frontend_design_delta/plan_phase :only (run-plan-phase))
  (import lisp_frontend_design_delta/projections :only (classify-work-item-terminal))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc ImplementationReviewDecision ImplementationState PlanDoc
      PlanReviewDecision ProgressLedger SteeringDoc TargetDesignDoc
      WorkItemBootstrapSeed WorkItemSource))
  (export run-entry)

  (defrecord WorkItemSelectionPayload
    (work_item_bootstrap WorkItemBootstrapSeed)
    (steering_path SteeringDoc)
    (target_design_path TargetDesignDoc)
    (baseline_design_path BaselineDesignDoc)
    (progress_ledger_path ProgressLedger))

  (defunion FixtureResult
    (COMPLETED
      (implementation_state ImplementationState)
      (execution_report WorkReport))
    (PLAN_BLOCKED
      (reason String)))

  (defworkflow run-entry
    ((work_item_bootstrap WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> FixtureResult
    (call bootstrap-item-ctx
      :work_item_bootstrap work_item_bootstrap
      :steering_path steering_path
      :target_design_path target_design_path
      :baseline_design_path baseline_design_path
      :progress_ledger_path progress_ledger_path))

  (defworkflow bootstrap-item-ctx
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
             (selection
               (record WorkItemSelectionPayload
                 :work_item_bootstrap work_item_bootstrap
                 :steering_path steering_path
                 :target_design_path target_design_path
                 :baseline_design_path baseline_design_path
                 :progress_ledger_path progress_ledger_path)))
        (invoke-run-item item-ctx selection (proc-ref run-item-ctx-first)))))

  (defproc invoke-run-item
    :forall (ItemCtxT SelectionT ResultT)
    ((item-ctx ItemCtxT)
     (selection SelectionT)
     (run-item ProcRef[(ItemCtxT SelectionT) -> ResultT]))
    :where ((ItemCtxT is-record)
            (SelectionT is-record)
            (ResultT is-union))
    -> ResultT
    :effects ()
    :lowering inline
    (run-item item-ctx selection))

  (defproc run-item-ctx-first
    ((item-ctx ItemCtx)
     (selection WorkItemSelectionPayload))
    -> FixtureResult
    :effects ((calls-workflow lisp_frontend_design_delta/bootstrap::project-work-item-inputs)
              (calls-workflow lisp_frontend_design_delta/implementation_phase::implementation-phase)
              (calls-workflow lisp_frontend_design_delta/plan_phase::run-plan-phase))
    :lowering inline
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
               :progress_report_target_path resolved.progress_report_target_path
               :plan_review_report_target_path resolved.plan_review_report_target_path)))
      (match plan
        ((APPROVED approved)
         (let* ((implementation
                  (call implementation-phase
                    :target_design selection.target_design_path
                    :baseline_design selection.baseline_design_path
                    :check_commands resolved.check_commands
                    :check_commands_target_path resolved.check_commands_target_path
                    :plan_path approved.approved_plan_path
                    :execution_report_target_path resolved.execution_report_target_path
                    :progress_report_target_path resolved.progress_report_target_path
                    :checks_report_target_path resolved.checks_report_target_path
                    :implementation_review_report_target_path
                      resolved.implementation_review_report_target_path)))
           (variant FixtureResult COMPLETED
             :implementation_state implementation.implementation-state
             :execution_report implementation.execution-report)))
        ((BLOCKED blocked)
         (variant FixtureResult PLAN_BLOCKED
           :reason "plan_blocked"))
        ((EXHAUSTED exhausted)
         (variant FixtureResult PLAN_BLOCKED
           :reason "plan_review_exhausted")))))

)
