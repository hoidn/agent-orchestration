(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath EscapedReport
    :kind relpath
    :under "../escape"
    :must-exist true)
  (defrecord EscapedSummary
    (status String)
    (report EscapedReport))
  (defworkflow escaped-summary
    ((report_path EscapedReport))
    -> EscapedSummary
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns EscapedSummary)))
