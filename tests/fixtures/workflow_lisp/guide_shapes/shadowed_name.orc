(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/shadowed_name)
  (export run)
  (defrecord Box (n Int))
  (defproc bump ((n Int)) -> Box
    :effects ((uses-command bump))
    :lowering inline
    (command-result bump :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "bump" n) :returns Box))
  (defworkflow run () -> Int
    (let* ((b (bump 1))
           (total (+ b.n (let* ((b (bump 10))) b.n))))
      (+ total b.n))))
