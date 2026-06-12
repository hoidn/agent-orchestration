(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/implementation_phase)
  (import std/phase :only
    (BlockerClass ReviewDecision ReviewFindings ReviewReportPath review-revise-loop))
  (import lisp_frontend_design_delta/types :only
    (ArtifactChecksPath ArtifactChecksTargetPath ArtifactReviewTargetPath ArtifactWorkPath
      ArtifactWorkTargetPath BaselineDesignDoc CheckCommandsPath ImplementationPhaseResult
      ImplementationReviewDecision ImplementationState PlanDoc TargetDesignDoc))
  (export implementation-phase)

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

  (defrecord PrivateImplementationReviewSubject
    (execution_report ArtifactWorkTargetPath)
    (checks_report ArtifactChecksPath))

  (defunion ImplementationAttempt
    (COMPLETED
      (implementation_state ImplementationState)
      (execution_report ArtifactWorkTargetPath))
    (BLOCKED
      (implementation_state ImplementationState)
      (implementation_review_decision ImplementationReviewDecision)
      (progress_report ArtifactWorkTargetPath)
      (blocker_class BlockerClass)))

  (defrecord ImplementationReviewInputs
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (plan_path PlanDoc)
    (execution_report_target_path ArtifactWorkTargetPath)
    (implementation_review_report_target_path ArtifactReviewTargetPath))

  (defproc run-checks
    ((check_commands_path CheckCommandsPath)
     (checks_report_target_path ArtifactChecksTargetPath))
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
    ((completed PrivateImplementationReviewSubject)
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
    ((completed PrivateImplementationReviewSubject)
     (inputs ImplementationReviewInputs)
     (findings ReviewFindings))
    -> PrivateImplementationReviewSubject
    :effects ((uses-provider providers.implementation.fix))
    :lowering inline
    (provider-result providers.implementation.fix
      :prompt prompts.implementation.fix
      :inputs (inputs.target_design
               inputs.baseline_design
               inputs.plan_path
               completed.execution_report
               inputs.execution_report_target_path
               completed.checks_report
               findings.items_path)
      :returns PrivateImplementationReviewSubject))

  (defworkflow implementation-phase
    ((phase-ctx PhaseCtx)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (check_commands_path CheckCommandsPath)
     (plan_path PlanDoc)
     (execution_report_target_path ArtifactWorkTargetPath)
     (progress_report_target_path ArtifactWorkTargetPath)
     (checks_report_target_path ArtifactChecksTargetPath)
     (implementation_review_report_target_path ArtifactReviewTargetPath))
    -> ImplementationPhaseResult
    (let* ((attempt
             (provider-result providers.implementation.execute
               :prompt prompts.implementation.execute
               :inputs (target_design
                        baseline_design
                        plan_path
                        check_commands_path
                        execution_report_target_path
                        progress_report_target_path
                        checks_report_target_path
                        implementation_review_report_target_path)
               :returns ImplementationAttempt)))
      (match attempt
        ((COMPLETED completed)
         (let* ((checks
                  (run-checks check_commands_path checks_report_target_path))
                (review-subject
                  (record PrivateImplementationReviewSubject
                    :execution_report completed.execution_report
                    :checks_report checks.checks_report))
                (review-inputs
                  (record ImplementationReviewInputs
                    :target_design target_design
                    :baseline_design baseline_design
                    :plan_path plan_path
                    :execution_report_target_path execution_report_target_path
                    :implementation_review_report_target_path implementation_review_report_target_path))
                (review
                  (review-revise-loop implementation-review
                    :ctx phase-ctx
                    :completed review-subject
                    :inputs review-inputs
                    :review (proc-ref review-implementation)
                    :fix (proc-ref fix-implementation)
                    :max 40))
                (review-decision
                  (match review
                    ((APPROVED approved)
                     ImplementationReviewDecision.APPROVE)
                    ((BLOCKED blocked)
                     ImplementationReviewDecision.REVISE)
                    ((EXHAUSTED exhausted)
                     ImplementationReviewDecision.REVISE))))
           (record ImplementationPhaseResult
             :implementation-state completed.implementation_state
             :implementation-review-decision review-decision
             :execution-report completed.execution_report
             :progress-report progress_report_target_path
             :checks-report checks_report_target_path
             :implementation-review-report implementation_review_report_target_path)))
        ((BLOCKED blocked)
        (record ImplementationPhaseResult
           :implementation-state blocked.implementation_state
           :implementation-review-decision blocked.implementation_review_decision
           :execution-report execution_report_target_path
           :progress-report blocked.progress_report
           :checks-report checks_report_target_path
           :implementation-review-report implementation_review_report_target_path))))))
