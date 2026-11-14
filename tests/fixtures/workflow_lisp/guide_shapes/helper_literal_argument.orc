(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule guide_shapes/helper_literal_argument)
  (export run)
  (defrecord Box (n Int))
  (defrecord Pair (a Int) (b Int) (turn Int))
  (defproc step ((state Pair) (branch String)) -> Pair
    (let* ((got (command-result bump :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "bump" state.turn) :returns Box)))
      (if (= branch "A")
        (record-update state :a (+ state.a got.n) :turn got.n)
        (record-update state :b (+ state.b got.n) :turn got.n))))
  (defworkflow run () -> Pair
    (loop/recur ((state (record Pair :a 0 :b 0 :turn 0))) :max 5
      :on-exhausted state
      (if (< state.a state.b)
        (let* ((next (step state "A")))
          (if (< next.turn 4) (continue next) (done next)))
        (let* ((next (step state "B")))
          (if (< next.turn 4) (continue next) (done next)))))))
