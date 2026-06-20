(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/work_item)
  (import std/context :only (ItemCtx))
  (import std/resource :only (BlockerClass SelectedItemResult WorkReport))
  (import lisp_frontend_design_delta/work_item_bridge_support :only
    (project-selected-compat))
  (import lisp_frontend_design_delta/bootstrap :only (project-work-item-inputs))
  (import lisp_frontend_design_delta/implementation_phase :only (implementation-phase))
  (import lisp_frontend_design_delta/plan_phase :only (run-plan-phase))
  (import lisp_frontend_design_delta/projections :only
    (classify-work-item-terminal normalize-blocked-recovery-route))
  (import lisp_frontend_design_delta/stdlib_adapters :only
    (finalize-selected-item-compat project-blocked-implementation-compat
      project-blocker-class-from-reason project-completed-implementation-compat
      project-plan-approved-compat project-plan-blocked-compat SelectedItemImplementationCompat
      SelectedItemPlanCompat))
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
    -> WorkItemResult
    :effects ()
    :lowering inline
    (variant WorkItemResult COMPLETED
      :reason ""
      :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                 :work_item_id resolved_inputs.work_item_id
                 :work_item_source resolved_inputs.work_item_source
                 :terminal_route "COMPLETED"
                 :reason "complete")))

  (defproc project-terminal-blocked-family-result
    ((resolved_inputs ResolvedWorkItemInputs)
     (reason String))
    -> WorkItemResult
    :effects ()
    :lowering inline
    (variant WorkItemResult TERMINAL_BLOCKED
      :reason reason
      :summary (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                 :work_item_id resolved_inputs.work_item_id
                 :work_item_source resolved_inputs.work_item_source
                 :terminal_route "TERMINAL_BLOCKED"
                 :reason reason)))

  (defproc finalize-selected-item-as-completed
    ((selection DesignDeltaSelectedItemPayload)
     (resolved_inputs ResolvedWorkItemInputs)
     (plan SelectedItemPlanCompat)
     (implementation SelectedItemImplementationCompat))
    -> WorkItemResult
    :effects ()
    :lowering inline
    (let* ((finalized
             (finalize-selected-item-compat
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
     (plan SelectedItemPlanCompat)
     (implementation SelectedItemImplementationCompat))
    -> WorkItemResult
    :effects ()
    :lowering inline
    (let* ((finalized
             (finalize-selected-item-compat
               selection
               plan
               implementation)))
      (match finalized
        ((CONTINUE continued)
         (project-terminal-blocked-family-result resolved_inputs reason))
        ((BLOCKED blocked)
         (project-terminal-blocked-family-result resolved_inputs reason)))))

  (defproc route-blocked-implementation
    ((selection DesignDeltaSelectedItemPayload)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (resolved_inputs ResolvedWorkItemInputs)
     (approved_plan_path lisp_frontend_design_delta/types/PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> WorkItemResult
    :effects ((calls-workflow lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery)
              (uses-provider providers.work-item.recovery-classifier))
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
         (let* ((plan
                  (project-plan-approved-compat
                    implementation_phase_result.execution-report))
                (implementation
                  (project-blocked-implementation-compat
                    implementation_phase_result.progress-report
                    BlockerClass.roadmap_conflict)))
           (finalize-selected-item-as-terminal-blocked
             selection
             resolved_inputs
             "implementation_blocked"
             plan
             implementation)))
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

  (defproc route-blocked-implementation-stdlib
    ((selection DesignDeltaSelectedItemPayload)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (resolved_inputs ResolvedWorkItemInputs)
     (approved_plan_path lisp_frontend_design_delta/types/PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> SelectedItemResult
    :effects ((calls-workflow lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery)
              (uses-provider providers.work-item.recovery-classifier)
              (writes blocked-recovery-summary))
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
         (let* ((plan
                  (project-plan-approved-compat
                    implementation_phase_result.execution-report))
                (implementation
                  (project-blocked-implementation-compat
                    implementation_phase_result.progress-report
                    BlockerClass.roadmap_conflict))
                (finalized
                  (finalize-selected-item-compat
                    selection
                    plan
                    implementation)))
           finalized))
        ((GAP_DESIGN_REVISION_REQUIRED recovery)
         (let* ((summary-path
                  (materialize-view blocked-recovery-summary
                    :value (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                             :work_item_id resolved_inputs.work_item_id
                             :work_item_source resolved_inputs.work_item_source
                             :terminal_route "BLOCKED_RECOVERY"
                             :reason "gap_design_revision_required")
                    :renderer canonical-json
                    :renderer-version 1
                    :target resolved_inputs.item_summary_target_path
                    :returns WorkReport))
                (blocker-class
                  (project-blocker-class-from-reason recovery.reason)))
           (variant SelectedItemResult BLOCKED
             :summary-path summary-path
             :blocker-class blocker-class
             :run-state selection.run_state_path)))
        ((TARGET_DESIGN_REVISION_REQUIRED recovery)
         (let* ((summary-path
                  (materialize-view blocked-recovery-summary
                    :value (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                             :work_item_id resolved_inputs.work_item_id
                             :work_item_source resolved_inputs.work_item_source
                             :terminal_route "BLOCKED_RECOVERY"
                             :reason "target_design_revision_required")
                    :renderer canonical-json
                    :renderer-version 1
                    :target resolved_inputs.item_summary_target_path
                    :returns WorkReport))
                (blocker-class
                  (project-blocker-class-from-reason recovery.reason)))
           (variant SelectedItemResult BLOCKED
             :summary-path summary-path
             :blocker-class blocker-class
             :run-state selection.run_state_path)))
        ((PREREQUISITE_GAP_REQUIRED recovery)
         (let* ((summary-path
                  (materialize-view blocked-recovery-summary
                    :value (record lisp_frontend_design_delta/types/WorkItemSummaryValue
                             :work_item_id resolved_inputs.work_item_id
                             :work_item_source resolved_inputs.work_item_source
                             :terminal_route "BLOCKED_RECOVERY"
                             :reason "prerequisite_gap_required")
                    :renderer canonical-json
                    :renderer-version 1
                    :target resolved_inputs.item_summary_target_path
                    :returns WorkReport))
                (blocker-class
                  (project-blocker-class-from-reason recovery.reason)))
           (variant SelectedItemResult BLOCKED
             :summary-path summary-path
             :blocker-class blocker-class
             :run-state selection.run_state_path))))))

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
                selection
                selection.target_design_path
                selection.baseline_design_path
                resolved
                approved.approved_plan_path
                implementation))
             ((PLAN_REVIEW_EXHAUSTED plan_review_exhausted)
              (let* ((plan-compat
                       (project-plan-approved-compat
                         implementation.execution-report))
                     (implementation-compat
                       (project-blocked-implementation-compat
                         implementation.progress-report
                         BlockerClass.unrecoverable_after_fix_attempt))
                     (finalized
                       (finalize-selected-item-compat
                         selection
                         plan-compat
                         implementation-compat)))
                finalized))
             ((IMPLEMENTATION_REVIEW_EXHAUSTED implementation_review_exhausted)
              (let* ((plan-compat
                       (project-plan-approved-compat
                         implementation.execution-report))
                     (implementation-compat
                       (project-blocked-implementation-compat
                         implementation.progress-report
                         BlockerClass.unrecoverable_after_fix_attempt))
                     (finalized
                       (finalize-selected-item-compat
                         selection
                         plan-compat
                         implementation-compat)))
                finalized))
             ((COMPLETE complete)
              (let* ((plan-compat
                       (project-plan-approved-compat
                         implementation.execution-report))
                     (implementation-compat
                       (project-completed-implementation-compat
                         implementation.execution-report))
                     (finalized
                       (finalize-selected-item-compat
                         selection
                         plan-compat
                         implementation-compat)))
                finalized)))))
        ((BLOCKED blocked)
         (let* ((plan-compat
                  (project-plan-blocked-compat
                    blocked.progress_report_path
                    BlockerClass.roadmap_conflict))
                (implementation-compat
                  (project-completed-implementation-compat
                    blocked.progress_report_path))
                (finalized
                  (finalize-selected-item-compat
                    selection
                    plan-compat
                    implementation-compat)))
           finalized))
        ((EXHAUSTED exhausted)
         (let* ((plan-compat
                  (project-plan-blocked-compat
                    exhausted.progress_report_path
                    BlockerClass.unrecoverable_after_fix_attempt))
                (implementation-compat
                  (project-completed-implementation-compat
                    exhausted.progress_report_path))
                (finalized
                  (finalize-selected-item-compat
                    selection
                    plan-compat
                    implementation-compat)))
           finalized)))))

  (defworkflow run-work-item
    ((phase-ctx PhaseCtx)
     (work_item_bootstrap lisp_frontend_design_delta/types/WorkItemBootstrapSeed)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger))
    -> WorkItemResult
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
              (route-blocked-implementation
                selection
                target_design_path
                baseline_design_path
                resolved
                approved.approved_plan_path
                implementation))
             ((PLAN_REVIEW_EXHAUSTED plan_review_exhausted)
              (let* ((plan-compat
                       (project-plan-approved-compat
                         implementation.execution-report))
                     (implementation-compat
                       (project-blocked-implementation-compat
                         implementation.progress-report
                         BlockerClass.unrecoverable_after_fix_attempt)))
                (finalize-selected-item-as-terminal-blocked
                  selection
                  resolved
                  "plan_review_exhausted"
                  plan-compat
                  implementation-compat)))
             ((IMPLEMENTATION_REVIEW_EXHAUSTED implementation_review_exhausted)
              (let* ((plan-compat
                       (project-plan-approved-compat
                         implementation.execution-report))
                     (implementation-compat
                       (project-blocked-implementation-compat
                         implementation.progress-report
                         BlockerClass.unrecoverable_after_fix_attempt)))
                (finalize-selected-item-as-terminal-blocked
                  selection
                  resolved
                  "implementation_review_exhausted"
                  plan-compat
                  implementation-compat)))
             ((COMPLETE complete)
              (let* ((plan-compat
                       (project-plan-approved-compat
                         implementation.execution-report))
                     (implementation-compat
                       (project-completed-implementation-compat
                         implementation.execution-report)))
                (finalize-selected-item-as-completed
                  selection
                  resolved
                  plan-compat
                  implementation-compat))))))
        ((BLOCKED blocked)
         (let* ((plan-compat
                  (project-plan-blocked-compat
                    blocked.progress_report_path
                    BlockerClass.roadmap_conflict))
                (implementation-compat
                  (project-completed-implementation-compat
                    blocked.progress_report_path)))
           (finalize-selected-item-as-terminal-blocked
             selection
             resolved
             "plan_blocked"
             plan-compat
             implementation-compat)))
        ((EXHAUSTED exhausted)
         (let* ((plan-compat
                  (project-plan-blocked-compat
                    exhausted.progress_report_path
                    BlockerClass.unrecoverable_after_fix_attempt))
                (implementation-compat
                  (project-completed-implementation-compat
                    exhausted.progress_report_path)))
           (finalize-selected-item-as-terminal-blocked
             selection
             resolved
             "plan_review_exhausted"
             plan-compat
             implementation-compat)))))))
