(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule review_loop_findings_contract_invalid)
  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult review-revise-loop with-phase))
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord CompletedAttempt
    (execution_report_path WorkReport))
  (defrecord ReviewInputs
    (design_review_prompt WorkReport)
    (fix_plan_prompt WorkReport))
  (defproc run-review
    ((completed CompletedAttempt)
     (inputs ReviewInputs))
    -> ReviewDecision
    :effects ()
    :lowering inline
    (variant ReviewDecision REVISE
      :review_report "artifacts/review/review-report.md"
      :findings (record ReviewFindings
                  :schema_version "ReviewFindings.v1"
                  :items_path completed.execution_report_path)))
  (defproc apply-fix
    ((completed CompletedAttempt)
     (inputs ReviewInputs)
     (findings ReviewFindings))
    -> CompletedAttempt
    :effects ()
    :lowering inline
    completed)
  (defworkflow invalid-review-loop
    ((phase-ctx PhaseCtx)
     (completed CompletedAttempt)
     (inputs ReviewInputs))
    -> ReviewLoopResult
    (with-phase phase-ctx implementation-review
      (review-revise-loop implementation-review
        :ctx phase-ctx
        :completed completed
        :inputs inputs
        :review (proc-ref run-review)
        :fix (proc-ref apply-fix)
        :max 3))))
