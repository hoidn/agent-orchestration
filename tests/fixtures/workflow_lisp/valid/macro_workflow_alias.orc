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
  (defrecord ImplementationSummary
    (report WorkReport))
  (defunion ImplementationState
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)))
  (defworkflow-alias command_checks
    ((report_path WorkReport))
    ChecksResult
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns ChecksResult))
  (defworkflow-alias provider_attempt
    ((input ChecksResult)
     (report_path WorkReport))
    ImplementationSummary
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (input report_path)
               :returns ImplementationState)))
      (match attempt
        ((COMPLETED completed)
         (record ImplementationSummary
           :report completed.execution_report))
        ((BLOCKED blocked)
         (record ImplementationSummary
           :report blocked.progress_report)))))
  (defmacro defworkflow-alias (name params return_type &body body)
    (defworkflow name
      params
      -> return_type
      (splice body))))
