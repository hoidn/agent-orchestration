(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/helpers)
  (import neurips/types :only (WorkReport ChecksResult ImplementationSummary))
  (export summarize)
  (defun summarize
    ((input ChecksResult))
    -> WorkReport
    input.report))
