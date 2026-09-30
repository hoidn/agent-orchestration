(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/on_exhausted_operator_in_state)
  (export run)
  (defworkflow run ((base Int)) -> Int
    (loop/recur :max 1
      :state (loop-state (turn Int 0) (fallback Int (+ base base)))
      :on-exhausted state.fallback
      (fn (state)
        (if (= state.turn 0)
          (continue (loop-state :like state :turn (+ state.turn 1)))
          (done base))))))
