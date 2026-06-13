(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule pointer_effect_lineage_invalid)
  (import std/phase :only (with-phase))
  (export orchestrate)
  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)
  (defenum ImplementationStateTag
    COMPLETED
    BLOCKED)
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
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord ImplementationInputs
    (design DesignDocPath)
    (plan PlanDocPath))
  (defunion ImplementationAttempt
    (COMPLETED
      (implementation_state ImplementationStateTag)
      (execution_report_path WorkReport))
    (BLOCKED
      (implementation_state ImplementationStateTag)
      (progress_report_path WorkReport)
      (blocker_class BlockerClass)))
  (defrecord ImplementationSummary
    (implementation_state ImplementationStateTag)
    (report_path WorkReport))
  (defworkflow orchestrate
    ((phase-ctx PhaseCtx)
     (inputs ImplementationInputs))
    -> ImplementationSummary
    (with-phase phase-ctx implementation
      (let* ((attempt
               (run-provider-phase implementation
                 :ctx phase-ctx
                 :inputs inputs
                 :provider providers.execute
                 :prompt prompts.implementation.execute
                 :returns ImplementationAttempt)))
        (match attempt
          ((COMPLETED completed)
           (record ImplementationSummary
             :implementation_state completed.implementation_state
             :report_path completed.execution_report_path))
          ((BLOCKED blocked)
           (record ImplementationSummary
             :implementation_state blocked.implementation_state
             :report_path blocked.progress_report_path)))))))
