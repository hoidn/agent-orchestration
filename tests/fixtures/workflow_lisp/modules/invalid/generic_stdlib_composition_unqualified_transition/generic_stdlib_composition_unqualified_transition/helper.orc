(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule generic_stdlib_composition_unqualified_transition/helper)
  (export OutcomeRequest OutcomeResult SummaryPath SummaryValue emit-run-outcome)
  (defpath SummaryPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord OutcomeState
    (status String))
  (defrecord OutcomeRequest
    (status String))
  (defrecord OutcomeTransitionResult
    (status String))
  (defrecord OutcomeAudit
    (status String))
  (defrecord SummaryValue
    (status String)
    (message String))
  (defrecord OutcomeResult
    (status String)
    (summary_path SummaryPath))
  (defresource outcome-state
    :state-type OutcomeState
    :backing state-layout)
  (deftransition record-outcome
    :resource outcome-state
    :request-type OutcomeRequest
    :result-type OutcomeTransitionResult
    :preconditions ((!= request.status ""))
    :updates ((set-field status request.status))
    :write-set (status)
    :idempotency-fields (status)
    :result (record OutcomeTransitionResult
      :status request.status)
    :audit (record OutcomeAudit
      :status request.status)
    :conflict-policy fail_closed
    :backend runtime_native)
  (defmacro emit-run-outcome (name)
    (defworkflow name
      ()
      -> OutcomeResult
      (let* ((summary-path
               (__generated-relpath-seed__
                 SummaryPath
                 "artifacts/work/generic-stdlib-unqualified-summary.json"
                 "generic_stdlib_unqualified_summary_seed"))
             (transition-result
               (resource-transition
                 :transition record-outcome
                 :resource outcome-state
                 :request (record OutcomeRequest
                            :status "APPROVED")))
             (rendered-summary
               (materialize-view unqualified-summary
                 :value (record SummaryValue
                          :status transition-result.status
                          :message "unqualified")
                 :renderer canonical-json
                 :renderer-version 1
                 :target summary-path
                 :returns SummaryPath)))
        (record OutcomeResult
          :status transition-result.status
          :summary_path rendered-summary)))))
