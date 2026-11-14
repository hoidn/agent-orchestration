(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule proc_refs/private_helper)
  (defproc echo-helper
    ((input String))
    -> String
    input))
