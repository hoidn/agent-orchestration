(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ImplementationSummary
    (report WorkReport))
  (defworkflow invalid-if-condition-not-bool
    ((report_path WorkReport)
     (fallback_path WorkReport))
    -> ImplementationSummary
    (if report_path
      (record ImplementationSummary
        :report report_path)
      (record ImplementationSummary
        :report fallback_path))))
