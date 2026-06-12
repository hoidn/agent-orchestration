(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule design_delta_projection_runtime_support/types)
  (export
    BlockedRecoveryDecision
    BlockedRecoveryReason
    BlockedRecoveryRoute
    DesignDeltaDrainAction
    ImplementationReviewDecision
    ImplementationState
    PlanReviewDecision
    SelectionBundlePath
    SelectionStatus
    WorkItemSource
    WorkItemTerminalDecision)

  (defpath SelectionBundlePath
    :kind relpath
    :under "state"
    :must-exist true)

  (defenum SelectionStatus
    SELECT_BACKLOG_ITEM
    DRAFT_DESIGN_GAP
    DONE
    BLOCKED)

  (defenum PlanReviewDecision
    APPROVE
    REVISE)

  (defenum ImplementationState
    COMPLETED
    BLOCKED)

  (defenum ImplementationReviewDecision
    APPROVE
    REVISE
    NOT_APPLICABLE)

  (defenum WorkItemSource
    BACKLOG_ITEM
    DESIGN_GAP)

  (defenum BlockedRecoveryRoute
    GAP_DESIGN_REVISION_REQUIRED
    TARGET_DESIGN_REVISION_REQUIRED
    PREREQUISITE_GAP_REQUIRED
    TERMINAL_BLOCKED)

  (defenum BlockedRecoveryReason
    not_blocked
    implementation_blocked
    implementation_architecture_under_scoped
    target_design_contract_gap
    prerequisite_gap_required
    true_external_dependency
    user_decision_required
    unsupported_blocker)

  (defunion DesignDeltaDrainAction
    (SELECTED_ITEM
      (selected_item_selection_bundle SelectionBundlePath))
    (DRAFT_DESIGN_GAP
      (design_gap_selection_bundle SelectionBundlePath))
    (BLOCKED_RECOVERY
      (blocked_recovery_reason String)
      (blocked_recovery_selection_bundle SelectionBundlePath))
    (DONE)
    (BLOCKED
      (blocked_reason String))
    (EXHAUSTED
      (exhausted_reason String)))

  (defunion WorkItemTerminalDecision
    (COMPLETE)
    (PLAN_REVIEW_EXHAUSTED)
    (IMPLEMENTATION_BLOCKED)
    (IMPLEMENTATION_REVIEW_EXHAUSTED))

  (defunion BlockedRecoveryDecision
    (GAP_DESIGN_REVISION_REQUIRED
      (reason BlockedRecoveryReason))
    (TARGET_DESIGN_REVISION_REQUIRED
      (reason BlockedRecoveryReason))
    (PREREQUISITE_GAP_REQUIRED
      (reason BlockedRecoveryReason))
    (TERMINAL_BLOCKED
      (reason BlockedRecoveryReason))))
