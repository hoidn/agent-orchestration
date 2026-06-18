(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/drain)
  (import lisp_frontend_design_delta/design_gap_architect :only
    (ArchitectureTargets draft-design-gap-architecture validate-design-gap-architecture))
  (import lisp_frontend_design_delta/projections :only (project-selector-action))
  (import lisp_frontend_design_delta/selector :only (select-next-work))
  (import lisp_frontend_design_delta/transitions :only
    (record-drain-terminal-outcome))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc DesignDeltaDrainAction DrainLoopTerminal DrainResult DrainState
      DrainSummaryValue DrainTerminalStatus ProgressLedger RunStatePath StateFile
      StateFileExisting SteeringDoc TargetDesignDoc WorkReport))
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
    (:publish
      ((DONE :as drain-summary)
       (BLOCKED :as drain-summary)
       (EXHAUSTED :as drain-summary)))
    (let* ((terminal
             (loop/recur
               :max 3
               :state (record DrainState
                        :iteration-count 0
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
                            :run_state run_state_path))
                        (action
                          (call project-selector-action
                            :selection_status selection.selection_status
                            :work_item_bootstrap selection.work_item_bootstrap
                            :blocked_reason selection.blocked_reason)))
                   (match action
                     ((DONE done)
                      (done
                        (variant DrainLoopTerminal DONE)))
                     ((SELECTED_ITEM selected)
                     (let* ((item
                             (call run-work-item
                               :work_item_bootstrap selected.selected_item_bootstrap
                               :steering_path steering_path
                               :target_design_path target_design_path
                               :baseline_design_path baseline_design_path
                                :progress_ledger_path progress_ledger_path)))
                        (continue
                          (record DrainState
                            :iteration-count (+ state.iteration-count 1)
                            :item-count (+ state.item-count 1)))))
                     ((DRAFT_DESIGN_GAP gap)
                     (let* ((draft
                             (call draft-design-gap-architecture
                               :steering steering_path
                               :target_design target_design_path
                               :baseline_design baseline_design_path
                               :progress_ledger progress_ledger_path
                               :design_gap_bootstrap gap.design_gap_bootstrap
                               :existing_architecture_index existing_architecture_index_path))
                             (validation
                               (call validate-design-gap-architecture
                                 :design_gap_bootstrap gap.design_gap_bootstrap)))
                        (continue
                          (record DrainState
                            :iteration-count (+ state.iteration-count 1)
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
         (let* ((recorded
                  (record-drain-terminal-outcome
                    run_state_path
                    DrainTerminalStatus.DONE
                    "")))
           (variant DrainResult DONE
             :run-state run_state_path
             :drain-summary (record lisp_frontend_design_delta/types/DrainSummaryValue
                              :drain_status recorded.drain_status
                              :drain_status_reason recorded.drain_status_reason
                              :state_version recorded.state_version))))
        ((BLOCKED blocked)
         (let* ((recorded
                  (record-drain-terminal-outcome
                    run_state_path
                    DrainTerminalStatus.BLOCKED
                    blocked.reason)))
           (variant DrainResult BLOCKED
             :reason blocked.reason
             :run-state run_state_path
             :drain-summary (record lisp_frontend_design_delta/types/DrainSummaryValue
                              :drain_status recorded.drain_status
                              :drain_status_reason recorded.drain_status_reason
                              :state_version recorded.state_version))))
        ((BLOCKED_RECOVERY recovery)
         (let* ((recorded
                  (record-drain-terminal-outcome
                    run_state_path
                    DrainTerminalStatus.BLOCKED
                    recovery.reason)))
           (variant DrainResult BLOCKED
             :reason recovery.reason
             :run-state run_state_path
             :drain-summary (record lisp_frontend_design_delta/types/DrainSummaryValue
                              :drain_status recorded.drain_status
                              :drain_status_reason recorded.drain_status_reason
                              :state_version recorded.state_version))))
        ((EXHAUSTED exhausted)
         (let* ((recorded
                  (record-drain-terminal-outcome
                    run_state_path
                    DrainTerminalStatus.EXHAUSTED
                    exhausted.reason)))
           (variant DrainResult EXHAUSTED
             :reason exhausted.reason
             :run-state run_state_path
             :drain-summary (record lisp_frontend_design_delta/types/DrainSummaryValue
                              :drain_status recorded.drain_status
                              :drain_status_reason recorded.drain_status_reason
                              :state_version recorded.state_version))))))))
