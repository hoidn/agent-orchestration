(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defunion CallerOutcome
    (BLOCKED
      (status String)
      (message String)))
  (defrecord WorkflowOutput
    (status String))
  (defproc status-from-outcome
    :forall (T)
    ((value T))
    :where ((T has-union-variant APPROVED (status String) (message String))
            (T has-union-variant BLOCKED (status String) (message String)))
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
      (variant CallerOutcome BLOCKED
        :status "BLOCKED"
        :message "blocked"))))
