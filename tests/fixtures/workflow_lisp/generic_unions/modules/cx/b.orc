(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule cx/b)
  (import cx/lib :only (Tagged))
  (export Item make-b)
  (defrecord Item
    (field_b Int))
  (defproc make-b
    ((n Int))
    -> Tagged[Item]
    (variant Tagged[Item] VAL :value n)))
