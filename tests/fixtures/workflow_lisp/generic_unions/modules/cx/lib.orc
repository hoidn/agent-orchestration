(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule cx/lib)
  (export Tagged keep)
  (defunion Tagged :forall (Tag)
    (VAL (value Int)))
  (defproc keep
    :forall (T)
    ((value T))
    -> T
    :effects ()
    :lowering inline
    value))
