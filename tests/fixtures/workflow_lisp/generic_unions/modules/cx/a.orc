(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule cx/a)
  (import cx/lib :only (Tagged))
  (export Item make-a)
  (defrecord Item
    (field_a Int))
  (defproc make-a
    ((n Int))
    -> Tagged[Item]
    (variant Tagged[Item] VAL :value n)))
