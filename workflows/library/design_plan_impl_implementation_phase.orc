(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule design_plan_impl_implementation_phase)
  (export design-plan-impl-implementation-phase)

  (defenum ReviewDecision
    APPROVE
    REVISE)

  (defpath DesignDocPath
    :kind relpath
    :under "docs/plans"
    :must-exist true)

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

)
