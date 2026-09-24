(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule uncalled_generic_function_specialization)
  (export orchestrate)
  (defproc identity
    :forall (T)
    ((value T))
    -> T
    :effects ()
    :lowering inline
    value)
  (defun unused-specialization
    ((value Int))
    -> Int
    (identity value))
  (defworkflow orchestrate
    ((value Int))
    -> Int
    value))
