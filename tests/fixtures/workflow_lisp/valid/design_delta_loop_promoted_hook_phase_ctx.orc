(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule design_delta_loop_promoted_hook_phase_ctx)
  (import std/context :only (RunCtx))
  (import std/drain :only (DrainResult backlog-drain-proc settle-drain-terminal))
  (import std/resource :only (BlockerClass WorkReport))
  (import lisp_frontend_design_delta/bootstrap :only (project-work-item-inputs))
  (import lisp_frontend_design_delta/implementation_phase :only (implementation-phase))
  (import lisp_frontend_design_delta/plan_phase :only (run-plan-phase))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc ProgressLedger SteeringDoc TargetDesignDoc
      WorkItemBootstrapSeed))
  (export drain-entry)

  (defrecord HookDrainCtx
    (run RunCtx)
    (state-root Path.state-root)
    (manifest Path.state-root)
    (ledger Path.state-root))

  (defrecord HookSelectionPayload
    (item-id String)
    (item-state-root Path.state-root)
    (work_item_bootstrap WorkItemBootstrapSeed)
    (steering_path SteeringDoc)
    (target_design_path TargetDesignDoc)
    (baseline_design_path BaselineDesignDoc)
    (progress_ledger_path ProgressLedger))

  (defrecord HookGapPayload
    (gap-id String))

  (defunion HookSelection
    (EMPTY)
    (SELECTED
      (selection HookSelectionPayload))
    (GAP
      (gap HookGapPayload))
    (BLOCKED
      (reason String)))

  (defunion HookRunResult
    (CONTINUE
      (summary-path WorkReport))
    (BLOCKED
      (summary-path WorkReport)
      (blocker-class BlockerClass)))

  (defunion HookGapResult
    (CONTINUE)
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))

  (defrecord FallbackReport
    (report WorkReport)
    (blocker BlockerClass))

  (defworkflow make-fallback-report
    ()
    -> FallbackReport
    (command-result mk_fallback_report
      :argv ("python" "scripts/make_fallback_report.py")
      :returns FallbackReport))

  (defproc select-stub
    ((ctx HookDrainCtx))
    -> HookSelection
    :effects ((uses-command drain_select))
    :lowering inline
    (command-result drain_select
      :argv ("python" "scripts/select_next_item.py" ctx.manifest)
      :returns HookSelection))

  (defproc gap-stub
    ((ctx HookDrainCtx)
     (gap HookGapPayload))
    -> HookGapResult
    :effects ((uses-command drain_draft_gap))
    :lowering inline
    (command-result drain_draft_gap
      :argv ("python" "scripts/draft_gap_item.py" ctx.manifest)
      :returns HookGapResult))

  (defproc run-item-with-child-phases
    ((item-ctx std/context/ItemCtx)
     (selection HookSelectionPayload))
    -> HookRunResult
    :effects ((calls-workflow design_delta_loop_promoted_hook_phase_ctx::make-fallback-report)
              (calls-workflow lisp_frontend_design_delta/bootstrap::project-work-item-inputs)
              (calls-workflow lisp_frontend_design_delta/implementation_phase::implementation-phase)
              (calls-workflow lisp_frontend_design_delta/plan_phase::run-plan-phase)
              (uses-command mk_fallback_report))
    :lowering inline
    (let* ((selection-ctx
             (record lisp_frontend_design_delta/types/SelectionCtx
               :state_root item-ctx.state-root
               :artifact_root item-ctx.artifact-root))
           (design-delta-item-ctx
             (record lisp_frontend_design_delta/types/ItemCtx
               :selection selection-ctx
               :work_item_id item-ctx.item-id
               :state_root item-ctx.state-root
               :artifact_root item-ctx.artifact-root))
           (resolved
             (call project-work-item-inputs
               :item_ctx design-delta-item-ctx
               :work_item_bootstrap selection.work_item_bootstrap))
           (fallback
             (call make-fallback-report))
           (plan
             (call run-plan-phase
               :steering selection.steering_path
               :target_design selection.target_design_path
               :baseline_design selection.baseline_design_path
               :work_item_context resolved.work_item_context
               :progress_ledger selection.progress_ledger_path
               :plan_target_path resolved.plan_target_path
               :progress_report_target_path resolved.progress_report_target_path
               :plan_review_report_target_path resolved.plan_review_report_target_path)))
      (match plan
        ((APPROVED approved)
         (let* ((implementation
                  (call implementation-phase
                    :target_design selection.target_design_path
                    :baseline_design selection.baseline_design_path
                    :check_commands resolved.check_commands
                    :check_commands_target_path resolved.check_commands_target_path
                    :plan_path approved.approved_plan_path
                    :execution_report_target_path resolved.execution_report_target_path
                    :progress_report_target_path resolved.progress_report_target_path
                    :checks_report_target_path resolved.checks_report_target_path
                    :implementation_review_report_target_path
                      resolved.implementation_review_report_target_path)))
           (variant HookRunResult CONTINUE
             :summary-path implementation.execution-report)))
        ((BLOCKED blocked)
         (variant HookRunResult BLOCKED
           :summary-path fallback.report
           :blocker-class fallback.blocker))
        ((EXHAUSTED exhausted)
         (variant HookRunResult BLOCKED
           :summary-path fallback.report
           :blocker-class fallback.blocker)))))

  (defworkflow drain-entry
    ()
    -> DrainResult
    (let* ((runtime-owned
             (call build-runtime-owned))
           (ctx
             (record HookDrainCtx
               :run runtime-owned.run
               :state-root runtime-owned.run.state-root
               :manifest runtime-owned.run.state-root
               :ledger runtime-owned.run.state-root))
           (terminal (backlog-drain-proc
                       ctx
                       (proc-ref select-stub)
                       (proc-ref run-item-with-child-phases)
                       (proc-ref gap-stub)
                       3
                       (__generated-relpath-seed__
                         WorkReport
                         "artifacts/work/drain-progress-report.md"
                         "design_delta_loop_promoted_hook_phase_ctx_progress_report_seed"))))
      (settle-drain-terminal terminal)))

  (defrecord LoopRuntimeOwned
    (run RunCtx))

  (defworkflow build-runtime-owned
    ((run RunCtx))
    -> LoopRuntimeOwned
    (record LoopRuntimeOwned
      :run (record RunCtx
             :run-id run.run-id
             :state-root run.state-root
             :artifact-root run.artifact-root))))
