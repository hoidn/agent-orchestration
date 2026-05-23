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
  (defworkflow echo-helper
    ((input WorkflowInput))
    -> WorkflowOutput
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" input.report)
      :returns WorkflowOutput))
  (defworkflow call-runner
    ((runner WorkflowRef[WorkflowInput -> WorkflowOutput])
     (input WorkflowInput))
    -> WorkflowOutput
    (call runner
      :input input))
  (defworkflow entry
    ((input WorkflowInput))
    -> WorkflowOutput
    (call call-runner
      :runner echo-helper
      :input input)))
