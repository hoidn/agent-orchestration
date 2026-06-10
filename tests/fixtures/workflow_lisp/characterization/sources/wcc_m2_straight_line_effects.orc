(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport :kind relpath :under "artifacts/work" :must-exist true)
  (defrecord ChecksResult (status String) (report WorkReport))
  (defrecord ImplementationSummary (report WorkReport))
  (defworkflow command-checks
    ((report_path WorkReport))
    -> ChecksResult
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns ChecksResult))
  (defworkflow provider-attempt
    ((input ChecksResult) (report_path WorkReport))
    -> ImplementationSummary
    (provider-result providers.execute
      :prompt prompts.implementation.execute
      :inputs (input report_path)
      :returns ImplementationSummary))
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> ImplementationSummary
    (let* ((checks (call command-checks :report_path report_path)))
      (call provider-attempt :input checks :report_path report_path))))
