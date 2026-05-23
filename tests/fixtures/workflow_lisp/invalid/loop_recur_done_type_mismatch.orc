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
    (status String)
    (report WorkReport))
  (defunion ImplementationState
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass)))
  (defworkflow loop-recur-done-type-mismatch
    ((input ChecksResult)
     (report_path WorkReport))
    -> ImplementationSummary
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (input report_path)
               :returns ImplementationState)))
      (loop/recur
        :max 3
        :state attempt
        (fn (state)
          (match state
            ((COMPLETED completed)
             (done
               (record ImplementationSummary
                 :status "completed"
                 :report completed.execution_report)))
            ((BLOCKED blocked)
             (done blocked.progress_report))))))))
