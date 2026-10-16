(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule beta/common)
  (export OtherReport)
  (defpath OtherReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true))
