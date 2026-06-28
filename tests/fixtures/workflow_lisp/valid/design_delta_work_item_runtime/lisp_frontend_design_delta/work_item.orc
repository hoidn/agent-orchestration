(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/work_item)
  (import std/context :only (ItemCtx))
  (import std/resource :only
    (BlockerClass SelectedItemResult WorkReport finalize-selected-item-proc))
  (import lisp_frontend_design_delta/work_item_bridge_support :only
    (project-selected-compat))
  (import lisp_frontend_design_delta/bootstrap :only (project-work-item-inputs))
  (import lisp_frontend_design_delta/implementation_phase :only (implementation-phase))
  (import lisp_frontend_design_delta/plan_phase :only (run-plan-phase))
  (import lisp_frontend_design_delta/projections :only
    (classify-work-item-terminal normalize-blocked-recovery-route))
  (import lisp_frontend_design_delta/stdlib_adapters :only
    (project-blocker-class-from-reason QueueTransitionCompat RoadmapCompat
      SelectedItemImplementationCompat SelectedItemPlanCompat SelectedItemStdlibCompat))
  (import lisp_frontend_design_delta/transitions :only
    (record-work-item-blocked-recovery-summary))
  (import lisp_frontend_design_delta/types :only
    (ArtifactWorkTargetPath BaselineDesignDoc BlockedRecoveryReason BlockedRecoveryRoute
      DesignDeltaSelectedItemPayload ImplementationPhaseResult ImplementationReviewDecision
      ImplementationState PlanDoc PlanReviewDecision ProgressLedger ResolvedWorkItemInputs
      SelectionCtx SteeringDoc TargetDesignDoc WorkItemContextValue WorkItemResult
      WorkItemSource WorkItemTerminalDecision))
  (export
    BlockedImplementationRecoveryClassification
    BlockedRecoveryClassification
    classify-blocked-implementation-recovery
    run-selected-item-stdlib
    run-work-item)

  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defunion PendingWorkItemResult
    (COMPLETED
      (reason String)
      (summary lisp_frontend_design_delta/types/WorkItemSummaryValue))
    (TERMINAL_BLOCKED
      (reason String)
      (summary lisp_frontend_design_delta/types/WorkItemSummaryValue)
      (blocker-class BlockerClass))
    (BLOCKED_RECOVERY
      (reason String)
      (summary lisp_frontend_design_delta/types/WorkItemSummaryValue)
      (blocker-class BlockerClass)))

  (defrecord BlockedRecoveryClassification
    (blocked_recovery_route BlockedRecoveryRoute)
    (reason BlockedRecoveryReason)
    (summary String))

  (defrecord BlockedImplementationRecoveryPromptSubject
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (work_item_context WorkItemContextValue)
    (approved_plan lisp_frontend_design_delta/types/PlanDoc)
    (implementation_state_bundle ArtifactWorkTargetPath)
    (progress_report ArtifactWorkTargetPath))

  (defrecord BlockedImplementationRecoveryRequest
    (subject BlockedImplementationRecoveryPromptSubject))

  (defrecord BlockedImplementationRecoveryClassification
    (blocked_recovery_route BlockedRecoveryRoute)
    (reason BlockedRecoveryReason)
    (summary String))

  (defworkflow classify-blocked-implementation-recovery
    ((target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (work_item_context WorkItemContextValue)
     (approved_plan lisp_frontend_design_delta/types/PlanDoc)
     (implementation_state_bundle ArtifactWorkTargetPath)
     (progress_report ArtifactWorkTargetPath))
    -> BlockedImplementationRecoveryClassification
    (let* ((subject
             (record BlockedImplementationRecoveryPromptSubject
               :target_design target_design
               :baseline_design baseline_design
               :work_item_context work_item_context
               :approved_plan approved_plan
               :implementation_state_bundle implementation_state_bundle
               :progress_report progress_report))
           (request
             (record BlockedImplementationRecoveryRequest
               :subject subject)))
      (provider-result providers.work-item.recovery-classifier
        :prompt prompts.work-item.classify-blocked-recovery
        :inputs (request)
        :returns BlockedImplementationRecoveryClassification)))

  (defproc project-completed-family-result
    ((resolved_inputs ResolvedWorkItemInputs))
    -> PendingWorkItemResult
    :effects ()
    :lowering inline
    (variant PendingWorkItemResult COMPLETED
      :reason ""
      :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                 :work_item_id resolved_inputs.work_item_id
                 :work_item_source resolved_inputs.work_item_source
                 :terminal_route "COMPLETED"
                 :reason "complete")))

  (defproc project-terminal-blocked-family-result
    ((resolved_inputs ResolvedWorkItemInputs)
     (reason String)
     (blocker-class BlockerClass))
    -> PendingWorkItemResult
    :effects ()
    :lowering inline
    (variant PendingWorkItemResult TERMINAL_BLOCKED
      :reason reason
      :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                 :work_item_id resolved_inputs.work_item_id
                 :work_item_source resolved_inputs.work_item_source
                 :terminal_route "TERMINAL_BLOCKED"
                 :reason reason)
      :blocker-class blocker-class))

  (defproc materialize-canonical-work-item-summary
    ((summary lisp_frontend_design_delta/types/WorkItemSummaryValue)
     (summary-target lisp_frontend_design_delta/types/WorkReportTarget))
    -> WorkReport
    :effects ((writes canonical-work-item-summary))
    :lowering inline
    (materialize-view canonical-work-item-summary
      :value summary
      :renderer canonical-json
      :renderer-version 1
      :target summary-target
      :returns WorkReport))

  (defproc project-work-item-result-summary
    ((result PendingWorkItemResult))
    -> lisp_frontend_design_delta/types/WorkItemSummaryValue
    :effects ()
    :lowering inline
    (match result
      ((COMPLETED completed)
       completed.summary)
      ((TERMINAL_BLOCKED terminal_blocked)
       terminal_blocked.summary)
      ((BLOCKED_RECOVERY blocked_recovery)
       blocked_recovery.summary)))

  (defproc build-finalizer-selected-item
    ((selection DesignDeltaSelectedItemPayload))
    -> SelectedItemStdlibCompat
    :effects ()
    :lowering inline
    (record SelectedItemStdlibCompat
      :item-id selection.item-id
      :is-active false
      :final-plan-gate-state selection.run_state_path))

  (defproc build-finalizer-approved-plan
    ((execution-report-path WorkReport))
    -> SelectedItemPlanCompat
    :effects ()
    :lowering inline
    (variant SelectedItemPlanCompat APPROVED
      :execution-report-path execution-report-path))

  (defproc build-finalizer-blocked-plan
    ((progress-report-path WorkReport)
     (blocker-class BlockerClass))
    -> SelectedItemPlanCompat
    :effects ()
    :lowering inline
    (variant SelectedItemPlanCompat BLOCKED
      :progress-report-path progress-report-path
      :blocker-class blocker-class))

  (defproc build-finalizer-completed-implementation
    ((execution-report-path WorkReport))
    -> SelectedItemImplementationCompat
    :effects ()
    :lowering inline
    (variant SelectedItemImplementationCompat COMPLETED
      :execution-report-path execution-report-path))

  (defproc build-finalizer-blocked-implementation
    ((progress-report-path WorkReport)
     (blocker-class BlockerClass))
    -> SelectedItemImplementationCompat
    :effects ()
    :lowering inline
    (variant SelectedItemImplementationCompat BLOCKED
      :progress-report-path progress-report-path
      :blocker-class blocker-class))

  (defproc materialize-pending-work-item-result
    ((result PendingWorkItemResult)
     (summary-path WorkReport))
    -> WorkItemResult
    :effects ()
    :lowering inline
    (match result
      ((COMPLETED completed)
       (variant WorkItemResult COMPLETED
         :reason completed.reason
         :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                    :work_item_id completed.summary.work_item_id
                    :work_item_source completed.summary.work_item_source
                    :terminal_route completed.summary.terminal_route
                    :reason completed.summary.reason)
         :summary-path summary-path))
      ((TERMINAL_BLOCKED terminal_blocked)
       (variant WorkItemResult TERMINAL_BLOCKED
         :reason terminal_blocked.reason
         :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                    :work_item_id terminal_blocked.summary.work_item_id
                    :work_item_source terminal_blocked.summary.work_item_source
                    :terminal_route terminal_blocked.summary.terminal_route
                    :reason terminal_blocked.summary.reason)
         :blocker-class terminal_blocked.blocker-class
         :summary-path summary-path))
      ((BLOCKED_RECOVERY blocked_recovery)
       (variant WorkItemResult BLOCKED_RECOVERY
         :reason blocked_recovery.reason
         :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                    :work_item_id blocked_recovery.summary.work_item_id
                    :work_item_source blocked_recovery.summary.work_item_source
                    :terminal_route blocked_recovery.summary.terminal_route
                    :reason blocked_recovery.summary.reason)
         :blocker-class blocked_recovery.blocker-class
         :summary-path summary-path))))

  (defproc call-imported-finalize-selected-item
    ((selection DesignDeltaSelectedItemPayload)
     (plan SelectedItemPlanCompat)
     (implementation SelectedItemImplementationCompat))
    -> SelectedItemResult
    :effects ((uses-command apply_resource_transition))
    :lowering inline
    (let* ((selected
             (build-finalizer-selected-item selection))
           (queue-transition-id "")
           (roadmap-status "NO_CHANGE"))
      (finalize-selected-item-proc
        selected.is-active
        selected.final-plan-gate-state
        queue-transition-id
        roadmap-status
        plan
        implementation)))

  (defproc finalize-selected-item-as-completed
    ((selection DesignDeltaSelectedItemPayload)
     (resolved_inputs ResolvedWorkItemInputs)
     (plan SelectedItemPlanCompat)
     (implementation SelectedItemImplementationCompat))
    -> PendingWorkItemResult
    :effects ((uses-command apply_resource_transition))
    :lowering inline
    (let* ((finalized
             (call-imported-finalize-selected-item
               selection
               plan
               implementation)))
      (match finalized
        ((CONTINUE continued)
         (project-completed-family-result resolved_inputs))
        ((BLOCKED blocked)
         (project-completed-family-result resolved_inputs)))))

  (defproc finalize-selected-item-as-terminal-blocked
    ((selection DesignDeltaSelectedItemPayload)
     (resolved_inputs ResolvedWorkItemInputs)
     (reason String)
     (blocker-class BlockerClass)
     (plan SelectedItemPlanCompat)
     (implementation SelectedItemImplementationCompat))
    -> PendingWorkItemResult
    :effects ((uses-command apply_resource_transition))
    :lowering inline
    (let* ((finalized
             (call-imported-finalize-selected-item
               selection
               plan
               implementation)))
      (match finalized
        ((CONTINUE continued)
         (project-terminal-blocked-family-result
           resolved_inputs
           reason
           blocker-class))
        ((BLOCKED blocked)
         (project-terminal-blocked-family-result
           resolved_inputs
           reason
           blocker-class)))))

  (defproc route-blocked-implementation
    ((selection DesignDeltaSelectedItemPayload)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (resolved_inputs ResolvedWorkItemInputs)
     (approved_plan_path lisp_frontend_design_delta/types/PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> PendingWorkItemResult
    :effects ((calls-workflow lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery)
              (uses-provider providers.work-item.recovery-classifier)
              (uses-command apply_resource_transition))
    :lowering inline
    (let* ((classification
             (call classify-blocked-implementation-recovery
               :target_design target_design_path
               :baseline_design baseline_design_path
               :work_item_context resolved_inputs.work_item_context
               :approved_plan approved_plan_path
               :implementation_state_bundle resolved_inputs.execution_report_target_path
               :progress_report resolved_inputs.progress_report_target_path))
           (decision
             (normalize-blocked-recovery-route
               resolved_inputs.work_item_source
               classification.blocked_recovery_route
               classification.reason)))
      (match decision
        ((TERMINAL_BLOCKED terminal)
         (let* ((finalizer-plan
                  (build-finalizer-approved-plan
                    implementation_phase_result.execution-report))
                (finalizer-implementation
                  (build-finalizer-blocked-implementation
                    implementation_phase_result.progress-report
                    BlockerClass.roadmap_conflict)))
           (finalize-selected-item-as-terminal-blocked
             selection
             resolved_inputs
             "implementation_blocked"
             BlockerClass.roadmap_conflict
             finalizer-plan
             finalizer-implementation)))
        ((GAP_DESIGN_REVISION_REQUIRED recovery)
         (let* ((recorded
                  (record-work-item-blocked-recovery-summary
                    selection.run_state_path
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs.work_item_context
                    resolved_inputs.work_item_context_view_target_path
                    BlockedRecoveryRoute.GAP_DESIGN_REVISION_REQUIRED
                    recovery.reason
                    "gap_design_revision_required"
                    resolved_inputs.item_summary_target_path))
                (blocker-class
                  (project-blocker-class-from-reason recovery.reason)))
           (variant PendingWorkItemResult BLOCKED_RECOVERY
             :reason "gap_design_revision_required"
             :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                        :work_item_id recorded.work_item_id
                        :work_item_source recorded.work_item_source
                        :terminal_route recorded.terminal_route
                        :reason recorded.reason)
             :blocker-class blocker-class)))
        ((TARGET_DESIGN_REVISION_REQUIRED recovery)
         (let* ((recorded
                  (record-work-item-blocked-recovery-summary
                    selection.run_state_path
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs.work_item_context
                    resolved_inputs.work_item_context_view_target_path
                    BlockedRecoveryRoute.TARGET_DESIGN_REVISION_REQUIRED
                    recovery.reason
                    "target_design_revision_required"
                    resolved_inputs.item_summary_target_path))
                (blocker-class
                  (project-blocker-class-from-reason recovery.reason)))
           (variant PendingWorkItemResult BLOCKED_RECOVERY
             :reason "target_design_revision_required"
             :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                        :work_item_id recorded.work_item_id
                        :work_item_source recorded.work_item_source
                        :terminal_route recorded.terminal_route
                        :reason recorded.reason)
             :blocker-class blocker-class)))
        ((PREREQUISITE_GAP_REQUIRED recovery)
         (let* ((recorded
                  (record-work-item-blocked-recovery-summary
                    selection.run_state_path
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs.work_item_context
                    resolved_inputs.work_item_context_view_target_path
                    BlockedRecoveryRoute.PREREQUISITE_GAP_REQUIRED
                    recovery.reason
                    "prerequisite_gap_required"
                    resolved_inputs.item_summary_target_path))
                (blocker-class
                  (project-blocker-class-from-reason recovery.reason)))
           (variant PendingWorkItemResult BLOCKED_RECOVERY
             :reason "prerequisite_gap_required"
             :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                        :work_item_id recorded.work_item_id
                        :work_item_source recorded.work_item_source
                        :terminal_route recorded.terminal_route
                        :reason recorded.reason)
             :blocker-class blocker-class))))))

  (defproc route-blocked-implementation-stdlib
    ((selection DesignDeltaSelectedItemPayload)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (resolved_inputs ResolvedWorkItemInputs)
     (approved_plan_path lisp_frontend_design_delta/types/PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> PendingWorkItemResult
    :effects ((calls-workflow lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery)
              (uses-provider providers.work-item.recovery-classifier)
              (uses-command apply_resource_transition))
    :lowering inline
    (route-blocked-implementation
      selection
      target_design_path
      baseline_design_path
      resolved_inputs
      approved_plan_path
      implementation_phase_result))

  (defworkflow run-selected-item-stdlib
    ((item-ctx std/context/ItemCtx)
     (selection DesignDeltaSelectedItemPayload))
    -> SelectedItemResult
    (let* ((selection-ctx
             (record SelectionCtx
               :state_root item-ctx.state-root
               :artifact_root item-ctx.artifact-root))
           (family-item-ctx
             (record lisp_frontend_design_delta/types/ItemCtx
               :selection selection-ctx
               :work_item_id selection.item-id
               :state_root item-ctx.state-root
               :artifact_root item-ctx.artifact-root))
           (resolved
             (call project-work-item-inputs
               :item_ctx family-item-ctx
               :work_item_bootstrap selection.work_item_bootstrap))
           (run_state_path
             selection.run_state_path)
           (result
             (call run-work-item
               :work_item_bootstrap selection.work_item_bootstrap
               :steering_path selection.steering_path
               :target_design_path selection.target_design_path
               :baseline_design_path selection.baseline_design_path
               :progress_ledger_path selection.progress_ledger_path)))
      (match result
        ((COMPLETED completed)
         (variant SelectedItemResult CONTINUE
           :summary-path completed.summary-path
           :run-state selection.run_state_path))
        ((TERMINAL_BLOCKED terminal_blocked)
         (variant SelectedItemResult BLOCKED
           :summary-path terminal_blocked.summary-path
           :blocker-class terminal_blocked.blocker-class
           :run-state selection.run_state_path))
        ((BLOCKED_RECOVERY blocked_recovery)
         (variant SelectedItemResult BLOCKED
           :summary-path blocked_recovery.summary-path
           :blocker-class blocked_recovery.blocker-class
           :run-state selection.run_state_path)))))

  (defworkflow run-work-item
    ((phase-ctx PhaseCtx)
     (work_item_bootstrap lisp_frontend_design_delta/types/WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> WorkItemResult
    (with-phase phase-ctx work-item
      (let* ((selected-compat
             (call project-selected-compat
               :item-id work_item_bootstrap.work_item_id))
           (bridged-run-state
             selected-compat.final-plan-gate-state)
           (selection
             (record DesignDeltaSelectedItemPayload
               :item-id work_item_bootstrap.work_item_id
               :item-state-root phase-ctx.state-root
               :work_item_bootstrap work_item_bootstrap
               :steering_path steering_path
               :target_design_path target_design_path
               :baseline_design_path baseline_design_path
               :progress_ledger_path progress_ledger_path
               :run_state_path bridged-run-state))
           (selection-ctx
             (record SelectionCtx
               :state_root phase-ctx.state-root
               :artifact_root phase-ctx.artifact-root))
           (item-ctx
             (record lisp_frontend_design_delta/types/ItemCtx
               :selection selection-ctx
               :work_item_id selection.item-id
               :state_root phase-ctx.state-root
               :artifact_root phase-ctx.artifact-root))
           (resolved
             (call project-work-item-inputs
               :item_ctx item-ctx
               :work_item_bootstrap selection.work_item_bootstrap))
           (work-item-summary-path
             resolved.item_summary_target_path)
           (plan
             (call run-plan-phase
               :phase-ctx phase-ctx
               :steering steering_path
               :target_design target_design_path
               :baseline_design baseline_design_path
               :work_item_context resolved.work_item_context
               :progress_ledger progress_ledger_path
               :plan_target_path resolved.plan_target_path
               :progress_report_target_path resolved.progress_report_target_path
               :plan_review_report_target_path resolved.plan_review_report_target_path)))
      (match plan
        ((APPROVED approved)
         (let* ((implementation
                  (call implementation-phase
                    :phase-ctx phase-ctx
                    :target_design target_design_path
                    :baseline_design baseline_design_path
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
             (let* ((result
                       (route-blocked-implementation
                         selection
                         target_design_path
                         baseline_design_path
                         resolved
                         approved.approved_plan_path
                         implementation))
                    (summary
                      (project-work-item-result-summary result))
                    (summary-path
                      (materialize-canonical-work-item-summary
                        summary
                        work-item-summary-path)))
                (materialize-pending-work-item-result result summary-path)))
             ((PLAN_REVIEW_EXHAUSTED plan_review_exhausted)
              (let* ((finalizer-plan
                       (build-finalizer-approved-plan
                         implementation.execution-report))
                     (finalizer-implementation
                       (build-finalizer-blocked-implementation
                         implementation.progress-report
                         BlockerClass.unrecoverable_after_fix_attempt))
                     (result
                       (finalize-selected-item-as-terminal-blocked
                         selection
                         resolved
                         "plan_review_exhausted"
                         BlockerClass.unrecoverable_after_fix_attempt
                         finalizer-plan
                         finalizer-implementation))
                     (summary
                       (project-work-item-result-summary result))
                     (summary-path
                       (materialize-canonical-work-item-summary
                         summary
                         work-item-summary-path)))
                (materialize-pending-work-item-result result summary-path)))
             ((IMPLEMENTATION_REVIEW_EXHAUSTED implementation_review_exhausted)
              (let* ((finalizer-plan
                       (build-finalizer-approved-plan
                         implementation.execution-report))
                     (finalizer-implementation
                       (build-finalizer-blocked-implementation
                         implementation.progress-report
                         BlockerClass.unrecoverable_after_fix_attempt))
                     (result
                       (finalize-selected-item-as-terminal-blocked
                         selection
                         resolved
                         "implementation_review_exhausted"
                         BlockerClass.unrecoverable_after_fix_attempt
                         finalizer-plan
                         finalizer-implementation))
                     (summary
                       (project-work-item-result-summary result))
                     (summary-path
                       (materialize-canonical-work-item-summary
                         summary
                         work-item-summary-path)))
                (materialize-pending-work-item-result result summary-path)))
             ((COMPLETE complete)
              (let* ((finalizer-plan
                       (build-finalizer-approved-plan
                         implementation.execution-report))
                     (finalizer-implementation
                       (build-finalizer-completed-implementation
                         implementation.execution-report))
                     (result
                       (finalize-selected-item-as-completed
                         selection
                         resolved
                         finalizer-plan
                         finalizer-implementation))
                     (summary
                       (project-work-item-result-summary result))
                     (summary-path
                       (materialize-canonical-work-item-summary
                         summary
                         work-item-summary-path)))
                (materialize-pending-work-item-result result summary-path))))))
        ((BLOCKED blocked)
         (let* ((finalizer-plan
                  (build-finalizer-blocked-plan
                    blocked.progress_report_path
                    BlockerClass.roadmap_conflict))
                (finalizer-implementation
                  (build-finalizer-completed-implementation
                    blocked.progress_report_path))
                (result
                  (finalize-selected-item-as-terminal-blocked
                    selection
                    resolved
                    "plan_blocked"
                    BlockerClass.roadmap_conflict
                    finalizer-plan
                    finalizer-implementation))
                (summary
                  (project-work-item-result-summary result))
                (summary-path
                  (materialize-canonical-work-item-summary
                    summary
                    work-item-summary-path)))
           (materialize-pending-work-item-result result summary-path)))
        ((EXHAUSTED exhausted)
         (let* ((finalizer-plan
                  (build-finalizer-blocked-plan
                    exhausted.progress_report_path
                    BlockerClass.unrecoverable_after_fix_attempt))
                (finalizer-implementation
                  (build-finalizer-completed-implementation
                    exhausted.progress_report_path))
                (result
                  (finalize-selected-item-as-terminal-blocked
                    selection
                    resolved
                    "plan_review_exhausted"
                    BlockerClass.unrecoverable_after_fix_attempt
                    finalizer-plan
                    finalizer-implementation))
                (summary
                  (project-work-item-result-summary result))
                (summary-path
                  (materialize-canonical-work-item-summary
                    summary
                    work-item-summary-path)))
           (materialize-pending-work-item-result result summary-path))))))))
