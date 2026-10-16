(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule phase_reference_owners)
  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult review-revise-loop))
  (export run)
  (defrecord PhaseInputContext (n Int)) (defrecord Completed (n Int)) (defrecord Inputs (n Int))
  (defproc review-plan ((completed Completed) (inputs Inputs)) -> ReviewDecision
    :effects ((uses-provider providers.review)) :lowering inline
    (provider-result providers.review :prompt prompts.review :inputs (completed.n) :returns ReviewDecision))
  (defproc fix-plan ((completed Completed) (inputs Inputs) (findings ReviewFindings)) -> Completed
    :effects ((uses-provider providers.fix)) :lowering inline
    (provider-result providers.fix :prompt prompts.fix :inputs (completed.n) :returns Completed))
  (defproc review-implementation ((completed Completed) (inputs Inputs)) -> ReviewDecision
    :effects ((uses-provider providers.review)) :lowering inline
    (provider-result providers.review :prompt prompts.review :inputs (completed.n) :returns ReviewDecision))
  (defproc fix-implementation ((completed Completed) (inputs Inputs) (findings ReviewFindings)) -> Completed
    :effects ((uses-provider providers.fix)) :lowering inline
    (provider-result providers.fix :prompt prompts.fix :inputs (completed.n) :returns Completed))
  (defworkflow run ((ctx PhaseInputContext) (completed Completed) (inputs Inputs)) -> ReviewLoopResult
    (let* ((first (review-revise-loop plan :ctx ctx :completed completed :inputs inputs
                  :review (proc-ref review-plan) :fix (proc-ref fix-plan) :max 3)))
      (review-revise-loop implementation :ctx ctx :completed completed :inputs inputs
        :review (proc-ref review-implementation) :fix (proc-ref fix-implementation) :max 5))))
