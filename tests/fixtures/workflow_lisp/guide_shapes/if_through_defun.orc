(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule guide_shapes/if_through_defun)
  (export run)
  (defrecord Box (n Int))
  (defrecord Pair (a Box) (b Box))
  (defproc fetch ((n Int)) -> Box
    (command-result fetch :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "fetch" n) :returns Box))
  (defun choose ((pair Pair) (branch String)) -> Box
    (if (= branch "A") pair.a pair.b))
  (defproc pick ((pair Pair) (branch String)) -> Box
    (let* ((current (choose pair branch))
           (got (fetch current.n)))
      (record Box :n (+ got.n current.n))))
  (defworkflow run ((branch String)) -> Box
    (loop/recur ((state (loop-state (pair Pair (record Pair :a (record Box :n 1) :b (record Box :n 2)))))) :max 2
      :on-exhausted (record Box :n 0)
      (let* ((got (pick state.pair branch)))
        (done got)))))
