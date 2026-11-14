(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord WorkflowInput
    (report WorkReport))
  (defrecord WorkflowOutput
    (report WorkReport))
  (defproc helper
    ((input WorkflowInput))
    -> WorkflowOutput
    (record WorkflowOutput
      :report input.report))
  (defproc forward-helper
    ((runner ProcRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    (helper input))
  (defworkflow entry
    ((input WorkflowInput))
    -> WorkflowOutput
    (forward-helper
      helper
      input)))
