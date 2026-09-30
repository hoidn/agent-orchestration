(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/if_over_scalars)
  (export run)
  (defrecord Box (n Int))
  (defrecord Pair (a Box) (b Box))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "fetch" n) :returns Box))
  (defproc pick ((pair Pair) (branch String)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (let* ((n (if (= branch "A") pair.a.n pair.b.n))
           (got (fetch n)))
      (record Box :n (+ got.n n))))
  (defworkflow run ((branch String)) -> Box
    (loop/recur :max 2
      :state (loop-state (pair Pair (record Pair :a (record Box :n 1) :b (record Box :n 2))))
      :on-exhausted (record Box :n 0)
      (fn (state)
        (let* ((got (pick state.pair branch)))
          (done got))))))
