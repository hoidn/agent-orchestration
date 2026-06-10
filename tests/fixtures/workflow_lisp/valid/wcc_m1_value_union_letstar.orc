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
  (defrecord ImplementationSummary
    (status String)
    (report WorkReport))
  (defrecord NestedImplementationSummary
    (summary ImplementationSummary))
  (defunion ImplementationState
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass)))
  (defworkflow value-union-letstar
    ((status String)
     (report_path WorkReport))
    -> ImplementationState
    (let* ((nested
             (record NestedImplementationSummary
               :summary (record ImplementationSummary
                          :status status
                          :report report_path)))
           (execution-report
             nested.summary.report)
           (attempt
             (variant ImplementationState COMPLETED
               :execution_report execution-report)))
      attempt)))
