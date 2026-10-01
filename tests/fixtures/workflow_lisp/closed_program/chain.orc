(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/chain)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defworkflow run () -> Box
    (let* ((a (fetch 1))
           (b (fetch (+ a.n 10)))
           (c (fetch 3))
           (d (fetch (+ b.n 100)))
           (e (if (> a.n 0) (fetch 7) (fetch 8))))
      (record Box :n (+ a.n b.n c.n d.n e.n)))))
