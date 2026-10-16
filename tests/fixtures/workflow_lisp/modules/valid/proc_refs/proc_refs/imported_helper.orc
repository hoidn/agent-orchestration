(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule proc_refs/imported_helper)
  (export echo-helper)
  (defproc echo-helper
    ((input String))
    -> String
    :effects ()
    :lowering inline
    input))
