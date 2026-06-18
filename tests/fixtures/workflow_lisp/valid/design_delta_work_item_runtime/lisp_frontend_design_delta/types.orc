(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/types)
  (import std/phase :only (BlockerClass ReviewDecision ReviewFindings ReviewReportPath))
  (export
    ArchitectureValidationResult
    ArtifactChecksPath
    ArtifactChecksTargetPath
    ArtifactReviewPath
    ArtifactReviewTargetPath
    ArtifactWorkPath
    ArtifactWorkTargetPath
    BaselineDesignDoc
    BlockedRecoveryDecision
    BlockedRecoveryRoute
    BlockedRecoveryReason
    BlockedRecoveryOutcome
    CheckCommandsPath
    CheckCommandsTargetPath
    CheckCommandsValue
    DesignRevisionDecision
    DesignRevisionReviewDecision
    DesignRevisionResult
    DesignGapId
    DrainIterationStatus
    DrainResult
    DrainTerminalStatus
    ImplementationAttempt
    ImplementationPhaseResult
    ImplementationReviewDecision
    ImplementationState
    ArtifactJustification
    BoundaryJustification
    DesignDeltaDrainAction
    DrainState
    DrainLoopTerminal
    DrainSummaryValue
    PlanDoc
    PlanDocTarget
    PlanDraftResult
    PlanPhaseResult
    PlanReviewDecision
    PreSelectionRoute
    RecoveredGapAttempt
    RecoveryDrainStatus
    ProgressLedger
    RecoveryStatus
    ResolvedWorkItemInputs
    RunStatePath
    SelectionBundlePath
    SelectionCtx
    SelectionResult
    SelectionStatus
    StateDir
    StateFile
    StateFileExisting
    SteeringDoc
    TargetDesignDoc
    ItemCtx
    WorkItemResult
    WorkItemBootstrapSeed
    WorkItemContextValue
    WorkItemSummaryValue
    WorkItemSource
    WorkItemTerminalDecision
    WorkItemTerminalReason
    WorkItemTerminalRoute
    WorkReport
    WorkReportTarget)

  (defenum DrainIterationStatus
    CONTINUE
    DONE
    BLOCKED)

  (defenum DrainTerminalStatus
    DONE
    BLOCKED
    EXHAUSTED)

  (defenum SelectionStatus
    SELECT_BACKLOG_ITEM
    DRAFT_DESIGN_GAP
    DONE
    BLOCKED)

  (defenum PreSelectionRoute
    SELECT_NORMAL_WORK
    SELECT_PREREQUISITE_WORK
    RECOVER_BLOCKED_DESIGN_GAP
    BLOCKED)

  (defenum RecoveryStatus
    NOT_APPLICABLE
    RETRY_READY
    WAITING_ON_RECOVERABLE_PREREQUISITE
    RECOVERY_CONTINUES
    BLOCKED)

  (defenum RecoveryDrainStatus
    CONTINUE
    BLOCKED
    RUN_RECOVERED_GAP)

  (defenum BlockedRecoveryReason
    not_blocked
    implementation_blocked
    implementation_architecture_under_scoped
    target_design_contract_gap
    prerequisite_gap_required
    true_external_dependency
    user_decision_required
    unsupported_blocker)

  (defenum BlockedRecoveryRoute
    GAP_DESIGN_REVISION_REQUIRED
    TARGET_DESIGN_REVISION_REQUIRED
    PREREQUISITE_GAP_REQUIRED
    TERMINAL_BLOCKED)

  (defenum ArchitectureValidationResult
    VALID
    BLOCKED
    INVALID)

  (defenum DesignRevisionDecision
    REVISED
    BLOCKED)

  (defenum DesignRevisionReviewDecision
    APPROVE
    REVISE
    BLOCKED)

  (defenum WorkItemSource
    BACKLOG_ITEM
    DESIGN_GAP)

  (defenum PlanReviewDecision
    APPROVE
    REVISE)

  (defenum ImplementationState
    COMPLETED
    BLOCKED)

  (defenum ImplementationReviewDecision
    APPROVE
    REVISE
    NOT_APPLICABLE)

  (defenum WorkItemTerminalReason
    plan_blocked
    plan_review_exhausted
    implementation_blocked
    implementation_review_exhausted)

  (defenum WorkItemTerminalRoute
    COMPLETE
    PLAN_REVIEW_EXHAUSTED
    IMPLEMENTATION_BLOCKED
    IMPLEMENTATION_REVIEW_EXHAUSTED)

  (defunion WorkItemTerminalDecision
    (COMPLETE)
    (PLAN_REVIEW_EXHAUSTED)
    (IMPLEMENTATION_BLOCKED)
    (IMPLEMENTATION_REVIEW_EXHAUSTED))

  (defenum DesignGapId
    DESIGN_GAP)

  (defpath SteeringDoc
    :kind relpath
    :under "docs"
    :must-exist true)

  (defpath TargetDesignDoc
    :kind relpath
    :under "docs/design"
    :must-exist true)

  (defpath BaselineDesignDoc
    :kind relpath
    :under "docs/design"
    :must-exist true)

  (defpath ProgressLedger
    :kind relpath
    :under "state"
    :must-exist true)

  (defpath RunStatePath
    :kind relpath
    :under "state"
    :must-exist true)

  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)

  (defpath StateFileExisting
    :kind relpath
    :under "state"
    :must-exist true)

  (defpath CheckCommandsTargetPath
    :kind relpath
    :under "state"
    :must-exist false)

  (defpath StateDir
    :kind relpath
    :under "state"
    :must-exist false)

  (defpath ArtifactWorkPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defpath ArtifactWorkTargetPath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defpath ArtifactReviewPath
    :kind relpath
    :under "artifacts/review"
    :must-exist true)

  (defpath ArtifactChecksPath
    :kind relpath
    :under "artifacts/checks"
    :must-exist true)

  (defpath ArtifactChecksTargetPath
    :kind relpath
    :under "artifacts/checks"
    :must-exist false)

  (defpath ArtifactReviewTargetPath
    :kind relpath
    :under "artifacts/review"
    :must-exist false)

  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defpath WorkReportTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defpath PlanDoc
    :kind relpath
    :under "docs/plans"
    :must-exist true)

  (defpath PlanDocTarget
    :kind relpath
    :under "docs/plans"
    :must-exist false)

  (defpath CheckCommandsPath
    :kind relpath
    :under "state"
    :must-exist true)

  (defpath SelectionBundlePath
    :kind relpath
    :under "state"
    :must-exist true)

  (defrecord CheckCommandsValue
    (commands List[String]))

  (defrecord SelectionCtx
    (state_root Path.state-root)
    (artifact_root Path.artifact-root))

  (defrecord ItemCtx
    (selection SelectionCtx)
    (work_item_id String)
    (state_root Path.state-root)
    (artifact_root Path.artifact-root))

  (defrecord WorkItemContextValue
    (work_item_source WorkItemSource)
    (work_item_id String)
    (plan_target_path PlanDocTarget)
    (architecture_path PlanDocTarget))

  (defrecord WorkItemBootstrapSeed
    (work_item_source WorkItemSource)
    (work_item_id String)
    (plan_target_path PlanDocTarget)
    (check_commands CheckCommandsValue)
    (architecture_path PlanDocTarget))

  (defrecord SelectionPayload
    (work-item-id String)
    (work-item-state-root StateFile))

  (defrecord GapPayload
    (design-gap-id String)
    (architecture-path StateFile))

  (defunion SelectionResult
    (SELECT_BACKLOG_ITEM
      (selection SelectionPayload))
    (DRAFT_DESIGN_GAP
      (gap GapPayload))
    (DONE
      (run-state RunStatePath))
    (BLOCKED
      (reason String)))

  (defunion BlockedRecoveryDecision
    (GAP_DESIGN_REVISION_REQUIRED
      (reason BlockedRecoveryReason))
    (TARGET_DESIGN_REVISION_REQUIRED
      (reason BlockedRecoveryReason))
    (PREREQUISITE_GAP_REQUIRED
      (reason BlockedRecoveryReason))
    (TERMINAL_BLOCKED
      (reason BlockedRecoveryReason)))

  (defunion RecoveredGapAttempt
    (DRAFTED
      (draft-bundle StateFileExisting))
    (VALIDATED
      (architecture-validation ArchitectureValidationResult)
      (architecture-bundle StateFileExisting))
    (PREPARED_WORK_ITEM
      (selection-bundle SelectionBundlePath)
      (manifest StateFileExisting)
      (architecture-bundle StateFileExisting)
      (work-item-state-root StateDir))
    (RETRY_UNAVAILABLE
      (reason String)))

  (defunion BlockedRecoveryOutcome
    (RECORDED_RECOVERY_EVENT
      (drain-status RecoveryDrainStatus)
      (summary WorkReport))
    (RETRY_READY
      (recovered-draft StateFileExisting)
      (architecture-bundle StateFileExisting)
      (selection-bundle SelectionBundlePath)
      (work-item-state-root StateDir))
    (PREREQUISITE_CHILD_EDGE
      (design-gap-id String)
      (record-status RecoveryStatus))
    (TERMINAL_BLOCK
      (reason BlockedRecoveryReason)
      (terminal-summary WorkReport)))

  (defrecord DesignRevisionResult
    (decision DesignRevisionDecision)
    (report WorkReport))

  (defunion ImplementationAttempt
    (COMPLETED
      (execution-report ArtifactWorkPath))
    (BLOCKED
      (progress-report ArtifactWorkPath)
      (blocker-class BlockerClass)))

  (defrecord PlanPhaseResult
    (plan-path PlanDoc)
    (plan-review-report ArtifactReviewPath)
    (plan-review-decision ReviewDecision))

  (defrecord PlanDraftResult
    (plan_path PlanDoc))

  (defrecord ResolvedWorkItemInputs
    (work_item_source WorkItemSource)
    (work_item_id String)
    (selection_state_root Path.state-root)
    (selection_artifact_root Path.artifact-root)
    (item_state_root Path.state-root)
    (item_artifact_root Path.artifact-root)
    (work_item_context WorkItemContextValue)
    (work_item_context_view_target_path WorkReportTarget)
    (check_commands CheckCommandsValue)
    (check_commands_target_path CheckCommandsTargetPath)
    (plan_target_path PlanDocTarget)
    (plan_phase_state_root StateDir)
    (implementation_phase_state_root StateDir)
    (plan_review_report_target_path ArtifactReviewTargetPath)
    (execution_report_target_path ArtifactWorkTargetPath)
    (progress_report_target_path ArtifactWorkTargetPath)
    (checks_report_target_path ArtifactChecksTargetPath)
    (implementation_review_report_target_path ArtifactReviewTargetPath)
    (item_summary_pointer_path WorkReportTarget)
    (drain_status_path StateFile)
    (item_summary_target_path WorkReportTarget))

  (defrecord ImplementationPhaseResult
    (implementation-state ImplementationState)
    (implementation-review-decision ImplementationReviewDecision)
    (execution-report ArtifactWorkTargetPath)
    (progress-report ArtifactWorkTargetPath)
    (checks-report ArtifactChecksTargetPath)
    (implementation-review-report ArtifactReviewTargetPath))

  (defunion WorkItemResult
    (COMPLETED
      (reason String)
      (summary WorkReport))
    (TERMINAL_BLOCKED
      (reason String)
      (summary WorkReport))
    (BLOCKED_RECOVERY
      (reason String)
      (summary WorkReport)))

  (defrecord DrainState
    (iteration-count Int)
    (item-count Int))

  (defunion DrainLoopTerminal
    (DONE)
    (BLOCKED
      (reason String))
    (BLOCKED_RECOVERY
      (reason String))
    (EXHAUSTED
      (reason String)))

  (defrecord DrainSummaryValue
    (drain_status DrainTerminalStatus)
    (drain_status_reason String)
    (run_state_path RunStatePath)
    (summary_target WorkReportTarget)
    (state_version String))

  (defrecord WorkItemSummaryValue
    (work_item_id String)
    (work_item_source WorkItemSource)
    (terminal_route String)
    (reason String))

  (defunion DesignDeltaDrainAction
    (SELECTED_ITEM
      (selected_item_bootstrap WorkItemBootstrapSeed))
    (DRAFT_DESIGN_GAP
      (design_gap_bootstrap WorkItemBootstrapSeed))
    (BLOCKED_RECOVERY
      (blocked_recovery_selection_bundle SelectionBundlePath)
      (blocked_recovery_reason String))
    (DONE)
    (BLOCKED
      (blocked_reason String))
    (EXHAUSTED
      (exhausted_reason String)))

  (defrecord BoundaryJustification
    (boundary_id String)
    (reason String)
    (route String)
    (schema_version Int)
    (readiness_label String)
    (parity_constrained Bool))

  (defrecord ArtifactJustification
    (artifact_id String)
    (reason String)
    (route String)
    (schema_version Int)
    (readiness_label String)
    (parity_constrained Bool))

  (defunion DrainResult
    (DONE
      (run-state RunStatePath)
      (drain-summary WorkReport))
    (BLOCKED
      (reason String)
      (run-state RunStatePath)
      (drain-summary WorkReport))
    (EXHAUSTED
      (reason String)
      (run-state RunStatePath)
      (drain-summary WorkReport))))
