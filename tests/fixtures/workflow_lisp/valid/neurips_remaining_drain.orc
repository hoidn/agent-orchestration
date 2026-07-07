(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defenum Queue
    active
    in_progress)
  (defenum LedgerEvent
    SELECTED)
  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
  (defpath StateExisting
    :kind relpath
    :under "state"
    :must-exist true)
  (defpath BacklogActivePath
    :kind relpath
    :under "docs/backlog/active"
    :must-exist true)
  (defpath BacklogInProgressPath
    :kind relpath
    :under "docs/backlog/in_progress"
    :must-exist true)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord DrainCtx
    (run RunCtx)
    (state-root Path.state-root)
    (manifest StateExisting)
    (ledger StateFile))
  (defrecord ItemCtx
    (run RunCtx)
    (item-id String)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root)
    (ledger StateFile))
  (defrecord SelectedItem
    (item-id String)
    (item-path BacklogActivePath)
    (is-active Bool)
    (final-plan-gate-state StateExisting))
  (defrecord SelectionPayload
    (item-id String)
    (item-state-root StateFile)
    (item-path BacklogActivePath)
    (is-active Bool)
    (final-plan-gate-state StateExisting)
    (roadmap-phase-ctx PhaseCtx)
    (plan-phase-ctx PhaseCtx)
    (implementation-phase-ctx PhaseCtx))
  (defrecord GapPayload
    (gap-id String))
  (defrecord SelectorProviderBindings
    (provider Provider)
    (prompt Prompt))
  (defrecord GapProviderBindings
    (provider Provider)
    (prompt Prompt))
  (defrecord DrainProviders
    (selector SelectorProviderBindings)
    (gap-drafter GapProviderBindings))
  (defunion SelectionResult
    (EMPTY)
    (GAP
      (gap GapPayload))
    (SELECTED
      (selection SelectionPayload))
    (BLOCKED
      (reason String)))
  (defrecord ResourceTransitionResult
    (resource-id String)
    (from Queue)
    (to Queue)
    (new-path BacklogInProgressPath)
    (transition-id String))
  (defrecord RoadmapSyncResult
    (status String))
  (defunion PlanGateResult
    (APPROVED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defunion ImplementationResult
    (COMPLETED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defunion SelectedItemResult
    (CONTINUE
      (summary-path WorkReport))
    (BLOCKED
      (summary-path WorkReport)
      (blocker-class BlockerClass)))
  (defunion GapDraftResult
    (CONTINUE)
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defunion DrainResult
    (EMPTY)
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass))
    (COMPLETED
      (items-processed Int)))
  (defworkflow selector-run
    ((ctx DrainCtx))
    -> SelectionResult
    (provider-result providers.selector
      :prompt prompts.selector
      :inputs (ctx.manifest)
      :returns SelectionResult))
  (defworkflow roadmap-sync
    ((phase-ctx PhaseCtx)
     (item-ctx ItemCtx)
     (selection SelectionPayload))
    -> RoadmapSyncResult
    (command-result resolve_roadmap
      :argv ("python" "scripts/resolve_roadmap.py" selection.item-id)
      :returns RoadmapSyncResult))
  (defworkflow plan-run
    ((phase-ctx PhaseCtx)
     (item-ctx ItemCtx)
     (selection SelectionPayload)
     (roadmap RoadmapSyncResult))
    -> PlanGateResult
    (command-result resolve_plan_gate
      :argv ("python" "scripts/resolve_plan_gate.py" selection.item-id)
      :returns PlanGateResult))
  (defworkflow implementation-run
    ((phase-ctx PhaseCtx)
     (item-ctx ItemCtx)
     (selection SelectionPayload))
    -> ImplementationResult
    (command-result execute_implementation
      :argv ("python" "scripts/execute_implementation.py" selection.item-id)
      :returns ImplementationResult))
  (defworkflow run-selected-item
    ((item-ctx ItemCtx)
     (selection SelectionPayload))
    -> SelectedItemResult
    (let* ((queue-transition
             (resource-transition backlog-item
               :ctx item-ctx
               :when selection.is-active
               :resource selection.item-id
               :from Queue.active
               :to Queue.in_progress
               :ledger item-ctx.ledger
               :event SELECTED))
           (roadmap
             (call roadmap-sync
               :phase-ctx selection.roadmap-phase-ctx
               :item-ctx item-ctx
               :selection selection))
           (plan
             (resume-or-start plan-gate
               :ctx selection.plan-phase-ctx
               :resume-from selection.final-plan-gate-state
               :valid-when (APPROVED)
               :start
                 (call plan-run
                   :phase-ctx selection.plan-phase-ctx
                   :item-ctx item-ctx
                   :selection selection
                   :roadmap roadmap)
               :returns PlanGateResult))
           (implementation
             (call implementation-run
               :phase-ctx selection.implementation-phase-ctx
               :item-ctx item-ctx
               :selection selection)))
      (finalize-selected-item
        :ctx item-ctx
        :selected selection
        :queue-transition queue-transition
        :roadmap roadmap
        :plan plan
        :implementation implementation)))
  (defworkflow gap-draft
    ((ctx DrainCtx)
     (gap GapPayload))
    -> GapDraftResult
    (provider-result providers.gap-drafter
      :prompt prompts.gap-drafter
      :inputs (gap.gap-id)
      :returns GapDraftResult))
  (defworkflow drain
    ((ctx DrainCtx)
     (max-iterations Int))
    -> DrainResult
    (backlog-drain neurips
      :ctx ctx
      :selector selector-run
      :run-item run-selected-item
      :gap-drafter gap-draft
      :providers (record DrainProviders
                   :selector (record SelectorProviderBindings
                               :provider providers.selector
                               :prompt prompts.selector)
                   :gap-drafter (record GapProviderBindings
                                  :provider providers.gap-drafter
                                  :prompt prompts.gap-drafter))
      :max-iterations 4)))
