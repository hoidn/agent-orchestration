(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule source)
  (export orchestrate)
  (defenum Decision APPROVE REJECT)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (decision Decision)
    (approved Bool)
    (report WorkReport))
  (defworkflow internal-phase
    ((report_path WorkReport))
    -> ChecksResult
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns ChecksResult))
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> ChecksResult
    (call internal-phase :report_path report_path)))
