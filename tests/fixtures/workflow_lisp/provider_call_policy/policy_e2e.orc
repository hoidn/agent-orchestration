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
    (let* ((provider-boundary
             (provider-result providers.execute
               :prompt prompts.execute
               :inputs ()
               :model model
               :effort effort
               :timeout-sec 7200
               :returns WorkResult)))
      (command-result finish
        :argv ("python" "finish.py")
        :returns WorkResult))))
