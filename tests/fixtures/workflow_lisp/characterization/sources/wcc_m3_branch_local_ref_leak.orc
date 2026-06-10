(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule branch_local_ref_leak_probe)
  (export summarize)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
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
                (record ImplementationSummary
                  :report completed.execution_report))
               ((BLOCKED blocked)
                (record ImplementationSummary
                  :report blocked.progress_report)))))
      (record ImplementationSummary
        :report completed.execution_report))))
