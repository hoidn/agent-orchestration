(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/map_effect_procedure_body)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "fetch" n) :returns Box))
  (defworkflow run ((items List[Int])) -> List[Box]
    (list/map-effect ((item items)) :max 4
      (fetch item))))
