(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule context_generalization_std_context_import)
  (import std/context
    :as context
    :only (PhaseCtx))
  (export entry run-phase)
  (defrecord Result
    (phase_name Symbol)
    (state_root Path.state-root))
  (defworkflow entry
    ()
    -> Result
    (call run-phase))
  (defworkflow run-phase
    ((phase-ctx context.PhaseCtx))
    -> Result
    (with-phase phase-ctx imported-phase
      (record Result
        :phase_name phase-ctx.phase-name
        :state_root phase-ctx.state-root))))
