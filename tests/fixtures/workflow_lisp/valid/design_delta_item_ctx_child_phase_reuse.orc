(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule design_delta_item_ctx_child_phase_reuse)
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
  (export run-entry run-entry-branching-terminal-reprojection)

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

  (defrecord FinalizerQueueTransitionCompat
    (transition-id String))

  (defrecord FinalizerRoadmapCompat
    (status String))

  (defunion FinalizerPlanCompat
    (APPROVED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))

  (defunion FinalizerImplementationCompat
    (COMPLETED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))

  (defproc project-plan-approved-compat
    ((execution-report-path WorkReport))
    -> FinalizerPlanCompat
    :effects ()
    :lowering inline
    (variant FinalizerPlanCompat APPROVED
      :execution-report-path execution-report-path))

  (defproc project-completed-implementation-compat
    ((execution-report-path WorkReport))
    -> FinalizerImplementationCompat
    :effects ()
    :lowering inline
    (variant FinalizerImplementationCompat COMPLETED
      :execution-report-path execution-report-path))

  (defproc project-blocked-implementation-compat
    ((progress-report-path WorkReport)
     (blocker-class BlockerClass))
    -> FinalizerImplementationCompat
    :effects ()
    :lowering inline
    (variant FinalizerImplementationCompat BLOCKED
      :progress-report-path progress-report-path
      :blocker-class blocker-class))

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

  (defworkflow run-entry-branching-terminal-reprojection
    ((work_item_bootstrap WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> SelectedItemResult
    (call bootstrap-item-ctx-branching-terminal-reprojection
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
        (call run-item-ctx-first
          :item-ctx item-ctx
          :selection selection))))

  (defworkflow bootstrap-item-ctx-branching-terminal-reprojection
    ((phase-ctx PhaseCtx)
     (work_item_bootstrap WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> SelectedItemResult
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
        (call run-item-ctx-first-branching-terminal-reprojection
          :item-ctx item-ctx
          :selection selection))))

  (defworkflow run-item-ctx-first
    ((item-ctx ItemCtx)
     (selection WorkItemSelectionPayload))
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

  (defworkflow run-item-ctx-first-branching-terminal-reprojection
    ((item-ctx ItemCtx)
     (selection WorkItemSelectionPayload))
    -> SelectedItemResult
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
           (selected
             (call project-selected-compat
               :item-id selection.work_item_bootstrap.work_item_id))
           (queue-transition
             (record FinalizerQueueTransitionCompat
               :transition-id ""))
           (roadmap
             (record FinalizerRoadmapCompat
               :status "NO_CHANGE"))
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
                      resolved.implementation_review_report_target_path))
                (terminal
                  (call classify-work-item-terminal
                    :plan_review_decision approved.plan_review_decision
                    :implementation_state implementation.implementation-state
                    :implementation_review_decision implementation.implementation-review-decision
                    :work_item_source resolved.work_item_source)))
           (match terminal
             ((IMPLEMENTATION_BLOCKED implementation_blocked)
              (variant SelectedItemResult BLOCKED
                :summary-path implementation.progress-report
                :blocker-class BlockerClass.unrecoverable_after_fix_attempt
                :run-state selected.final-plan-gate-state))
             ((PLAN_REVIEW_EXHAUSTED plan_review_exhausted)
              (variant SelectedItemResult BLOCKED
                :summary-path implementation.progress-report
                :blocker-class BlockerClass.unrecoverable_after_fix_attempt
                :run-state selected.final-plan-gate-state))
             ((IMPLEMENTATION_REVIEW_EXHAUSTED implementation_review_exhausted)
              (let* ((plan-compat
                       (project-plan-approved-compat
                         implementation.execution-report))
                     (implementation-compat
                       (project-blocked-implementation-compat
                         implementation.progress-report
                         BlockerClass.unrecoverable_after_fix_attempt)))
                (finalize-selected-item
                  :ctx item-ctx
                  :selected selected
                  :queue-transition queue-transition
                  :roadmap roadmap
                  :plan plan-compat
                  :implementation implementation-compat)))
             ((COMPLETE complete)
              (let* ((plan-compat
                       (project-plan-approved-compat
                         implementation.execution-report))
                     (implementation-compat
                       (project-completed-implementation-compat
                         implementation.execution-report)))
                (finalize-selected-item
                  :ctx item-ctx
                  :selected selected
                  :queue-transition queue-transition
                  :roadmap roadmap
                  :plan plan-compat
                  :implementation implementation-compat))))))
        ((BLOCKED blocked)
         (variant SelectedItemResult BLOCKED
           :summary-path blocked.progress_report_path
           :blocker-class blocked.blocker_class
           :run-state selected.final-plan-gate-state))
        ((EXHAUSTED exhausted)
         (variant SelectedItemResult BLOCKED
           :summary-path exhausted.progress_report_path
           :blocker-class BlockerClass.unrecoverable_after_fix_attempt
           :run-state selected.final-plan-gate-state))))))
