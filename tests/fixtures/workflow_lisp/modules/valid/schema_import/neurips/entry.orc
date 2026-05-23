(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/entry)
  (import neurips/schemas :only (WorkReport ReviewTargets))
  (export WorkflowInputs)
  (defrecord WorkflowInputs
    (:include ReviewTargets)
    (review_report WorkReport)))
