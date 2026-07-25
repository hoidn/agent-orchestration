(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.16")
  (defmodule provider_supervision_continue)
  (export orchestrate)
  (defworkflow orchestrate () -> String
    (with-live-providers
      ((worker
        (provider-result providers.worker
          :prompt prompts.worker
          :inputs ()
          :timeout-sec 30
          :returns String))
       (supervisor
        (provider-result providers.supervisor
          :prompt prompts.supervisor
          :inputs ()
          :timeout-sec 30
          :returns ProviderSteeringDirective)
        :observes worker))
      worker)))
