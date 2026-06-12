(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule design_delta_projection_runtime)
  (import design_delta_projection_runtime_support/projections :only
    (classify-work-item-terminal normalize-blocked-recovery-route project-selector-action))
  (import design_delta_projection_runtime_support/types :only
    (BlockedRecoveryDecision BlockedRecoveryReason BlockedRecoveryRoute DesignDeltaDrainAction
      ImplementationReviewDecision ImplementationState PlanReviewDecision SelectionBundlePath
      SelectionStatus WorkItemSource WorkItemTerminalDecision))
  (export run-projection)

  (defproc project-selector-route
    ((decision DesignDeltaDrainAction)
     (fallback_bundle SelectionBundlePath))
    -> String
    :effects ()
    :lowering inline
    (match decision
      ((SELECTED_ITEM selected)
       "SELECTED_ITEM")
      ((DRAFT_DESIGN_GAP gap)
       "DRAFT_DESIGN_GAP")
      ((BLOCKED_RECOVERY blocked_recovery)
       blocked_recovery.blocked_recovery_reason)
      ((DONE done)
       "DONE")
      ((BLOCKED blocked)
       blocked.blocked_reason)
      ((EXHAUSTED exhausted)
       exhausted.exhausted_reason)))

  (defproc project-selector-bundle
    ((decision DesignDeltaDrainAction)
     (fallback_bundle SelectionBundlePath))
    -> SelectionBundlePath
    :effects ()
    :lowering inline
    (match decision
      ((SELECTED_ITEM selected)
       selected.selected_item_selection_bundle)
      ((DRAFT_DESIGN_GAP gap)
       gap.design_gap_selection_bundle)
      ((BLOCKED_RECOVERY blocked_recovery)
       blocked_recovery.blocked_recovery_selection_bundle)
      ((DONE done)
       fallback_bundle)
      ((BLOCKED blocked)
       fallback_bundle)
      ((EXHAUSTED exhausted)
       fallback_bundle)))

  (defproc project-terminal-route
    ((decision WorkItemTerminalDecision))
    -> String
    :effects ()
    :lowering inline
    (match decision
      ((COMPLETE complete)
       "COMPLETE")
      ((PLAN_REVIEW_EXHAUSTED plan_review_exhausted)
       "PLAN_REVIEW_EXHAUSTED")
      ((IMPLEMENTATION_BLOCKED implementation_blocked)
       "IMPLEMENTATION_BLOCKED")
      ((IMPLEMENTATION_REVIEW_EXHAUSTED implementation_review_exhausted)
       "IMPLEMENTATION_REVIEW_EXHAUSTED")))

  (defproc project-blocked-recovery-route
    ((decision BlockedRecoveryDecision))
    -> String
    :effects ()
    :lowering inline
    (match decision
      ((GAP_DESIGN_REVISION_REQUIRED gap)
       "GAP_DESIGN_REVISION_REQUIRED")
      ((TARGET_DESIGN_REVISION_REQUIRED target)
       "TARGET_DESIGN_REVISION_REQUIRED")
      ((PREREQUISITE_GAP_REQUIRED prerequisite)
       "PREREQUISITE_GAP_REQUIRED")
      ((TERMINAL_BLOCKED terminal)
       "TERMINAL_BLOCKED")))

  (defproc project-blocked-recovery-reason
    ((decision BlockedRecoveryDecision))
    -> BlockedRecoveryReason
    :effects ()
    :lowering inline
    (match decision
      ((GAP_DESIGN_REVISION_REQUIRED gap)
       gap.reason)
      ((TARGET_DESIGN_REVISION_REQUIRED target)
       target.reason)
      ((PREREQUISITE_GAP_REQUIRED prerequisite)
       prerequisite.reason)
      ((TERMINAL_BLOCKED terminal)
       terminal.reason)))

  (defrecord ProjectionResult
    (selector_route String)
    (terminal_route String)
    (blocked_recovery_route String)
    (blocked_recovery_reason BlockedRecoveryReason)
    (selection_bundle SelectionBundlePath))

  (defworkflow run-projection
    ((selection_bundle SelectionBundlePath)
     (selection_status SelectionStatus)
     (blocked_reason String)
     (implementation_state ImplementationState)
     (implementation_review_decision ImplementationReviewDecision)
     (work_item_source WorkItemSource)
     (blocked_recovery_route BlockedRecoveryRoute)
     (blocked_recovery_reason BlockedRecoveryReason))
    -> ProjectionResult
    (let* ((computed_blocked_reason
             (string/concat blocked_reason "-computed"))
           (selector_action
             (call project-selector-action
               :selection_status selection_status
               :selection_bundle_path selection_bundle
               :blocked_reason computed_blocked_reason))
           (terminal_decision
             (call classify-work-item-terminal
               :plan_review_decision PlanReviewDecision.APPROVE
               :implementation_state implementation_state
               :implementation_review_decision implementation_review_decision
               :work_item_source work_item_source))
           (blocked_recovery_decision
             (call normalize-blocked-recovery-route
               :work_item_source work_item_source
               :blocked_recovery_route blocked_recovery_route
               :reason blocked_recovery_reason))
           (selector_route
             (project-selector-route selector_action selection_bundle))
           (selector_bundle
             (project-selector-bundle selector_action selection_bundle))
           (terminal_route
             (project-terminal-route terminal_decision))
           (blocked_route
             (project-blocked-recovery-route blocked_recovery_decision))
           (blocked_reason_output
             (project-blocked-recovery-reason blocked_recovery_decision)))
      (record ProjectionResult
        :selector_route selector_route
        :terminal_route terminal_route
        :blocked_recovery_route blocked_route
        :blocked_recovery_reason blocked_reason_output
        :selection_bundle selector_bundle))))
