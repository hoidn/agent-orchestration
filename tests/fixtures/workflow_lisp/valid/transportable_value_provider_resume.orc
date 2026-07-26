(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.19")
  (defmodule transportable_value_provider_resume)
  (export orchestrate)
  (defproc pass-value
    ((payload Value))
    -> Value
    :effects ()
    :lowering inline
    payload)
  (defworkflow orchestrate
    ()
    -> Value
    (let* ((payload
             (provider-result providers.value
               :prompt prompts.value
               :inputs ()
               :returns Value))
           (finished
             (command-result finish-run
               :argv ("python" "scripts/finish.py")
               :returns Bool)))
      (pass-value payload))))
