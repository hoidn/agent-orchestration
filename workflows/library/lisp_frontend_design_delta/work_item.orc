(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/work_item)
  (import lisp_frontend_design_delta/implementation_phase :only (implementation-phase))
  (import lisp_frontend_design_delta/plan_phase :only (run-plan-phase))
  (import lisp_frontend_design_delta/projections :only
    (classify-work-item-terminal normalize-blocked-recovery-route))
  (import lisp_frontend_design_delta/transitions :only
    (BlockedRecoveryOutcomeRequest TerminalWorkItemRequest drain-run-state
      record-blocked-recovery-outcome record-terminal-work-item))
  (import lisp_frontend_design_delta/types :only
    (ArtifactWorkTargetPath BaselineDesignDoc BlockedRecoveryReason BlockedRecoveryRoute
      CheckCommandsPath ImplementationPhaseResult ImplementationReviewDecision
      ImplementationState PlanDoc PlanReviewDecision ProgressLedger ResolvedWorkItemInputs
      RunStatePath SelectionBundlePath StateFile StateFileExisting SteeringDoc TargetDesignDoc
      WorkItemResult WorkItemSource WorkItemSummaryValue WorkItemTerminalDecision WorkReport
      WorkReportTarget))
  (export
    BlockedImplementationRecoveryClassification
    BlockedRecoveryClassification
    WorkItemSummary
    classify-blocked-implementation-recovery
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

  (defrecord BlockedRecoveryClassification
    (blocked_recovery_route BlockedRecoveryRoute)
    (reason BlockedRecoveryReason)
    (summary String))

  (defrecord BlockedImplementationRecoveryPromptSubject
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (work_item_context WorkReport)
    (approved_plan PlanDoc)
    (implementation_state_bundle WorkReport)
    (progress_report WorkReport))

  (defrecord BlockedImplementationRecoveryRequest
    (subject BlockedImplementationRecoveryPromptSubject))

  (defrecord BlockedImplementationRecoveryClassification
    (blocked_recovery_route BlockedRecoveryRoute)
    (reason BlockedRecoveryReason)
    (summary String))

  (defrecord BlockedRecoveryStatePromptSubject
    (target_design_path TargetDesignDoc)
    (baseline_design_path BaselineDesignDoc)
    (work_item_context_path WorkReport)
    (approved_plan_path PlanDoc)
    (progress_report ArtifactWorkTargetPath))

  (defrecord BlockedRecoveryStateRequest
    (subject BlockedRecoveryStatePromptSubject))

  (defrecord WorkItemSummary
    (summary WorkReport))

  (defproc resolve-work-item-inputs
    ((selection_bundle_path SelectionBundlePath)
     (manifest_path StateFileExisting)
     (architecture_bundle_path StateFile))
    -> ResolvedWorkItemInputs
    :effects ((uses-command materialize_lisp_frontend_work_item_inputs))
    :lowering inline
    (command-result materialize_lisp_frontend_work_item_inputs
      :adapter materialize_lisp_frontend_work_item_inputs
      :inputs
        ((selection_bundle_path selection_bundle_path)
         (manifest_path manifest_path)
         (architecture_bundle_path architecture_bundle_path))
      :returns ResolvedWorkItemInputs))

  (defworkflow classify-blocked-implementation-recovery
    ((target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (work_item_context WorkReport)
     (approved_plan PlanDoc)
     (implementation_state_bundle WorkReport)
     (progress_report WorkReport))
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

  (defproc classify-blocked-implementation-recovery-state
    ((target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (work_item_context_path WorkReport)
     (approved_plan_path PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> BlockedRecoveryClassification
    :effects ((uses-provider providers.work-item.recovery-classifier))
    :lowering inline
    (let* ((subject
             (record BlockedRecoveryStatePromptSubject
               :target_design_path target_design_path
               :baseline_design_path baseline_design_path
               :work_item_context_path work_item_context_path
               :approved_plan_path approved_plan_path
               :progress_report implementation_phase_result.progress-report))
           (request
             (record BlockedRecoveryStateRequest
               :subject subject)))
      (provider-result providers.work-item.recovery-classifier
        :prompt prompts.work-item.classify-blocked-recovery
        :inputs (request)
        :returns BlockedRecoveryClassification)))

  (defproc finalize-terminal-work-item
    ((work_item_id String)
     (work_item_source WorkItemSource)
     (reason String)
     (item_summary_target_path WorkReportTarget)
     (item_summary_pointer_path WorkReportTarget)
     (drain_status_path StateFile)
     (terminal_route String))
    -> WorkItemSummary
    :effects ((uses-command apply_resource_transition)
              (writes work-item-terminal-summary-view))
    :lowering inline
    (let* ((transition-result
             (resource-transition
               :transition record-terminal-work-item
               :resource drain-run-state
               :request (record TerminalWorkItemRequest
                 :work_item_id work_item_id
                 :work_item_source work_item_source
                 :reason reason
                 :item_summary_target_path item_summary_target_path
                 :item_summary_pointer_path item_summary_pointer_path
                 :drain_status_path drain_status_path)))
           (rendered-summary
             (materialize-view work-item-terminal-summary-view
               :value (record WorkItemSummaryValue
                        :work_item_id work_item_id
                        :work_item_source work_item_source
                        :terminal_route terminal_route
                        :reason reason)
               :renderer canonical-json
               :renderer-version 1
               :target transition-result.summary_path
               :returns WorkReport)))
      (record WorkItemSummary
        :summary rendered-summary)))

  (defproc finalize-blocked-recovery-outcome
    ((work_item_id String)
     (work_item_source WorkItemSource)
     (resolved_inputs ResolvedWorkItemInputs)
     (implementation_phase_result ImplementationPhaseResult)
     (recovery_route BlockedRecoveryRoute)
     (reason BlockedRecoveryReason)
     (summary_reason String))
    -> WorkItemSummary
    :effects ((uses-command apply_resource_transition)
              (writes work-item-blocked-recovery-summary-view))
    :lowering inline
    (let* ((transition-result
             (resource-transition
               :transition record-blocked-recovery-outcome
               :resource drain-run-state
               :request (record BlockedRecoveryOutcomeRequest
                 :work_item_id work_item_id
                 :work_item_source work_item_source
                 :recovery_route recovery_route
                 :reason reason
                 :target_design_review_decision "APPROVE"
                 :terminal_action "continue"
                 :summary_path resolved_inputs.item_summary_target_path
                 :summary_pointer_path resolved_inputs.item_summary_pointer_path
                 :drain_status_path resolved_inputs.drain_status_path
                 :progress_report_path implementation_phase_result.progress-report
                 :implementation_state_path implementation_phase_result.execution-report
                 :architecture_bundle_path resolved_inputs.work_item_context_path
                 :plan_path resolved_inputs.plan_target_path)))
           (rendered-summary
             (materialize-view work-item-blocked-recovery-summary-view
               :value (record WorkItemSummaryValue
                        :work_item_id work_item_id
                        :work_item_source work_item_source
                        :terminal_route "BLOCKED_RECOVERY"
                        :reason summary_reason)
               :renderer canonical-json
               :renderer-version 1
               :target transition-result.summary_path
               :returns WorkReport)))
      (record WorkItemSummary
        :summary rendered-summary)))

  (defworkflow route-blocked-implementation
    ((target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (resolved_inputs ResolvedWorkItemInputs)
     (approved_plan_path PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> WorkItemResult
    (let* ((classification
             (classify-blocked-implementation-recovery-state
               target_design_path
               baseline_design_path
               resolved_inputs.work_item_context_path
               approved_plan_path
               implementation_phase_result))
           (decision
             (call normalize-blocked-recovery-route
               :work_item_source resolved_inputs.work_item_source
               :blocked_recovery_route classification.blocked_recovery_route
               :reason classification.reason)))
      (match decision
        ((TERMINAL_BLOCKED terminal)
         (let* ((recorded
                  (finalize-terminal-work-item
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    "implementation_blocked"
                    resolved_inputs.item_summary_target_path
                    resolved_inputs.item_summary_pointer_path
                    resolved_inputs.drain_status_path
                    "TERMINAL_BLOCKED")))
           (variant WorkItemResult TERMINAL_BLOCKED
             :reason "implementation_blocked"
             :summary recorded.summary)))
        ((GAP_DESIGN_REVISION_REQUIRED recovery)
         (let* ((recorded
                  (finalize-blocked-recovery-outcome
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs
                    implementation_phase_result
                    BlockedRecoveryRoute.GAP_DESIGN_REVISION_REQUIRED
                    recovery.reason
                    "gap_design_revision_required")))
           (variant WorkItemResult BLOCKED_RECOVERY
             :reason "gap_design_revision_required"
             :summary recorded.summary)))
        ((TARGET_DESIGN_REVISION_REQUIRED recovery)
         (let* ((recorded
                  (finalize-blocked-recovery-outcome
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs
                    implementation_phase_result
                    BlockedRecoveryRoute.TARGET_DESIGN_REVISION_REQUIRED
                    recovery.reason
                    "target_design_revision_required")))
           (variant WorkItemResult BLOCKED_RECOVERY
             :reason "target_design_revision_required"
             :summary recorded.summary)))
        ((PREREQUISITE_GAP_REQUIRED recovery)
         (let* ((recorded
                  (finalize-blocked-recovery-outcome
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs
                    implementation_phase_result
                    BlockedRecoveryRoute.PREREQUISITE_GAP_REQUIRED
                    recovery.reason
                    "prerequisite_gap_required")))
           (variant WorkItemResult BLOCKED_RECOVERY
             :reason "prerequisite_gap_required"
             :summary recorded.summary))))))

  (defworkflow run-work-item
    ((phase-ctx PhaseCtx)
     (selection_bundle_path SelectionBundlePath)
     (manifest_path StateFileExisting)
     (architecture_bundle_path StateFile)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> WorkItemResult
    (let* ((resolved
             (resolve-work-item-inputs
               selection_bundle_path
               manifest_path
               architecture_bundle_path))
           (plan
             (call run-plan-phase
               :phase-ctx phase-ctx
               :steering steering_path
               :target_design target_design_path
               :baseline_design baseline_design_path
               :work_item_context resolved.work_item_context_path
               :progress_ledger progress_ledger_path
               :plan_target_path resolved.plan_target_path
               :plan_review_report_target_path resolved.plan_review_report_target_path)))
      (match plan
        ((APPROVED approved)
         (let* ((implementation
                  (call implementation-phase
                    :phase-ctx phase-ctx
                    :target_design target_design_path
                    :baseline_design baseline_design_path
                    :check_commands_path resolved.check_commands_path
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
              (call route-blocked-implementation
                :target_design_path target_design_path
                :baseline_design_path baseline_design_path
                :resolved_inputs resolved
                :approved_plan_path approved.approved_plan_path
                :implementation_phase_result implementation))
             ((PLAN_REVIEW_EXHAUSTED plan_review_exhausted)
              (let* ((recorded
                       (finalize-terminal-work-item
                         resolved.work_item_id
                         resolved.work_item_source
                         "plan_review_exhausted"
                         resolved.item_summary_target_path
                         resolved.item_summary_pointer_path
                         resolved.drain_status_path
                         "TERMINAL_BLOCKED")))
                (variant WorkItemResult TERMINAL_BLOCKED
                  :reason "plan_review_exhausted"
                  :summary recorded.summary)))
             ((IMPLEMENTATION_REVIEW_EXHAUSTED implementation_review_exhausted)
              (let* ((recorded
                       (finalize-terminal-work-item
                         resolved.work_item_id
                         resolved.work_item_source
                         "implementation_review_exhausted"
                         resolved.item_summary_target_path
                         resolved.item_summary_pointer_path
                         resolved.drain_status_path
                         "TERMINAL_BLOCKED")))
                (variant WorkItemResult TERMINAL_BLOCKED
                  :reason "implementation_review_exhausted"
                  :summary recorded.summary)))
             ((COMPLETE complete)
              (let* ((recorded
                       (finalize-terminal-work-item
                         resolved.work_item_id
                         resolved.work_item_source
                         "complete"
                         resolved.item_summary_target_path
                         resolved.item_summary_pointer_path
                         resolved.drain_status_path
                         "COMPLETED")))
                (variant WorkItemResult COMPLETED
                  :reason ""
                  :summary recorded.summary))))))
        ((BLOCKED blocked)
         (let* ((recorded
                  (finalize-terminal-work-item
                    resolved.work_item_id
                    resolved.work_item_source
                    "plan_blocked"
                    resolved.item_summary_target_path
                    resolved.item_summary_pointer_path
                    resolved.drain_status_path
                    "TERMINAL_BLOCKED")))
           (variant WorkItemResult TERMINAL_BLOCKED
             :reason "plan_blocked"
             :summary recorded.summary)))
        ((EXHAUSTED exhausted)
         (let* ((recorded
                  (finalize-terminal-work-item
                    resolved.work_item_id
                    resolved.work_item_source
                    "plan_review_exhausted"
                    resolved.item_summary_target_path
                    resolved.item_summary_pointer_path
                    resolved.drain_status_path
                    "TERMINAL_BLOCKED")))
           (variant WorkItemResult TERMINAL_BLOCKED
             :reason "plan_review_exhausted"
             :summary recorded.summary)))))))
