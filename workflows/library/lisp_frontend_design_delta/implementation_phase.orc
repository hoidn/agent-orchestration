(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/implementation_phase)
  (import std/phase :only
    (BlockerClass ReviewDecision ReviewFindings ReviewReportPath review-revise-loop))
  (import lisp_frontend_design_delta/types :only
    (ArtifactChecksPath ArtifactWorkPath BaselineDesignDoc CheckCommandsPath PlanDoc TargetDesignDoc))
  (export execute-implementation-attempt review-completed-implementation)

  (defpath ExecutionReportTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defpath ProgressReportTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defpath ChecksReportTarget
    :kind relpath
    :under "artifacts/checks"
    :must-exist false)

  (defpath ImplementationReviewReportTarget
    :kind relpath
    :under "artifacts/review"
    :must-exist false)

  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord ChecksResult
    (checks_report ArtifactChecksPath))

  (defunion ImplementationAttempt
    (COMPLETED
      (execution_report ArtifactWorkPath))
    (BLOCKED
      (progress_report ArtifactWorkPath)
      (blocker_class BlockerClass)))

  (defrecord ImplementationReviewSubject
    (execution_report ArtifactWorkPath)
    (checks_report ArtifactChecksPath))

  (defrecord ImplementationFixResult
    (execution_report ArtifactWorkPath))

  (defrecord ImplementationReviewInputs
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (plan_path PlanDoc)
    (execution_report_target_path ExecutionReportTarget)
    (implementation_review_report_target_path ImplementationReviewReportTarget))

  (defunion CompletedImplementationReviewResult
    (APPROVED
      (approved_execution_report ArtifactWorkPath)
      (approved_checks_report ArtifactChecksPath)
      (approved_implementation_review_report_path ReviewReportPath)
      (implementation_review_decision String)
      (approved_findings ReviewFindings))
    (BLOCKED
      (blocked_execution_report ArtifactWorkPath)
      (blocked_checks_report ArtifactChecksPath)
      (blocked_implementation_review_report_path ReviewReportPath)
      (blocker_class BlockerClass)
      (implementation_review_decision String)
      (blocked_findings ReviewFindings))
    (EXHAUSTED
      (exhausted_execution_report ArtifactWorkPath)
      (exhausted_checks_report ArtifactChecksPath)
      (last_implementation_review_report_path ReviewReportPath)
      (implementation_review_decision String)
      (reason String)
      (exhausted_findings ReviewFindings)))

  (defworkflow execute-implementation-attempt
    ((target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (plan_path PlanDoc)
     (check_commands_path CheckCommandsPath)
     (execution_report_target_path ExecutionReportTarget)
     (progress_report_target_path ProgressReportTarget))
    -> ImplementationAttempt
    (provider-result providers.implementation.execute
      :prompt prompts.implementation.execute
      :inputs (target_design
               baseline_design
               plan_path
               check_commands_path
               execution_report_target_path
               progress_report_target_path)
      :returns ImplementationAttempt))

  (defproc run-checks
    ((check_commands_path CheckCommandsPath)
     (checks_report_target_path ChecksReportTarget))
    -> ChecksResult
    :effects ((uses-command run_neurips_backlog_checks))
    :lowering inline
    (command-result run_neurips_backlog_checks
      :argv ("python"
             "workflows/library/scripts/run_neurips_backlog_checks.py"
             "--checks-path"
             check_commands_path
             "--report-path"
             checks_report_target_path
             "--cwd"
             ".")
      :returns ChecksResult))

  (defproc review-implementation
    ((completed ImplementationReviewSubject)
     (inputs ImplementationReviewInputs))
    -> ReviewDecision
    :effects ((uses-provider providers.implementation.review))
    :lowering inline
    (provider-result providers.implementation.review
      :prompt prompts.implementation.review
      :inputs (inputs.target_design
               inputs.baseline_design
               inputs.plan_path
               completed.execution_report
               completed.checks_report
               inputs.implementation_review_report_target_path)
      :returns ReviewDecision))

  (defproc fix-implementation
    ((completed ImplementationReviewSubject)
     (inputs ImplementationReviewInputs)
     (findings ReviewFindings))
    -> ImplementationReviewSubject
    :effects ((uses-provider providers.implementation.fix))
    :lowering inline
    (let* ((fixed
             (provider-result providers.implementation.fix
               :prompt prompts.implementation.fix
               :inputs (inputs.target_design
                        inputs.baseline_design
                        inputs.plan_path
                        completed.execution_report
                        inputs.execution_report_target_path
                        completed.checks_report
                        findings.items_path)
               :returns ImplementationFixResult)))
      (record ImplementationReviewSubject
        :execution_report fixed.execution_report
        :checks_report completed.checks_report)))

  (defworkflow review-completed-implementation
    ((phase-ctx PhaseCtx)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (plan_path PlanDoc)
     (execution_report ArtifactWorkPath)
     (check_commands_path CheckCommandsPath)
     (execution_report_target_path ExecutionReportTarget)
     (checks_report_target_path ChecksReportTarget)
     (implementation_review_report_target_path ImplementationReviewReportTarget))
    -> CompletedImplementationReviewResult
    (with-phase phase-ctx implementation-review
      (let* ((checks
               (run-checks check_commands_path checks_report_target_path))
             (completed
               (record ImplementationReviewSubject
                 :execution_report execution_report
                 :checks_report checks.checks_report))
             (inputs
               (record ImplementationReviewInputs
                 :target_design target_design
                 :baseline_design baseline_design
                 :plan_path plan_path
                 :execution_report_target_path execution_report_target_path
                 :implementation_review_report_target_path implementation_review_report_target_path))
             (review
               (review-revise-loop implementation-review
                 :ctx phase-ctx
                 :completed completed
                 :inputs inputs
                 :review (proc-ref review-implementation)
                 :fix (proc-ref fix-implementation)
                 :max 40)))
        (match review
          ((APPROVED approved)
           (variant CompletedImplementationReviewResult APPROVED
             :approved_execution_report completed.execution_report
             :approved_checks_report completed.checks_report
             :approved_implementation_review_report_path approved.review_report
             :implementation_review_decision "APPROVE"
             :approved_findings
               (record ReviewFindings
                 :schema_version approved.findings.schema_version
                 :items_path approved.findings.items_path)))
          ((BLOCKED blocked)
           (variant CompletedImplementationReviewResult BLOCKED
             :blocked_execution_report completed.execution_report
             :blocked_checks_report completed.checks_report
             :blocked_implementation_review_report_path blocked.review_report
             :blocker_class blocked.blocker_class
             :implementation_review_decision "REVISE"
             :blocked_findings
               (record ReviewFindings
                 :schema_version blocked.findings.schema_version
                 :items_path blocked.findings.items_path)))
          ((EXHAUSTED exhausted)
           (variant CompletedImplementationReviewResult EXHAUSTED
             :exhausted_execution_report completed.execution_report
             :exhausted_checks_report completed.checks_report
             :last_implementation_review_report_path exhausted.last_review_report
             :implementation_review_decision "REVISE"
             :reason exhausted.reason
             :exhausted_findings
               (record ReviewFindings
                 :schema_version exhausted.findings.schema_version
                 :items_path exhausted.findings.items_path))))))))
