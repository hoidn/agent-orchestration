(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (report WorkReport))
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> ChecksResult
    (build-checks))
  (defproc build-checks
    ((report_path WorkReport))
    -> ChecksResult
    :effects ()
    :lowering inline
    (record ChecksResult
      :report report_path)))
