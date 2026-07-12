(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/work_item)
  (import std/context :only (ItemCtx))
  (import std/resource :only
    (BlockerClass SelectedItemResult WorkReport finalize-selected-item-proc))
  (import lisp_frontend_design_delta/bootstrap :only (project-work-item-inputs))
  (import lisp_frontend_design_delta/implementation_phase :only (implementation-phase))
  (import lisp_frontend_design_delta/plan_phase :only (run-plan-phase))
  (import lisp_frontend_design_delta/projections :only
    (classify-work-item-terminal normalize-blocked-recovery-route))
  (import lisp_frontend_design_delta/stdlib_adapters :only
    (project-blocker-class-from-reason))
  (import lisp_frontend_design_delta/transitions :only
    (record-work-item-blocked-recovery-summary))
  (import lisp_frontend_design_delta/types :only
    (ArtifactWorkTargetPath BaselineDesignDoc BlockedRecoveryReason BlockedRecoveryRoute
      DesignDeltaSelectedItemPayload ImplementationPhaseResult ImplementationReviewDecision
      ImplementationState PlanDoc PlanReviewDecision ProgressLedger ResolvedWorkItemInputs
      SelectionCtx SteeringDoc TargetDesignDoc WorkItemContextValue
      WorkItemResult WorkItemSource WorkItemTerminalDecision))
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
      (summary lisp_frontend_design_delta/types/WorkItemSummaryValue)
      (public_summary_path WorkReport))
    (TERMINAL_BLOCKED
      (reason String)
      (summary lisp_frontend_design_delta/types/WorkItemSummaryValue)
      (public_summary_path WorkReport)
      (blocker-class BlockerClass))
    (BLOCKED_RECOVERY
      (reason String)
      (summary lisp_frontend_design_delta/types/WorkItemSummaryValue)
      (public_summary_path WorkReport)
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

  (defrecord WorkItemPendingSelection
    (work_item_bootstrap lisp_frontend_design_delta/types/WorkItemBootstrapSeed)
    (steering_path SteeringDoc)
    (target_design_path TargetDesignDoc)
    (baseline_design_path BaselineDesignDoc)
    (progress_ledger_path ProgressLedger))

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

  (defunion SelectedItemFinalizerDecision
    (COMPLETED)
    (BLOCKED
      (blocker-class std/resource/BlockerClass)))

  (defunion SelectedItemFinalizerPlan
    (APPROVED
      (execution-report-path std/resource/WorkReport))
    (BLOCKED
      (progress-report-path std/resource/WorkReport)
      (blocker-class std/resource/BlockerClass)))

  (defunion SelectedItemFinalizerImplementation
    (COMPLETED
      (execution-report-path std/resource/WorkReport))
    (BLOCKED
      (progress-report-path std/resource/WorkReport)
      (blocker-class std/resource/BlockerClass)))

  (defworkflow project-selected-item-finalizer-approved-plan
    ((implementation_phase_result ImplementationPhaseResult))
    -> SelectedItemFinalizerPlan
    (variant SelectedItemFinalizerPlan APPROVED
      :execution-report-path implementation_phase_result.execution-report))

  (defworkflow project-selected-item-finalizer-completed-implementation
    ((implementation_phase_result ImplementationPhaseResult))
    -> SelectedItemFinalizerImplementation
    (variant SelectedItemFinalizerImplementation COMPLETED
      :execution-report-path implementation_phase_result.execution-report))

  (defworkflow project-selected-item-finalizer-blocked-implementation
    ((implementation_phase_result ImplementationPhaseResult)
     (blocker-class std/resource/BlockerClass))
    -> SelectedItemFinalizerImplementation
    (variant SelectedItemFinalizerImplementation BLOCKED
      :progress-report-path implementation_phase_result.progress-report
      :blocker-class blocker-class))

  (defworkflow finalize-selected-item-from-completed-implementation
    ((implementation_phase_result ImplementationPhaseResult))
    -> SelectedItemResult
    (let* ((plan
             (call project-selected-item-finalizer-approved-plan
               :implementation_phase_result implementation_phase_result))
           (implementation
             (call project-selected-item-finalizer-completed-implementation
               :implementation_phase_result implementation_phase_result))
           (queue-transition-id "")
           (roadmap-status "NO_CHANGE"))
      (finalize-selected-item-proc
        false
        queue-transition-id
        roadmap-status
        plan
        implementation)))

  (defworkflow finalize-selected-item-from-blocked-implementation
    ((implementation_phase_result ImplementationPhaseResult)
     (blocker-class std/resource/BlockerClass))
    -> SelectedItemResult
    (let* ((plan
             (call project-selected-item-finalizer-approved-plan
               :implementation_phase_result implementation_phase_result))
           (implementation
             (call project-selected-item-finalizer-blocked-implementation
               :implementation_phase_result implementation_phase_result
               :blocker-class blocker-class))
           (queue-transition-id "")
           (roadmap-status "NO_CHANGE"))
      (finalize-selected-item-proc
        false
        queue-transition-id
        roadmap-status
        plan
        implementation)))

  (defproc project-completed-family-result
    ((resolved_inputs ResolvedWorkItemInputs)
     (public_summary_path WorkReport))
    -> PendingWorkItemResult
    :effects ()
    :lowering inline
    (variant PendingWorkItemResult COMPLETED
      :reason ""
      :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                 :work_item_id resolved_inputs.work_item_id
                 :work_item_source resolved_inputs.work_item_source
                 :terminal_route "COMPLETED"
                 :reason "complete")
      :public_summary_path public_summary_path))

  (defproc project-terminal-blocked-family-result
    ((resolved_inputs ResolvedWorkItemInputs)
     (reason String)
     (blocker-class BlockerClass)
     (public_summary_path WorkReport))
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
      :public_summary_path public_summary_path
      :blocker-class blocker-class))

  (defproc project-blocked-recovery-family-result
    ((resolved_inputs ResolvedWorkItemInputs)
     (reason String)
     (blocker-class BlockerClass)
     (public_summary_path WorkReport))
    -> PendingWorkItemResult
    :effects ()
    :lowering inline
    (variant PendingWorkItemResult BLOCKED_RECOVERY
      :reason reason
      :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                 :work_item_id resolved_inputs.work_item_id
                 :work_item_source resolved_inputs.work_item_source
                 :terminal_route "BLOCKED_RECOVERY"
                 :reason reason)
      :public_summary_path public_summary_path
      :blocker-class blocker-class))

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

  (defproc project-pending-work-item-result
    ((result PendingWorkItemResult))
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
                    :reason completed.summary.reason)))
      ((TERMINAL_BLOCKED terminal_blocked)
       (variant WorkItemResult TERMINAL_BLOCKED
         :reason terminal_blocked.reason
         :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                    :work_item_id terminal_blocked.summary.work_item_id
                    :work_item_source terminal_blocked.summary.work_item_source
                    :terminal_route terminal_blocked.summary.terminal_route
                    :reason terminal_blocked.summary.reason)
         :blocker-class terminal_blocked.blocker-class))
      ((BLOCKED_RECOVERY blocked_recovery)
       (variant WorkItemResult BLOCKED_RECOVERY
         :reason blocked_recovery.reason
         :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                    :work_item_id blocked_recovery.summary.work_item_id
                    :work_item_source blocked_recovery.summary.work_item_source
                    :terminal_route blocked_recovery.summary.terminal_route
                    :reason blocked_recovery.summary.reason)
         :blocker-class blocked_recovery.blocker-class))))

  (defproc route-blocked-implementation
    ((target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (resolved_inputs ResolvedWorkItemInputs)
     (approved_plan_path lisp_frontend_design_delta/types/PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> PendingWorkItemResult
    :effects ((calls-workflow lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery)
              (calls-workflow lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation)
              (calls-workflow lisp_frontend_design_delta/work_item::project-selected-item-finalizer-approved-plan)
              (calls-workflow lisp_frontend_design_delta/work_item::project-selected-item-finalizer-blocked-implementation)
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
         (let* ((finalized
                  (call finalize-selected-item-from-blocked-implementation
                    :implementation_phase_result implementation_phase_result
                    :blocker-class BlockerClass.roadmap_conflict)))
           (project-terminal-blocked-family-result
             resolved_inputs
             "implementation_blocked"
             BlockerClass.roadmap_conflict
             implementation_phase_result.progress-report)))
        ((GAP_DESIGN_REVISION_REQUIRED recovery)
         (let* ((durability-recorded
                  (record-work-item-blocked-recovery-summary
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    BlockedRecoveryRoute.GAP_DESIGN_REVISION_REQUIRED
                    recovery.reason
                    "gap_design_revision_required"
                    implementation_phase_result.progress-report))
                (blocker-class
                  (project-blocker-class-from-reason recovery.reason))
                (ignored durability-recorded))
           (project-blocked-recovery-family-result
             resolved_inputs
             "gap_design_revision_required"
             blocker-class
             implementation_phase_result.progress-report)))
        ((TARGET_DESIGN_REVISION_REQUIRED recovery)
         (let* ((durability-recorded
                  (record-work-item-blocked-recovery-summary
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    BlockedRecoveryRoute.TARGET_DESIGN_REVISION_REQUIRED
                    recovery.reason
                    "target_design_revision_required"
                    implementation_phase_result.progress-report))
                (blocker-class
                  (project-blocker-class-from-reason recovery.reason))
                (ignored durability-recorded))
           (project-blocked-recovery-family-result
             resolved_inputs
             "target_design_revision_required"
             blocker-class
             implementation_phase_result.progress-report)))
        ((PREREQUISITE_GAP_REQUIRED recovery)
         (let* ((durability-recorded
                  (record-work-item-blocked-recovery-summary
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    BlockedRecoveryRoute.PREREQUISITE_GAP_REQUIRED
                    recovery.reason
                    "prerequisite_gap_required"
                    implementation_phase_result.progress-report))
                (blocker-class
                  (project-blocker-class-from-reason recovery.reason))
                (ignored durability-recorded))
           (project-blocked-recovery-family-result
             resolved_inputs
             "prerequisite_gap_required"
             blocker-class
             implementation_phase_result.progress-report))))))

  (defproc route-blocked-implementation-stdlib
    ((target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (resolved_inputs ResolvedWorkItemInputs)
     (approved_plan_path lisp_frontend_design_delta/types/PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> SelectedItemResult
    :effects ((calls-workflow lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery)
              (calls-workflow lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation)
              (calls-workflow lisp_frontend_design_delta/work_item::project-selected-item-finalizer-approved-plan)
              (calls-workflow lisp_frontend_design_delta/work_item::project-selected-item-finalizer-blocked-implementation)
              (uses-provider providers.work-item.recovery-classifier)
              (uses-command apply_resource_transition))
    :lowering inline
    (let* ((result
             (route-blocked-implementation
               target_design_path
               baseline_design_path
               resolved_inputs
               approved_plan_path
               implementation_phase_result)))
      (match result
        ((COMPLETED completed)
         (variant SelectedItemResult CONTINUE
           :summary-path implementation_phase_result.execution-report))
        ((TERMINAL_BLOCKED terminal_blocked)
         (variant SelectedItemResult BLOCKED
           :summary-path implementation_phase_result.progress-report
           :blocker-class terminal_blocked.blocker-class))
        ((BLOCKED_RECOVERY blocked_recovery)
         (variant SelectedItemResult BLOCKED
           :summary-path implementation_phase_result.progress-report
           :blocker-class blocked_recovery.blocker-class)))))

  (defproc run-selected-item-stdlib
    ((item-ctx ItemCtx)
     (selection DesignDeltaSelectedItemPayload))
    -> SelectedItemResult
    :effects ((calls-workflow lisp_frontend_design_delta/bootstrap::project-work-item-inputs)
              (calls-workflow lisp_frontend_design_delta/implementation_phase::implementation-phase)
              (calls-workflow lisp_frontend_design_delta/plan_phase::run-plan-phase)
              (calls-workflow lisp_frontend_design_delta/projections::classify-work-item-terminal)
              (calls-workflow lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery)
              (calls-workflow lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation)
              (calls-workflow lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation)
              (calls-workflow lisp_frontend_design_delta/work_item::project-selected-item-finalizer-approved-plan)
              (calls-workflow lisp_frontend_design_delta/work_item::project-selected-item-finalizer-blocked-implementation)
              (calls-workflow lisp_frontend_design_delta/work_item::project-selected-item-finalizer-completed-implementation)
              (uses-command apply_resource_transition)
              (uses-provider providers.work-item.recovery-classifier))
    :lowering inline
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
              (route-blocked-implementation-stdlib
                selection.target_design_path
                selection.baseline_design_path
                resolved
                approved.approved_plan_path
                implementation))
             ((PLAN_REVIEW_EXHAUSTED plan_review_exhausted)
              (call finalize-selected-item-from-blocked-implementation
                :implementation_phase_result implementation
                :blocker-class BlockerClass.unrecoverable_after_fix_attempt))
             ((IMPLEMENTATION_REVIEW_EXHAUSTED implementation_review_exhausted)
              (call finalize-selected-item-from-blocked-implementation
                :implementation_phase_result implementation
                :blocker-class BlockerClass.unrecoverable_after_fix_attempt))
             ((COMPLETE complete)
              (call finalize-selected-item-from-completed-implementation
                :implementation_phase_result implementation)))))
        ((BLOCKED blocked)
         (variant SelectedItemResult BLOCKED
           :summary-path blocked.progress_report_path
           :blocker-class BlockerClass.roadmap_conflict))
        ((EXHAUSTED exhausted)
         (variant SelectedItemResult BLOCKED
           :summary-path exhausted.progress_report_path
           :blocker-class BlockerClass.unrecoverable_after_fix_attempt)))))

  (defworkflow run-work-item
    ((phase-ctx PhaseCtx)
     (work_item_bootstrap lisp_frontend_design_delta/types/WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> WorkItemResult
    (with-phase phase-ctx work-item
      (let* ((pending
               (call run-work-item-pending
                 :phase-ctx phase-ctx
                 :work_item_bootstrap work_item_bootstrap
                 :steering_path steering_path
                 :target_design_path target_design_path
                 :baseline_design_path baseline_design_path
                 :progress_ledger_path progress_ledger_path)))
        (project-pending-work-item-result pending))))

  (defworkflow run-work-item-pending
    ((phase-ctx PhaseCtx)
     (work_item_bootstrap lisp_frontend_design_delta/types/WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> PendingWorkItemResult
    (with-phase phase-ctx work-item
      (let* ((selection
             (record DesignDeltaSelectedItemPayload
               :item-id work_item_bootstrap.work_item_id
               :item-state-root phase-ctx.state-root
               :work_item_bootstrap work_item_bootstrap
               :steering_path steering_path
               :target_design_path target_design_path
               :baseline_design_path baseline_design_path
               :progress_ledger_path progress_ledger_path))
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
                    :work_item_source resolved.work_item_source))
                (pending
                  (match terminal
                    ((IMPLEMENTATION_BLOCKED implementation_blocked)
                     (route-blocked-implementation
                       target_design_path
                       baseline_design_path
                       resolved
                       approved.approved_plan_path
                       implementation))
                    ((PLAN_REVIEW_EXHAUSTED plan_review_exhausted)
                     (let* ((finalized
                              (call finalize-selected-item-from-blocked-implementation
                                :implementation_phase_result implementation
                                :blocker-class BlockerClass.unrecoverable_after_fix_attempt)))
                       (project-terminal-blocked-family-result
                         resolved
                         "plan_review_exhausted"
                         BlockerClass.unrecoverable_after_fix_attempt
                         implementation.progress-report)))
                    ((IMPLEMENTATION_REVIEW_EXHAUSTED implementation_review_exhausted)
                     (let* ((finalized
                              (call finalize-selected-item-from-blocked-implementation
                                :implementation_phase_result implementation
                                :blocker-class BlockerClass.unrecoverable_after_fix_attempt)))
                       (project-terminal-blocked-family-result
                         resolved
                         "implementation_review_exhausted"
                         BlockerClass.unrecoverable_after_fix_attempt
                         implementation.progress-report)))
                    ((COMPLETE complete)
                     (let* ((finalized
                              (call finalize-selected-item-from-completed-implementation
                                :implementation_phase_result implementation)))
                       (project-completed-family-result
                         resolved
                         implementation.execution-report))))))
           pending))
        ((BLOCKED blocked)
         (project-terminal-blocked-family-result
           resolved
           "plan_blocked"
           BlockerClass.roadmap_conflict
           blocked.progress_report_path))
        ((EXHAUSTED exhausted)
         (project-terminal-blocked-family-result
           resolved
           "plan_review_exhausted"
           BlockerClass.unrecoverable_after_fix_attempt
           exhausted.progress_report_path))))))
)
