(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule run)
  (export run)
  (defworkflow run ((omp_conf_root String)) -> String
    (provider-result providers.task
      :prompt prompts.task
      :inputs (omp_conf_root)
      :model "openai-codex/gpt-5.6-sol"
      :session-artifact omp_session
      :returns String)
)
)
