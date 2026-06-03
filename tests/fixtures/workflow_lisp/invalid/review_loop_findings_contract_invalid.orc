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
    :under "artifacts/review"
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
  (defworkflow invalid-review-loop-contract
    ((phase-ctx PhaseCtx)
     (completed CompletedAttempt)
     (inputs ReviewInputs))
    -> BrokenReviewLoopResult
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
           (variant BrokenReviewLoopResult APPROVED
             :checks_report approved.checks_report
             :review_report approved.review_report
             :review_decision approved.review_decision
             :findings (record WrongFindings
               :schema_version approved.findings.schema_version
               :items_path approved.findings.items_path)))
          ((BLOCKED blocked)
           (variant BrokenReviewLoopResult BLOCKED
             :progress_report blocked.progress_report
             :blocker_class blocked.blocker_class
             :findings (record WrongFindings
               :schema_version blocked.findings.schema_version
               :items_path blocked.findings.items_path)))
          ((EXHAUSTED exhausted)
           (variant BrokenReviewLoopResult EXHAUSTED
             :last_review_report exhausted.last_review_report
             :reason exhausted.reason)))))))
