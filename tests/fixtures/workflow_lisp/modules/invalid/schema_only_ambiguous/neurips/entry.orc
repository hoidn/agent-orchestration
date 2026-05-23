(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/entry)
  (import neurips/a :only (SharedTargets))
  (import neurips/b :only (SharedTargets))
  (export WorkflowInputs)
  (defrecord WorkflowInputs
    (:include SharedTargets)))
