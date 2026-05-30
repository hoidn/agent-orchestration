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
  (defproc invoke-runner
    ((runner ProcRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (runner input))
  (defworkflow entry
    ((input WorkflowInput))
    -> WorkflowOutput
    (let* ((runner (proc-ref %let-proc.entry.run-local.fake)))
      (invoke-runner runner input))))
