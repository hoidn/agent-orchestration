(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defenum BlockerClass
    missing_resource
    unavailable_hardware)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ImplementationSummary
    (report WorkReport))
  (defunion ImplementationState
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass)))
  (defun select-report
    ((ready Bool)
     (attempt ImplementationState)
     (fallback_path WorkReport))
    -> WorkReport
    (if (= ready true)
      attempt.execution_report
      fallback_path))
  (defworkflow invalid-pure-expr-computed-if-variant-ref-unproved
    ((fallback_path WorkReport))
    -> ImplementationSummary
    (record ImplementationSummary
      :report fallback_path)))
