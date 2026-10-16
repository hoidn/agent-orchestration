(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule proc_refs/private_helper)
  (defproc echo-helper
    ((input String))
    -> String
    :effects ()
    :lowering inline
    input))
