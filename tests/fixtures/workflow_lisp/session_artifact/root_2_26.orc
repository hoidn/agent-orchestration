(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.26")
  (defmodule root_2_26)
  (export run)
  (defworkflow run () -> String
    (provider-result providers.session
      :prompt prompts.session
      :inputs ()
      :session-artifact omp_session
      :returns String)))
