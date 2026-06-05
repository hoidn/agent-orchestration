(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry)
  (import types :only (WorkReport LoopResult))
  (import helper :as helper :only (project-exhausted))
  (export orchestrate)
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> LoopResult
    (call helper.project-exhausted
      :report_path report_path)))
