(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/projections)
  (import lisp_frontend_design_delta/types :only
    (BlockedRecoveryDecision BlockedRecoveryRoute BlockedRecoveryReason DesignDeltaDrainAction
      ImplementationReviewDecision ImplementationState PlanReviewDecision SelectionBundlePath SelectionStatus
      WorkItemSource WorkItemTerminalDecision))
  (export
    classify-work-item-terminal
    normalize-blocked-recovery-route
    project-selector-action)

  (defworkflow project-selector-action
    ((selection_status SelectionStatus)
     (selection_bundle_path SelectionBundlePath)
     (blocked_reason String))
    -> DesignDeltaDrainAction
    (let* ((is-selected
             (= selection_status SelectionStatus.SELECT_BACKLOG_ITEM))
           (is-design-gap
             (= selection_status SelectionStatus.DRAFT_DESIGN_GAP))
           (is-done
             (= selection_status SelectionStatus.DONE))
           (normalized-blocked-reason
             (if (= blocked_reason "")
               "selector_blocked"
               blocked_reason)))
      (if is-selected
        (variant DesignDeltaDrainAction SELECTED_ITEM
          :selected_item_selection_bundle selection_bundle_path)
        (if is-design-gap
          (variant DesignDeltaDrainAction DRAFT_DESIGN_GAP
            :design_gap_selection_bundle selection_bundle_path)
          (if is-done
            (variant DesignDeltaDrainAction DONE)
            (variant DesignDeltaDrainAction BLOCKED
              :blocked_reason normalized-blocked-reason))))))

  (defworkflow classify-work-item-terminal
    ((plan_review_decision PlanReviewDecision)
     (implementation_state ImplementationState)
     (implementation_review_decision ImplementationReviewDecision)
     (work_item_source WorkItemSource))
    -> WorkItemTerminalDecision
    (let* ((plan-revise
             (= plan_review_decision PlanReviewDecision.REVISE))
           (implementation-blocked
             (= implementation_state ImplementationState.BLOCKED))
           (implementation-approved
             (= implementation_review_decision ImplementationReviewDecision.APPROVE)))
      (if plan-revise
        (variant WorkItemTerminalDecision PLAN_REVIEW_EXHAUSTED)
        (if implementation-blocked
          (variant WorkItemTerminalDecision IMPLEMENTATION_BLOCKED)
          (if implementation-approved
            (variant WorkItemTerminalDecision COMPLETE)
            (variant WorkItemTerminalDecision IMPLEMENTATION_REVIEW_EXHAUSTED))))))

  (defworkflow normalize-blocked-recovery-route
    ((work_item_source WorkItemSource)
     (blocked_recovery_route BlockedRecoveryRoute)
     (reason BlockedRecoveryReason))
    -> BlockedRecoveryDecision
    (let* ((is-backlog-item
             (= work_item_source WorkItemSource.BACKLOG_ITEM))
           (rewrite-user-decision
             (and
               (= blocked_recovery_route BlockedRecoveryRoute.TERMINAL_BLOCKED)
               (= reason BlockedRecoveryReason.user_decision_required)))
           (is-gap-design-revision
             (= blocked_recovery_route BlockedRecoveryRoute.GAP_DESIGN_REVISION_REQUIRED))
           (is-target-design-revision
             (= blocked_recovery_route BlockedRecoveryRoute.TARGET_DESIGN_REVISION_REQUIRED))
           (is-prerequisite-gap
             (= blocked_recovery_route BlockedRecoveryRoute.PREREQUISITE_GAP_REQUIRED)))
      (if is-backlog-item
        (variant BlockedRecoveryDecision TERMINAL_BLOCKED
          :reason BlockedRecoveryReason.implementation_blocked)
        (if rewrite-user-decision
          (variant BlockedRecoveryDecision GAP_DESIGN_REVISION_REQUIRED
            :reason BlockedRecoveryReason.implementation_architecture_under_scoped)
          (if is-gap-design-revision
            (variant BlockedRecoveryDecision GAP_DESIGN_REVISION_REQUIRED
              :reason reason)
            (if is-target-design-revision
              (variant BlockedRecoveryDecision TARGET_DESIGN_REVISION_REQUIRED
                :reason reason)
              (if is-prerequisite-gap
                (variant BlockedRecoveryDecision PREREQUISITE_GAP_REQUIRED
                  :reason reason)
                (variant BlockedRecoveryDecision TERMINAL_BLOCKED
                  :reason reason))))))))
)
