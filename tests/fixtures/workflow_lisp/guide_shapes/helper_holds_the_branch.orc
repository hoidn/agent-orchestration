(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule guide_shapes/helper_holds_the_branch)
  (export run)
  (defrecord Box (n Int))
  (defrecord Pair (a Int) (b Int) (turn Int))
  (defproc step ((state Pair)) -> Pair
    (let* ((got (command-result bump :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "bump" state.turn) :returns Box)))
      (if (< state.a state.b)
        (record-update state :a (+ state.a got.n) :turn got.n)
        (record-update state :b (+ state.b got.n) :turn got.n))))
  (defworkflow run () -> Pair
    (loop/recur ((state (record Pair :a 0 :b 0 :turn 0))) :max 5
      :on-exhausted state
      (let* ((next (step state)))
        (if (< next.turn 4) (continue next) (done next))))))
