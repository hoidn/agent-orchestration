(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/types)
  (import std/phase :only (BlockerClass ReviewDecision ReviewFindings))
  (export
    ArchitectureValidationResult
    ArtifactChecksPath
    ArtifactReviewPath
    ArtifactWorkPath
    BaselineDesignDoc
    BlockedRecoveryDecision
    BlockedRecoveryReason
    BlockedRecoveryOutcome
    CheckCommandsPath
    DesignRevisionDecision
    DesignRevisionReviewDecision
    DesignRevisionResult
    DesignGapId
    DrainIterationStatus
    DrainResult
    DrainTerminalStatus
    ImplementationAttempt
    ImplementationPhaseResult
    PlanDoc
    PlanPhaseResult
    PreSelectionRoute
    RecoveredGapAttempt
    RecoveryDrainStatus
    ProgressLedger
    RecoveryStatus
    RunStatePath
    SelectionBundlePath
    SelectionResult
    SelectionStatus
    StateDir
    StateFile
    StateFileExisting
    SteeringDoc
    TargetDesignDoc
    WorkItemSource
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

  (defenum WorkItemTerminalRoute
    COMPLETE
    PLAN_REVIEW_EXHAUSTED
    IMPLEMENTATION_BLOCKED
    IMPLEMENTATION_REVIEW_EXHAUSTED)

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

  (defpath StateDir
    :kind relpath
    :under "state"
    :must-exist false)

  (defpath ArtifactWorkPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defpath ArtifactReviewPath
    :kind relpath
    :under "artifacts/review"
    :must-exist true)

  (defpath ArtifactChecksPath
    :kind relpath
    :under "artifacts/checks"
    :must-exist true)

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

  (defpath CheckCommandsPath
    :kind relpath
    :under "state"
    :must-exist true)

  (defpath SelectionBundlePath
    :kind relpath
    :under "state"
    :must-exist true)

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

  (defrecord ImplementationPhaseResult
    (implementation-state String)
    (implementation-review-decision String)
    (execution-report ArtifactWorkPath)
    (progress-report ArtifactWorkPath)
    (checks-report ArtifactChecksPath)
    (implementation-review-report ArtifactReviewPath))

  (defunion DrainResult
    (DONE
      (run-state RunStatePath)
      (drain-summary ArtifactWorkPath))
    (BLOCKED
      (reason String)
      (run-state RunStatePath)
      (drain-summary ArtifactWorkPath))
    (EXHAUSTED
      (run-state RunStatePath)
      (drain-summary ArtifactWorkPath))))
