(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defunion CallerOutcome
    (APPROVED
      (status String))
    (BLOCKED
      (status String)))
  (defrecord WorkflowOutput
    (status String))
  (defproc status-from-outcome
    :forall (T)
    ((value T))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (match value
      ((APPROVED approved)
       (record WorkflowOutput :status approved.status))
      ((BLOCKED blocked)
       (record WorkflowOutput :status blocked.status))))
  (defworkflow run-outcome
    ()
    -> WorkflowOutput
    (status-from-outcome
      (variant CallerOutcome APPROVED
        :status "APPROVED"))))
