(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ReportResult
    (report WorkReport))
  (defworkflow invalid-phase-target
    ((report_path WorkReport))
    -> ReportResult
    (record ReportResult
      :report (phase-target execution-report))))
