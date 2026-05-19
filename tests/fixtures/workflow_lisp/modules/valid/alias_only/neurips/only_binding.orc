(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/only_binding)
  (import neurips/types :only (WorkReport ImplementationSummary))
  (export orchestrate)
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> ImplementationSummary
    (record ImplementationSummary
      :report report_path)))
