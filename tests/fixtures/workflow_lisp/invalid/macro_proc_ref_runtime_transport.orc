(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defrecord WorkflowInput
    (value String))
  (defrecord WorkflowOutput
    (value String))
  (emit-proc-ref-workflow entry)
  (defmacro emit-proc-ref-workflow (name)
    (defworkflow name
      ((runner ProcRef[WorkflowInput -> WorkflowOutput]))
      -> WorkflowOutput
      (record WorkflowOutput
        :value "ok"))))
