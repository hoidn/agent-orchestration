(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule typed_prompt_input_phase)
  (import std/phase :only (with-phase))
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
  (defrecord PromptContext
    (design DesignDocPath)
    (plan PlanDocPath)
    (focus String))
  (defrecord ImplementationInputs
    (prompt_context PromptContext))
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
  (defworkflow run-typed-prompt-phase-demo
    ((phase-ctx PhaseCtx)
     (inputs ImplementationInputs))
    -> ImplementationSummary
    (with-phase phase-ctx implementation
      (let* ((attempt
               (run-provider-phase implementation
                 :ctx phase-ctx
                 :inputs inputs.prompt_context
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
