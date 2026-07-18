(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule provider_prompt_dependencies/without_instruction)
  (export RequiredReport OptionalContext DependencyInputs WorkResult without_instruction)
  (defpath RequiredReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath OptionalContext
    :kind relpath
    :under "artifacts/context"
    :must-exist false)
  (defrecord DependencyInputs
    (required RequiredReport)
    (optional OptionalContext))
  (defrecord WorkResult
    (approved Bool)
    (summary String))
  (defworkflow without_instruction
    ((inputs DependencyInputs))
    -> WorkResult
    (provider-result providers.execute
      :prompt prompts.execute
      :inputs ()
      :prompt-dependencies
        (:required (inputs.required)
         :optional (inputs.optional)
         :position append)
      :returns WorkResult)))
