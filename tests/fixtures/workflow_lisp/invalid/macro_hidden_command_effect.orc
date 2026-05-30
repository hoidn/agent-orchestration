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
  (emit-command-workflow command_checks)
  (defmacro emit-command-workflow (name)
    (defworkflow name
      ((report_path WorkReport))
      -> ChecksResult
      (command-result run_checks
        :argv ("python" "scripts/run_checks.py" report_path)
        :returns ChecksResult))))
