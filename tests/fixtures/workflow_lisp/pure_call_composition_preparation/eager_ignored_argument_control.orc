(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule eager_ignored_argument_control)
  (export orchestrate)
  (defun ignore-first
    ((ignored Path.state-root)
     (value String))
    -> String
    value)
  (defworkflow orchestrate
    ((child String))
    -> String
    (ignore-first (path/join-under Path.state-root child) child)))
