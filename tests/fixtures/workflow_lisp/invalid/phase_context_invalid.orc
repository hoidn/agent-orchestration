(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule phase_context_invalid)
  (import std/phase :only (with-phase))
  (defpath DesignDocPath
    :kind relpath
    :under "docs/design"
    :must-exist true)
  (defpath PlanDocPath
    :kind relpath
    :under "docs/plans"
    :must-exist true)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath ImplementationStateBundlePath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
  (defrecord ImplementationAttemptInputs
    (design DesignDocPath)
    (plan PlanDocPath))
  (defrecord ImplementationAttemptPhaseCtx
    (implementation_state_bundle_path ImplementationStateBundlePath)
    (execution_report_target WorkReport)
    (progress_report_target WorkReport))
  (defworkflow invalid-phase-context
    ((phase-ctx ImplementationAttemptPhaseCtx)
     (inputs ImplementationAttemptInputs))
    -> ImplementationAttemptInputs
    (with-phase phase-ctx implementation
      inputs)))
