(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule root_two)
  (export run)
  (defworkflow run () -> String
    (let* ((first (provider-result providers.session
                    :prompt prompts.session
                    :inputs ()
                    :session-artifact omp_session
                    :returns String)))
      (provider-result providers.session
        :prompt prompts.session
        :inputs ()
        :session-artifact omp_session_2
        :returns String))))
