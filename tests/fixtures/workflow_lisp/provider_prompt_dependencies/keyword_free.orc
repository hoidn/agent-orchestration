(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defrecord WorkResult
    (approved Bool)
    (summary String))
  (defworkflow keyword-free () -> WorkResult
    (provider-result providers.execute
      :prompt prompts.execute
      :inputs ()
      :returns WorkResult)))
