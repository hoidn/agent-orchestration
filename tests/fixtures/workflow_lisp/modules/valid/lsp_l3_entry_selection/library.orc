(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule library)
  (export library-helper)
  (defproc library-helper
    ((value String))
    -> String
    :effects ()
    :lowering inline
    value))
