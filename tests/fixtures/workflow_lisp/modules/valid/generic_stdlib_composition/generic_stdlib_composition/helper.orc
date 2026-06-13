(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule generic_stdlib_composition/helper)
  (export OutcomeState OutcomeRequest OutcomeTransitionResult OutcomeAudit SummaryPath SummaryValue OutcomeResult outcome-state record-outcome run-generic emit-run-outcome emit-inline-run-outcome)
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
  (defproc run-generic
    :forall (T)
    ((value T)
     (summary_path SummaryPath))
    :where ((T has-union-variant APPROVED (status String) (message String))
            (T has-union-variant BLOCKED (status String) (message String)))
    -> OutcomeResult
    :effects ((uses-command apply_resource_transition)
              (writes approved-summary)
              (writes blocked-summary))
    :lowering inline
    (match value
      ((APPROVED approved)
       (let* ((transition-result
                (resource-transition
                  :transition record-outcome
                  :resource outcome-state
                  :request (record OutcomeRequest
                    :status approved.status)))
              (rendered-summary
                (materialize-view approved-summary
                  :value (record SummaryValue
                           :status transition-result.status
                           :message approved.message)
                  :renderer canonical-json
                  :renderer-version 1
                  :target summary_path
                  :returns SummaryPath)))
         (record OutcomeResult
           :status transition-result.status
           :summary_path rendered-summary)))
      ((BLOCKED blocked)
       (let* ((transition-result
                (resource-transition
                  :transition record-outcome
                  :resource outcome-state
                  :request (record OutcomeRequest
                    :status blocked.status)))
              (rendered-summary
                (materialize-view blocked-summary
                  :value (record SummaryValue
                           :status transition-result.status
                           :message blocked.message)
                  :renderer canonical-json
                  :renderer-version 1
                  :target summary_path
                  :returns SummaryPath)))
         (record OutcomeResult
           :status transition-result.status
           :summary_path rendered-summary)))))
  (defmacro emit-run-outcome (name outcome)
    (defworkflow name
      ()
      -> OutcomeResult
      (let* ((summary-path
               (__generated-relpath-seed__
                 SummaryPath
                 "artifacts/work/generic-stdlib-summary.json"
                 "generic_stdlib_summary_seed"))
             (resolved-outcome outcome))
        (run-generic resolved-outcome summary-path))))
  (defmacro emit-inline-run-outcome (name status message)
    (defworkflow name
      ()
      -> OutcomeResult
      (let* ((summary-path
               (__generated-relpath-seed__
                 SummaryPath
                 "artifacts/work/generic-stdlib-inline-summary.json"
                 "generic_stdlib_inline_summary_seed"))
              (transition-result
               (resource-transition
                 :transition generic_stdlib_composition/helper/record-outcome
                 :resource generic_stdlib_composition/helper/outcome-state
                 :request (record OutcomeRequest
                            :status status)))
              (rendered-summary
               (materialize-view approved-summary
                 :value (record SummaryValue
                          :status status
                          :message message)
                 :renderer canonical-json
                 :renderer-version 1
                 :target summary-path
                 :returns SummaryPath)))
        (record OutcomeResult
          :status status
          :summary_path rendered-summary)))))
