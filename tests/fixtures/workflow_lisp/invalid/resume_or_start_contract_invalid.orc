(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defenum BlockerClass
    missing_resource)
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
      (execution_report_path WorkReport))
    (BLOCKED
      (progress_report_path WorkReport)
      (blocker_class BlockerClass)))
  (defrecord PlanGateSurfaceResult
    (report_path WorkReport))
  (defworkflow invalid-resume-contract
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
                   (command-result run_checks
                     :argv ("python" "scripts/run_checks.py" inputs.report_path)
                     :returns ChecksResult)
                 :returns PlanGateResult)))
        (match result
          ((APPROVED approved)
           (record PlanGateSurfaceResult
             :report_path approved.execution_report_path))
          ((BLOCKED blocked)
           (record PlanGateSurfaceResult
             :report_path blocked.progress_report_path)))))))
