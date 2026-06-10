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
  (defworkflow invalid-proof-use
    ((ready Bool)
     (report WorkReport)
     (fallback WorkReport))
    -> WorkflowOutput
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report)
               :returns Attempt)))
      (if ready
        (record WorkflowOutput
          :report attempt.execution_report)
        (record WorkflowOutput
          :report fallback)))))
