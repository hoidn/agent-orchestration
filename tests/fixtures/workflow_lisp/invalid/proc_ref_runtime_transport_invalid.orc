(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defrecord WorkflowInput
    (value String))
  (defrecord WorkflowOutput
    (value String))
  (defproc helper
    ((input WorkflowInput))
    -> WorkflowOutput
    (record WorkflowOutput
      :value input.value))
  (defworkflow entry
    ((runner ProcRef[WorkflowInput -> WorkflowOutput]))
    -> WorkflowOutput
    (record WorkflowOutput
      :value "ok")))
