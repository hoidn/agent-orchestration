(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule provider_prompt_dependencies/mixed)
  (export RequiredReport OptionalContext DependencyInputs E2eDependencyInputs WorkResult invoke-provider mixed mixed-e2e dependency-leaf dependency-middle dependency-call-root)
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
  (defrecord E2eDependencyInputs
    (required_a RequiredReport)
    (required_b RequiredReport)
    (required_c RequiredReport)
    (required_d RequiredReport)
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
        :returns WorkResult)))
  (defworkflow mixed-e2e
    ((inputs E2eDependencyInputs))
    -> WorkResult
    (let* ((provider-result-value
             (provider-result providers.execute
               :prompt prompts.execute
               :inputs ()
               :prompt-dependencies
                 (:required
                    (inputs.required_a
                     inputs.required_b
                     inputs.required_c
                     inputs.required_d)
                  :optional (inputs.optional)
                  :position append
                  :instruction "Use the supplied dependency set.")
               :returns WorkResult)))
      (record WorkResult
        :approved provider-result-value.approved
        :summary provider-result-value.summary)))
  (defworkflow dependency-leaf
    ((inputs DependencyInputs))
    -> WorkResult
    (provider-result providers.execute
      :prompt prompts.execute
      :inputs ()
      :prompt-dependencies
        (:required (inputs.required)
         :optional (inputs.optional)
         :position append
         :instruction "Use the call-frame dependency set.")
      :returns WorkResult))
  (defworkflow dependency-middle
    ((inputs DependencyInputs))
    -> WorkResult
    (call dependency-leaf
      :inputs inputs))
  (defworkflow dependency-call-root
    ((inputs DependencyInputs))
    -> WorkResult
    (call dependency-middle
      :inputs inputs)))
