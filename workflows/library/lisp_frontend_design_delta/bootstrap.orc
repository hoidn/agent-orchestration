(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/bootstrap)
  (import lisp_frontend_design_delta/types :only
    (ArtifactChecksTargetPath ArtifactReviewTargetPath ArtifactWorkTargetPath
      CheckCommandsTargetPath ItemCtx ResolvedWorkItemInputs StateDir StateFile
      WorkItemBootstrapSeed WorkItemContextValue WorkReportTarget))
  (export project-work-item-inputs)

  (defworkflow project-work-item-inputs
    ((item_ctx ItemCtx)
     (work_item_bootstrap WorkItemBootstrapSeed))
    -> ResolvedWorkItemInputs
    (let* ((work-item-context-view-target
             (__generated-relpath-seed__
               WorkReportTarget
               "artifacts/work/runtime_work_item_context.md"
               "work_item_context_view_target"))
           (check-commands-target
             (__generated-relpath-seed__
               CheckCommandsTargetPath
               "state/runtime_work_item/check_commands.json"
               "work_item_check_commands_target"))
           (plan-phase-state-root
             (__generated-relpath-seed__
               StateDir
               "state/runtime_work_item/plan-phase"
               "work_item_plan_phase_state_root"))
           (implementation-phase-state-root
             (__generated-relpath-seed__
               StateDir
               "state/runtime_work_item/implementation-phase"
               "work_item_implementation_phase_state_root"))
           (plan-review-report-target
             (__generated-relpath-seed__
               ArtifactReviewTargetPath
               "artifacts/review/plan_review_report.md"
               "work_item_plan_review_report_target"))
           (execution-report-target
             (__generated-relpath-seed__
               ArtifactWorkTargetPath
               "artifacts/work/execution_report.md"
               "work_item_execution_report_target"))
           (progress-report-target
             (__generated-relpath-seed__
               ArtifactWorkTargetPath
               "artifacts/work/progress_report.md"
               "work_item_progress_report_target"))
           (checks-report-target
             (__generated-relpath-seed__
               ArtifactChecksTargetPath
               "artifacts/checks/checks_report.md"
               "work_item_checks_report_target"))
           (implementation-review-report-target
             (__generated-relpath-seed__
               ArtifactReviewTargetPath
               "artifacts/review/implementation_review_report.md"
               "work_item_implementation_review_report_target"))
           (item-summary-pointer-target
             (__generated-relpath-seed__
               WorkReportTarget
               "artifacts/work/item_summary.json.pointer.txt"
               "work_item_summary_pointer_target"))
           (drain-status-target
             (__generated-relpath-seed__
               StateFile
               "state/runtime_work_item/drain_status.txt"
               "work_item_drain_status_target"))
           (item-summary-target
             (__generated-relpath-seed__
               WorkReportTarget
               "artifacts/work/item_summary.json"
               "work_item_summary_target")))
      (record ResolvedWorkItemInputs
        :work_item_source work_item_bootstrap.work_item_source
        :work_item_id item_ctx.work_item_id
        :selection_state_root item_ctx.selection.state_root
        :selection_artifact_root item_ctx.selection.artifact_root
        :item_state_root item_ctx.state_root
        :item_artifact_root item_ctx.artifact_root
        :work_item_context
          (record WorkItemContextValue
            :work_item_source work_item_bootstrap.work_item_source
            :work_item_id item_ctx.work_item_id
            :plan_target_path work_item_bootstrap.plan_target_path
            :architecture_path work_item_bootstrap.architecture_path)
        :work_item_context_view_target_path work-item-context-view-target
        :check_commands work_item_bootstrap.check_commands
        :check_commands_target_path check-commands-target
        :plan_target_path work_item_bootstrap.plan_target_path
        :plan_phase_state_root plan-phase-state-root
        :implementation_phase_state_root implementation-phase-state-root
        :plan_review_report_target_path plan-review-report-target
        :execution_report_target_path execution-report-target
        :progress_report_target_path progress-report-target
        :checks_report_target_path checks-report-target
        :implementation_review_report_target_path implementation-review-report-target
        :item_summary_pointer_path item-summary-pointer-target
        :drain_status_path drain-status-target
        :item_summary_target_path item-summary-target))))
