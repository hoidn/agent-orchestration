(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule gu/entry_alias)
  (import gu/lib :as lib :only (Outcome lib-ok))
  (export entry)
  (defproc relay
    ((outcome lib.Outcome[Int String]))
    -> lib.Outcome[Int String]
    :effects ()
    outcome)
  (defproc relay-ok
    ((n Int))
    -> lib.Outcome[Int String]
    :effects ()
    (relay (lib-ok n)))
  (defworkflow entry
    ((n Int))
    -> lib.Outcome[Int String]
    (relay-ok n)))
