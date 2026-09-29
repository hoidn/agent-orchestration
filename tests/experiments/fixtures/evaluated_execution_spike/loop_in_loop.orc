(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/loop_in_loop)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defworkflow run () -> Box
    (loop/recur :max 3
      :state (loop-state (i Int 0) (total Int 0))
      :on-exhausted (record Box :n outer.total)
      (fn (outer)
        (let* ((inner (loop/recur :max 3
                        :state (loop-state (j Int 0))
                        :on-exhausted (record Box :n 0)
                        (fn (st)
                          (let* ((b (fetch (+ (* outer.i 10) st.j))))
                            (if (< st.j 1) (continue (loop-state :like st :j (+ st.j 1))) (done b))))))
               (total (+ outer.total inner.n)))
          (if (< outer.i 1)
            (continue (loop-state :like outer :i (+ outer.i 1) :total total))
            (done (record Box :n total))))))))
