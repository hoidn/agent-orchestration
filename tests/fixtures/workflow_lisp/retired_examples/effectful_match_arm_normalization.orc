(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule effectful_match_arm_normalization)
  (export run-effectful-match-arm-normalization)

  (defenum BlockerClass
    missing_resource
    unavailable_hardware)

  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defrecord AttemptReport
    (report WorkReport))

  (defunion ImplementationState
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass)))

  (defworkflow run-effectful-match-arm-normalization
    ((report_path WorkReport))
    -> AttemptReport
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report_path)
               :returns ImplementationState)))
      (match attempt
        ((COMPLETED completed)
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :inputs (completed.execution_report)
           :returns AttemptReport))
        ((BLOCKED blocked)
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :inputs (blocked.progress_report)
           :returns AttemptReport))))))
