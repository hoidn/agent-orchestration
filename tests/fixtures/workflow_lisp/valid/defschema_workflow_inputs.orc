(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule defschema_workflow_inputs)
  (export summarize)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defschema ReportTargets
    (execution_report WorkReport))
  (defschema ReviewTargets
    (status String)
    (:include ReportTargets)
    (review_report WorkReport))
  (defrecord WorkflowInputs
    (:include ReviewTargets))
  (defrecord WorkflowSummary
    (status String)
    (:include ReportTargets))
  (defworkflow build-summary
    ((input WorkflowInputs))
    -> WorkflowSummary
    (loop/recur
      :max 1
      :state input
      (fn (state)
        (done
          (record WorkflowSummary
            :status state.status
            :execution_report state.execution_report)))))
  (defworkflow summarize
    ((input WorkflowInputs))
    -> WorkflowSummary
    (call build-summary
      :input input)))
