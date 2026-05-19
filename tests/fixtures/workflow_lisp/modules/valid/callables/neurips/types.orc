(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/types)
  (export WorkReport ChecksResult ImplementationSummary)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (status String)
    (report WorkReport))
  (defrecord ImplementationSummary
    (report WorkReport)))
