(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/default_alias)
  (import neurips/types)
  (export orchestrate)
  (defworkflow orchestrate
    ((report_path types.WorkReport))
    -> types.ImplementationSummary
    (record types.ImplementationSummary
      :report report_path)))
