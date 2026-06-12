(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule context_generalization_experiment_ctx)
  (export entry use-context)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord ExperimentCtx
    (run RunCtx))
  (defrecord Result
    (run_id RunId)
    (state_root Path.state-root)
    (artifact_root Path.artifact-root))
  (defworkflow entry
    ()
    -> Result
    (call use-context))
  (defworkflow use-context
    ((ctx ExperimentCtx))
    -> Result
    (record Result
      :run_id ctx.run.run-id
      :state_root ctx.run.state-root
      :artifact_root ctx.run.artifact-root)))
