(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule nested_join_inside_arm_probe)
  (export summarize)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defunion ReviewDecision
    (APPROVED
      (execution_report WorkReport))
    (REVISE
      (progress_report WorkReport)))
  (defunion ImplementationAttempt
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)))
  (defrecord ImplementationSummary
    (report WorkReport))
  (defworkflow summarize
    ((report WorkReport))
    -> ImplementationSummary
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report)
               :returns ImplementationAttempt))
           (summary
             (match attempt
               ((COMPLETED completed)
                (let* ((review
                         (provider-result providers.execute
                           :prompt prompts.implementation.execute
                           :inputs (completed.execution_report)
                           :returns ReviewDecision))
                       (approved_report
                         (match review
                           ((APPROVED approved)
                            approved.execution_report)
                           ((REVISE revise)
                            revise.progress_report)))
                       (branch_only
                         (record ImplementationSummary
                           :report approved_report)))
                  branch_only))
               ((BLOCKED blocked)
                (record ImplementationSummary
                  :report blocked.progress_report)))))
      (record ImplementationSummary
        :report summary.report))))
