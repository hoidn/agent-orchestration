(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defworkflow provider_attempt
    ((provider Provider)
     (prompt Prompt)
     (input ChecksResult)
     (report_path WorkReport))
    -> ImplementationState
    (provider-result provider
      :prompt prompt
      :inputs (input report_path)
      :returns ImplementationState))
  (defworkflow command_checks
    ((report_path WorkReport))
    -> ChecksResult
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns ChecksResult))
  (defworkflow orchestrate
    ((provider Provider)
     (prompt Prompt)
     (input ChecksResult)
     (report_path WorkReport))
    -> ImplementationState
    (call provider_attempt
      :provider provider
      :prompt prompt
      :input input
      :report_path report_path)))
