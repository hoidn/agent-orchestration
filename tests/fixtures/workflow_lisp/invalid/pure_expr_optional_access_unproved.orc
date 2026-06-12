(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ImplementationSummary
    (report WorkReport))
  (defun extract-report
    ((maybe_summary Optional[ImplementationSummary]))
    -> WorkReport
    maybe_summary.report)
  (defworkflow invalid-pure-expr-optional-access-unproved
    ((fallback_path WorkReport))
    -> ImplementationSummary
    (record ImplementationSummary
      :report fallback_path)))
