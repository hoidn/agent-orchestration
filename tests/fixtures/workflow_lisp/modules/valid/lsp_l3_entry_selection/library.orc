(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule library)
  (export library-helper)
  (defproc library-helper
    ((value String))
    -> String
    value))
