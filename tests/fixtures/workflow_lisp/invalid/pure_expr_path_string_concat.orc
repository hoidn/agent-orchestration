(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (status String)
    (report WorkReport))
  (defworkflow invalid-pure-expr-path-string-concat
    ((report_path WorkReport))
    -> ChecksResult
    (record ChecksResult
      :status (string/concat report_path ".bak")
      :report report_path)))
