(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/drain)
  (import lisp_frontend_design_delta/design_gap_architect :only
    (ArchitectureTargets ArchitectureValidationBundleTarget CommandAdapterContractDoc
      DraftBundleTarget draft-design-gap-architecture validate-design-gap-architecture))
  (import lisp_frontend_design_delta/projections :only (project-selector-action))
  (import lisp_frontend_design_delta/selector :only
    (select-next-work))
  (import lisp_frontend_design_delta/transitions :only
    (drain-run-state write-drain-status))
  (import lisp_frontend_design_delta/types :only
    (ArtifactWorkPath BaselineDesignDoc DesignDeltaDrainAction DrainIterationStatus DrainResult
      DrainState PlanDraftResult ProgressLedger RunStatePath StateFile StateFileExisting SteeringDoc
      TargetDesignDoc WorkItemResult WorkReport WorkReportTarget))
  (import lisp_frontend_design_delta/work_item :only (run-work-item))
  (export drain)

  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord DrainStatusUpdate
    (run_state RunStatePath)
    (summary WorkReport))

  (defrecord DrainSummary
    (summary WorkReport))

  (defrecord SelectorInputs
    (steering SteeringDoc)
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (manifest StateFileExisting)
    (progress_ledger ProgressLedger)
    (run_state RunStatePath))

  (defrecord DrainCtx
    (run RunCtx)
    (state-root Path.state-root)
    (manifest StateFileExisting)
    (ledger ProgressLedger)
    (phase-ctx PhaseCtx)
    (steering SteeringDoc)
    (target-design TargetDesignDoc)
    (baseline-design BaselineDesignDoc)
    (architecture-bundle StateFile)
    (command-adapter-contract CommandAdapterContractDoc)
    (selection-bundle-report WorkReport)
    (architecture-targets ArchitectureTargets)
    (existing-architecture-index WorkReport)
    (draft-bundle-target DraftBundleTarget)
    (architecture-validation-bundle-target ArchitectureValidationBundleTarget)
    (drain-summary-target WorkReportTarget)
    (run-state RunStatePath))

  (defproc write-drain-status
    ((run_state_path RunStatePath)
     (status String)
     (reason String)
     (summary_path WorkReportTarget))
    -> DrainStatusUpdate
    :effects ((uses-command write_lisp_frontend_drain_status))
    :lowering inline
    (command-result write_lisp_frontend_drain_status
      :adapter write_lisp_frontend_drain_status
      :inputs
        ((run_state_path run_state_path)
         (status status)
         (reason reason)
         (summary_path summary_path))
      :returns DrainStatusUpdate))

  (defproc finalize-drain-summary
    ((run_state_path RunStatePath)
     (drain_status String)
     (summary_path WorkReportTarget)
     (state_root Path.state-root))
    -> DrainSummary
    :effects ((uses-command finalize_lisp_frontend_drain_summary))
    :lowering inline
    (command-result finalize_lisp_frontend_drain_summary
      :adapter finalize_lisp_frontend_drain_summary
      :inputs
        ((run_state_path run_state_path)
         (drain_status drain_status)
         (summary_path summary_path)
         (state_root state_root))
      :returns DrainSummary))

  (defworkflow drain
    ((phase-ctx PhaseCtx)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (manifest_path StateFileExisting)
     (progress_ledger_path ProgressLedger)
     (run_state_path RunStatePath)
     (architecture_bundle_path StateFile)
     (command_adapter_contract_path CommandAdapterContractDoc)
     (selection_bundle_report_path WorkReport)
     (architecture_targets ArchitectureTargets)
     (existing_architecture_index_path WorkReport)
     (draft_bundle_target_path DraftBundleTarget)
     (architecture_validation_bundle_target_path ArchitectureValidationBundleTarget)
     (drain_summary_target_path WorkReportTarget))
    -> DrainResult
    (loop/recur
      :max 3
      :state (record DrainState
               :status "CONTINUE"
               :iteration-count 0
               :run-state run_state_path
               :item-count 0
               :last-summary selection_bundle_report_path
               :last-progress selection_bundle_report_path
               :blocker-reason ""
               :recovery-reason "")
      :on-exhausted (variant DrainResult EXHAUSTED
                      :reason "max_iterations_exhausted"
                      :run-state state.run-state
                      :drain-summary state.last-summary)
      (fn (state)
        (let* ((selection
               (call select-next-work
                   :steering steering_path
                   :target_design target_design_path
                   :baseline_design baseline_design_path
                   :manifest manifest_path
                   :progress_ledger progress_ledger_path
                   :run_state state.run-state))
               (action
                 (call project-selector-action
                   :selection_status selection.selection_status
                   :selection_bundle_path selection.selection_bundle_path
                   :blocked_reason selection.blocked_reason)))
          (match action
            ((DONE done)
             (let* ((status
                      (command-result write_lisp_frontend_drain_status
                        :adapter write_lisp_frontend_drain_status
                        :inputs
                          ((run_state_path state.run-state)
                           (status "DONE")
                           (reason "")
                           (summary_path drain_summary_target_path))
                        :returns DrainStatusUpdate))
                    (summary
                      (command-result finalize_lisp_frontend_drain_summary
                        :adapter finalize_lisp_frontend_drain_summary
                        :inputs
                          ((run_state_path state.run-state)
                           (drain_status "DONE")
                           (summary_path drain_summary_target_path)
                           (state_root phase-ctx.state-root))
                        :returns DrainSummary)))
               (done
                 (variant DrainResult DONE
                        :run-state state.run-state
                        :drain-summary summary.summary))))
            ((SELECTED_ITEM selected)
             (let* ((item
                      (call run-work-item
                        :phase-ctx phase-ctx
                        :selection_bundle_path selected.selected_item_selection_bundle
                        :manifest_path manifest_path
                        :architecture_bundle_path architecture_bundle_path
                        :steering_path steering_path
                        :target_design_path target_design_path
                        :baseline_design_path baseline_design_path
                        :progress_ledger_path progress_ledger_path
                        :run_state_path state.run-state)))
               (continue
                 (record DrainState
                   :status "CONTINUE"
                   :iteration-count state.iteration-count
                   :run-state state.run-state
                   :item-count state.item-count
                   :last-summary selection_bundle_report_path
                   :last-progress selection_bundle_report_path
                   :blocker-reason ""
                   :recovery-reason ""))))
            ((DRAFT_DESIGN_GAP gap)
             (let* ((draft
                      (call draft-design-gap-architecture
                        :steering steering_path
                        :target_design target_design_path
                        :baseline_design baseline_design_path
                        :command_adapter_contract command_adapter_contract_path
                        :progress_ledger gap.design_gap_selection_bundle
                        :selection_bundle gap.design_gap_selection_bundle
                        :architecture_targets architecture_targets
                        :existing_architecture_index existing_architecture_index_path
                        :draft_bundle_target draft_bundle_target_path))
                    (validation
                      (call validate-design-gap-architecture
                        :draft_bundle draft_bundle_target_path
                        :architecture_targets_bundle gap.design_gap_selection_bundle
                        :validation_bundle_target architecture_validation_bundle_target_path)))
               (continue
                 (record DrainState
                   :status "CONTINUE"
                   :iteration-count state.iteration-count
                   :run-state state.run-state
                   :item-count state.item-count
                   :last-summary selection_bundle_report_path
                   :last-progress selection_bundle_report_path
                   :blocker-reason draft.draft_status
                   :recovery-reason validation.architecture_validation_status))))
            ((BLOCKED_RECOVERY recovery)
             (let* ((status
                      (command-result write_lisp_frontend_drain_status
                        :adapter write_lisp_frontend_drain_status
                        :inputs
                          ((run_state_path state.run-state)
                           (status "BLOCKED")
                           (reason recovery.blocked_recovery_reason)
                           (summary_path drain_summary_target_path))
                        :returns DrainStatusUpdate))
                    (summary
                      (command-result finalize_lisp_frontend_drain_summary
                        :adapter finalize_lisp_frontend_drain_summary
                        :inputs
                          ((run_state_path state.run-state)
                           (drain_status "BLOCKED")
                           (summary_path drain_summary_target_path)
                           (state_root phase-ctx.state-root))
                        :returns DrainSummary)))
               (done
                 (variant DrainResult BLOCKED
                   :reason recovery.blocked_recovery_reason
                   :run-state state.run-state
                   :drain-summary summary.summary))))
            ((BLOCKED blocked)
             (let* ((status
                      (command-result write_lisp_frontend_drain_status
                        :adapter write_lisp_frontend_drain_status
                        :inputs
                          ((run_state_path state.run-state)
                           (status "BLOCKED")
                           (reason blocked.blocked_reason)
                           (summary_path drain_summary_target_path))
                        :returns DrainStatusUpdate))
                    (summary
                      (command-result finalize_lisp_frontend_drain_summary
                        :adapter finalize_lisp_frontend_drain_summary
                        :inputs
                          ((run_state_path state.run-state)
                           (drain_status "BLOCKED")
                           (summary_path drain_summary_target_path)
                           (state_root phase-ctx.state-root))
                        :returns DrainSummary)))
               (done
                 (variant DrainResult BLOCKED
                   :reason blocked.blocked_reason
                   :run-state state.run-state
                   :drain-summary summary.summary))))
            ((EXHAUSTED exhausted)
             (done
               (variant DrainResult EXHAUSTED
                 :reason exhausted.exhausted_reason
                 :run-state state.run-state
                 :drain-summary state.last-summary)))))))))
