(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule phase_stdlib_review_loop)
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
    :effects ((uses-provider providers.review))
    :lowering inline
    (provider-result providers.review
      :prompt prompts.implementation.review
      :inputs (completed.execution_report_path
               inputs.design_review_prompt
               inputs.fix_plan_prompt)
      :returns ReviewDecision))
  (defproc apply-fix
    ((completed CompletedAttempt)
     (inputs ReviewInputs)
     (findings ReviewFindings))
    -> CompletedAttempt
    :effects ((uses-provider providers.fix))
    :lowering inline
    (provider-result providers.fix
      :prompt prompts.implementation.fix
      :inputs (completed.execution_report_path
               inputs.design_review_prompt
               inputs.fix_plan_prompt
               findings.items_path)
      :returns CompletedAttempt))
  (defworkflow review-revise-loop-demo
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
        :max 5))))
