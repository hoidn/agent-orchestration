(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/plan_phase)
  (import std/phase :only
    (BlockerClass ReviewDecision ReviewFindings ReviewFindingsJsonPath ReviewReportPath
      review-revise-loop with-phase))
  (import lisp_frontend_design_delta/types :only
    (ArtifactReviewTargetPath BaselineDesignDoc PlanDoc PlanDocTarget PlanReviewDecision
      ProgressLedger SteeringDoc TargetDesignDoc WorkItemContextValue))
  (export
    DesignDeltaPlanPhaseResult
    PhaseCtx
    PlanPhaseInputs
    PlanSubject
    RunCtx
    run-plan-phase)

  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord PlanSubject
    (plan_path PlanDoc))

  (defrecord PlanDraftResult
    (plan_path PlanDoc))

  (defrecord PlanDraftPromptSubject
    (steering SteeringDoc)
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (work_item_context WorkItemContextValue)
    (progress_ledger ProgressLedger))

  (defrecord PlanDraftProviderTargets
    (plan_target_path PlanDocTarget))

  (defrecord PlanDraftRequest
    (subject PlanDraftPromptSubject)
    (targets PlanDraftProviderTargets))

  (defrecord PlanReviewPromptSubject
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (work_item_context WorkItemContextValue)
    (plan_path PlanDoc))

  (defrecord PlanReviewProviderTargets
    (plan_review_report_target_path ArtifactReviewTargetPath))

  (defrecord PlanReviewRequest
    (subject PlanReviewPromptSubject)
    (targets PlanReviewProviderTargets))

  (defrecord PlanFixPromptSubject
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (work_item_context WorkItemContextValue)
    (plan_path PlanDoc)
    (findings_items_path ReviewFindingsJsonPath))

  (defrecord PlanFixProviderTargets
    (plan_target_path PlanDocTarget))

  (defrecord PlanFixRequest
    (subject PlanFixPromptSubject)
    (targets PlanFixProviderTargets))

  (defrecord PlanPhaseInputs
    (steering SteeringDoc)
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (work_item_context WorkItemContextValue)
    (progress_ledger ProgressLedger)
    (plan_target_path PlanDocTarget)
    (plan_review_report_target_path ArtifactReviewTargetPath))

  (defunion DesignDeltaPlanPhaseResult
    (APPROVED
      (approved_plan_path PlanDoc)
      (approved_plan_review_report_path ReviewReportPath)
      (plan_review_decision PlanReviewDecision)
      (findings ReviewFindings))
    (BLOCKED
      (blocked_plan_path PlanDoc)
      (blocked_plan_review_report_path ReviewReportPath)
      (blocker_class BlockerClass)
      (findings ReviewFindings))
    (EXHAUSTED
      (exhausted_plan_path PlanDoc)
      (last_plan_review_report_path ReviewReportPath)
      (reason String)
      (findings ReviewFindings)))

  (defproc review-plan
    ((completed PlanSubject)
     (inputs PlanPhaseInputs))
    -> ReviewDecision
    :effects ((uses-provider providers.plan.review))
    :lowering inline
    (let* ((subject
             (record PlanReviewPromptSubject
               :target_design inputs.target_design
               :baseline_design inputs.baseline_design
               :work_item_context inputs.work_item_context
               :plan_path completed.plan_path))
           (targets
             (record PlanReviewProviderTargets
               :plan_review_report_target_path inputs.plan_review_report_target_path))
           (request
             (record PlanReviewRequest
               :subject subject
               :targets targets)))
      (provider-result providers.plan.review
        :prompt prompts.plan.review
        :inputs (request)
        :returns ReviewDecision)))

  (defproc revise-plan
    ((completed PlanSubject)
     (inputs PlanPhaseInputs)
     (findings ReviewFindings))
    -> PlanSubject
    :effects ((uses-provider providers.plan.fix))
    :lowering inline
    (let* ((subject
             (record PlanFixPromptSubject
               :target_design inputs.target_design
               :baseline_design inputs.baseline_design
               :work_item_context inputs.work_item_context
               :plan_path completed.plan_path
               :findings_items_path findings.items_path))
           (targets
             (record PlanFixProviderTargets
               :plan_target_path inputs.plan_target_path))
           (request
             (record PlanFixRequest
               :subject subject
               :targets targets))
           (draft
             (provider-result providers.plan.fix
               :prompt prompts.plan.fix
               :inputs (request)
               :returns PlanDraftResult)))
      (record PlanSubject
        :plan_path draft.plan_path)))

  (defworkflow run-plan-phase
    ((phase-ctx PhaseCtx)
     (steering SteeringDoc)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (work_item_context WorkItemContextValue)
     (progress_ledger ProgressLedger)
     (plan_target_path PlanDocTarget)
     (plan_review_report_target_path ArtifactReviewTargetPath))
    -> DesignDeltaPlanPhaseResult
    (with-phase phase-ctx plan
        (let* ((draft-subject
                 (record PlanDraftPromptSubject
                   :steering steering
                   :target_design target_design
                   :baseline_design baseline_design
                   :work_item_context work_item_context
                   :progress_ledger progress_ledger))
               (draft-targets
                 (record PlanDraftProviderTargets
                   :plan_target_path plan_target_path))
               (draft-request
                 (record PlanDraftRequest
                   :subject draft-subject
                   :targets draft-targets))
               (draft
                 (provider-result providers.plan.draft
                   :prompt prompts.plan.draft
                   :inputs (draft-request)
                 :returns PlanDraftResult))
             (completed
               (record PlanSubject
                 :plan_path draft.plan_path))
             (inputs
               (record PlanPhaseInputs
                 :steering steering
                 :target_design target_design
                 :baseline_design baseline_design
                 :work_item_context work_item_context
                 :progress_ledger progress_ledger
                 :plan_target_path plan_target_path
                 :plan_review_report_target_path plan_review_report_target_path))
             (review
               (review-revise-loop plan
                 :ctx phase-ctx
                 :completed completed
                 :inputs inputs
                 :review (proc-ref review-plan)
                 :fix (proc-ref revise-plan)
                 :max 12)))
        (match review
          ((APPROVED approved)
           (variant DesignDeltaPlanPhaseResult APPROVED
             :approved_plan_path completed.plan_path
             :approved_plan_review_report_path approved.review_report
             :plan_review_decision PlanReviewDecision.APPROVE
             :findings
               (record ReviewFindings
                 :schema_version approved.findings.schema_version
                 :items_path approved.findings.items_path)))
          ((BLOCKED blocked)
           (variant DesignDeltaPlanPhaseResult BLOCKED
             :blocked_plan_path completed.plan_path
             :blocked_plan_review_report_path blocked.review_report
             :blocker_class blocked.blocker_class
             :findings
               (record ReviewFindings
                 :schema_version blocked.findings.schema_version
                 :items_path blocked.findings.items_path)))
          ((EXHAUSTED exhausted)
           (variant DesignDeltaPlanPhaseResult EXHAUSTED
             :exhausted_plan_path completed.plan_path
             :last_plan_review_report_path exhausted.last_review_report
             :reason exhausted.reason
             :findings
               (record ReviewFindings
                 :schema_version exhausted.findings.schema_version
                 :items_path exhausted.findings.items_path))))))))
