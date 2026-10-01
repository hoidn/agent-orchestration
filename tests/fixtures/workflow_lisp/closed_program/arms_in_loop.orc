(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/arms_in_loop)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defunion Turn (FIRST (n Int)) (SECOND (n Int)) (THIRD (n Int)))
  (defworkflow run () -> Int
    (loop/recur :max 4
      :state (loop-state (i Int 0) (total Int 0))
      :on-exhausted state.total
      (fn (state)
        (let* ((turn (if (= state.i 0)
                       (variant Turn FIRST :n 1)
                       (if (= state.i 1)
                         (variant Turn SECOND :n 2)
                         (if (= state.i 2) (variant Turn THIRD :n 3) (variant Turn FIRST :n 4)))))
               (got (match turn
                      ((FIRST f) (fetch f.n))
                      ((SECOND s) (fetch s.n))
                      ((THIRD t) (fetch t.n)))))
          (if (< state.i 3)
            (continue (loop-state :like state :i (+ state.i 1) :total (+ state.total got.n)))
            (done (+ state.total got.n))))))))
