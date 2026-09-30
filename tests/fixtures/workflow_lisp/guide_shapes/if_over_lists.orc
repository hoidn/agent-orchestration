(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/if_over_lists)
  (export run)
  (defrecord Box (n Int))
  (defrecord Pair (a Box) (b Box))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "fetch" n) :returns Box))
  (defrecord Out (n Int) (parents List[Box]))
  (defproc pick ((pair Pair) (branch String)) -> Out
    :effects ((uses-command fetch))
    :lowering inline
    (let* ((current (if (= branch "A") pair.a pair.b))
           (parents (if (= branch "C") (list pair.b) (list current)))
           (got (fetch current.n)))
      (record Out :n got.n :parents parents)))
  (defworkflow run ((branch String)) -> Out
    (loop/recur :max 2
      :state (loop-state (pair Pair (record Pair :a (record Box :n 1) :b (record Box :n 2))))
      :on-exhausted (record Out :n 0 :parents (list))
      (fn (state)
        (let* ((got (pick state.pair branch)))
          (done got))))))
