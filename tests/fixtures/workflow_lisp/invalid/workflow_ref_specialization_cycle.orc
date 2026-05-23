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
  (defworkflow use-runner
    ((runner WorkflowRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    (call runner
      :input input))
  (defworkflow loop-helper
    ((input WorkflowInput))
    -> WorkflowOutput
    (call use-runner
      :runner (workflow-ref loop-helper)
      :input input))
  (defworkflow entry
    ((input WorkflowInput))
    -> WorkflowOutput
    (call use-runner
      :runner (workflow-ref loop-helper)
      :input input)))
