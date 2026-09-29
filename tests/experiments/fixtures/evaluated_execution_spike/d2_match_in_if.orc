(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/d2_match_in_if)
  (export run)
  (defrecord Box (n Int))
  (defunion Gate (OPEN (n Int)) (SHUT (n Int)))
  (defworkflow run ((a Bool)) -> Box
    (if a
      (match (command-result gate :argv ("python" "probe.py" "gate" "3") :returns Gate)
        ((OPEN o) (command-result fetch :argv ("python" "probe.py" "fetch" "4") :returns Box))
        ((SHUT s) (record Box :n 0)))
      (record Box :n 1))))
