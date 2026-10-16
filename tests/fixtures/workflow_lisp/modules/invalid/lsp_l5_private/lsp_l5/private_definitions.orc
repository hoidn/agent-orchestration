(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule lsp_l5/private_definitions)

  (defproc hidden
    ((input String))
    -> String
    :effects ()
    :lowering inline
    input))
