(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/stdlib_adapters)
  (import std/resource :only (BlockerClass))
  (import lisp_frontend_design_delta/design_gap_architect :only
    (draft-design-gap-architecture-stdlib validate-design-gap-architecture-stdlib))
  (import lisp_frontend_design_delta/selector :only (select-next-work))
  (import lisp_frontend_design_delta/transitions :only (record-design-gap-progress))
  (import lisp_frontend_design_delta/types :only
    (ArchitectureValidationResult BlockedRecoveryReason DesignDeltaDrainCtx
      DesignDeltaGapPayload DesignDeltaSelectedItemPayload DesignDeltaSelectionResult
      DrainSummaryValue))
  (export
    DesignDeltaGapResult
    project-blocker-class-from-reason
    select-next-work-stdlib
    draft-design-gap-stdlib)

  (defunion DesignDeltaGapResult
    (CONTINUE)
    (BLOCKED
      (progress-report-path std/resource/WorkReport)
      (blocker-class std/resource/BlockerClass)))

  (defworkflow select-next-work-stdlib
    ((ctx DesignDeltaDrainCtx))
    -> DesignDeltaSelectionResult
    (let* ((selection
             (call select-next-work
               :ctx ctx))
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
               :progress_ledger_path ctx.progress_ledger_path))
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
            (variant DesignDeltaSelectionResult EMPTY)
            (variant DesignDeltaSelectionResult BLOCKED
              :reason selection.blocked_reason))))))

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
             validation.work_item_bundle_path))
      (if (= validation.architecture_validation_status "VALID")
        (let* ((recorded-progress
                 (record-design-gap-progress
                   gap.work_item_id
                   gap.architecture_path
                   gap.plan_target_path
                   ArchitectureValidationResult.VALID)))
          (variant DesignDeltaGapResult CONTINUE))
        (if (= validation.architecture_validation_status "BLOCKED")
          (variant DesignDeltaGapResult BLOCKED
            :progress-report-path blocked-progress-report
            :blocker-class BlockerClass.roadmap_conflict)
          (variant DesignDeltaGapResult BLOCKED
            :progress-report-path blocked-progress-report
            :blocker-class BlockerClass.unrecoverable_after_fix_attempt)))))

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
              BlockerClass.roadmap_conflict)))))))
