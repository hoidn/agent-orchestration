(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule nested/implementation-phase)
  (import std/phase :only (BlockerClass ReviewDecision ReviewFindings ReviewReportPath review-revise-loop))
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath WorkReportTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
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
    (execution_report WorkReport))
  (defrecord ChecksResult
    (checks_report WorkReport))
  (defrecord ReviewInputs
    (review_prompt WorkReport)
    (fix_prompt WorkReport)
    (execution_report_target WorkReportTarget)
    (review_report_target WorkReportTarget))
  (defunion ImplementationAttempt
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass)))
  (defrecord ImplementationPhaseResult
    (execution_report WorkReport)
    (progress_report WorkReport)
    (checks_report WorkReport)
    (implementation_review_report WorkReportTarget))
  (defproc run-review
    ((completed CompletedAttempt)
     (inputs ReviewInputs))
    -> ReviewDecision
    :effects ((uses-provider providers.review))
    :lowering inline
    (provider-result providers.review
      :prompt prompts.implementation.review
      :inputs (completed.execution_report
               inputs.review_prompt
               inputs.fix_prompt
               inputs.review_report_target)
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
      :inputs (completed.execution_report
               inputs.review_prompt
               inputs.fix_prompt
               findings.items_path
               inputs.execution_report_target)
      :returns CompletedAttempt))
  (defworkflow implementation-phase
    ((phase-ctx PhaseCtx)
     (review_prompt WorkReport)
     (fix_prompt WorkReport)
     (checks_report_target WorkReportTarget)
     (execution_report_target WorkReportTarget)
     (progress_report_target WorkReportTarget)
     (review_report_target WorkReportTarget))
    -> ImplementationPhaseResult
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (review_prompt
                        fix_prompt
                        execution_report_target
                        progress_report_target)
               :returns ImplementationAttempt)))
      (match attempt
        ((COMPLETED completed)
         (let* ((checks
                  (command-result run_checks
                    :argv ("python" "scripts/run_checks.py"
                           completed.execution_report
                           checks_report_target)
                    :returns ChecksResult))
                (completed-attempt
                  (record CompletedAttempt
                    :execution_report completed.execution_report))
                (review-result
                  (review-revise-loop implementation-review
                    :ctx phase-ctx
                    :completed completed-attempt
                    :inputs (record ReviewInputs
                              :review_prompt review_prompt
                              :fix_prompt fix_prompt
                              :execution_report_target execution_report_target
                              :review_report_target review_report_target)
                    :review (proc-ref run-review)
                    :fix (proc-ref apply-fix)
                    :max 3)))
           (match review-result
             ((APPROVED approved)
              (record ImplementationPhaseResult
                :execution_report completed.execution_report
                :progress_report completed.execution_report
                :checks_report checks.checks_report
                :implementation_review_report review_report_target))
             ((BLOCKED blocked)
              (record ImplementationPhaseResult
                :execution_report completed.execution_report
                :progress_report completed.execution_report
                :checks_report checks.checks_report
                :implementation_review_report review_report_target))
             ((EXHAUSTED exhausted)
              (record ImplementationPhaseResult
                :execution_report completed.execution_report
                :progress_report completed.execution_report
                :checks_report checks.checks_report
                :implementation_review_report review_report_target)))))
        ((BLOCKED blocked)
         (record ImplementationPhaseResult
           :execution_report blocked.progress_report
           :progress_report blocked.progress_report
           :checks_report blocked.progress_report
           :implementation_review_report review_report_target))))))
