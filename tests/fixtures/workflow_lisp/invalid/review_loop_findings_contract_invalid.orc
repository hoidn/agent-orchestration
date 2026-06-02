(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule review_loop_findings_contract_invalid)
  (import std/phase :only (ReviewFindings review-revise-loop))
  (defenum BlockerClass
    missing_resource)
  (defenum ReviewDecision
    APPROVE
    REVISE
    BLOCKED)
  (defpath ReviewReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath ChecksReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath ProgressReport
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
    (execution_report_path ReviewReport))
  (defrecord ReviewInputs
    (design_review_prompt ReviewReport)
    (fix_plan_prompt ReviewReport))
  (defrecord WrongFindings
    (schema_version String)
    (items_path ReviewReport))
  (defunion BrokenReviewLoopResult
    (APPROVED
      (checks_report ChecksReport)
      (review_report ReviewReport)
      (review_decision ReviewDecision)
      (findings WrongFindings))
    (BLOCKED
      (progress_report ProgressReport)
      (blocker_class BlockerClass)
      (findings WrongFindings))
    (EXHAUSTED
      (last_review_report ReviewReport)
      (reason String)))
  (defrecord ReviewLoopSurfaceResult
    (report_path ReviewReport))
  (defworkflow invalid-review-loop-contract
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
                 :returns BrokenReviewLoopResult)))
        (match result
          ((APPROVED approved)
           (record ReviewLoopSurfaceResult
             :report_path approved.review_report))
          ((BLOCKED blocked)
           (record ReviewLoopSurfaceResult
             :report_path blocked.progress_report)))))))
