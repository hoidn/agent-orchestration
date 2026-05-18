(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defworkflow provider_attempt
    ((provider Provider)
     (prompt Prompt)
     (input ChecksResult)
     (report_path WorkReport))
    -> ImplementationState
    (provider-result provider
      :prompt prompt
      :inputs (input report_path)
      :returns Prompt)))
