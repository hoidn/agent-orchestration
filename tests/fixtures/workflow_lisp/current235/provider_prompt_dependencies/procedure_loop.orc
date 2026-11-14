(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule provider_prompt_dependencies/procedure_loop)
  (import provider_prompt_dependencies/mixed
    :as deps
    :only (DependencyInputs WorkResult invoke-provider))
  (export procedure-loop loop-carried)
  (defworkflow procedure-loop
    ((inputs DependencyInputs))
    -> WorkResult
    (deps.invoke-provider
      inputs.required
      inputs.optional))
  (defworkflow loop-carried
    ((inputs DependencyInputs))
    -> WorkResult
    (loop/recur ((state inputs))
      :max 1
      (let* ((result
               (provider-result providers.execute
                 :prompt prompts.execute
                 :inputs ()
                 :prompt-dependencies
                   (:required (state.required)
                    :optional (state.optional)
                    :position append
                    :instruction "Use the loop-carried dependency set.")
                 :returns WorkResult)))
        (done
          (record WorkResult
            :approved result.approved
            :summary result.summary))))))
