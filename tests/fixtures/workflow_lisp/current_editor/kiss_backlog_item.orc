(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule kiss_backlog_item)
  (export run-backlog-item)
  (defrecord PhaseCtx (name String))
  (defrecord BacklogItemInputs
    (backlog_item String)
    (work_instructions String))
  (defrecord PlanDraftSurfaceResult (report_path String))
  (defrecord BacklogItemResult (summary_path String))
  (defproc draft-plan-phase
    ((inputs BacklogItemInputs))
    -> PlanDraftSurfaceResult
    :effects ((uses-provider providers.plan))
    :lowering auto
    (provider-result providers.plan
      :prompt prompts.plan.draft
      :inputs (inputs.backlog_item inputs.work_instructions)
      :returns PlanDraftSurfaceResult))
  (defworkflow summarize ((plan PlanDraftSurfaceResult)) -> BacklogItemResult
    (record BacklogItemResult :summary_path plan.report_path))
  (defworkflow run-backlog-item
    ((plan-review-ctx PhaseCtx)
     (implementation-review-ctx PhaseCtx)
     (backlog-inputs BacklogItemInputs))
    -> BacklogItemResult
    (let* ((plan (draft-plan-phase backlog-inputs)))
      (call summarize :plan plan))))
