(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/work_item)
  (import lisp_frontend_design_delta/bootstrap :only (project-work-item-inputs))
  (import lisp_frontend_design_delta/implementation_phase :only (implementation-phase))
  (import lisp_frontend_design_delta/plan_phase :only (run-plan-phase))
  (import lisp_frontend_design_delta/projections :only
    (classify-work-item-terminal normalize-blocked-recovery-route))
  (import lisp_frontend_design_delta/transitions :only
    (record-work-item-blocked-recovery-summary record-work-item-terminal-outcome))
  (import lisp_frontend_design_delta/types :only
    (ArtifactWorkTargetPath BaselineDesignDoc BlockedRecoveryReason BlockedRecoveryRoute
      ImplementationPhaseResult ItemCtx PlanDoc PlanReviewDecision ProgressLedger
      ResolvedWorkItemInputs SelectionCtx SteeringDoc TargetDesignDoc WorkItemBootstrapSeed
      WorkItemContextValue WorkItemResult WorkItemSource WorkItemTerminalDecision
      WorkItemTerminalReason WorkItemTerminalRoute))
  (export
    BlockedImplementationRecoveryClassification
    BlockedRecoveryClassification
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
    (work_item_context WorkItemContextValue)
    (approved_plan PlanDoc)
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
     (approved_plan PlanDoc)
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

  (defworkflow route-blocked-implementation
    ((target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (resolved_inputs ResolvedWorkItemInputs)
     (approved_plan_path PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> WorkItemResult
    (let* ((classification
             (call classify-blocked-implementation-recovery
               :target_design target_design_path
               :baseline_design baseline_design_path
               :work_item_context resolved_inputs.work_item_context
               :approved_plan approved_plan_path
               :implementation_state_bundle implementation_phase_result.execution-report
               :progress_report implementation_phase_result.progress-report))
           (decision
             (call normalize-blocked-recovery-route
               :work_item_source resolved_inputs.work_item_source
               :blocked_recovery_route classification.blocked_recovery_route
               :reason classification.reason)))
      (match decision
        ((TERMINAL_BLOCKED terminal)
         (let* ((recorded
                  (record-work-item-terminal-outcome
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    WorkItemTerminalRoute.IMPLEMENTATION_BLOCKED
                    WorkItemTerminalReason.implementation_blocked
                    "TERMINAL_BLOCKED"
                    "implementation_blocked"
                    resolved_inputs.item_summary_target_path)))
           (variant WorkItemResult TERMINAL_BLOCKED
             :reason "implementation_blocked"
             :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                        :work_item_id recorded.work_item_id
                        :work_item_source recorded.work_item_source
                        :terminal_route recorded.terminal_route
                        :reason recorded.reason))))
        ((GAP_DESIGN_REVISION_REQUIRED recovery)
         (let* ((recorded
                  (record-work-item-blocked-recovery-summary
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs.work_item_context
                    resolved_inputs.work_item_context_view_target_path
                    BlockedRecoveryRoute.GAP_DESIGN_REVISION_REQUIRED
                    recovery.reason
                    "gap_design_revision_required"
                    resolved_inputs.item_summary_target_path)))
           (variant WorkItemResult BLOCKED_RECOVERY
             :reason "gap_design_revision_required"
             :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                        :work_item_id recorded.work_item_id
                        :work_item_source recorded.work_item_source
                        :terminal_route recorded.terminal_route
                        :reason recorded.reason))))
        ((TARGET_DESIGN_REVISION_REQUIRED recovery)
         (let* ((recorded
                  (record-work-item-blocked-recovery-summary
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs.work_item_context
                    resolved_inputs.work_item_context_view_target_path
                    BlockedRecoveryRoute.TARGET_DESIGN_REVISION_REQUIRED
                    recovery.reason
                    "target_design_revision_required"
                    resolved_inputs.item_summary_target_path)))
           (variant WorkItemResult BLOCKED_RECOVERY
             :reason "target_design_revision_required"
             :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                        :work_item_id recorded.work_item_id
                        :work_item_source recorded.work_item_source
                        :terminal_route recorded.terminal_route
                        :reason recorded.reason))))
        ((PREREQUISITE_GAP_REQUIRED recovery)
         (let* ((recorded
                  (record-work-item-blocked-recovery-summary
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs.work_item_context
                    resolved_inputs.work_item_context_view_target_path
                    BlockedRecoveryRoute.PREREQUISITE_GAP_REQUIRED
                    recovery.reason
                    "prerequisite_gap_required"
                    resolved_inputs.item_summary_target_path)))
           (variant WorkItemResult BLOCKED_RECOVERY
             :reason "prerequisite_gap_required"
             :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                        :work_item_id recorded.work_item_id
                        :work_item_source recorded.work_item_source
                        :terminal_route recorded.terminal_route
                        :reason recorded.reason)))))))

  (defworkflow run-work-item
    ((phase-ctx PhaseCtx)
     (work_item_bootstrap WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> WorkItemResult
    (let* ((selection-ctx
             (record SelectionCtx
               :state_root phase-ctx.state-root
               :artifact_root phase-ctx.artifact-root))
           (item-ctx
             (record ItemCtx
               :selection selection-ctx
               :work_item_id work_item_bootstrap.work_item_id
               :state_root phase-ctx.state-root
               :artifact_root phase-ctx.artifact-root))
           (resolved
             (call project-work-item-inputs
               :item_ctx item-ctx
               :work_item_bootstrap work_item_bootstrap))
           (plan
             (call run-plan-phase
               :phase-ctx phase-ctx
               :steering steering_path
               :target_design target_design_path
               :baseline_design baseline_design_path
               :work_item_context resolved.work_item_context
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
              (call route-blocked-implementation
                :target_design_path target_design_path
                :baseline_design_path baseline_design_path
                :resolved_inputs resolved
                :approved_plan_path approved.approved_plan_path
                :implementation_phase_result implementation))
             ((PLAN_REVIEW_EXHAUSTED plan_review_exhausted)
              (let* ((recorded
                       (record-work-item-terminal-outcome
                         resolved.work_item_id
                         resolved.work_item_source
                         WorkItemTerminalRoute.PLAN_REVIEW_EXHAUSTED
                         WorkItemTerminalReason.plan_review_exhausted
                         "TERMINAL_BLOCKED"
                         "plan_review_exhausted"
                         resolved.item_summary_target_path)))
                (variant WorkItemResult TERMINAL_BLOCKED
                  :reason "plan_review_exhausted"
                  :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                             :work_item_id recorded.work_item_id
                             :work_item_source recorded.work_item_source
                             :terminal_route recorded.terminal_route
                             :reason recorded.reason))))
             ((IMPLEMENTATION_REVIEW_EXHAUSTED implementation_review_exhausted)
              (let* ((recorded
                       (record-work-item-terminal-outcome
                         resolved.work_item_id
                         resolved.work_item_source
                         WorkItemTerminalRoute.IMPLEMENTATION_REVIEW_EXHAUSTED
                         WorkItemTerminalReason.implementation_review_exhausted
                         "TERMINAL_BLOCKED"
                         "implementation_review_exhausted"
                         resolved.item_summary_target_path)))
                (variant WorkItemResult TERMINAL_BLOCKED
                  :reason "implementation_review_exhausted"
                  :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                             :work_item_id recorded.work_item_id
                             :work_item_source recorded.work_item_source
                             :terminal_route recorded.terminal_route
                             :reason recorded.reason))))
             ((COMPLETE complete)
              (let* ((recorded
                       (record-work-item-terminal-outcome
                         resolved.work_item_id
                         resolved.work_item_source
                         WorkItemTerminalRoute.COMPLETE
                         WorkItemTerminalReason.completed
                         "COMPLETED"
                         "complete"
                         resolved.item_summary_target_path)))
                (variant WorkItemResult COMPLETED
                  :reason ""
                  :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                             :work_item_id recorded.work_item_id
                             :work_item_source recorded.work_item_source
                             :terminal_route recorded.terminal_route
                             :reason recorded.reason)))))))
        ((BLOCKED blocked)
         (let* ((recorded
                  (record-work-item-terminal-outcome
                    resolved.work_item_id
                    resolved.work_item_source
                    WorkItemTerminalRoute.PLAN_BLOCKED
                    WorkItemTerminalReason.plan_blocked
                    "TERMINAL_BLOCKED"
                    "plan_blocked"
                    resolved.item_summary_target_path)))
           (variant WorkItemResult TERMINAL_BLOCKED
             :reason "plan_blocked"
             :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                        :work_item_id recorded.work_item_id
                        :work_item_source recorded.work_item_source
                        :terminal_route recorded.terminal_route
                        :reason recorded.reason))))
        ((EXHAUSTED exhausted)
         (let* ((recorded
                  (record-work-item-terminal-outcome
                    resolved.work_item_id
                    resolved.work_item_source
                    WorkItemTerminalRoute.PLAN_REVIEW_EXHAUSTED
                    WorkItemTerminalReason.plan_review_exhausted
                    "TERMINAL_BLOCKED"
                    "plan_review_exhausted"
                    resolved.item_summary_target_path)))
           (variant WorkItemResult TERMINAL_BLOCKED
             :reason "plan_review_exhausted"
             :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                        :work_item_id recorded.work_item_id
                        :work_item_source recorded.work_item_source
                        :terminal_route recorded.terminal_route
                        :reason recorded.reason))))))))
