(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule gu/narrow)
  (import gu/lib :only (Item))
  (export narrow)
  (defunion Alpha :forall (T)
    (ONE (value T)))
  (defunion Beta :forall (T)
    (ONE (value T)))
  (defproc narrow
    ((alpha Alpha[Item]))
    -> Alpha[Item]
    :effects ()
    (match alpha
      ((ONE one) one))))
