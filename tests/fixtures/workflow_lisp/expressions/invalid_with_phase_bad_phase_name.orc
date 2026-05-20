(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defworkflow run
  ((phase_ctx String)
   (execute_provider Provider)
   (execute_prompt Prompt))
  ->
  Attempt
  (with-phase phase_ctx "implementation"
    (provider-result execute_provider
      :prompt execute_prompt
      :inputs (phase_ctx)
      :returns Attempt)))
