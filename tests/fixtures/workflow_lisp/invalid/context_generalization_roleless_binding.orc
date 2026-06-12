(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule context_generalization_roleless_binding)
  (export entry use-context)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
  (defrecord ExperimentCtx
    (run RunCtx)
    (experiment-root StateFile))
  (defrecord Result
    (experiment_root StateFile))
  (defworkflow entry
    ()
    -> Result
    (call use-context))
  (defworkflow use-context
    ((ctx ExperimentCtx))
    -> Result
    (record Result
      :experiment_root ctx.experiment-root)))
