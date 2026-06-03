(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule phase_stdlib_review_loop)
  (import std/phase :only (ReviewFindings review-revise-loop))
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
  (defpath ReviewReport
    :kind relpath
    :under "artifacts/review"
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
      (review_report ReviewReport)
      (review_decision ReviewDecision)
      (findings ReviewFindings))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass)
      (findings ReviewFindings))
    (EXHAUSTED
      (last_review_report ReviewReport)
      (reason String)
      (findings ReviewFindings)))
  (defworkflow review-revise-loop-demo
    ((phase-ctx PhaseCtx)
     (completed CompletedAttempt)
     (inputs ReviewInputs))
    -> ReviewLoopResult
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
           (variant ReviewLoopResult APPROVED
             :checks_report approved.checks_report
             :review_report approved.review_report
             :review_decision approved.review_decision
             :findings (record ReviewFindings
               :schema_version approved.findings.schema_version
               :items_path approved.findings.items_path)))
          ((BLOCKED blocked)
           (variant ReviewLoopResult BLOCKED
             :progress_report blocked.progress_report
             :blocker_class blocked.blocker_class
             :findings (record ReviewFindings
               :schema_version blocked.findings.schema_version
               :items_path blocked.findings.items_path)))
          ((EXHAUSTED exhausted)
           (variant ReviewLoopResult EXHAUSTED
             :last_review_report exhausted.last_review_report
             :reason exhausted.reason
             :findings (record ReviewFindings
               :schema_version exhausted.findings.schema_version
               :items_path exhausted.findings.items_path))))))))
