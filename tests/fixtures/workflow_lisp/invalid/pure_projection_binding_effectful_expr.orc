(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule pure_projection_binding_effectful_expr)
  (export Result project run)

  (defrecord Result
    (status String))

  (defworkflow project
    ((input Result))
    -> Result
    (let* ((status
             (string/concat input.status "-projected")))
      (record Result
        :status status)))

  (defworkflow run
    ((reason String))
    -> Result
    (call project
      :input (command-result run_checks
               :argv ("python" "scripts/run_checks.py" reason)
               :returns Result))))
