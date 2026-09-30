(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/effect_argument)
  (export run)
  (defrecord Box (n Int))
  (defproc bump ((n Int)) -> Box
    :effects ((uses-command bump))
    :lowering inline
    (command-result bump :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "bump" n) :returns Box))
  (defproc fetch ((box Box)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "fetch" box.n) :returns Box))
  (defworkflow run () -> Box
    (fetch (bump 26))))
