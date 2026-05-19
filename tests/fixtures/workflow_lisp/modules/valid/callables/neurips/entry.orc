(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/entry)
  (import neurips/types :only (WorkReport ImplementationSummary))
  (import neurips/procedures :as proc :only (build-checks))
  (import neurips/helper :as helper :only (provider-attempt secondary))
  (export orchestrate)
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> ImplementationSummary
    (let* ((checks
             (proc.build-checks report_path)))
      (call helper.provider-attempt
        :input checks
        :report_path report_path))))
