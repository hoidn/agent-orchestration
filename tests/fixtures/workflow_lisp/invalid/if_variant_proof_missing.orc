(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (status String)
    (report WorkReport))
  (defrecord ImplementationSummary
    (report WorkReport))
  (defunion ImplementationState
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass)))
  (defworkflow invalid-if-variant-proof-missing
    ((ready Bool)
     (input ChecksResult)
     (report_path WorkReport)
     (fallback_path WorkReport))
    -> ImplementationSummary
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (input report_path)
               :returns ImplementationState)))
      (if ready
        (record ImplementationSummary
          :report attempt.execution_report)
        (record ImplementationSummary
          :report fallback_path)))))
