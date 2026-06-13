(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule library/phase_stdlib_resume_or_start_promoted_entry_bootstrap_helper)
  (import std/phase :only (with-phase))
  (export ResumeInputs PlanGateWrapperSurfaceResult resume-plan-gate-wrapper)

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

  (defunion PlanGateResult
    (APPROVED
      (shared_report_path WorkReport))
    (BLOCKED
      (shared_report_path WorkReport)))

  (defworkflow plan-run
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> PlanGateResult
    (command-result resolve_plan_gate
      :argv ("python" "scripts/resolve_plan_gate.py" inputs.report_path)
      :returns PlanGateResult))

  (defunion PlanGateWrapperResult
    (APPROVED
      (report_path WorkReport))
    (BLOCKED
      (report_path WorkReport)))

  (defworkflow wrap-plan-gate
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> PlanGateWrapperResult
    (let* ((result
             (call plan-run
               :phase-ctx phase-ctx
               :inputs inputs)))
      (match result
        ((APPROVED approved)
         (variant PlanGateWrapperResult APPROVED
           :report_path approved.shared_report_path))
        ((BLOCKED blocked)
         (variant PlanGateWrapperResult BLOCKED
           :report_path blocked.shared_report_path)))))

  (defrecord PlanGateWrapperSurfaceResult
    (report_path WorkReport))

  (defworkflow resume-plan-gate-wrapper
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> PlanGateWrapperSurfaceResult
    (with-phase phase-ctx plan-gate-wrapper
      (let* ((result
               (resume-or-start plan-gate-wrapper
                 :ctx phase-ctx
                 :resume-from inputs.resume_from
                 :valid-when (APPROVED)
                 :start
                   (call wrap-plan-gate
                     :phase-ctx phase-ctx
                     :inputs inputs)
                 :returns PlanGateWrapperResult)))
        (match result
          ((APPROVED approved)
           (record PlanGateWrapperSurfaceResult
             :report_path approved.report_path))
          ((BLOCKED blocked)
           (record PlanGateWrapperSurfaceResult
             :report_path blocked.report_path)))))))
