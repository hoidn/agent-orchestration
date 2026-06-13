(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/drain)
  (import lisp_frontend_design_delta/design_gap_architect :only
    (ArchitectureTargets draft-design-gap-architecture validate-design-gap-architecture))
  (import lisp_frontend_design_delta/projections :only (project-selector-action))
  (import lisp_frontend_design_delta/selector :only (select-next-work))
  (import lisp_frontend_design_delta/transitions :only
    (DrainStatusRequest drain-run-state write-drain-status))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc DesignDeltaDrainAction DrainLoopTerminal DrainResult DrainState
      DrainSummaryValue DrainTerminalStatus ProgressLedger RunStatePath StateFile
      StateFileExisting SteeringDoc TargetDesignDoc WorkReport WorkReportTarget))
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

  (defworkflow drain
    ((run RunCtx)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (manifest_path StateFileExisting)
     (progress_ledger_path ProgressLedger)
     (run_state_path RunStatePath)
     (architecture_bundle_path StateFile)
     (architecture_targets ArchitectureTargets)
     (existing_architecture_index_path WorkReport))
    -> DrainResult
    (let* ((drain-summary-path
             (__generated-relpath-seed__
               WorkReportTarget
               "artifacts/work/drain_summary.json"
               "design_delta_parent_drain_summary"))
           (terminal
             (loop/recur
               :max 3
               :state (record DrainState
                        :iteration-count 0
                        :run-state run_state_path
                        :item-count 0)
               :on-exhausted (variant DrainLoopTerminal EXHAUSTED
                               :reason "max_iterations_exhausted")
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
                      (done
                        (variant DrainLoopTerminal DONE)))
                     ((SELECTED_ITEM selected)
                     (let* ((item
                               (call run-work-item
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
                            :iteration-count (+ state.iteration-count 1)
                            :run-state state.run-state
                            :item-count (+ state.item-count 1)))))
                     ((DRAFT_DESIGN_GAP gap)
                      (let* ((draft
                               (call draft-design-gap-architecture
                                 :steering steering_path
                                 :target_design target_design_path
                                 :baseline_design baseline_design_path
                                 :progress_ledger gap.design_gap_selection_bundle
                                 :selection_bundle gap.design_gap_selection_bundle
                                 :architecture_targets architecture_targets
                                 :existing_architecture_index existing_architecture_index_path))
                             (validation
                               (call validate-design-gap-architecture
                                 :architecture_targets_bundle gap.design_gap_selection_bundle)))
                        (continue
                          (record DrainState
                            :iteration-count (+ state.iteration-count 1)
                            :run-state state.run-state
                            :item-count state.item-count))))
                     ((BLOCKED_RECOVERY recovery)
                      (done
                        (variant DrainLoopTerminal BLOCKED_RECOVERY
                          :reason recovery.blocked_recovery_reason)))
                     ((BLOCKED blocked)
                      (done
                        (variant DrainLoopTerminal BLOCKED
                          :reason blocked.blocked_reason)))
                     ((EXHAUSTED exhausted)
                      (done
                        (variant DrainLoopTerminal EXHAUSTED
                          :reason exhausted.exhausted_reason)))))))))
      (match terminal
        ((DONE done)
         (let* ((status
                  (resource-transition
                    :transition write-drain-status
                    :resource drain-run-state
                    :request (record DrainStatusRequest
                      :status "DONE"
                      :reason ""
                      :summary_path drain-summary-path)))
                (summary
                  (materialize-view drain-summary-view
                    :value (record DrainSummaryValue
                             :drain_status DrainTerminalStatus.DONE
                             :drain_status_reason ""
                             :run_state_path run_state_path
                             :summary_target drain-summary-path
                             :state_version "lisp_frontend_autonomous_drain_run_state/v1")
                    :renderer canonical-json
                    :renderer-version 1
                    :target status.summary_path
                    :returns WorkReport)))
           (variant DrainResult DONE
             :run-state run_state_path
             :drain-summary summary)))
        ((BLOCKED blocked)
         (let* ((status
                  (resource-transition
                    :transition write-drain-status
                    :resource drain-run-state
                    :request (record DrainStatusRequest
                      :status "BLOCKED"
                      :reason blocked.reason
                      :summary_path drain-summary-path)))
                (summary
                  (materialize-view drain-summary-view
                    :value (record DrainSummaryValue
                             :drain_status DrainTerminalStatus.BLOCKED
                             :drain_status_reason blocked.reason
                             :run_state_path run_state_path
                             :summary_target drain-summary-path
                             :state_version "lisp_frontend_autonomous_drain_run_state/v1")
                    :renderer canonical-json
                    :renderer-version 1
                    :target status.summary_path
                    :returns WorkReport)))
           (variant DrainResult BLOCKED
             :reason blocked.reason
             :run-state run_state_path
             :drain-summary summary)))
        ((BLOCKED_RECOVERY recovery)
         (let* ((status
                  (resource-transition
                    :transition write-drain-status
                    :resource drain-run-state
                    :request (record DrainStatusRequest
                      :status "BLOCKED"
                      :reason recovery.reason
                      :summary_path drain-summary-path)))
                (summary
                  (materialize-view drain-summary-view
                    :value (record DrainSummaryValue
                             :drain_status DrainTerminalStatus.BLOCKED
                             :drain_status_reason recovery.reason
                             :run_state_path run_state_path
                             :summary_target drain-summary-path
                             :state_version "lisp_frontend_autonomous_drain_run_state/v1")
                    :renderer canonical-json
                    :renderer-version 1
                    :target status.summary_path
                    :returns WorkReport)))
           (variant DrainResult BLOCKED
             :reason recovery.reason
             :run-state run_state_path
             :drain-summary summary)))
        ((EXHAUSTED exhausted)
         (let* ((status
                  (resource-transition
                    :transition write-drain-status
                    :resource drain-run-state
                    :request (record DrainStatusRequest
                      :status "EXHAUSTED"
                      :reason exhausted.reason
                      :summary_path drain-summary-path)))
                (summary
                  (materialize-view drain-summary-view
                    :value (record DrainSummaryValue
                             :drain_status DrainTerminalStatus.EXHAUSTED
                             :drain_status_reason exhausted.reason
                             :run_state_path run_state_path
                             :summary_target drain-summary-path
                             :state_version "lisp_frontend_autonomous_drain_run_state/v1")
                    :renderer canonical-json
                    :renderer-version 1
                    :target status.summary_path
                    :returns WorkReport)))
           (variant DrainResult EXHAUSTED
             :reason exhausted.reason
             :run-state run_state_path
             :drain-summary summary)))))))
