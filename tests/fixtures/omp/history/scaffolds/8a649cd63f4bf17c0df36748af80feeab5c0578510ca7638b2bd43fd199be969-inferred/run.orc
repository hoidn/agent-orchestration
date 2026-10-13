(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule run)
  (export run)
  (defrecord PromptResult_fe3340e5
    (summary String)
)
  (defworkflow run () -> PromptResult_fe3340e5
    (provider-result providers.task
      :prompt prompts.task
      :inputs ()
      :model "openai-codex/gpt-5.6-sol"
      :session-artifact omp_session
      :returns PromptResult_fe3340e5)
)
)
