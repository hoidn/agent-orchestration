(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule workflow_refs/types)
  (export WorkReport WorkflowInput WorkflowOutput)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord WorkflowInput
    (report WorkReport))
  (defrecord WorkflowOutput
    (report WorkReport)))
