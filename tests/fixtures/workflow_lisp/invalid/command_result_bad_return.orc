(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defworkflow command_checks
    ((report_path WorkReport))
    -> ChecksResult
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns String)))
