(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/work_item)
  (import lisp_frontend_design_delta/implementation_phase :only (implementation-phase))
  (import lisp_frontend_design_delta/plan_phase :only (run-plan-phase))
  (import lisp_frontend_design_delta/transitions :only
    (drain-run-state record-blocked-recovery-outcome record-terminal-work-item))
  (import lisp_frontend_design_delta/types :only
    (ArtifactWorkTargetPath BaselineDesignDoc BlockedRecoveryDecision BlockedRecoveryReason CheckCommandsPath ImplementationPhaseResult
      PlanDoc PlanDocTarget PlanDraftResult ProgressLedger ResolvedWorkItemInputs RunStatePath SelectionBundlePath
      StateFile StateFileExisting SteeringDoc TargetDesignDoc WorkItemResult WorkReport
      WorkReportTarget))
  (export
    BlockedImplementationRecoveryClassification
    BlockedRecoveryClassification
    WorkItemSummary
    WorkItemTerminalClassification
    classify-blocked-implementation-recovery
    classify-work-item-terminal
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

  (defrecord WorkItemTerminalClassification
    (route String)
    (terminal_route String)
    (block_reason String)
    (implementation_blocked Bool)
    (plan_review_exhausted Bool)
    (implementation_review_exhausted Bool))

  (defrecord BlockedRecoveryClassification
    (blocked_recovery_route String)
    (reason String)
    (summary String))

  (defrecord BlockedImplementationRecoveryClassification
    (blocked_recovery_route String)
    (reason String)
    (summary String))

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

  (defworkflow classify-work-item-terminal
    ((plan_review_decision String)
     (implementation_state_bundle WorkReport)
     (implementation_review_decision_path WorkReport)
     (work_item_source String)
     (terminal_route_target WorkReportTarget))
    -> WorkItemTerminalClassification
    (command-result classify_lisp_frontend_work_item_terminal
      :argv ("python"
             "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py"
             "--plan-review-decision"
             plan_review_decision
             "--implementation-state-path"
             implementation_state_bundle
             "--implementation-review-decision-path"
             implementation_review_decision_path
             "--implementation-bundle-path"
             implementation_state_bundle
             "--work-item-source"
             work_item_source
             "--output"
             terminal_route_target)
      :returns WorkItemTerminalClassification))

  (defproc classify-work-item-terminal-state
    ((plan_review_decision String)
     (implementation_state String)
     (implementation_review_decision String)
     (work_item_source String))
    -> WorkItemTerminalClassification
    :effects ((uses-command classify_lisp_frontend_work_item_terminal))
    :lowering inline
    (command-result classify_lisp_frontend_work_item_terminal
      :adapter classify_lisp_frontend_work_item_terminal
      :inputs
        ((plan_review_decision plan_review_decision)
         (implementation_state implementation_state)
         (implementation_review_decision implementation_review_decision)
         (work_item_source work_item_source))
      :returns WorkItemTerminalClassification))

  (defworkflow classify-blocked-implementation-recovery
    ((target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (work_item_context WorkReport)
     (approved_plan PlanDoc)
     (implementation_state_bundle WorkReport)
     (progress_report WorkReport))
    -> BlockedImplementationRecoveryClassification
    (provider-result providers.work-item.recovery-classifier
      :prompt prompts.work-item.classify-blocked-recovery
      :inputs (target_design
               baseline_design
               work_item_context
               approved_plan
               implementation_state_bundle
               progress_report)
      :returns BlockedImplementationRecoveryClassification))

  (defproc classify-blocked-implementation-recovery-state
    ((target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (work_item_context_path WorkReport)
     (approved_plan_path PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> BlockedRecoveryClassification
    :effects ((uses-provider providers.work-item.recovery-classifier))
    :lowering inline
    (provider-result providers.work-item.recovery-classifier
      :prompt prompts.work-item.classify-blocked-recovery
      :inputs (target_design_path
               baseline_design_path
               work_item_context_path
               approved_plan_path
               implementation_phase_result.progress-report)
      :returns BlockedRecoveryClassification))

  (defproc normalize-blocked-recovery-route
    ((terminal_route String)
     (work_item_source String)
     (blocked_recovery_route String)
     (reason String))
    -> BlockedRecoveryDecision
    :effects ((uses-command select_lisp_frontend_blocked_recovery_route))
    :lowering inline
    (command-result select_lisp_frontend_blocked_recovery_route
      :adapter select_lisp_frontend_blocked_recovery_route
      :inputs
        ((terminal_route terminal_route)
         (work_item_source work_item_source)
         (blocked_recovery_route blocked_recovery_route)
         (reason reason))
      :returns BlockedRecoveryDecision))

  (defproc record-terminal-work-item
    ((run_state_path RunStatePath)
     (work_item_id String)
     (work_item_source String)
     (reason String)
     (item_summary_target_path WorkReportTarget)
     (item_summary_pointer_path WorkReportTarget)
     (drain_status_path StateFile))
    -> WorkItemSummary
    :effects ((uses-command record_terminal_work_item))
    :lowering inline
    (command-result record_terminal_work_item
      :adapter record_terminal_work_item
      :inputs
        ((run_state_path run_state_path)
         (work_item_id work_item_id)
         (work_item_source work_item_source)
         (reason reason)
         (item_summary_target_path item_summary_target_path)
         (item_summary_pointer_path item_summary_pointer_path)
         (drain_status_path drain_status_path))
      :returns WorkItemSummary))

  (defproc record-blocked-recovery-outcome
    ((run_state_path RunStatePath)
     (work_item_id String)
     (work_item_source String)
     (resolved_inputs ResolvedWorkItemInputs)
     (implementation_phase_result ImplementationPhaseResult)
     (recovery_route String)
     (reason BlockedRecoveryReason))
    -> WorkItemSummary
    :effects ((uses-command record_blocked_recovery_outcome))
    :lowering inline
    (command-result record_blocked_recovery_outcome
      :adapter record_blocked_recovery_outcome
      :inputs
        ((run_state_path run_state_path)
         (work_item_id work_item_id)
         (work_item_source work_item_source)
         (recovery_route recovery_route)
         (reason reason)
         (target_design_review_decision "APPROVE")
         (terminal_action "continue")
         (summary_path resolved_inputs.item_summary_target_path)
         (summary_pointer_path resolved_inputs.item_summary_pointer_path)
         (drain_status_path resolved_inputs.drain_status_path)
         (progress_report_path implementation_phase_result.progress-report)
         (implementation_state_path implementation_phase_result.execution-report)
         (architecture_bundle_path resolved_inputs.work_item_context_path)
         (plan_path resolved_inputs.plan_target_path))
      :returns WorkItemSummary))

  (defproc route-blocked-implementation
    ((target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (run_state_path RunStatePath)
     (resolved_inputs ResolvedWorkItemInputs)
     (approved_plan_path PlanDoc)
     (implementation_phase_result ImplementationPhaseResult))
    -> WorkItemResult
    :effects ((uses-provider providers.work-item.recovery-classifier)
              (uses-command select_lisp_frontend_blocked_recovery_route)
              (uses-command record_terminal_work_item)
              (uses-command record_blocked_recovery_outcome))
    :lowering private-workflow
    (let* ((classification
             (classify-blocked-implementation-recovery-state
               target_design_path
               baseline_design_path
               resolved_inputs.work_item_context_path
               approved_plan_path
               implementation_phase_result))
           (decision
             (normalize-blocked-recovery-route
               "IMPLEMENTATION_BLOCKED"
               resolved_inputs.work_item_source
               classification.blocked_recovery_route
               classification.reason)))
      (match decision
        ((TERMINAL_BLOCKED terminal)
         (let* ((recorded
                  (record-terminal-work-item
                    run_state_path
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    "implementation_blocked"
                    resolved_inputs.item_summary_target_path
                    resolved_inputs.item_summary_pointer_path
                    resolved_inputs.drain_status_path)))
           (variant WorkItemResult TERMINAL_BLOCKED
             :reason "implementation_blocked"
             :summary recorded.summary)))
        ((GAP_DESIGN_REVISION_REQUIRED recovery)
         (let* ((recorded
                  (record-blocked-recovery-outcome
                    run_state_path
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs
                    implementation_phase_result
                    "GAP_DESIGN_REVISION_REQUIRED"
                    recovery.reason)))
           (variant WorkItemResult BLOCKED_RECOVERY
             :reason "gap_design_revision_required"
             :summary recorded.summary)))
        ((TARGET_DESIGN_REVISION_REQUIRED recovery)
         (let* ((recorded
                  (record-blocked-recovery-outcome
                    run_state_path
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs
                    implementation_phase_result
                    "TARGET_DESIGN_REVISION_REQUIRED"
                    recovery.reason)))
           (variant WorkItemResult BLOCKED_RECOVERY
             :reason "target_design_revision_required"
             :summary recorded.summary)))
        ((PREREQUISITE_GAP_REQUIRED recovery)
         (let* ((recorded
                  (record-blocked-recovery-outcome
                    run_state_path
                    resolved_inputs.work_item_id
                    resolved_inputs.work_item_source
                    resolved_inputs
                    implementation_phase_result
                    "PREREQUISITE_GAP_REQUIRED"
                    recovery.reason)))
           (variant WorkItemResult BLOCKED_RECOVERY
             :reason "prerequisite_gap_required"
             :summary recorded.summary))))))

  (defproc finalize-approved-review-state
    ((run_state_path RunStatePath)
     (resolved_inputs ResolvedWorkItemInputs)
     (terminal WorkItemTerminalClassification))
    -> WorkItemResult
    :effects ((uses-command record_terminal_work_item))
    :lowering private-workflow
    (if terminal.implementation_review_exhausted
      (let* ((recorded
               (record-terminal-work-item
                 run_state_path
                 resolved_inputs.work_item_id
                 resolved_inputs.work_item_source
                 "implementation_review_exhausted"
                 resolved_inputs.item_summary_target_path
                 resolved_inputs.item_summary_pointer_path
                 resolved_inputs.drain_status_path)))
        (variant WorkItemResult TERMINAL_BLOCKED
          :reason "implementation_review_exhausted"
          :summary recorded.summary))
      (let* ((recorded
               (record-terminal-work-item
                 run_state_path
                 resolved_inputs.work_item_id
                 resolved_inputs.work_item_source
                 "complete"
                 resolved_inputs.item_summary_target_path
                 resolved_inputs.item_summary_pointer_path
                 resolved_inputs.drain_status_path)))
        (variant WorkItemResult COMPLETED
          :reason ""
          :summary recorded.summary))))

  (defproc finalize-approved-nonblocked
    ((run_state_path RunStatePath)
     (resolved_inputs ResolvedWorkItemInputs)
     (terminal WorkItemTerminalClassification))
    -> WorkItemResult
    :effects ((uses-command record_terminal_work_item))
    :lowering private-workflow
    (if terminal.plan_review_exhausted
      (let* ((recorded
               (record-terminal-work-item
                 run_state_path
                 resolved_inputs.work_item_id
                 resolved_inputs.work_item_source
                 "plan_review_exhausted"
                 resolved_inputs.item_summary_target_path
                 resolved_inputs.item_summary_pointer_path
                 resolved_inputs.drain_status_path)))
        (variant WorkItemResult TERMINAL_BLOCKED
          :reason "plan_review_exhausted"
          :summary recorded.summary))
      (finalize-approved-review-state
        run_state_path
        resolved_inputs
        terminal)))

  (defworkflow run-work-item
    ((phase-ctx PhaseCtx)
     (selection_bundle_path SelectionBundlePath)
     (manifest_path StateFileExisting)
     (architecture_bundle_path StateFile)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (progress_ledger_path ProgressLedger)
     (run_state_path RunStatePath))
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
                  (classify-work-item-terminal-state
                    approved.plan_review_decision
                    implementation.implementation-state
                    implementation.implementation-review-decision
                    resolved.work_item_source)))
           (if terminal.implementation_blocked
             (route-blocked-implementation
               target_design_path
               baseline_design_path
               run_state_path
               resolved
               approved.approved_plan_path
               implementation)
             (finalize-approved-nonblocked
               run_state_path
               resolved
               terminal))))
        ((BLOCKED blocked)
         (let* ((recorded
                  (record-terminal-work-item
                    run_state_path
                    resolved.work_item_id
                    resolved.work_item_source
                    "plan_blocked"
                    resolved.item_summary_target_path
                    resolved.item_summary_pointer_path
                    resolved.drain_status_path)))
           (variant WorkItemResult TERMINAL_BLOCKED
             :reason "plan_blocked"
             :summary recorded.summary)))
        ((EXHAUSTED exhausted)
         (let* ((recorded
                  (record-terminal-work-item
                    run_state_path
                    resolved.work_item_id
                    resolved.work_item_source
                    "plan_review_exhausted"
                    resolved.item_summary_target_path
                    resolved.item_summary_pointer_path
                    resolved.drain_status_path)))
           (variant WorkItemResult TERMINAL_BLOCKED
             :reason "plan_review_exhausted"
             :summary recorded.summary)))))))
