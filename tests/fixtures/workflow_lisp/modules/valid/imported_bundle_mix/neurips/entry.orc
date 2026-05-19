(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/entry)
  (import neurips/types :only (ChecksResult ImplementationSummary WorkReport))
  (import neurips/helper :as helper :only (provider-attempt))
  (export orchestrate)
  (defworkflow orchestrate
    ((input ChecksResult)
     (report_path WorkReport))
    -> ImplementationSummary
    (let* ((local
             (call helper.provider-attempt
               :input input
               :report_path report_path))
           (remote
             (call selector-run
               :input input
               :report_path report_path)))
      (record ImplementationSummary
        :report local.report))))
