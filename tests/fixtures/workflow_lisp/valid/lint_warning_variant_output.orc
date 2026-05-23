(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lint_warning_variant_output)
  (export orchestrate)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defenum ImplementationState
    COMPLETED
    BLOCKED)
  (defunion ImplementationAttempt
    (COMPLETED
      (implementation_state ImplementationState))
    (BLOCKED
      (implementation_state ImplementationState)))
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> ImplementationAttempt
    (provider-result providers.execute
      :prompt prompts.implementation.execute
      :inputs (report_path)
      :returns ImplementationAttempt)))
