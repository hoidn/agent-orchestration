(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/types)
  (export WorkReport)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord HiddenSummary
    (report WorkReport)))
