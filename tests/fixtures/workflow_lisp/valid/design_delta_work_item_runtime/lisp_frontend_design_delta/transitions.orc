(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/transitions)
  (import lisp_frontend_design_delta/types :only
    (BlockedRecoveryReason BlockedRecoveryRoute DrainSummaryValue DrainTerminalStatus RunStatePath
      WorkItemContextValue WorkItemSource WorkItemSummaryValue WorkItemTerminalReason
      WorkItemTerminalRoute WorkReport WorkReportTarget))
  (export
    apply-drain-status-transition
    BlockedRecoveryOutcomeRequest
    BlockedRecoveryOutcomeAudit
    BlockedRecoveryOutcomeResult
    DrainStatusAudit
    DrainStatusRequest
    DrainStatusResult
    DrainRunStateRecord
    record-work-item-blocked-recovery-summary
    record-drain-terminal-outcome
    record-work-item-terminal-outcome
    TerminalOutcomeAudit
    TerminalOutcomeResult
    TerminalWorkItemRequest
    drain-run-state
    emit-drain-status-transition-audit
    write-drain-status-runtime-native
    write-drain-status
    record-terminal-work-item
    record-blocked-recovery-outcome)

  (defrecord DrainRunStateRecord
    (drain_status DrainTerminalStatus)
    (drain_status_reason String)
    (drain_status_summary WorkReportTarget)
    (terminal_reason WorkItemTerminalReason)
    (terminal_summary WorkReportTarget)
    (blocked_recovery_reason BlockedRecoveryReason)
    (blocked_recovery_summary WorkReportTarget))

  (defrecord DrainStatusRequest
    (status DrainTerminalStatus)
    (reason String)
    (summary_path WorkReportTarget))

  (defrecord DrainStatusResult
    (status DrainTerminalStatus)
    (summary_path WorkReportTarget))

  (defrecord DrainStatusAudit
    (status DrainTerminalStatus)
    (summary_path WorkReportTarget))

  (defrecord TerminalWorkItemRequest
    (work_item_id String)
    (work_item_source WorkItemSource)
    (terminal_route WorkItemTerminalRoute)
    (reason WorkItemTerminalReason)
    (summary_path WorkReportTarget))

  (defrecord BlockedRecoveryOutcomeRequest
    (work_item_id String)
    (work_item_source WorkItemSource)
    (recovery_route BlockedRecoveryRoute)
    (reason BlockedRecoveryReason)
    (summary_path WorkReportTarget))

  (defrecord TerminalOutcomeResult
    (reason WorkItemTerminalReason)
    (summary_path WorkReportTarget))

  (defrecord BlockedRecoveryOutcomeResult
    (reason BlockedRecoveryReason)
    (summary_path WorkReportTarget))

  (defrecord TerminalOutcomeAudit
    (reason WorkItemTerminalReason)
    (summary_path WorkReportTarget))

  (defrecord BlockedRecoveryOutcomeAudit
    (reason BlockedRecoveryReason)
    (summary_path WorkReportTarget))

  (defrecord RenderedSummary
    (summary WorkReport))

  (defresource drain-run-state
    :state-type lisp_frontend_design_delta/transitions/DrainRunStateRecord
    :backing (bridge run_state_path))

  (deftransition write-drain-status-runtime-native
    :resource drain-run-state
    :request-type lisp_frontend_design_delta/transitions/DrainStatusRequest
    :result-type lisp_frontend_design_delta/transitions/DrainStatusResult
    :preconditions ()
    :updates ((set-field drain_status request.status)
              (set-field drain_status_reason request.reason)
              (set-field drain_status_summary request.summary_path))
    :write-set (drain_status drain_status_reason drain_status_summary)
    :idempotency-fields (status reason summary_path)
    :result (record lisp_frontend_design_delta/transitions/DrainStatusResult
      :status request.status
      :summary_path request.summary_path)
    :audit (record lisp_frontend_design_delta/transitions/DrainStatusAudit
      :status request.status
      :summary_path request.summary_path)
    :conflict-policy fail_closed
    :backend runtime_native)

  (deftransition write-drain-status
    :resource drain-run-state
    :request-type lisp_frontend_design_delta/transitions/DrainStatusRequest
    :result-type lisp_frontend_design_delta/transitions/DrainStatusResult
    :preconditions ()
    :updates ((set-field drain_status request.status)
              (set-field drain_status_reason request.reason)
              (set-field drain_status_summary request.summary_path))
    :write-set (drain_status drain_status_reason drain_status_summary)
    :idempotency-fields (status reason summary_path)
    :result (record lisp_frontend_design_delta/transitions/DrainStatusResult
      :status request.status
      :summary_path request.summary_path)
    :audit (record lisp_frontend_design_delta/transitions/DrainStatusAudit
      :status request.status
      :summary_path request.summary_path)
    :conflict-policy fail_closed
    :backend runtime_native)

  (deftransition record-terminal-work-item
    :resource drain-run-state
    :request-type lisp_frontend_design_delta/transitions/TerminalWorkItemRequest
    :result-type lisp_frontend_design_delta/transitions/TerminalOutcomeResult
    :preconditions ((!= request.work_item_id ""))
    :updates ((set-field terminal_reason request.reason)
              (set-field terminal_summary request.summary_path))
    :write-set (terminal_reason terminal_summary)
    :idempotency-fields (work_item_id work_item_source terminal_route reason summary_path)
    :result (record lisp_frontend_design_delta/transitions/TerminalOutcomeResult
      :reason request.reason
      :summary_path request.summary_path)
    :audit (record lisp_frontend_design_delta/transitions/TerminalOutcomeAudit
      :reason request.reason
      :summary_path request.summary_path)
    :conflict-policy fail_closed
    :backend runtime_native)

  (deftransition record-blocked-recovery-outcome
    :resource drain-run-state
    :request-type lisp_frontend_design_delta/transitions/BlockedRecoveryOutcomeRequest
    :result-type lisp_frontend_design_delta/transitions/BlockedRecoveryOutcomeResult
    :preconditions ((!= request.recovery_route BlockedRecoveryRoute.TERMINAL_BLOCKED)
                    (!= request.reason BlockedRecoveryReason.not_blocked))
    :updates ((set-field blocked_recovery_reason request.reason)
              (set-field blocked_recovery_summary request.summary_path))
    :write-set (blocked_recovery_reason blocked_recovery_summary)
    :idempotency-fields (work_item_id work_item_source recovery_route reason summary_path)
    :result (record lisp_frontend_design_delta/transitions/BlockedRecoveryOutcomeResult
      :reason request.reason
      :summary_path request.summary_path)
    :audit (record lisp_frontend_design_delta/transitions/BlockedRecoveryOutcomeAudit
      :reason request.reason
      :summary_path request.summary_path)
    :conflict-policy fail_closed
    :backend runtime_native)

  (defworkflow emit-drain-status-transition-audit
    ((run_state_path RunStatePath)
     (summary_path WorkReportTarget))
    -> DrainStatusResult
    (resource-transition
      :transition write-drain-status-runtime-native
      :resource drain-run-state
      :request (record lisp_frontend_design_delta/transitions/DrainStatusRequest
        :status DrainTerminalStatus.BLOCKED
        :reason "runtime_native_fixture"
        :summary_path summary_path)))

  (defworkflow apply-drain-status-transition
    ((run_state_path RunStatePath)
     (status DrainTerminalStatus)
     (reason String)
     (summary_path WorkReportTarget))
    -> DrainStatusResult
    (resource-transition
      :transition write-drain-status
      :resource drain-run-state
      :request (record lisp_frontend_design_delta/transitions/DrainStatusRequest
        :status status
        :reason reason
        :summary_path summary_path)))

  (defproc record-drain-terminal-outcome
    ((run_state_path RunStatePath)
     (status DrainTerminalStatus)
     (reason String)
     (summary_path WorkReportTarget))
    -> RenderedSummary
    :effects ((uses-command apply_resource_transition)
              (writes drain-summary-view))
    :lowering inline
    (let* ((transition-result
             (resource-transition
               :transition write-drain-status
               :resource drain-run-state
               :request (record lisp_frontend_design_delta/transitions/DrainStatusRequest
                 :status status
                 :reason reason
                 :summary_path summary_path)))
           (rendered-summary
             (materialize-view drain-summary-view
               :value (record DrainSummaryValue
                        :drain_status status
                        :drain_status_reason reason
                        :run_state_path run_state_path
                        :summary_target summary_path
                        :state_version "lisp_frontend_autonomous_drain_run_state/v1")
               :renderer canonical-json
               :renderer-version 1
               :target transition-result.summary_path
               :returns WorkReport)))
      (record RenderedSummary
        :summary rendered-summary)))

  (defproc record-work-item-terminal-outcome
    ((work_item_id String)
     (work_item_source WorkItemSource)
     (terminal_route WorkItemTerminalRoute)
     (reason WorkItemTerminalReason)
     (summary_route String)
     (summary_reason String)
     (summary_path WorkReportTarget))
    -> RenderedSummary
    :effects ((uses-command apply_resource_transition)
              (writes work-item-terminal-summary-view))
    :lowering inline
    (let* ((transition-result
             (resource-transition
               :transition record-terminal-work-item
               :resource drain-run-state
               :request (record TerminalWorkItemRequest
                 :work_item_id work_item_id
                 :work_item_source work_item_source
                 :terminal_route terminal_route
                 :reason reason
                 :summary_path summary_path)))
           (rendered-summary
             (materialize-view work-item-terminal-summary-view
               :value (record WorkItemSummaryValue
                        :work_item_id work_item_id
                        :work_item_source work_item_source
                        :terminal_route summary_route
                        :reason summary_reason)
               :renderer canonical-json
               :renderer-version 1
               :target transition-result.summary_path
               :returns WorkReport)))
      (record RenderedSummary
        :summary rendered-summary)))

  (defproc record-work-item-blocked-recovery-summary
    ((work_item_id String)
     (work_item_source WorkItemSource)
     (work_item_context WorkItemContextValue)
     (work_item_context_view_target_path WorkReportTarget)
     (recovery_route BlockedRecoveryRoute)
     (reason BlockedRecoveryReason)
     (summary_reason String)
     (summary_path WorkReportTarget))
    -> RenderedSummary
    :effects ((uses-command apply_resource_transition)
              (writes work-item-blocked-recovery-summary-view)
              (writes work-item-context-view))
    :lowering inline
    (let* ((work-item-context-view
             (materialize-view work-item-context-view
               :value work_item_context
               :renderer canonical-json
               :renderer-version 1
               :target work_item_context_view_target_path
               :returns WorkReport))
           (transition-result
             (resource-transition
               :transition record-blocked-recovery-outcome
               :resource drain-run-state
               :request (record BlockedRecoveryOutcomeRequest
                 :work_item_id work_item_id
                 :work_item_source work_item_source
                 :recovery_route recovery_route
                 :reason reason
                 :summary_path summary_path)))
           (rendered-summary
             (materialize-view work-item-blocked-recovery-summary-view
               :value (record WorkItemSummaryValue
                        :work_item_id work_item_id
                        :work_item_source work_item_source
                        :terminal_route "BLOCKED_RECOVERY"
                        :reason summary_reason)
               :renderer canonical-json
               :renderer-version 1
               :target transition-result.summary_path
               :returns WorkReport)))
      (record RenderedSummary
        :summary rendered-summary)))
)
