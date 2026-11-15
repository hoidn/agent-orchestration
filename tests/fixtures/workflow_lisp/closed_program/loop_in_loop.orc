(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/loop_in_loop)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defworkflow run () -> Box
    (loop/recur ((outer (loop-state (i Int 0) (total Int 0)))) :max 3
      :on-exhausted (record Box :n outer.total)
      (let* ((inner (loop/recur ((st (loop-state (j Int 0)))) :max 3
                      :on-exhausted (record Box :n 0)
                      (let* ((b (fetch (+ (* outer.i 10) st.j))))
                        (if (< st.j 1) (continue (loop-state :like st :j (+ st.j 1))) (done b)))))
             (total (+ outer.total inner.n)))
        (if (< outer.i 1)
          (continue (loop-state :like outer :i (+ outer.i 1) :total total))
          (done (record Box :n total)))))))
