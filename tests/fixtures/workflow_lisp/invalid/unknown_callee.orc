(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defworkflow missing-helper
    ((provider Provider)
     (prompt Prompt)
     (input ChecksResult)
     (report_path WorkReport))
    -> ImplementationState
    (call unknown_helper
      :provider provider
      :prompt prompt
      :input input
      :report_path report_path)))
