(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule examples/design_plan_impl_review_stack_v2_call)
  (export design-plan-impl-review-stack)

  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)

  (defenum DesignReviewDecision
    APPROVE
    REVISE
    BLOCK)

  (defenum ReviewDecision
    APPROVE
    REVISE)

  (defpath BriefPath
    :kind relpath
    :under "workflows/examples/inputs"
    :must-exist true)

  (defpath DesignDocTarget
    :kind relpath
    :under "docs/plans"
    :must-exist false)

  (defpath DesignDocPath
    :kind relpath
    :under "docs/plans"
    :must-exist true)

  (defpath PlanDocTarget
    :kind relpath
    :under "docs/plans"
    :must-exist false)

  (defpath PlanDocPath
    :kind relpath
    :under "docs/plans"
    :must-exist true)

  (defpath ReviewReportTarget
    :kind relpath
    :under "artifacts/review"
    :must-exist false)

  (defpath ReviewReportPath
    :kind relpath
    :under "artifacts/review"
    :must-exist true)

  (defpath ExecutionReportTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defpath ExecutionReportPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defrecord DraftDesignResult
    (design_path DesignDocPath))

  (defunion DesignReviewOutcome
    (APPROVE
      (design_review_report_path ReviewReportPath)
      (design_review_decision DesignReviewDecision))
    (REVISE
      (design_review_report_path ReviewReportPath)
      (design_review_decision DesignReviewDecision))
    (BLOCK
      (design_review_report_path ReviewReportPath)
      (design_review_decision DesignReviewDecision)))

  (defrecord DesignPhaseOutput
    (design_path DesignDocPath)
    (design_review_report_path ReviewReportPath)
    (design_review_decision DesignReviewDecision))

  (defrecord PlanDraftResult
    (plan_path PlanDocPath))

  (defunion PlanReviewOutcome
    (APPROVE
      (plan_review_report_path ReviewReportPath)
      (plan_review_decision ReviewDecision))
    (REVISE
      (plan_review_report_path ReviewReportPath)
      (plan_review_decision ReviewDecision)))

  (defrecord PlanPhaseOutput
    (plan_path PlanDocPath)
    (plan_review_report_path ReviewReportPath)
    (plan_review_decision ReviewDecision))

  (defrecord ImplementationAttemptResult
    (execution_report_path ExecutionReportPath))

  (defunion ImplementationReviewOutcome
    (APPROVE
      (implementation_review_report_path ReviewReportPath)
      (implementation_review_decision ReviewDecision))
    (REVISE
      (implementation_review_report_path ReviewReportPath)
      (implementation_review_decision ReviewDecision)))

  (defrecord ImplementationPhaseOutput
    (execution_report_path ExecutionReportPath)
    (implementation_review_report_path ReviewReportPath)
    (implementation_review_decision ReviewDecision))

  (defrecord StackOutput
    (design_path DesignDocPath)
    (design_review_report_path ReviewReportPath)
    (design_review_decision DesignReviewDecision)
    (plan_path PlanDocPath)
    (plan_review_report_path ReviewReportPath)
    (plan_review_decision ReviewDecision)
    (execution_report_path ExecutionReportPath)
    (implementation_review_report_path ReviewReportPath)
    (implementation_review_decision ReviewDecision))

  (defworkflow tracked-design-phase
    ((brief_path BriefPath)
     (design_target_path DesignDocTarget)
     (design_review_report_target_path ReviewReportTarget))
    -> DesignPhaseOutput
    (let* ((draft
             (provider-result providers.design.draft
               :prompt prompts.design.draft
               :inputs (brief_path design_target_path)
               :returns DraftDesignResult))
           (review
             (provider-result providers.design.review
               :prompt prompts.design.review
               :inputs (brief_path draft.design_path design_review_report_target_path)
               :returns DesignReviewOutcome)))
      (match review
        ((APPROVE approved)
         (record DesignPhaseOutput
           :design_path draft.design_path
           :design_review_report_path approved.design_review_report_path
           :design_review_decision approved.design_review_decision))
        ((BLOCK blocked)
         (record DesignPhaseOutput
           :design_path draft.design_path
           :design_review_report_path blocked.design_review_report_path
           :design_review_decision blocked.design_review_decision))
        ((REVISE revise)
         (record DesignPhaseOutput
           :design_path draft.design_path
           :design_review_report_path revise.design_review_report_path
           :design_review_decision revise.design_review_decision)))))

  (defproc tracked-plan-phase
    ((design_path DesignDocPath)
     (plan_target_path PlanDocTarget)
     (plan_review_report_target_path ReviewReportTarget))
    -> PlanPhaseOutput
    :effects ((uses-provider providers.plan.draft)
              (uses-provider providers.plan.review))
    :lowering inline
    (let* ((draft
             (provider-result providers.plan.draft
               :prompt prompts.plan.draft
               :inputs (design_path plan_target_path)
               :returns PlanDraftResult))
           (review
             (provider-result providers.plan.review
               :prompt prompts.plan.review
               :inputs (design_path draft.plan_path plan_review_report_target_path)
               :returns PlanReviewOutcome)))
      (match review
        ((APPROVE approved)
         (record PlanPhaseOutput
           :plan_path draft.plan_path
           :plan_review_report_path approved.plan_review_report_path
           :plan_review_decision approved.plan_review_decision))
        ((REVISE revise)
         (record PlanPhaseOutput
           :plan_path draft.plan_path
           :plan_review_report_path revise.plan_review_report_path
           :plan_review_decision revise.plan_review_decision)))))

  (defworkflow design-plan-impl-implementation-phase
    ((design_path DesignDocPath)
     (plan_path PlanDocPath)
     (execution_report_target_path ExecutionReportTarget)
     (implementation_review_report_target_path ReviewReportTarget))
    -> ImplementationPhaseOutput
    (let* ((attempt
             (provider-result providers.implementation.execute
               :prompt prompts.implementation.execute
               :inputs (design_path plan_path execution_report_target_path)
               :returns ImplementationAttemptResult))
           (review
             (provider-result providers.implementation.review
               :prompt prompts.implementation.review
               :inputs
                 (design_path
                  plan_path
                  attempt.execution_report_path
                  implementation_review_report_target_path)
               :returns ImplementationReviewOutcome)))
      (match review
        ((APPROVE approved)
         (record ImplementationPhaseOutput
           :execution_report_path attempt.execution_report_path
           :implementation_review_report_path approved.implementation_review_report_path
           :implementation_review_decision approved.implementation_review_decision))
        ((REVISE revise)
         (record ImplementationPhaseOutput
           :execution_report_path attempt.execution_report_path
           :implementation_review_report_path revise.implementation_review_report_path
           :implementation_review_decision revise.implementation_review_decision)))))

  (defworkflow design-plan-impl-review-stack
    ((brief_path BriefPath)
     (design_target_path DesignDocTarget)
     (design_review_report_target_path ReviewReportTarget)
     (plan_target_path PlanDocTarget)
     (plan_review_report_target_path ReviewReportTarget)
     (execution_report_target_path ExecutionReportTarget)
     (implementation_review_report_target_path ReviewReportTarget))
    -> StackOutput
    (let* ((design
             (call tracked-design-phase
               :brief_path brief_path
               :design_target_path design_target_path
               :design_review_report_target_path design_review_report_target_path))
           (plan
             (tracked-plan-phase
               design.design_path
               plan_target_path
               plan_review_report_target_path))
           (implementation
             (call design-plan-impl-implementation-phase
               :design_path design.design_path
               :plan_path plan.plan_path
               :execution_report_target_path execution_report_target_path
               :implementation_review_report_target_path implementation_review_report_target_path)))
      (record StackOutput
        :design_path design.design_path
        :design_review_report_path design.design_review_report_path
        :design_review_decision design.design_review_decision
        :plan_path plan.plan_path
        :plan_review_report_path plan.plan_review_report_path
        :plan_review_decision plan.plan_review_decision
        :execution_report_path implementation.execution_report_path
        :implementation_review_report_path implementation.implementation_review_report_path
        :implementation_review_decision implementation.implementation_review_decision))))
