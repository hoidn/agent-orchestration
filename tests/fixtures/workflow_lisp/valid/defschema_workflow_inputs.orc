(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
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
    (loop/recur ((state input))
      :max 1
      (done
        (record WorkflowSummary
          :status state.status
          :execution_report state.execution_report))))
  (defworkflow summarize
    ((input WorkflowInputs))
    -> WorkflowSummary
    (call build-summary
      :input input)))
