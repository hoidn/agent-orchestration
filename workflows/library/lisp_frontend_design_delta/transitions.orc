(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/transitions)
  (import lisp_frontend_design_delta/types :only
    (ArtifactWorkTargetPath BlockedRecoveryReason BlockedRecoveryRoute PlanDocTarget RunStatePath
      StateFile WorkItemSource WorkReport WorkReportTarget))
  (export
    apply-drain-status-transition
    BlockedRecoveryOutcomeRequest
    BlockedRecoveryOutcomeAudit
    BlockedRecoveryOutcomeResult
    DrainStatusAudit
    DrainStatusRequest
    DrainStatusResult
    DrainRunStateRecord
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
    (drain_status String)
    (drain_status_reason String)
    (drain_status_summary WorkReportTarget)
    (terminal_reason String)
    (terminal_summary WorkReportTarget)
    (blocked_recovery_reason BlockedRecoveryReason)
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

  (defrecord TerminalWorkItemRequest
    (work_item_id String)
    (work_item_source WorkItemSource)
    (reason String)
    (item_summary_target_path WorkReportTarget)
    (item_summary_pointer_path WorkReportTarget)
    (drain_status_path StateFile))

  (defrecord BlockedRecoveryOutcomeRequest
    (work_item_id String)
    (work_item_source WorkItemSource)
    (recovery_route BlockedRecoveryRoute)
    (reason BlockedRecoveryReason)
    (target_design_review_decision String)
    (terminal_action String)
    (summary_path WorkReportTarget)
    (summary_pointer_path WorkReportTarget)
    (drain_status_path StateFile)
    (progress_report_path ArtifactWorkTargetPath)
    (implementation_state_path ArtifactWorkTargetPath)
    (work_item_context_path WorkReport)
    (plan_path PlanDocTarget))

  (defrecord TerminalOutcomeResult
    (reason String)
    (summary_path WorkReportTarget))

  (defrecord BlockedRecoveryOutcomeResult
    (reason BlockedRecoveryReason)
    (summary_path WorkReportTarget))

  (defrecord TerminalOutcomeAudit
    (reason String)
    (summary_path WorkReportTarget))

  (defrecord BlockedRecoveryOutcomeAudit
    (reason BlockedRecoveryReason)
    (summary_path WorkReportTarget))

  (defresource drain-run-state
    :state-type lisp_frontend_design_delta/transitions/DrainRunStateRecord
    :backing (bridge run_state_path))

  (deftransition write-drain-status-runtime-native
    :resource drain-run-state
    :request-type lisp_frontend_design_delta/transitions/DrainStatusRequest
    :result-type lisp_frontend_design_delta/transitions/DrainStatusResult
    :preconditions ((!= request.status ""))
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
    :preconditions ((!= request.status ""))
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
    :preconditions ((!= request.reason ""))
    :updates ((set-field terminal_reason request.reason)
              (set-field terminal_summary request.item_summary_target_path))
    :write-set (terminal_reason terminal_summary)
    :idempotency-fields (reason item_summary_target_path)
    :result (record lisp_frontend_design_delta/transitions/TerminalOutcomeResult
      :reason request.reason
      :summary_path request.item_summary_target_path)
    :audit (record lisp_frontend_design_delta/transitions/TerminalOutcomeAudit
      :reason request.reason
      :summary_path request.item_summary_target_path)
    :conflict-policy fail_closed
    :backend runtime_native)

  (deftransition record-blocked-recovery-outcome
    :resource drain-run-state
    :request-type lisp_frontend_design_delta/transitions/BlockedRecoveryOutcomeRequest
    :result-type lisp_frontend_design_delta/transitions/BlockedRecoveryOutcomeResult
    :preconditions ((= request.reason request.reason))
    :updates ((set-field blocked_recovery_reason request.reason)
              (set-field blocked_recovery_summary request.summary_path))
    :write-set (blocked_recovery_reason blocked_recovery_summary)
    :idempotency-fields (reason summary_path)
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
        :status "BLOCKED"
        :reason "runtime_native_fixture"
        :summary_path summary_path)))

  (defworkflow apply-drain-status-transition
    ((run_state_path RunStatePath)
     (status String)
     (reason String)
     (summary_path WorkReportTarget))
    -> DrainStatusResult
    (resource-transition
      :transition write-drain-status
      :resource drain-run-state
      :request (record lisp_frontend_design_delta/transitions/DrainStatusRequest
        :status status
        :reason reason
        :summary_path summary_path))))
