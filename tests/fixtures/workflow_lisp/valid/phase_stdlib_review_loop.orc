(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule phase_stdlib_review_loop)
  (import std/phase :only (review-revise-loop))
  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)
  (defenum ReviewDecision
    APPROVE
    REVISE
    BLOCKED)
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
  (defunion ReviewLoopResult
    (APPROVED
      (checks_report WorkReport)
      (review_report WorkReport)
      (review_decision ReviewDecision))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass))
    (EXHAUSTED
      (last_review_report WorkReport)
      (reason String)))
  (defrecord ReviewLoopSurfaceResult
    (report_path WorkReport))
  (defworkflow review-revise-loop-demo
    ((phase-ctx PhaseCtx)
     (completed CompletedAttempt)
     (inputs ReviewInputs))
    -> ReviewLoopSurfaceResult
    (with-phase phase-ctx implementation-review
      (let* ((result
               (review-revise-loop implementation-review
                 :ctx phase-ctx
                 :completed completed
                 :inputs inputs
                 :review-provider providers.review
                 :fix-provider providers.fix
                 :review-prompt prompts.implementation.review
                 :fix-prompt prompts.implementation.fix
                 :max 5
                 :returns ReviewLoopResult)))
        (match result
          ((APPROVED approved)
           (record ReviewLoopSurfaceResult
             :report_path approved.review_report))
          ((BLOCKED blocked)
           (record ReviewLoopSurfaceResult
             :report_path blocked.progress_report))
          ((EXHAUSTED exhausted)
           (record ReviewLoopSurfaceResult
             :report_path exhausted.last_review_report)))))))
