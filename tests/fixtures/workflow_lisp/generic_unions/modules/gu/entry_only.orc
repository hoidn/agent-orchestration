(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule gu/entry_only)
  (import gu/lib :only (Outcome lib-ok))
  (export entry)
  (defproc relay
    ((outcome Outcome[Int String]))
    -> Outcome[Int String]
    outcome)
  (defproc relay-ok
    ((n Int))
    -> Outcome[Int String]
    (relay (lib-ok n)))
  (defworkflow entry
    ((n Int))
    -> Outcome[Int String]
    (relay-ok n)))
