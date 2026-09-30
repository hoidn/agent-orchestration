(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/record_fields_command_input)
  (export run)
  (defrecord Box (n Int))
  (defworkflow run () -> Box
    (let* ((box (record Box :n 4)))
      (command-result fetch :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "fetch" box.n) :returns Box))))
