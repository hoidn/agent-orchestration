(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ReadyResult
    (ready Bool))
  (defrecord ImplementationSummary
    (report WorkReport))
  (defworkflow invalid-if-condition-effectful
    ((report_path WorkReport)
     (fallback_path WorkReport))
    -> ImplementationSummary
    (if
      (let* ((ready-result
               (command-result run_checks
                 :argv ("python" "scripts/run_checks.py" report_path)
                 :returns ReadyResult)))
        ready-result.ready)
      (record ImplementationSummary
        :report report_path)
      (record ImplementationSummary
        :report fallback_path))))
