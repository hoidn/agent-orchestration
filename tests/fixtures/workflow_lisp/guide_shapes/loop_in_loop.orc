(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule guide_shapes/loop_in_loop)
  (export run)
  (defrecord Box (n Int))
  (defproc bump ((n Int)) -> Box
    (command-result bump :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "bump" n) :returns Box))
  (defworkflow run () -> Box
    (loop/recur ((outer (loop-state (round Int 0) (total Int 0)))) :max 3
      :on-exhausted (record Box :n outer.total)
      (let* ((inner (loop/recur ((state (record Box :n 0))) :max 5
                      :on-exhausted state
                      (let* ((next (bump state.n)))
                        (if (< next.n 2) (continue next) (done next)))))
             (total (+ outer.total inner.n)))
        (if (< outer.round 1)
          (continue (loop-state :like outer :round (+ outer.round 1) :total total))
          (done (record Box :n total)))))))
