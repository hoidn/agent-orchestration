(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule effectful_let_star_normalization)
  (export run-effectful-let-star-normalization)

  (defenum BlockerClass
    missing_resource
    unavailable_hardware)

  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defrecord AttemptReport
    (report WorkReport))

  (defrecord FinalReport
    (report WorkReport))

  (defunion ImplementationState
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass)))

  (defworkflow run-effectful-let-star-normalization
    ((report_path WorkReport))
    -> FinalReport
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report_path)
               :returns ImplementationState))
            (alias attempt)
            (attempt-report
             (match alias
               ((COMPLETED completed)
                (provider-result providers.execute
                  :prompt prompts.implementation.execute
                  :inputs (completed.execution_report)
                  :returns AttemptReport))
               ((BLOCKED blocked)
                (provider-result providers.execute
                  :prompt prompts.implementation.execute
                  :inputs (blocked.progress_report)
                  :returns AttemptReport))))
            (final-report
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (attempt-report.report)
               :returns FinalReport)))
      final-report)))
