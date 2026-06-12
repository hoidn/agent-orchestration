(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule pure_projection_effectful_boundary_lints)
  (export BoundaryDecision BoundaryStatePath run)

  (defpath BoundaryStatePath
    :kind relpath
    :under "state"
    :must-exist false)

  (defunion BoundaryDecision
    (ALLOW
      (reason String))
    (RETRY
      (reason String)))

  (defworkflow run
    ((state_path BoundaryStatePath)
     (reason String))
    -> BoundaryDecision
    (provider-result providers.execute
      :prompt prompts.implementation.execute
      :inputs (state_path reason)
      :returns BoundaryDecision)))
