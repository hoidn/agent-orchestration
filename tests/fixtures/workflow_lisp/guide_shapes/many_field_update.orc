(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/many_field_update)
  (export run)
  (defrecord Box (n Int))
  (defrecord Search
    (turn Int) (best Int) (worst Int) (sum Int) (tries Int) (wins Int)
    (losses Int) (streak Int) (last Int) (spread Int) (gain Int) (improved Bool))
  (defproc bump ((n Int)) -> Box
    :effects ((uses-command bump))
    :lowering inline
    (command-result bump :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "bump" n) :returns Box))
  (defworkflow run () -> Search
    (loop/recur :max 5
      :state (record Search :turn 0 :best 0 :worst 0 :sum 0 :tries 0 :wins 0
               :losses 0 :streak 0 :last 0 :spread 0 :gain 0 :improved false)
      :on-exhausted state
      (fn (state)
        (let* ((got (bump state.turn))
               (score (- (* got.n got.n) (* 2 state.turn)))
               (better (> score state.best))
               (next (record-update state
                       :turn got.n
                       :best (if better score state.best)
                       :worst (if better state.worst score)
                       :sum (+ state.sum score)
                       :tries (+ state.tries 1)
                       :wins (if better (+ state.wins 1) state.wins)
                       :losses (if better state.losses (+ state.losses 1))
                       :streak (if better (+ state.streak 1) 0)
                       :last score
                       :spread (- (max score state.best) (min score state.worst))
                       :gain (if better (- score state.best) 0)
                       :improved better)))
          (if (< got.n 3) (continue next) (done next)))))))
