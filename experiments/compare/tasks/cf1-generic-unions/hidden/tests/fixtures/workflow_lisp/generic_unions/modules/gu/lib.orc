(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule gu/lib)
  (export Outcome Item lib-ok)
  (defunion Outcome :forall (T E)
    (OK (value T))
    (ERROR (error E)))
  (defrecord Item
    (label String))
  (defproc lib-ok
    ((n Int))
    -> Outcome[Int String]
    :effects ()
    (variant Outcome[Int String] OK :value n)))
