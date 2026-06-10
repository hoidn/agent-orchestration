(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord WorkflowInput
    (report WorkReport))
  (defrecord WorkflowOutput
    (report WorkReport))
  (defunion Attempt
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)))
  (defworkflow summarize-completed
    ((input WorkflowInput))
    -> WorkflowOutput
    (call echo-helper
      :input input))
  (defworkflow echo-helper
    ((input WorkflowInput))
    -> WorkflowOutput
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" input.report)
      :returns WorkflowOutput))
  (defworkflow entry
    ((report WorkReport))
    -> WorkflowOutput
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report)
               :returns Attempt)))
      (match attempt
        ((COMPLETED completed)
         (call summarize-completed
           :input (record WorkflowInput
                    :report completed.execution_report)))
        ((BLOCKED blocked)
         (record WorkflowOutput
           :report blocked.progress_report))))))
