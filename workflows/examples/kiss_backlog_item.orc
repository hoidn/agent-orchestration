(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule kiss_backlog_item)
  (import std/phase :only
    (ReviewDecision ReviewFindings ReviewLoopResult ReviewReportPath review-revise-loop))
  (export run-backlog-item)

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

  (defrecord ReviewableSurfaceResult
    (execution_report_path WorkReport)
    (report_path WorkReport))

  (defrecord ReviewSurfaceResult
    (report_path ReviewReportPath))

  (defrecord ReviewContextInputs
    (backlog_item BacklogItemPath)
    (work_instructions WorkInstructionsPath)
    (plan_path WorkReport))

  (defrecord ImplementationSurfaceResult
    (execution_report_path WorkReport)
    (report_path WorkReport))

  (defrecord BacklogItemResult
    (summary_path ReviewReportPath))

  (defproc draft-plan-phase
    ((inputs BacklogItemInputs))
    -> PlanDraftSurfaceResult
    :effects ((uses-provider providers.plan))
    :lowering auto
    (provider-result providers.plan
      :prompt prompts.plan.draft
      :inputs (inputs.backlog_item inputs.work_instructions)
      :returns PlanDraftSurfaceResult))

  (defproc review-plan
    ((completed ReviewableSurfaceResult)
     (inputs ReviewContextInputs))
    -> ReviewDecision
    :effects ((uses-provider providers.plan-review))
    :lowering inline
    (provider-result providers.plan-review
      :prompt prompts.plan.review
      :inputs (completed.execution_report_path
               completed.report_path
               inputs.backlog_item
               inputs.work_instructions
               inputs.plan_path)
      :returns ReviewDecision))

  (defproc fix-plan
    ((completed ReviewableSurfaceResult)
     (inputs ReviewContextInputs)
     (findings ReviewFindings))
    -> ReviewableSurfaceResult
    :effects ((uses-provider providers.plan-fix))
    :lowering inline
    (let* ((fixed
             (provider-result providers.plan-fix
               :prompt prompts.plan.fix
               :inputs (completed.execution_report_path
                        completed.report_path
                        inputs.backlog_item
                        inputs.work_instructions
                        inputs.plan_path
                        findings.items_path)
               :returns PlanDraftSurfaceResult)))
      (record ReviewableSurfaceResult
        :execution_report_path fixed.plan_path
        :report_path fixed.report_path)))

  (defproc execute-implementation-phase
    ((backlog_item BacklogItemPath)
     (work_instructions WorkInstructionsPath)
     (plan_path WorkReport))
    -> ImplementationSurfaceResult
    :effects ((uses-provider providers.implementation))
    :lowering auto
    (provider-result providers.implementation
      :prompt prompts.implementation.execute
      :inputs (backlog_item work_instructions plan_path)
      :returns ImplementationSurfaceResult))

  (defproc review-implementation
    ((completed ReviewableSurfaceResult)
     (inputs ReviewContextInputs))
    -> ReviewDecision
    :effects ((uses-provider providers.implementation-review))
    :lowering inline
    (provider-result providers.implementation-review
      :prompt prompts.implementation.review
      :inputs (completed.execution_report_path
               completed.report_path
               inputs.backlog_item
               inputs.work_instructions
               inputs.plan_path)
      :returns ReviewDecision))

  (defproc fix-implementation
    ((completed ReviewableSurfaceResult)
     (inputs ReviewContextInputs)
     (findings ReviewFindings))
    -> ReviewableSurfaceResult
    :effects ((uses-provider providers.implementation-fix))
    :lowering inline
    (let* ((fixed
             (provider-result providers.implementation-fix
               :prompt prompts.implementation.fix
               :inputs (completed.execution_report_path
                        completed.report_path
                        inputs.backlog_item
                        inputs.work_instructions
                        inputs.plan_path
                        findings.items_path)
               :returns ImplementationSurfaceResult)))
      (record ReviewableSurfaceResult
        :execution_report_path fixed.execution_report_path
        :report_path fixed.report_path)))

  (defworkflow run-backlog-item
    ((plan-review-ctx PhaseCtx)
     (implementation-review-ctx PhaseCtx)
     (backlog-inputs BacklogItemInputs))
    -> BacklogItemResult
    (let* ((plan
             (draft-plan-phase backlog-inputs))
           (review-inputs
             (record ReviewContextInputs
               :backlog_item backlog-inputs.backlog_item
               :work_instructions backlog-inputs.work_instructions
               :plan_path plan.plan_path))
           (plan-review-completed
             (record ReviewableSurfaceResult
               :execution_report_path plan.plan_path
               :report_path plan.report_path))
           (plan-review
             (with-phase plan-review-ctx plan-review
               (let* ((review
                        (review-revise-loop plan-review
                          :ctx plan-review-ctx
                          :completed plan-review-completed
                          :inputs review-inputs
                          :review (proc-ref review-plan)
                          :fix (proc-ref fix-plan)
                          :max 3)))
                 (match review
                   ((APPROVED approved)
                    (record ReviewSurfaceResult
                      :report_path approved.review_report))
                   ((BLOCKED blocked)
                    (record ReviewSurfaceResult
                      :report_path blocked.review_report))
                   ((EXHAUSTED exhausted)
                    (record ReviewSurfaceResult
                      :report_path exhausted.last_review_report))))))
           (implementation
             (execute-implementation-phase
               backlog-inputs.backlog_item
               backlog-inputs.work_instructions
               plan.plan_path))
           (implementation-review-completed
             (record ReviewableSurfaceResult
               :execution_report_path implementation.execution_report_path
               :report_path implementation.report_path))
           (implementation-review
             (with-phase implementation-review-ctx implementation-review
               (let* ((review
                        (review-revise-loop implementation-review
                          :ctx implementation-review-ctx
                          :completed implementation-review-completed
                          :inputs review-inputs
                          :review (proc-ref review-implementation)
                          :fix (proc-ref fix-implementation)
                          :max 5)))
                 (match review
                   ((APPROVED approved)
                    (record ReviewSurfaceResult
                      :report_path approved.review_report))
                   ((BLOCKED blocked)
                    (record ReviewSurfaceResult
                      :report_path blocked.review_report))
                   ((EXHAUSTED exhausted)
                    (record ReviewSurfaceResult
                      :report_path exhausted.last_review_report)))))))
      (record BacklogItemResult
        :summary_path implementation-review.report_path))))
