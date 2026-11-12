(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule gu/entry_shadow)
  (import gu/lib :as lib :only (lib-ok))
  (export relay-ok)
  (defunion Outcome :forall (T E)
    (OK (value T))
    (ERROR (error E)))
  (defproc relay
    ((outcome Outcome[Int String]))
    -> Outcome[Int String]
    :effects ()
    outcome)
  (defproc relay-ok
    ((n Int))
    -> Outcome[Int String]
    :effects ()
    (relay (lib-ok n))))
