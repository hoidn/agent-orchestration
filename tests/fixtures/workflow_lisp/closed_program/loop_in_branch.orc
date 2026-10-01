(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/loop_in_branch)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defworkflow run ((go Bool)) -> Box
    (if go
      (loop/recur :max 5
        :state (loop-state (n Int 0))
        :on-exhausted (record Box :n state.n)
        (fn (state)
          (let* ((b (fetch (+ state.n 1))))
            (if (< b.n 3) (continue (loop-state :like state :n b.n)) (done b)))))
      (record Box :n 0))))
