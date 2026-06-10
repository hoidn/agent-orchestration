(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule design_delta_parent_calls_implementation_phase)
  (import lisp_frontend_design_delta/implementation_phase :only (implementation-phase))
  (import lisp_frontend_design_delta/types :only
    (ArtifactChecksTargetPath ArtifactReviewTargetPath ArtifactWorkTargetPath BaselineDesignDoc
      CheckCommandsPath ImplementationPhaseResult PlanDoc TargetDesignDoc))
  (export run-implementation-phase)

  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defworkflow run-implementation-phase
    ((phase-ctx PhaseCtx)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (plan_path PlanDoc)
     (check_commands_path CheckCommandsPath)
     (execution_report_target_path ArtifactWorkTargetPath)
     (progress_report_target_path ArtifactWorkTargetPath)
     (checks_report_target_path ArtifactChecksTargetPath)
     (implementation_review_report_target_path ArtifactReviewTargetPath))
    -> ImplementationPhaseResult
    (let* ((phase-result
             (call implementation-phase
               :phase-ctx phase-ctx
               :target_design target_design
               :baseline_design baseline_design
               :plan_path plan_path
               :check_commands_path check_commands_path
               :execution_report_target_path execution_report_target_path
               :progress_report_target_path progress_report_target_path
               :checks_report_target_path checks_report_target_path
               :implementation_review_report_target_path implementation_review_report_target_path)))
      (record ImplementationPhaseResult
        :implementation-state phase-result.implementation-state
        :implementation-review-decision phase-result.implementation-review-decision
        :execution-report phase-result.execution-report
        :progress-report phase-result.progress-report
        :checks-report phase-result.checks-report
        :implementation-review-report phase-result.implementation-review-report))))
