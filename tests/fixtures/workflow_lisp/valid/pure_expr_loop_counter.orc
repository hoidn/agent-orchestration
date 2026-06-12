(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule pure_expr_loop_counter)
  (export run-counter)
  (defrecord CounterState
    (count Int)
    (label String))
  (defrecord CounterResult
    (count Int)
    (label String))
  (defworkflow run-counter
    ()
    -> CounterResult
    (loop/recur
      :max 6
      :state (record CounterState
               :count 0
               :label "seed")
      (fn (state)
        (if (< state.count 3)
          (continue
            (record-update state
              :count (+ state.count 1)
              :label "tick"))
          (done
            (record CounterResult
              :count state.count
              :label state.label)))))))
