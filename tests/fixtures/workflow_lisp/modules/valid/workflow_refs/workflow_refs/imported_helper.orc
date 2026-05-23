(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule workflow_refs/imported_helper)
  (import workflow_refs/types :only (WorkflowInput WorkflowOutput))
  (export echo-helper)
  (defworkflow echo-helper
    ((input WorkflowInput))
    -> WorkflowOutput
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" input.report)
      :returns WorkflowOutput)))
