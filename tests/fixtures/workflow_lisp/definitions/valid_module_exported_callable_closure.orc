(defmodule neurips.closure
  (:language workflow-lisp "0.1")
  (:target-dsl "2.14")

  (export
    RunInput
    RunResult
    run_public)

  (defrecord RunInput
    (prompt Prompt))

  (defrecord RunResult
    (status String))

  (defproc build_status
    ((inputs RunInput))
    ->
    RunResult
    (record RunResult
      :status "built"))

  (defworkflow private_helper ((inputs RunInput)) -> RunResult
    (call build_status
      :inputs inputs))

  (defworkflow run_public ((inputs RunInput)) -> RunResult
    (call private_helper
      :inputs inputs))

  (defworkflow internal_only ((inputs RunInput)) -> RunResult
    (record RunResult
      :status "internal")))
