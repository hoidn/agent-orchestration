(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule nested/imported-branch)
  (import workflow_refs/types :only (WorkReport WorkflowInput WorkflowOutput))
  (import workflow_refs/imported_helper :as helper :only (echo-helper))
  (defunion Attempt
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)))
  (defworkflow entry
    ((report WorkReport))
    -> WorkflowOutput
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report)
               :returns Attempt)))
      (match attempt
        ((COMPLETED completed)
         (call helper.echo-helper
           :input (record WorkflowInput
                    :report completed.execution_report)))
        ((BLOCKED blocked)
         (record WorkflowOutput
           :report blocked.progress_report))))))
