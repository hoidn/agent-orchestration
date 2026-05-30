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
    (let* ((fixed input.label))
      (let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput
                  :captures (fixed)
                  (command-result run_checks
                    :argv ("python" "scripts/run_checks.py" item.report fixed)
                    :returns WorkflowOutput))
        (invoke-runner (proc-ref run-local) input)))))
