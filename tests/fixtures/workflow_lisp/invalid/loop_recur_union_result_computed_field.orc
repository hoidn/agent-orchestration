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
  (defunion ImplementationState
    (COMPLETED
      (attempt_count Int)
      (execution_report WorkReport)
      (completion_status String))
    (BLOCKED
      (attempt_count Int)
      (progress_report WorkReport)
      (blocker_class BlockerClass)))
  (defworkflow loop-recur-union-result-computed-field
    ((input ChecksResult)
     (report_path WorkReport))
    -> ImplementationState
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (input report_path)
               :returns ImplementationState)))
      (loop/recur
        :max 2
        :state attempt
        (fn (state)
          (match state
            ((COMPLETED completed)
             (done state))
            ((BLOCKED blocked)
             (done
               (variant ImplementationState BLOCKED
                 :attempt_count (+ blocked.attempt_count 1)
                 :progress_report blocked.progress_report
                 :blocker_class blocked.blocker_class)))))))))
