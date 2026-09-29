(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/d1_if_in_if)
  (export run)
  (defrecord Box (n Int))
  (defworkflow run ((a Bool) (b Bool)) -> Box
    (if a
      (if b (command-result fetch :argv ("python" "probe.py" "fetch" "5") :returns Box) (record Box :n 1))
      (record Box :n 0))))
