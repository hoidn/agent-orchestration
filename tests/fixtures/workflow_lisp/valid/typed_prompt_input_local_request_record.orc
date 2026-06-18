(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule typed_prompt_input_local_request_record)
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
  (defpath WorkReportTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PromptSubject
    (design DesignDocPath)
    (plan PlanDocPath)
    (focus String))
  (defrecord ProviderTargets
    (execution_report_target WorkReportTarget)
    (progress_report_target WorkReportTarget))
  (defrecord ImplementationRequest
    (subject PromptSubject)
    (targets ProviderTargets))
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
  (defworkflow run-local-request-record-demo
    ((phase-ctx PhaseCtx)
     (inputs ImplementationInputs))
    -> ImplementationSummary
    (with-phase phase-ctx implementation
      (let* ((subject
               (record PromptSubject
                 :design inputs.design
                 :plan inputs.plan
                 :focus "typed provider request"))
             (targets
               (record ProviderTargets
                 :execution_report_target (phase-target execution-report)
                 :progress_report_target (phase-target progress-report)))
             (request
               (record ImplementationRequest
                 :subject subject
                 :targets targets))
             (attempt
               (run-provider-phase implementation
                 :ctx phase-ctx
                 :inputs request
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
