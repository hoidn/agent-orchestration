(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule application)
  (export first selected)
  (defproc application-helper
    ((value String))
    -> String
    :effects ()
    :lowering inline
    value)
  (defworkflow first () -> String "first")
  (defworkflow selected () -> String
    (application-helper "selected")))
