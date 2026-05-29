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
  (defproc use-runner
    ((runner ProcRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (runner input))
  (defproc loop-helper
    ((input WorkflowInput))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (use-runner (proc-ref loop-helper) input))
  (defworkflow entry
    ((input WorkflowInput))
    -> WorkflowOutput
    (use-runner (proc-ref loop-helper) input)))
