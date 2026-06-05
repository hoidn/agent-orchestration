(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule review_loop_legacy_bridge_operands_invalid)
  (import std/phase :only (ReviewLoopResult review-revise-loop))
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
        :review-provider providers.review
        :fix-provider providers.fix
        :max 3))))
