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
  (defun compare-attempts
    ((left ImplementationState)
     (right ImplementationState))
    -> Bool
    (= left right))
  (defworkflow invalid-pure-expr-union-equality
    ((report_path WorkReport))
    -> ImplementationSummary
    (record ImplementationSummary
      :report report_path)))
