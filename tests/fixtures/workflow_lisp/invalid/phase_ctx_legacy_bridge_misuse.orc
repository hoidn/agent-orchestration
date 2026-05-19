(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defenum BlockerClass
    missing_resource)
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
  (defrecord ImplementationAttemptPhaseCtx
    (implementation_state_bundle_path ImplementationStateBundlePath)
    (execution_report_target WorkReportTarget)
    (progress_report_target WorkReportTarget))
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
  (defworkflow invalid-legacy-bridge
    ((phase-ctx ImplementationAttemptPhaseCtx)
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
