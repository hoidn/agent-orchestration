(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defrecord WorkflowOutput
    (status String))
  (defworkflow entry
    ((attempt_ids List[Int]))
    -> WorkflowOutput
    (record WorkflowOutput
      :status "ok")))
