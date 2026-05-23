(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ImplementationSummary
    (report WorkReport))
  (defworkflow invalid-if-condition-not-projectable
    ((ready Bool)
     (report_path WorkReport)
     (fallback_path WorkReport))
    -> ImplementationSummary
    (if (let* ((alias ready)) alias)
      (record ImplementationSummary
        :report report_path)
      (record ImplementationSummary
        :report fallback_path))))
