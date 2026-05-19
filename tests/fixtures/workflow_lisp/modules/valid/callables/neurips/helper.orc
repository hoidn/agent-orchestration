(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/helper)
  (import neurips/types :only (ChecksResult ImplementationSummary WorkReport))
  (export provider-attempt secondary)
  (defworkflow provider-attempt
    ((input ChecksResult)
     (report_path WorkReport))
    -> ImplementationSummary
    (provider-result providers.execute
      :prompt prompts.implementation.execute
      :inputs (input report_path)
      :returns ImplementationSummary))
  (defworkflow secondary
    ((input ChecksResult)
     (report_path WorkReport))
    -> ImplementationSummary
    (call provider-attempt
      :input input
      :report_path report_path)))
