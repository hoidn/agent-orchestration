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
  (defproc helper
    ((input WorkflowInput))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (record WorkflowOutput
      :report input.report))
  (defproc forward-helper
    ((runner ProcRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    :effects ((uses-command run_checks))
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" input.report)
      :returns WorkflowOutput))
  (defworkflow entry
    ((input WorkflowInput))
    -> WorkflowOutput
    (forward-helper
      (proc-ref helper)
      input)))
