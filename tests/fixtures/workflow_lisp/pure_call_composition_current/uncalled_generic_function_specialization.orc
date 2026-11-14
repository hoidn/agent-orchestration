(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule uncalled_generic_function_specialization)
  (export orchestrate)
  (defproc identity
    :forall (T)
    ((value T))
    -> T
    value)
  (defun unused-specialization
    ((value Int))
    -> Int
    (identity value))
  (defworkflow orchestrate
    ((value Int))
    -> Int
    value))
