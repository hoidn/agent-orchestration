(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule tracked_plan_phase)
  (export tracked-plan-phase)

  (defenum ReviewDecision
    APPROVE
    REVISE)

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

  (defworkflow tracked-plan-phase
    ((design_path DesignDocPath)
     (plan_target_path PlanDocTarget)
     (plan_review_report_target_path ReviewReportTarget))
    -> PlanPhaseOutput
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

)
