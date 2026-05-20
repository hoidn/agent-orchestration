(defmodule mvp.import.overlapping_qualifiers
  (:language workflow-lisp "0.1")
  (:target-dsl "2.14")

  (import remote)
  (import remote/workflows)

  (defworkflow run () -> String
    (call remote/workflows/run_phase :returns String)))
