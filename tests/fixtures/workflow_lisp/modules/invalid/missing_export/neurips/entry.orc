(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/entry)
  (import neurips/types :only (HiddenSummary WorkReport))
  (export orchestrate)
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> HiddenSummary
    (record HiddenSummary
      :report report_path)))
