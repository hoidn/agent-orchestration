(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/commands_in_sequence)
  (export run)
  (defrecord Box (n Int))
  (defworkflow run ((items List[Int])) -> List[Box]
    (list/map-effect ((item items)) :max 4
      (command-result fetch :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "fetch" item) :returns Box))))
