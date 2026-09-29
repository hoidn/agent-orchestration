(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/three_call_sites)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defworkflow run () -> Box
    (let* ((a (fetch 1))
           (b (fetch 2))
           (c (fetch 3)))
      (record Box :n (+ a.n b.n c.n)))))
