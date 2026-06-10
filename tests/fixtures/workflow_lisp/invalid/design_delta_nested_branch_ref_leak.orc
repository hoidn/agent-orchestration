(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord WorkflowOutput
    (report WorkReport))
  (defunion Attempt
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)))
  (defworkflow invalid-branch-ref-leak
    ((report WorkReport))
    -> WorkflowOutput
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report)
               :returns Attempt))
           (selected
             (match attempt
               ((COMPLETED completed)
                (record WorkflowOutput
                  :report completed.execution_report))
               ((BLOCKED blocked)
                (record WorkflowOutput
                  :report blocked.progress_report)))))
      (record WorkflowOutput
        :report attempt.execution_report))))
