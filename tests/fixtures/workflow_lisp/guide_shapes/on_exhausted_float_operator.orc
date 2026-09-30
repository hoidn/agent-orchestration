(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/on_exhausted_float_operator)
  (export run)
  (defworkflow run ((base Float)) -> Float
    (loop/recur :max 1
      :state (loop-state (turn Int 0))
      :on-exhausted (+ base base)
      (fn (state)
        (if (= state.turn 0)
          (continue (loop-state :like state :turn (+ state.turn 1)))
          (done base))))))
