(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/stdlib_adapters)
  (import std/drain :only (DrainResult))
  (import std/resource :only
    (BlockerClass StateExisting WorkReport))
  (import lisp_frontend_design_delta/design_gap_architect :only
    (draft-design-gap-architecture-stdlib validate-design-gap-architecture-stdlib))
  (import lisp_frontend_design_delta/selector :only (select-next-work))
  (import lisp_frontend_design_delta/transitions :only
    (record-design-gap-progress record-drain-terminal-outcome-stdlib))
  (import lisp_frontend_design_delta/types :only
    (ArchitectureValidationResult BlockedRecoveryReason DesignDeltaDrainCtx
      DesignDeltaGapPayload DesignDeltaSelectedItemPayload DesignDeltaSelectionResult
      DrainSummaryValue))
  (export
    DesignDeltaGapResult
    project-blocked-implementation-compat
    project-blocker-class-from-reason
    project-completed-implementation-compat
    project-drain-result-compat
    project-plan-approved-compat
    project-plan-blocked-compat
    project-selected-item-compat
    QueueTransitionCompat
    RoadmapCompat
    SelectedItemImplementationCompat
    SelectedItemPlanCompat
    SelectedItemStdlibCompat
    select-next-work-stdlib
    draft-design-gap-stdlib)

  (defunion DesignDeltaGapResult
    (CONTINUE
      (run-state StateExisting))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))

  (defrecord SelectedItemStdlibCompat
    (item-id String)
    (is-active Bool)
    (final-plan-gate-state StateExisting))

  (defrecord QueueTransitionCompat
    (transition-id String))

  (defrecord RoadmapCompat
    (status String))

  (defunion SelectedItemPlanCompat
    (APPROVED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))

  (defunion SelectedItemImplementationCompat
    (COMPLETED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))

  (defworkflow select-next-work-stdlib
    ((ctx DesignDeltaDrainCtx))
    -> DesignDeltaSelectionResult
    (let* ((selection
             (call select-next-work
               :steering ctx.steering_path
               :target_design ctx.target_design_path
               :baseline_design ctx.baseline_design_path
               :manifest ctx.manifest
               :progress_ledger ctx.progress_ledger_path
               :run_state ctx.run_state_path))
           (selected-payload
             (record DesignDeltaSelectedItemPayload
               :item-id selection.work_item_bootstrap.work_item_id
               :item-state-root ctx.state-root
               :work_item_bootstrap (record lisp_frontend_design_delta/types/WorkItemBootstrapSeed
                                      :work_item_source selection.work_item_bootstrap.work_item_source
                                      :work_item_id selection.work_item_bootstrap.work_item_id
                                      :plan_target_path selection.work_item_bootstrap.plan_target_path
                                      :check_commands selection.work_item_bootstrap.check_commands
                                      :architecture_path selection.work_item_bootstrap.architecture_path)
               :steering_path ctx.steering_path
               :target_design_path ctx.target_design_path
               :baseline_design_path ctx.baseline_design_path
               :progress_ledger_path ctx.progress_ledger_path
               :run_state_path ctx.run_state_path))
           (design-gap-payload
             (record DesignDeltaGapPayload
               :work_item_id selection.work_item_bootstrap.work_item_id
               :plan_target_path selection.work_item_bootstrap.plan_target_path
               :architecture_path selection.work_item_bootstrap.architecture_path)))
      (if selection.is_selected
        (variant DesignDeltaSelectionResult SELECTED
          :selection selected-payload)
        (if selection.is_design_gap
          (variant DesignDeltaSelectionResult GAP
            :gap design-gap-payload)
          (if selection.is_done
            (variant DesignDeltaSelectionResult EMPTY
              :run-state ctx.run_state_path)
            (variant DesignDeltaSelectionResult BLOCKED
              :reason selection.blocked_reason
              :run-state ctx.run_state_path))))))

  (defworkflow draft-design-gap-stdlib
    ((ctx DesignDeltaDrainCtx)
     (gap DesignDeltaGapPayload))
    -> DesignDeltaGapResult
    (let* ((draft
             (call draft-design-gap-architecture-stdlib
               :steering ctx.steering_path
               :target_design ctx.target_design_path
               :baseline_design ctx.baseline_design_path
               :progress_ledger ctx.progress_ledger_path
               :gap gap
               :existing_architecture_index ctx.existing_architecture_index_path))
           (validation
             (call validate-design-gap-architecture-stdlib
               :gap gap))
           (blocked-progress-report
             validation.work_item_bundle_path)
           (continued-run-state
             ctx.run_state_path))
      (if (= validation.architecture_validation_status "VALID")
        (let* ((recorded-progress
                 (record-design-gap-progress
                   ctx.run_state_path
                   gap.work_item_id
                   gap.architecture_path
                   gap.plan_target_path
                   ArchitectureValidationResult.VALID)))
          (variant DesignDeltaGapResult CONTINUE
            :run-state continued-run-state))
        (if (= validation.architecture_validation_status "BLOCKED")
          (variant DesignDeltaGapResult BLOCKED
            :progress-report-path blocked-progress-report
            :blocker-class BlockerClass.roadmap_conflict)
          (variant DesignDeltaGapResult BLOCKED
            :progress-report-path blocked-progress-report
            :blocker-class BlockerClass.unrecoverable_after_fix_attempt)))))

  (defproc project-selected-item-compat
    ((selection DesignDeltaSelectedItemPayload))
    -> SelectedItemStdlibCompat
    :effects ()
    :lowering inline
    (record SelectedItemStdlibCompat
      :item-id selection.item-id
      :is-active false
      :final-plan-gate-state selection.run_state_path))

  (defproc project-plan-approved-compat
    ((execution-report-path WorkReport))
    -> SelectedItemPlanCompat
    :effects ()
    :lowering inline
    (variant SelectedItemPlanCompat APPROVED
      :execution-report-path execution-report-path))

  (defproc project-plan-blocked-compat
    ((progress-report-path WorkReport)
     (blocker-class BlockerClass))
    -> SelectedItemPlanCompat
    :effects ()
    :lowering inline
    (variant SelectedItemPlanCompat BLOCKED
      :progress-report-path progress-report-path
      :blocker-class blocker-class))

  (defproc project-completed-implementation-compat
    ((execution-report-path WorkReport))
    -> SelectedItemImplementationCompat
    :effects ()
    :lowering inline
    (variant SelectedItemImplementationCompat COMPLETED
      :execution-report-path execution-report-path))

  (defproc project-blocked-implementation-compat
    ((progress-report-path WorkReport)
     (blocker-class BlockerClass))
    -> SelectedItemImplementationCompat
    :effects ()
    :lowering inline
    (variant SelectedItemImplementationCompat BLOCKED
      :progress-report-path progress-report-path
      :blocker-class blocker-class))

  (defproc project-blocker-class-from-reason
    ((reason BlockedRecoveryReason))
    -> BlockerClass
    :effects ()
    :lowering inline
    (let* ((is-external
             (= reason BlockedRecoveryReason.true_external_dependency))
           (is-prerequisite-gap
             (= reason BlockedRecoveryReason.prerequisite_gap_required))
           (is-not-blocked
             (= reason BlockedRecoveryReason.not_blocked))
           (is-unsupported
             (= reason BlockedRecoveryReason.unsupported_blocker)))
      (if is-external
        BlockerClass.external_dependency_outside_authority
        (if is-prerequisite-gap
          BlockerClass.missing_resource
          (if is-not-blocked
            BlockerClass.missing_resource
            (if is-unsupported
              BlockerClass.unrecoverable_after_fix_attempt
              BlockerClass.roadmap_conflict))))))

  (defproc project-drain-result-compat
    ((run_state_path StateExisting)
     (result DrainResult))
    -> lisp_frontend_design_delta/types/DrainResult
    :effects ()
    :lowering inline
    (match result
      ((EMPTY empty)
       (let* ((recorded
                (record-drain-terminal-outcome-stdlib
                  run_state_path
                  lisp_frontend_design_delta/types/DrainTerminalStatus.DONE
                  "")))
         (variant lisp_frontend_design_delta/types/DrainResult DONE
           :run-state run_state_path
           :drain-summary (record DrainSummaryValue
                            :drain_status recorded.drain_status
                            :drain_status_reason recorded.drain_status_reason
                            :state_version recorded.state_version))))
      ((COMPLETED completed)
       (let* ((recorded
                (record-drain-terminal-outcome-stdlib
                  run_state_path
                  lisp_frontend_design_delta/types/DrainTerminalStatus.DONE
                  "")))
         (variant lisp_frontend_design_delta/types/DrainResult DONE
           :run-state run_state_path
           :drain-summary (record DrainSummaryValue
                            :drain_status recorded.drain_status
                            :drain_status_reason recorded.drain_status_reason
                            :state_version recorded.state_version))))
      ((BLOCKED blocked)
       (let* ((is-exhausted
                (= blocked.blocker-class BlockerClass.unrecoverable_after_fix_attempt)))
         (if is-exhausted
           (let* ((recorded
                    (record-drain-terminal-outcome-stdlib
                      run_state_path
                      lisp_frontend_design_delta/types/DrainTerminalStatus.EXHAUSTED
                      "max_iterations_exhausted")))
             (variant lisp_frontend_design_delta/types/DrainResult EXHAUSTED
               :reason "max_iterations_exhausted"
               :run-state run_state_path
               :drain-summary (record DrainSummaryValue
                                :drain_status recorded.drain_status
                                :drain_status_reason recorded.drain_status_reason
                                :state_version recorded.state_version)))
           (let* ((recorded
                    (record-drain-terminal-outcome-stdlib
                      run_state_path
                      lisp_frontend_design_delta/types/DrainTerminalStatus.BLOCKED
                      "selector_blocked")))
             (variant lisp_frontend_design_delta/types/DrainResult BLOCKED
               :reason "selector_blocked"
               :run-state run_state_path
               :drain-summary (record DrainSummaryValue
                                :drain_status recorded.drain_status
                                :drain_status_reason recorded.drain_status_reason
                                :state_version recorded.state_version)))))))))
