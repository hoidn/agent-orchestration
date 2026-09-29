(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/d3_loop_in_if)
  (export run)
  (defrecord Box (n Int))
  (defrecord Out (n Int))
  (defworkflow run ((go Bool)) -> Out
    (if go
      (loop/recur :max 3 :state (record Box :n 0)
        (fn (state)
          (let* ((c (command-result fetch :argv ("python" "probe.py" "fetch" "2") :returns Box)))
            (if (< c.n 2) (continue (record Box :n c.n)) (done (record Out :n c.n))))))
      (record Out :n 0))))
