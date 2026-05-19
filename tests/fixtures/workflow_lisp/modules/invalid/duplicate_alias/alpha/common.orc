(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule alpha/common)
  (export SharedReport)
  (defpath SharedReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true))
