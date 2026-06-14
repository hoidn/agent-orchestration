(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lexical_checkpoint_effect_policies)
  (export orchestrate)
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath MaterializedSummaryPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (status String)
    (report WorkReport))
  (defrecord ProviderSummary
    (status String)
    (report WorkReport))
  (defrecord ProjectionSummary
    (label String)
    (should-run Bool))
  (defrecord CallSummary
    (label String)
    (status String)
    (report WorkReport))
  (defrecord DrainRunState
    (drain_status String))
  (defrecord DrainStatusRequest
    (status String))
  (defrecord DrainStatusResult
    (status String))
  (defrecord DrainStatusAudit
    (status String))
  (defrecord OrchestrateResult
    (summary_path MaterializedSummaryPath)
    (transition_status String)
    (call_status String))
  (defresource drain-run-state
    :state-type DrainRunState
    :backing (bridge run_state_path))
  (deftransition write-drain-status
    :resource drain-run-state
    :request-type DrainStatusRequest
    :result-type DrainStatusResult
    :preconditions ((!= request.status ""))
    :updates ((set-field drain_status request.status))
    :write-set (drain_status)
    :idempotency-fields (status)
    :result (record DrainStatusResult
      :status request.status)
    :audit (record DrainStatusAudit
      :status request.status)
    :conflict-policy fail_closed
    :backend runtime_native)
  (defworkflow pure-helper
    ((projection ProjectionSummary)
     (review ProviderSummary))
    -> CallSummary
    (record CallSummary
      :label projection.label
      :status review.status
      :report review.report))
  (defworkflow orchestrate
    ((run_state_path StateFile)
     (report_path WorkReport)
     (summary_target MaterializedSummaryPath)
     (run_checks_now Bool))
    -> OrchestrateResult
    (let* ((projection
             (if run_checks_now
               (record ProjectionSummary
                 :label "checked"
                 :should-run true)
               (record ProjectionSummary
                 :label "skipped"
                 :should-run false)))
           (checks
             (command-result run_checks
               :argv ("python" "scripts/run_checks.py" report_path)
               :returns ChecksResult))
           (review
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (checks report_path)
               :returns ProviderSummary))
           (called
             (call pure-helper
               :projection projection
               :review review))
           (summary_path
             (materialize-view runtime-summary
               :value called
               :renderer canonical-json
               :renderer-version 1
               :target summary_target
               :returns MaterializedSummaryPath))
           (transition
             (resource-transition
               :transition write-drain-status
               :resource drain-run-state
               :request (record DrainStatusRequest
                 :status called.status))))
      (record OrchestrateResult
        :summary_path summary_path
        :transition_status transition.status
        :call_status called.status))))
