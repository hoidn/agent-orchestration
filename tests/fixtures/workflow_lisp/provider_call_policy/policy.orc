(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defrecord WorkResult
    (approved Bool)
    (summary String))
  (defworkflow policy
    ((model String)
     (effort String))
    -> WorkResult
    (provider-result providers.execute
      :prompt prompts.execute
      :inputs ()
      :model model
      :effort effort
      :timeout-sec 7200
      :returns WorkResult)))
