(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/loop_in_loop)
  (export run)
  (defrecord Box (n Int))
  (defproc bump ((n Int)) -> Box
    :effects ((uses-command bump))
    :lowering inline
    (command-result bump :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "bump" n) :returns Box))
  (defworkflow run () -> Box
    (loop/recur :max 3
      :state (loop-state (round Int 0) (total Int 0))
      :on-exhausted (record Box :n outer.total)
      (fn (outer)
        (let* ((inner (loop/recur :max 5
                        :state (record Box :n 0)
                        :on-exhausted state
                        (fn (state)
                          (let* ((next (bump state.n)))
                            (if (< next.n 2) (continue next) (done next))))))
               (total (+ outer.total inner.n)))
          (if (< outer.round 1)
            (continue (loop-state :like outer :round (+ outer.round 1) :total total))
            (done (record Box :n total))))))))
