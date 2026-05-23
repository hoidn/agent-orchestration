(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/entry)
  (import neurips/mid/bridge :only (ExtendedFields))
  (export WorkflowInputs)
  (defrecord WorkflowInputs
    (:include ExtendedFields)
    (review_report String)))
