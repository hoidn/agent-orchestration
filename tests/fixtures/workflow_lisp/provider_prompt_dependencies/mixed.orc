(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule provider_prompt_dependencies/mixed)
  (export RequiredReport OptionalContext DependencyInputs WorkResult invoke-provider mixed)
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
  (defproc invoke-provider
    ((required RequiredReport)
     (optional OptionalContext))
    -> WorkResult
    :effects ((uses-provider providers.execute))
    :lowering inline
    (provider-result providers.execute
      :prompt prompts.execute
      :inputs ()
      :prompt-dependencies
        (:required (required)
         :optional (optional)
         :position append
         :instruction "Use the supplied dependency set.")
      :returns WorkResult))
  (defworkflow mixed
    ((inputs DependencyInputs))
    -> WorkResult
    (let* ((required-alias inputs.required)
           (optional-alias inputs.optional))
      (provider-result providers.execute
        :prompt prompts.execute
        :inputs ()
        :prompt-dependencies
          (:required (required-alias inputs.required)
           :optional (optional-alias inputs.optional)
           :position append
           :instruction "Use the supplied dependency set.")
        :returns WorkResult))))
