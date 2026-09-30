(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/identity_base)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defproc keep ((a Box) (b Box)) -> Box :effects () :lowering inline b)
  (defproc touch ((b Box)) -> Box :effects () :lowering inline b)
  (defproc step ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (let* ((a (fetch n)))
      (keep a (fetch (+ n 1)))))
  (defworkflow run () -> Box
    (let* ((x (step 10))
           (y (step 20)))
      (keep (touch x) (fetch (+ y.n 5))))))
