(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule design_delta_projection_runtime_support/projections)
  (import design_delta_projection_runtime_support/types :only
    (BlockedRecoveryDecision BlockedRecoveryRoute BlockedRecoveryReason DesignDeltaDrainAction
      ImplementationReviewDecision ImplementationState PlanReviewDecision SelectionBundlePath SelectionStatus
      WorkItemSource WorkItemTerminalDecision))
  (export
    classify-work-item-terminal
    normalize-blocked-recovery-route
    project-selector-action)

  (defworkflow project-selector-action-blocked
    ((blocked_reason String))
    -> DesignDeltaDrainAction
    (let* ((use-default-reason
             (= blocked_reason "")))
      (if use-default-reason
        (variant DesignDeltaDrainAction BLOCKED
          :blocked_reason "selector_blocked")
        (variant DesignDeltaDrainAction BLOCKED
          :blocked_reason blocked_reason))))

  (defworkflow project-selector-action-after-gap
    ((selection_status SelectionStatus)
     (blocked_reason String))
    -> DesignDeltaDrainAction
    (let* ((is-done
             (= selection_status SelectionStatus.DONE)))
      (if is-done
        (variant DesignDeltaDrainAction DONE)
        (call project-selector-action-blocked
          :blocked_reason blocked_reason))))

  (defworkflow project-selector-action-after-selected
    ((selection_status SelectionStatus)
     (selection_bundle_path SelectionBundlePath)
     (blocked_reason String))
    -> DesignDeltaDrainAction
    (let* ((is-design-gap
             (= selection_status SelectionStatus.DRAFT_DESIGN_GAP)))
      (if is-design-gap
        (variant DesignDeltaDrainAction DRAFT_DESIGN_GAP
          :design_gap_selection_bundle selection_bundle_path)
        (call project-selector-action-after-gap
          :selection_status selection_status
          :blocked_reason blocked_reason))))

  (defworkflow project-selector-action
    ((selection_status SelectionStatus)
     (selection_bundle_path SelectionBundlePath)
     (blocked_reason String))
    -> DesignDeltaDrainAction
    (let* ((is-selected
             (= selection_status SelectionStatus.SELECT_BACKLOG_ITEM)))
      (if is-selected
        (variant DesignDeltaDrainAction SELECTED_ITEM
          :selected_item_selection_bundle selection_bundle_path)
        (call project-selector-action-after-selected
          :selection_status selection_status
          :selection_bundle_path selection_bundle_path
          :blocked_reason blocked_reason))))

  (defworkflow classify-work-item-terminal-after-plan
    ((implementation_state ImplementationState)
     (implementation_review_decision ImplementationReviewDecision)
     (work_item_source WorkItemSource))
    -> WorkItemTerminalDecision
    (let* ((implementation-blocked
             (= implementation_state ImplementationState.BLOCKED)))
      (if implementation-blocked
        (variant WorkItemTerminalDecision IMPLEMENTATION_BLOCKED)
        (call classify-work-item-terminal-after-implementation
          :implementation_review_decision implementation_review_decision
          :work_item_source work_item_source))))

  (defworkflow classify-work-item-terminal-after-implementation
    ((implementation_review_decision ImplementationReviewDecision)
     (work_item_source WorkItemSource))
    -> WorkItemTerminalDecision
    (let* ((implementation-approved
             (= implementation_review_decision ImplementationReviewDecision.APPROVE)))
      (if implementation-approved
        (variant WorkItemTerminalDecision COMPLETE)
        (variant WorkItemTerminalDecision IMPLEMENTATION_REVIEW_EXHAUSTED))))

  (defworkflow classify-work-item-terminal
    ((plan_review_decision PlanReviewDecision)
     (implementation_state ImplementationState)
     (implementation_review_decision ImplementationReviewDecision)
     (work_item_source WorkItemSource))
    -> WorkItemTerminalDecision
    (let* ((plan-revise
             (= plan_review_decision PlanReviewDecision.REVISE)))
      (if plan-revise
        (variant WorkItemTerminalDecision PLAN_REVIEW_EXHAUSTED)
        (call classify-work-item-terminal-after-plan
          :implementation_state implementation_state
          :implementation_review_decision implementation_review_decision
          :work_item_source work_item_source))))

  (defworkflow normalize-design-gap-blocked-recovery-route-after-gap
    ((blocked_recovery_route BlockedRecoveryRoute)
     (reason BlockedRecoveryReason))
    -> BlockedRecoveryDecision
    (let* ((is-target-design-revision
             (= blocked_recovery_route BlockedRecoveryRoute.TARGET_DESIGN_REVISION_REQUIRED)))
      (if is-target-design-revision
        (variant BlockedRecoveryDecision TARGET_DESIGN_REVISION_REQUIRED
          :reason reason)
        (call normalize-design-gap-blocked-recovery-route-after-target
          :blocked_recovery_route blocked_recovery_route
          :reason reason))))

  (defworkflow normalize-design-gap-blocked-recovery-route-after-target
    ((blocked_recovery_route BlockedRecoveryRoute)
     (reason BlockedRecoveryReason))
    -> BlockedRecoveryDecision
    (let* ((is-prerequisite-gap
             (= blocked_recovery_route BlockedRecoveryRoute.PREREQUISITE_GAP_REQUIRED)))
      (if is-prerequisite-gap
        (variant BlockedRecoveryDecision PREREQUISITE_GAP_REQUIRED
          :reason reason)
        (variant BlockedRecoveryDecision TERMINAL_BLOCKED
          :reason reason))))

  (defworkflow normalize-design-gap-blocked-recovery-route-after-rewrite
    ((blocked_recovery_route BlockedRecoveryRoute)
     (reason BlockedRecoveryReason))
    -> BlockedRecoveryDecision
    (let* ((is-gap-design-revision
             (= blocked_recovery_route BlockedRecoveryRoute.GAP_DESIGN_REVISION_REQUIRED)))
      (if is-gap-design-revision
        (variant BlockedRecoveryDecision GAP_DESIGN_REVISION_REQUIRED
          :reason reason)
        (call normalize-design-gap-blocked-recovery-route-after-gap
          :blocked_recovery_route blocked_recovery_route
          :reason reason))))

  (defworkflow normalize-design-gap-blocked-recovery-route
    ((blocked_recovery_route BlockedRecoveryRoute)
     (reason BlockedRecoveryReason))
    -> BlockedRecoveryDecision
    (call normalize-design-gap-blocked-recovery-route-after-rewrite
      :blocked_recovery_route blocked_recovery_route
      :reason reason))

  (defworkflow normalize-blocked-recovery-route
    ((work_item_source WorkItemSource)
     (blocked_recovery_route BlockedRecoveryRoute)
     (reason BlockedRecoveryReason))
    -> BlockedRecoveryDecision
    (let* ((is-backlog-item
             (= work_item_source WorkItemSource.BACKLOG_ITEM)))
      (if is-backlog-item
        (variant BlockedRecoveryDecision TERMINAL_BLOCKED
          :reason BlockedRecoveryReason.implementation_blocked)
        (call normalize-design-gap-blocked-recovery-route
          :blocked_recovery_route blocked_recovery_route
          :reason reason)))))
