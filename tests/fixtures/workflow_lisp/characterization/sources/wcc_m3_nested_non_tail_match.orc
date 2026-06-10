(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule nested_match_probe)
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
           (review
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report)
               :returns ReviewDecision))
           (summary
             (match attempt
               ((COMPLETED completed)
                (match review
                  ((APPROVED approved)
                   (record ImplementationSummary
                     :report approved.execution_report))
                  ((REVISE revise)
                   (record ImplementationSummary
                     :report revise.progress_report))))
               ((BLOCKED blocked)
                (record ImplementationSummary
                  :report blocked.progress_report)))))
      (record ImplementationSummary
        :report summary.report))))
