(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/transitions)
  (import lisp_frontend_design_delta/types :only
    (RunStatePath WorkReportTarget))
  (export
    DrainStatusRequest
    DrainStatusResult
    drain-run-state
    emit-drain-status-transition-audit
    write-drain-status
    record-terminal-work-item
    record-blocked-recovery-outcome)

  (defrecord DrainRunStateRecord
    (drain_status String)
    (drain_status_reason String)
    (drain_status_summary WorkReportTarget)
    (terminal_reason String)
    (terminal_summary WorkReportTarget)
    (blocked_recovery_reason String)
    (blocked_recovery_summary WorkReportTarget))

  (defrecord DrainStatusRequest
    (status String)
    (reason String)
    (summary_path WorkReportTarget))

  (defrecord DrainStatusResult
    (status String)
    (summary_path WorkReportTarget))

  (defrecord DrainStatusAudit
    (status String)
    (summary_path WorkReportTarget))

  (defrecord TerminalOutcomeRequest
    (reason String)
    (summary_path WorkReportTarget))

  (defrecord TerminalOutcomeResult
    (reason String)
    (summary_path WorkReportTarget))

  (defrecord TerminalOutcomeAudit
    (reason String)
    (summary_path WorkReportTarget))

  (defresource drain-run-state
    :state-type DrainRunStateRecord
    :backing (bridge run_state_path))

  (deftransition write-drain-status-runtime-native
    :resource drain-run-state
    :request-type DrainStatusRequest
    :result-type DrainStatusResult
    :preconditions ((!= request.status ""))
    :updates ((set-field drain_status request.status)
              (set-field drain_status_reason request.reason)
              (set-field drain_status_summary request.summary_path))
    :write-set (drain_status drain_status_reason drain_status_summary)
    :idempotency-fields (status reason summary_path)
    :result (record DrainStatusResult
      :status request.status
      :summary_path request.summary_path)
    :audit (record DrainStatusAudit
      :status request.status
      :summary_path request.summary_path)
    :conflict-policy fail_closed
    :backend runtime_native)

  (deftransition write-drain-status
    :resource drain-run-state
    :request-type DrainStatusRequest
    :result-type DrainStatusResult
    :preconditions ((!= request.status ""))
    :updates ((set-field drain_status request.status)
              (set-field drain_status_reason request.reason)
              (set-field drain_status_summary request.summary_path))
    :write-set (drain_status drain_status_reason drain_status_summary)
    :idempotency-fields (status reason summary_path)
    :result (record DrainStatusResult
      :status request.status
      :summary_path request.summary_path)
    :audit (record DrainStatusAudit
      :status request.status
      :summary_path request.summary_path)
    :conflict-policy fail_closed
    :backend write_lisp_frontend_drain_status)

  (deftransition record-terminal-work-item
    :resource drain-run-state
    :request-type TerminalOutcomeRequest
    :result-type TerminalOutcomeResult
    :preconditions ((!= request.reason ""))
    :updates ((set-field terminal_reason request.reason)
              (set-field terminal_summary request.summary_path))
    :write-set (terminal_reason terminal_summary)
    :idempotency-fields (reason summary_path)
    :result (record TerminalOutcomeResult
      :reason request.reason
      :summary_path request.summary_path)
    :audit (record TerminalOutcomeAudit
      :reason request.reason
      :summary_path request.summary_path)
    :conflict-policy fail_closed
    :backend record_terminal_work_item)

  (deftransition record-blocked-recovery-outcome
    :resource drain-run-state
    :request-type TerminalOutcomeRequest
    :result-type TerminalOutcomeResult
    :preconditions ((!= request.reason ""))
    :updates ((set-field blocked_recovery_reason request.reason)
              (set-field blocked_recovery_summary request.summary_path))
    :write-set (blocked_recovery_reason blocked_recovery_summary)
    :idempotency-fields (reason summary_path)
    :result (record TerminalOutcomeResult
      :reason request.reason
      :summary_path request.summary_path)
    :audit (record TerminalOutcomeAudit
      :reason request.reason
      :summary_path request.summary_path)
    :conflict-policy fail_closed
    :backend record_blocked_recovery_outcome)

  (defworkflow emit-drain-status-transition-audit
    ((run_state_path RunStatePath)
     (summary_path WorkReportTarget))
    -> DrainStatusResult
    (resource-transition
      :transition write-drain-status-runtime-native
      :resource drain-run-state
      :request (record DrainStatusRequest
        :status "BLOCKED"
        :reason "runtime_native_fixture"
        :summary_path summary_path))))
