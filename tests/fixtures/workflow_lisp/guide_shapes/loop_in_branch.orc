(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/loop_in_branch)
  (export run)
  (defrecord Box (n Int))
  (defproc bump ((n Int)) -> Box
    :effects ((uses-command bump))
    :lowering inline
    (command-result bump :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "bump" n) :returns Box))
  (defworkflow run ((go Bool)) -> Box
    (if go
      (loop/recur :max 5
        :state (record Box :n 0)
        :on-exhausted state
        (fn (state)
          (let* ((next (bump state.n)))
            (if (< next.n 3) (continue next) (done next)))))
      (record Box :n 0))))
