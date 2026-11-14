(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule guide_shapes/on_exhausted_pure_proc)
  (export run)
  (defrecord Box (n Int))
  (defrecord Outcome (n Int) (status String))
  (defproc bump ((n Int)) -> Box
    (command-result bump :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "bump" n) :returns Box))
  (defproc outcome ((box Box) (status String)) -> Outcome
    (record Outcome :n box.n :status status))
  (defworkflow run () -> Outcome
    (loop/recur ((state (record Box :n 0))) :max 2
      :on-exhausted (outcome state "exhausted")
      (let* ((next (bump state.n)))
        (if (< next.n 5) (continue next) (done (outcome next "done")))))))
