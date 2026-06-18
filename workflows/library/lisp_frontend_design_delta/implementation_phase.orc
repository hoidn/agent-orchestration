(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/implementation_phase)
  (import std/phase :only
    (BlockerClass ReviewDecision ReviewFindings ReviewFindingsJsonPath ReviewReportPath
      review-revise-loop))
  (import lisp_frontend_design_delta/types :only
    (ArtifactChecksPath ArtifactChecksTargetPath ArtifactReviewTargetPath ArtifactWorkPath
      ArtifactWorkTargetPath BaselineDesignDoc CheckCommandsPath CheckCommandsTargetPath
      CheckCommandsValue ImplementationPhaseResult ImplementationReviewDecision
      ImplementationState PlanDoc TargetDesignDoc))
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

  (defrecord ImplementationExecutePromptSubject
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (plan_path PlanDoc)
    (check_commands CheckCommandsValue))

  (defrecord ImplementationExecuteProviderTargets
    (execution_report_target_path ArtifactWorkTargetPath)
    (progress_report_target_path ArtifactWorkTargetPath)
    (checks_report_target_path ArtifactChecksTargetPath)
    (implementation_review_report_target_path ArtifactReviewTargetPath))

  (defrecord ImplementationExecuteRequest
    (subject ImplementationExecutePromptSubject)
    (targets ImplementationExecuteProviderTargets))

  (defrecord PrivateImplementationReviewSubject
    (execution_report ArtifactWorkTargetPath)
    (checks_report ArtifactChecksPath))

  (defrecord ImplementationReviewPromptSubject
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (plan_path PlanDoc)
    (execution_report ArtifactWorkTargetPath)
    (checks_report ArtifactChecksPath))

  (defrecord ImplementationReviewProviderTargets
    (implementation_review_report_target_path ArtifactReviewTargetPath))

  (defrecord ImplementationReviewRequest
    (subject ImplementationReviewPromptSubject)
    (targets ImplementationReviewProviderTargets))

  (defrecord ImplementationFixPromptSubject
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (plan_path PlanDoc)
    (execution_report ArtifactWorkTargetPath)
    (checks_report ArtifactChecksPath)
    (findings_items_path ReviewFindingsJsonPath))

  (defrecord ImplementationFixProviderTargets
    (execution_report_target_path ArtifactWorkTargetPath))

  (defrecord ImplementationFixRequest
    (subject ImplementationFixPromptSubject)
    (targets ImplementationFixProviderTargets))

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
    ((check_commands CheckCommandsValue)
     (check_commands_target_path CheckCommandsTargetPath)
     (checks_report_target_path ArtifactChecksTargetPath))
    -> ChecksResult
    :effects ((uses-command run_neurips_backlog_checks)
              (writes check-commands-view))
    :lowering inline
    (let* ((check-commands-path
             (materialize-view check-commands-view
               :value check_commands.commands
               :renderer canonical-json
               :renderer-version 1
               :target check_commands_target_path
               :returns CheckCommandsPath)))
      (command-result run_neurips_backlog_checks
        :argv ("python"
               "workflows/library/scripts/run_neurips_backlog_checks.py"
               "--checks-path"
               check-commands-path
               "--report-path"
               checks_report_target_path
               "--cwd"
               ".")
        :returns ChecksResult)))

  (defproc review-implementation
    ((completed PrivateImplementationReviewSubject)
     (inputs ImplementationReviewInputs))
    -> ReviewDecision
    :effects ((uses-provider providers.implementation.review))
    :lowering inline
    (let* ((subject
             (record ImplementationReviewPromptSubject
               :target_design inputs.target_design
               :baseline_design inputs.baseline_design
               :plan_path inputs.plan_path
               :execution_report completed.execution_report
               :checks_report completed.checks_report))
           (targets
             (record ImplementationReviewProviderTargets
               :implementation_review_report_target_path inputs.implementation_review_report_target_path))
           (request
             (record ImplementationReviewRequest
               :subject subject
               :targets targets)))
      (provider-result providers.implementation.review
        :prompt prompts.implementation.review
        :inputs (request)
        :returns ReviewDecision)))

  (defproc fix-implementation
    ((completed PrivateImplementationReviewSubject)
     (inputs ImplementationReviewInputs)
     (findings ReviewFindings))
    -> PrivateImplementationReviewSubject
    :effects ((uses-provider providers.implementation.fix))
    :lowering inline
    (let* ((subject
             (record ImplementationFixPromptSubject
               :target_design inputs.target_design
               :baseline_design inputs.baseline_design
               :plan_path inputs.plan_path
               :execution_report completed.execution_report
               :checks_report completed.checks_report
               :findings_items_path findings.items_path))
           (targets
             (record ImplementationFixProviderTargets
               :execution_report_target_path inputs.execution_report_target_path))
           (request
             (record ImplementationFixRequest
               :subject subject
               :targets targets)))
      (provider-result providers.implementation.fix
        :prompt prompts.implementation.fix
        :inputs (request)
        :returns PrivateImplementationReviewSubject)))

  (defworkflow implementation-phase
    ((phase-ctx PhaseCtx)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (check_commands CheckCommandsValue)
     (check_commands_target_path CheckCommandsTargetPath)
     (plan_path PlanDoc)
     (execution_report_target_path ArtifactWorkTargetPath)
     (progress_report_target_path ArtifactWorkTargetPath)
     (checks_report_target_path ArtifactChecksTargetPath)
     (implementation_review_report_target_path ArtifactReviewTargetPath))
    -> ImplementationPhaseResult
    (let* ((execute-subject
             (record ImplementationExecutePromptSubject
               :target_design target_design
               :baseline_design baseline_design
               :plan_path plan_path
               :check_commands check_commands))
           (execute-targets
             (record ImplementationExecuteProviderTargets
               :execution_report_target_path execution_report_target_path
               :progress_report_target_path progress_report_target_path
               :checks_report_target_path checks_report_target_path
               :implementation_review_report_target_path implementation_review_report_target_path))
           (execute-request
             (record ImplementationExecuteRequest
               :subject execute-subject
               :targets execute-targets))
           (attempt
             (provider-result providers.implementation.execute
               :prompt prompts.implementation.execute
               :inputs (execute-request)
               :returns ImplementationAttempt)))
      (match attempt
        ((COMPLETED completed)
         (let* ((checks
                  (run-checks
                    check_commands
                    check_commands_target_path
                    checks_report_target_path))
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
