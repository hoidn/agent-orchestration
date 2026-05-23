(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule workflow_refs/imported_entry)
  (import workflow_refs/types :only (WorkflowInput WorkflowOutput))
  (import workflow_refs/imported_helper :as helper :only (echo-helper))
  (export call-runner entry)
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
      :runner helper.echo-helper
      :input input)))
