(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/list_in_state_update)
  (export run)
  (defrecord Box (n Int))
  (defrecord Pair (a Box) (b Box))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "fetch" n) :returns Box))
  (defrecord Out (n Int) (parents List[Box]))
  (defrecord Walk (pair Pair) (out Out))
  (defun choose ((pair Pair) (branch String)) -> Box
    (if (= branch "A") pair.a pair.b))
  (defproc pick ((walk Walk) (branch String)) -> Walk
    :effects ((uses-command fetch))
    :lowering inline
    (let* ((current (choose walk.pair branch))
           (got (fetch current.n)))
      (record-update walk
        :out (record Out :n got.n :parents (if (= branch "C") (list walk.pair.b) (list current))))))
  (defworkflow run ((branch String)) -> Out
    (loop/recur :max 2
      :state (record Walk :pair (record Pair :a (record Box :n 1) :b (record Box :n 2))
               :out (record Out :n 0 :parents (list)))
      :on-exhausted state.out
      (fn (state)
        (let* ((next (pick state branch)))
          (done next.out))))))
