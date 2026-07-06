(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/types)
  (import std/context :only (RunCtx))
  (import std/resource :only (SelectedItemResult))
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
    DesignDeltaDrainCtx
    DesignDeltaGapPayload
    DesignDeltaSelectedItemPayload
    DesignDeltaSelectionResult
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
    completed
    plan_blocked
    plan_review_exhausted
    implementation_blocked
    implementation_review_exhausted)

  (defenum WorkItemTerminalRoute
    COMPLETE
    PLAN_BLOCKED
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

  (defrecord DesignDeltaDrainCtx
    (run RunCtx)
    (state-root Path.state-root)
    (manifest StateFileExisting)
    (ledger Path.state-root)
    (steering_path SteeringDoc)
    (target_design_path TargetDesignDoc)
    (baseline_design_path BaselineDesignDoc)
    (progress_ledger_path ProgressLedger)
    (existing_architecture_index_path WorkReport))

  (defrecord DesignDeltaSelectedItemPayload
    (item-id String)
    (item-state-root Path.state-root)
    (work_item_bootstrap WorkItemBootstrapSeed)
    (steering_path SteeringDoc)
    (target_design_path TargetDesignDoc)
    (baseline_design_path BaselineDesignDoc)
    (progress_ledger_path ProgressLedger))

  (defrecord DesignDeltaGapPayload
    (work_item_id String)
    (plan_target_path PlanDocTarget)
    (architecture_path PlanDocTarget))

  (defunion DesignDeltaSelectionResult
    (EMPTY)
    (GAP
      (gap DesignDeltaGapPayload))
    (SELECTED
      (selection DesignDeltaSelectedItemPayload))
    (BLOCKED
      (reason String)))

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
    (DONE)
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
      (summary WorkReportTarget))
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
      (terminal-summary WorkReportTarget)))

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
    (blocker-class BlockerClass)
    (execution-report std/resource/WorkReport)
    (progress-report std/resource/WorkReport)
    (checks-report ArtifactChecksPath)
    (implementation-review-report ReviewReportPath))

  (defunion WorkItemResult
    (COMPLETED
      (reason String)
      (summary WorkItemSummaryValue))
    (TERMINAL_BLOCKED
      (reason String)
      (summary WorkItemSummaryValue)
      (blocker-class std/resource/BlockerClass))
    (BLOCKED_RECOVERY
      (reason String)
      (summary WorkItemSummaryValue)
      (blocker-class std/resource/BlockerClass)))

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
      (drain-summary DrainSummaryValue))
    (BLOCKED
      (reason String)
      (drain-summary DrainSummaryValue))
    (EXHAUSTED
      (reason String)
      (drain-summary DrainSummaryValue))))
