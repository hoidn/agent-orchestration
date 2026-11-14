(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule guide_shapes/loop_in_called_workflow)
  (export run)
  (defrecord Box (n Int))
  (defproc bump ((n Int)) -> Box
    (command-result bump :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "bump" n) :returns Box))
  (defworkflow count-up () -> Box
    (loop/recur ((state (record Box :n 0))) :max 5
      :on-exhausted state
      (let* ((next (bump state.n)))
        (if (< next.n 3) (continue next) (done next)))))
  (defworkflow run ((go Bool)) -> Box
    (if go
      (call count-up)
      (record Box :n 0))))
