(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule guide_shapes/if_over_scalars)
  (export run)
  (defrecord Box (n Int))
  (defrecord Pair (a Box) (b Box))
  (defproc fetch ((n Int)) -> Box
    (command-result fetch :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "fetch" n) :returns Box))
  (defproc pick ((pair Pair) (branch String)) -> Box
    (let* ((n (if (= branch "A") pair.a.n pair.b.n))
           (got (fetch n)))
      (record Box :n (+ got.n n))))
  (defworkflow run ((branch String)) -> Box
    (loop/recur ((state (loop-state (pair Pair (record Pair :a (record Box :n 1) :b (record Box :n 2)))))) :max 2
      :on-exhausted (record Box :n 0)
      (let* ((got (pick state.pair branch)))
        (done got)))))
