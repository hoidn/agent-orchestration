(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defworkflow command_checks
    ((report_path WorkReport))
    -> ChecksResult
    (command-result run_checks
      :argv ("bash" "-c" "echo ok")
      :returns ChecksResult)))
