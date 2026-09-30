(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/list_in_state_update)
  (export run)
  (defrecord Box (n Int))
  (defrecord Pair (a Box) (b Box))
  (defrecord Trial (parents List[Box]) (n Int))
  (defrecord Walk (pair Pair) (history List[Trial]) (turn Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "tests/fixtures/workflow_lisp/guide_shapes/probe.py" "fetch" n) :returns Box))
  (defun choose ((pair Pair) (branch String)) -> Box
    (if (= branch "A") pair.a pair.b))
  (defproc pick ((walk Walk) (branch String)) -> Walk
    :effects ((uses-command fetch))
    :lowering inline
    (let* ((current (choose walk.pair branch))
           (got (fetch current.n)))
      (record-update walk
        :turn (+ walk.turn 1)
        :history (list/append walk.history
                   (record Trial :parents (if (= branch "C") (list walk.pair.a) (list current)) :n got.n)))))
  (defworkflow run ((branch String)) -> Walk
    (loop/recur :max 3
      :state (record Walk :pair (record Pair :a (record Box :n 1) :b (record Box :n 2)) :history (list) :turn 0)
      :on-exhausted state
      (fn (state)
        (let* ((next (pick state branch)))
          (if (< next.turn 2) (continue next) (done next)))))))
