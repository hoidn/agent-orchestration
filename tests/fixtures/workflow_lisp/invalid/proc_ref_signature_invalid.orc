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
  (defrecord WrongInput
    (report WorkReport)
    (title String))
  (defproc helper
    ((input WorkflowInput))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (record WorkflowOutput
      :report input.report))
  (defproc wrong-helper
    ((input WrongInput))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (record WorkflowOutput
      :report input.report))
  (defproc forward-helper
    ((runner ProcRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (helper input))
  (defworkflow entry
    ((input WorkflowInput))
    -> WorkflowOutput
    (forward-helper
      (proc-ref wrong-helper)
      input)))
