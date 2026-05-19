(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
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
  (defpath ImplementationStateBundlePath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
  (defrecord ImplementationAttemptInputs
    (design DesignDocPath)
    (plan PlanDocPath))
  (defrecord ImplementationAttemptPhaseCtx
    (implementation_state_bundle_path ImplementationStateBundlePath)
    (execution_report_target WorkReportTarget)
    (progress_report_target WorkReportTarget))
  (defunion ImplementationAttempt
    (COMPLETED
      (implementation_state ImplementationStateTag)
      (execution_report_path WorkReport))
    (BLOCKED
      (implementation_state ImplementationStateTag)
      (progress_report_path WorkReport)
      (blocker_class BlockerClass)))
  (defrecord ImplementationAttemptSurfaceResult
    (implementation_state ImplementationStateTag)
    (implementation_state_bundle_path ImplementationStateBundlePath))
  (defworkflow run-implementation-attempt
    ((phase-ctx ImplementationAttemptPhaseCtx)
     (inputs ImplementationAttemptInputs))
    -> ImplementationAttemptSurfaceResult
    (with-phase phase-ctx implementation
      (let* ((attempt
               (provider-result providers.execute
                 :prompt prompts.implementation.execute
                 :inputs (inputs.design
                          inputs.plan
                          (phase-target execution-report)
                          (phase-target progress-report))
                 :returns ImplementationAttempt)))
        (match attempt
          ((COMPLETED completed)
           (record ImplementationAttemptSurfaceResult
             :implementation_state completed.implementation_state
             :implementation_state_bundle_path
               phase-ctx.implementation_state_bundle_path))
          ((BLOCKED blocked)
           (record ImplementationAttemptSurfaceResult
             :implementation_state blocked.implementation_state
             :implementation_state_bundle_path
               phase-ctx.implementation_state_bundle_path)))))))
