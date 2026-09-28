(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule gu/narrow)
  (import gu/lib :only (Item))
  (export narrow same-tag)
  (defunion Alpha :forall (T)
    (ONE (value T)))
  (defunion Beta :forall (T)
    (ONE (value T)))
  (defrecord Flag
    (same Bool))
  (defproc narrow
    ((alpha Alpha[Item]))
    -> Alpha[Item]
    :effects ()
    (match alpha
      ((ONE one) one)))
  (defproc same-tag
    ((left Alpha[Item])
     (right Alpha[Item]))
    -> Flag
    :effects ()
    (record Flag :same (= left.variant right.variant))))
