(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/procedures)
  (import neurips/types :only (WorkReport ChecksResult))
  (export build-checks)
  (defproc build-checks
    ((report_path WorkReport))
    -> ChecksResult
    :effects ((uses-command run_checks))
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns ChecksResult)))
