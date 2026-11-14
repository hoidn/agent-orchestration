(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule guide_shapes/on_exhausted_float_in_state)
  (export run)
  (defworkflow run ((base Float)) -> Float
    (loop/recur ((state (loop-state (turn Int 0) (fallback Float (+ base base))))) :max 1
      :on-exhausted state.fallback
      (if (= state.turn 0)
        (continue (loop-state :like state :turn (+ state.turn 1)))
        (done base)))))
