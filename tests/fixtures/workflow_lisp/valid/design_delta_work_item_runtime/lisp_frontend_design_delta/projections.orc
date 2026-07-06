(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/projections)
  (import std/drain :only (DrainResult))
  (import std/resource :only (BlockerClass))
  (import lisp_frontend_design_delta/types :only
    (BlockedRecoveryDecision BlockedRecoveryRoute BlockedRecoveryReason
      DesignDeltaDrainAction DrainSummaryValue DrainTerminalStatus
      ImplementationReviewDecision ImplementationState PlanReviewDecision
      SelectionBundlePath SelectionStatus WorkItemBootstrapSeed WorkItemSource
      WorkItemTerminalDecision))
  (export
    classify-work-item-terminal
    normalize-blocked-recovery-route
    project-parent-drain-terminal
    project-parent-drain-terminal-status
    project-selector-action)

  (defrecord ParentDrainTerminalStatus
    (status DrainTerminalStatus)
    (reason String))

  (defworkflow project-selector-action
    ((selection_status SelectionStatus)
     (work_item_bootstrap WorkItemBootstrapSeed)
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
          :selected_item_bootstrap work_item_bootstrap)
        (if is-design-gap
          (variant DesignDeltaDrainAction DRAFT_DESIGN_GAP
            :design_gap_bootstrap work_item_bootstrap)
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

  (defproc project-parent-drain-terminal-status
    ((result DrainResult))
    -> ParentDrainTerminalStatus
    :effects ()
    :lowering inline
    (match result
      ((EMPTY empty)
       (record ParentDrainTerminalStatus
         :status DrainTerminalStatus.DONE
         :reason ""))
      ((COMPLETED completed)
       (record ParentDrainTerminalStatus
         :status DrainTerminalStatus.DONE
         :reason ""))
      ((BLOCKED blocked)
       (let* ((is-exhausted
                (= blocked.blocker-class BlockerClass.unrecoverable_after_fix_attempt)))
         (if is-exhausted
         (record ParentDrainTerminalStatus
           :status DrainTerminalStatus.EXHAUSTED
           :reason "max_iterations_exhausted")
          (record ParentDrainTerminalStatus
            :status DrainTerminalStatus.BLOCKED
            :reason "selector_blocked"))))))

  (defproc project-parent-drain-terminal
    ((result DrainResult))
    -> lisp_frontend_design_delta/types/DrainResult
    :effects ()
    :lowering inline
    (let* ((terminal-status
             (project-parent-drain-terminal-status result))
           (drain-summary
             (record DrainSummaryValue
               :drain_status terminal-status.status
               :drain_status_reason terminal-status.reason
               :state_version "lisp_frontend_autonomous_drain_run_state/v1"))
           (is-done
             (= terminal-status.status DrainTerminalStatus.DONE))
           (is-exhausted
             (= terminal-status.status DrainTerminalStatus.EXHAUSTED)))
      (if is-done
        (variant lisp_frontend_design_delta/types/DrainResult DONE
          :drain-summary drain-summary)
        (if is-exhausted
          (variant lisp_frontend_design_delta/types/DrainResult EXHAUSTED
            :reason terminal-status.reason
            :drain-summary drain-summary)
          (variant lisp_frontend_design_delta/types/DrainResult BLOCKED
            :reason terminal-status.reason
            :drain-summary drain-summary)))))

  (defproc normalize-blocked-recovery-route
    ((work_item_source WorkItemSource)
     (blocked_recovery_route BlockedRecoveryRoute)
     (reason BlockedRecoveryReason))
    -> BlockedRecoveryDecision
    :effects ()
    :lowering inline
    (let* ((is-backlog-item
             (= work_item_source WorkItemSource.BACKLOG_ITEM))
           (is-gap-design-revision
             (= blocked_recovery_route BlockedRecoveryRoute.GAP_DESIGN_REVISION_REQUIRED))
           (is-target-design-revision
             (= blocked_recovery_route BlockedRecoveryRoute.TARGET_DESIGN_REVISION_REQUIRED))
           (is-prerequisite-gap
             (= blocked_recovery_route BlockedRecoveryRoute.PREREQUISITE_GAP_REQUIRED)))
      (if is-backlog-item
        (variant BlockedRecoveryDecision TERMINAL_BLOCKED
          :reason BlockedRecoveryReason.implementation_blocked)
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
                :reason reason))))))
))
