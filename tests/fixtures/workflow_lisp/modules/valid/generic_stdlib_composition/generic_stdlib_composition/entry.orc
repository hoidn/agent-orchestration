(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule generic_stdlib_composition/entry)
  (import generic_stdlib_composition/helper :only (OutcomeState OutcomeRequest OutcomeTransitionResult OutcomeAudit OutcomeResult SummaryPath SummaryValue run-generic emit-run-outcome emit-inline-run-outcome))
  (export run-outcome run-outcome-wrapped run-outcome-inline)
  (defunion CallerOutcome
    (APPROVED
      (status String)
      (message String))
    (BLOCKED
      (status String)
      (message String)))
  (defproc load-approved-outcome
    ()
    -> CallerOutcome
    :effects ()
    :lowering private-workflow
    (variant CallerOutcome APPROVED
      :status "APPROVED"
      :message "accepted"))
  (defproc load-blocked-outcome
    ()
    -> CallerOutcome
    :effects ()
    :lowering private-workflow
    (variant CallerOutcome BLOCKED
      :status "BLOCKED"
      :message "blocked"))
  (defworkflow run-outcome
    ()
    -> OutcomeResult
    (let* ((summary-path
             (__generated-relpath-seed__
               SummaryPath
               "artifacts/work/generic-stdlib-direct-summary.json"
               "generic_stdlib_direct_summary_seed"))
           (outcome
             (load-approved-outcome)))
      (run-generic outcome summary-path)))
  (emit-run-outcome run-outcome-wrapped
    (load-blocked-outcome))
  (emit-inline-run-outcome run-outcome-inline
    "APPROVED"
    "inline"))
