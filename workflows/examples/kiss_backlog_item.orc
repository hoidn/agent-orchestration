(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule kiss_backlog_item)
  (export run-backlog-item)

  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)

  (defenum ReviewDecision
    APPROVE
    REVISE
    BLOCKED)

  (defpath BacklogItemPath
    :kind relpath
    :under "docs/backlog/active"
    :must-exist true)

  (defpath WorkInstructionsPath
    :kind relpath
    :under "docs"
    :must-exist true)

  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord BacklogItemInputs
    (backlog_item BacklogItemPath)
    (work_instructions WorkInstructionsPath))

  (defrecord PlanDraftSurfaceResult
    (plan_path WorkReport)
    (report_path WorkReport))

  (defunion ReviewLoopResult
    (APPROVED
      (checks_report WorkReport)
      (review_report WorkReport)
      (review_decision ReviewDecision))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass))
    (EXHAUSTED
      (last_review_report WorkReport)
      (reason String)))

  (defrecord ReviewSurfaceResult
    (report_path WorkReport))

  (defrecord ImplementationInputs
    (backlog_item BacklogItemPath)
    (work_instructions WorkInstructionsPath)
    (plan_path WorkReport))

  (defrecord ImplementationSurfaceResult
    (execution_report_path WorkReport)
    (report_path WorkReport))

  (defrecord BacklogItemResult
    (summary_path WorkReport))

  (defworkflow draft-plan-phase
    ((inputs BacklogItemInputs))
    -> PlanDraftSurfaceResult
    (provider-result providers.plan
      :prompt prompts.plan.draft
      :inputs (inputs.backlog_item inputs.work_instructions)
      :returns PlanDraftSurfaceResult))

  (defworkflow review-plan-phase
    ((phase-ctx PhaseCtx)
     (draft PlanDraftSurfaceResult)
     (inputs BacklogItemInputs))
    -> ReviewSurfaceResult
    (with-phase phase-ctx plan-review
      (let* ((review
               (review-revise-loop plan-review
                 :ctx phase-ctx
                 :completed draft
                 :inputs inputs
                 :review-provider providers.plan-review
                 :fix-provider providers.plan-fix
                 :review-prompt prompts.plan.review
                 :fix-prompt prompts.plan.fix
                 :max 3
                 :returns ReviewLoopResult)))
        (match review
          ((APPROVED approved)
           (record ReviewSurfaceResult
             :report_path approved.review_report))
          ((BLOCKED blocked)
           (record ReviewSurfaceResult
             :report_path blocked.progress_report))
          ((EXHAUSTED exhausted)
           (record ReviewSurfaceResult
             :report_path exhausted.last_review_report))))))

  (defworkflow execute-implementation-phase
    ((backlog_item BacklogItemPath)
     (work_instructions WorkInstructionsPath)
     (plan_path WorkReport))
    -> ImplementationSurfaceResult
    (provider-result providers.implementation
      :prompt prompts.implementation.execute
      :inputs (backlog_item work_instructions plan_path)
      :returns ImplementationSurfaceResult))

  (defworkflow review-implementation-phase
    ((phase-ctx PhaseCtx)
     (completed ImplementationSurfaceResult)
     (backlog_item BacklogItemPath)
     (work_instructions WorkInstructionsPath)
     (plan_path WorkReport))
    -> ReviewSurfaceResult
    (with-phase phase-ctx implementation-review
      (let* ((review
               (review-revise-loop implementation-review
                 :ctx phase-ctx
                 :completed completed
                 :inputs
                   (record ImplementationInputs
                     :backlog_item backlog_item
                     :work_instructions work_instructions
                     :plan_path plan_path)
                 :review-provider providers.implementation-review
                 :fix-provider providers.implementation-fix
                 :review-prompt prompts.implementation.review
                 :fix-prompt prompts.implementation.fix
                 :max 5
                 :returns ReviewLoopResult)))
        (match review
          ((APPROVED approved)
           (record ReviewSurfaceResult
             :report_path approved.review_report))
          ((BLOCKED blocked)
           (record ReviewSurfaceResult
             :report_path blocked.progress_report))
          ((EXHAUSTED exhausted)
           (record ReviewSurfaceResult
             :report_path exhausted.last_review_report))))))

  (defworkflow run-approved-plan
    ((implementation-review-ctx PhaseCtx)
     (inputs BacklogItemInputs)
     (plan PlanDraftSurfaceResult))
    -> BacklogItemResult
    (let* ((implementation
             (call execute-implementation-phase
               :backlog_item inputs.backlog_item
               :work_instructions inputs.work_instructions
               :plan_path plan.plan_path))
           (implementation-review
             (call review-implementation-phase
               :phase-ctx implementation-review-ctx
               :completed implementation
               :backlog_item inputs.backlog_item
               :work_instructions inputs.work_instructions
               :plan_path plan.plan_path)))
      (record BacklogItemResult
        :summary_path implementation-review.report_path)))

  (defworkflow run-backlog-item
    ((plan-review-ctx PhaseCtx)
     (implementation-review-ctx PhaseCtx)
     (inputs BacklogItemInputs))
    -> BacklogItemResult
    (let* ((plan
             (call draft-plan-phase
               :inputs inputs))
           (plan-review
             (call review-plan-phase
               :phase-ctx plan-review-ctx
               :draft plan
               :inputs inputs)))
      (call run-approved-plan
        :implementation-review-ctx implementation-review-ctx
        :inputs inputs
        :plan plan))))
