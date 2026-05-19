(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (report WorkReport))
  (defproc build-checks
    ((report_path WorkReport))
    -> ChecksResult
    :effects
      ((uses-command run_checks))
    :lowering auto
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns ChecksResult))
  (defworkflow first
    ((report_path WorkReport))
    -> ChecksResult
    (build-checks report_path))
  (defworkflow second
    ((report_path WorkReport))
    -> ChecksResult
    (build-checks report_path)))
