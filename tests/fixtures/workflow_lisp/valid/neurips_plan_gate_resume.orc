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
  (defpath PhaseStateBundle
    :kind relpath
    :under "state"
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
  (defrecord ResumeInputs
    (resume-from PhaseStateBundle)
    (design DesignDocPath)
    (plan PlanDocPath)
    (report-path WorkReport))
  (defunion PlanGateResult
    (APPROVED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defrecord PlanGateSurfaceResult
    (report-path WorkReport))
  (defworkflow plan-run
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> PlanGateResult
    (command-result resolve_plan_gate
      :argv ("python" "scripts/resolve_plan_gate.py" inputs.report-path)
      :returns PlanGateResult))
  (defworkflow resume-plan-gate
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> PlanGateSurfaceResult
    (with-phase phase-ctx plan-gate
      (let* ((result
               (resume-or-start plan-gate
                 :ctx phase-ctx
                 :resume-from inputs.resume-from
                 :valid-when (APPROVED)
                 :start
                   (call plan-run
                     :phase-ctx phase-ctx
                     :inputs inputs)
                 :returns PlanGateResult)))
        (match result
          ((APPROVED approved)
           (record PlanGateSurfaceResult
             :report-path approved.execution-report-path))
          ((BLOCKED blocked)
           (record PlanGateSurfaceResult
             :report-path blocked.progress-report-path)))))))
