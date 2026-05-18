(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defworkflow entry
    ((provider Provider)
     (prompt Prompt)
     (input ChecksResult)
     (report_path WorkReport))
    -> ImplementationState
    (call helper
      :provider provider
      :prompt prompt
      :input input
      :report_path report_path))
  (defworkflow helper
    ((provider Provider)
     (prompt Prompt)
     (input ChecksResult)
     (report_path WorkReport))
    -> ImplementationState
    (provider-result provider
      :prompt prompt
      :inputs (input report_path)
      :returns ImplementationState)))
