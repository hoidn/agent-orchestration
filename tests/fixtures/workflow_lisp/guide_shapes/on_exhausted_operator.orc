(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule guide_shapes/on_exhausted_operator)
  (export run)
  (defworkflow run ((base Int)) -> Int
    (loop/recur ((state (loop-state (turn Int 0)))) :max 1
      :on-exhausted (+ base base)
      (if (= state.turn 0)
        (continue (loop-state :like state :turn (+ state.turn 1)))
        (done base)))))
