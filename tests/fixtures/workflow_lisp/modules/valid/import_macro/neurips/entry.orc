(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/entry)
  (import neurips/types :only (WorkReport ImplementationSummary))
  (import neurips/macros :only (defworkflow-alias))
  (export generated)
  (defworkflow-alias generated))
