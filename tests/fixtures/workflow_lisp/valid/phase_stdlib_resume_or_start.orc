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
    (resume_from PhaseStateBundle)
    (design DesignDocPath)
    (plan PlanDocPath)
    (report_path WorkReport))
  (defrecord ChecksResult
    (checks_report WorkReport))
  (defunion PlanGateResult
    (APPROVED
      (shared_report_path WorkReport)
      (execution_report_path WorkReport))
    (BLOCKED
      (shared_report_path WorkReport)
      (progress_report_path WorkReport)
      (blocker_class BlockerClass)))
  (defworkflow plan-run
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> PlanGateResult
    (command-result resolve_plan_gate
      :argv ("python" "scripts/resolve_plan_gate.py" inputs.report_path)
      :returns PlanGateResult))
  (defrecord PlanGateSurfaceResult
    (report_path WorkReport))
  (defworkflow resume-record-phase
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> ChecksResult
    (with-phase phase-ctx checks
      (resume-or-start checks
        :ctx phase-ctx
        :resume-from inputs.resume_from
        :start
          (command-result run_checks
            :argv ("python" "scripts/run_checks.py" inputs.report_path)
            :returns ChecksResult)
        :returns ChecksResult)))
  (defworkflow resume-plan-gate
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> PlanGateSurfaceResult
    (with-phase phase-ctx plan-gate
      (let* ((result
               (resume-or-start plan-gate
                 :ctx phase-ctx
                 :resume-from inputs.resume_from
                 :valid-when (APPROVED)
                 :start
                   (call plan-run
                     :phase-ctx phase-ctx
                     :inputs inputs)
                 :returns PlanGateResult)))
        (match result
          ((APPROVED approved)
           (record PlanGateSurfaceResult
             :report_path approved.execution_report_path))
          ((BLOCKED blocked)
           (record PlanGateSurfaceResult
             :report_path blocked.progress_report_path)))))))
