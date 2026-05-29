(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
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
    :effects ((uses-command run_checks))
    :lowering inline
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" input.report fixed)
      :returns WorkflowOutput))
  (defproc invoke-runner
    ((runner ProcRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (runner input))
  (defproc forward-runner
    ((runner ProcRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (invoke-runner runner input))
  (defworkflow entry
    ((input WorkflowInput))
    -> WorkflowOutput
    (let* ((bound (bind-proc (proc-ref helper)
                    :fixed input.label)))
      (forward-runner bound input))))
