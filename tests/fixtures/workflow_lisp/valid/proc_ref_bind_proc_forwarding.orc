(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord WorkflowInput
    (report WorkReport)
    (label String))
  (defrecord WorkflowOutput
    (report WorkReport))
  (defproc helper
    ((fixed String)
     (input WorkflowInput))
    -> WorkflowOutput
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" input.report fixed)
      :returns WorkflowOutput))
  (defproc invoke-runner
    ((runner ProcRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    (runner input))
  (defproc forward-runner
    ((runner ProcRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    (invoke-runner runner input))
  (defworkflow entry
    ((input WorkflowInput))
    -> WorkflowOutput
    (let* ((bound (bind-proc (proc-ref helper)
                    :fixed input.label)))
      (forward-runner bound input))))
