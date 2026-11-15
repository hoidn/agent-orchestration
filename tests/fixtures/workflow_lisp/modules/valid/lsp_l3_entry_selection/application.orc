(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule application)
  (export first selected)
  (defproc application-helper
    ((value String))
    -> String
    value)
  (defworkflow first () -> String "first")
  (defworkflow selected () -> String
    (application-helper "selected")))
