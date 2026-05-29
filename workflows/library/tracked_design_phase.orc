(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule tracked_design_phase)
  (export tracked-design-phase)

  (defenum DesignReviewDecision
    APPROVE
    REVISE
    BLOCK)

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

  (defpath ReviewReportTarget
    :kind relpath
    :under "artifacts/review"
    :must-exist false)

  (defpath ReviewReportPath
    :kind relpath
    :under "artifacts/review"
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

)
