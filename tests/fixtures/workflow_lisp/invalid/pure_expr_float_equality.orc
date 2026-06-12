(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ImplementationSummary
    (report WorkReport))
  (defun compare-floats
    ((left Float)
     (right Float))
    -> Bool
    (= left right))
  (defworkflow invalid-pure-expr-float-equality
    ((report_path WorkReport))
    -> ImplementationSummary
    (record ImplementationSummary
      :report report_path)))
