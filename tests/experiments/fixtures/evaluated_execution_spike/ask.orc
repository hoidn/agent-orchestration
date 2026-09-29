(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/ask)
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defworkflow run () -> Box
    (let* ((first (fetch 1))
           (reply (request-input "Go on?")))
      (match reply
        ((ANSWERED a) (fetch (+ first.n 1)))
        ((CANCELLED c) (record Box :n 0))))))
