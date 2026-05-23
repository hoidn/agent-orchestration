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
  (defrecord WorkflowEnvelope
    (runner WorkflowRef[WorkflowInput -> WorkflowOutput]))
  (defworkflow echo-helper
    ((input WorkflowInput))
    -> WorkflowOutput
    (record WorkflowOutput
      :report input.report))
  (defworkflow entry
    ((runner WorkflowRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowEnvelope
    (record WorkflowEnvelope
      :runner runner)))
