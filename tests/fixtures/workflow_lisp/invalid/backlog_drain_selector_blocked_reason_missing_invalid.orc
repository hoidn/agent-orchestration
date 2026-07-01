(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
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
  (defrecord RunCtx
    (run-id RunId)
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
  (defrecord SelectionPayload
    (item-id String)
    (item-state-root StateFile))
  (defrecord GapPayload
    (gap-id String))
  (defunion SelectionResult
    (EMPTY
      (run-state StateExisting))
    (GAP
      (gap GapPayload))
    (SELECTED
      (selection SelectionPayload))
    (BLOCKED))
  (defunion SelectedItemResult
    (CONTINUE
      (summary-path WorkReport)
      (run-state StateExisting))
    (BLOCKED
      (summary-path WorkReport)
      (blocker-class BlockerClass)
      (run-state StateExisting)))
  (defunion GapDraftResult
    (CONTINUE
      (run-state StateExisting))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defunion DrainResult
    (EMPTY
      (run-state StateExisting))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass))
    (COMPLETED
      (items-processed Int)
      (run-state StateExisting)))
  (defworkflow selector-run
    ((ctx DrainCtx))
    -> SelectionResult
    (command-result select_next_item
      :argv ("python" "scripts/select_next_item.py" ctx.manifest)
      :returns SelectionResult))
  (defworkflow run-selected-item
    ((item-ctx ItemCtx)
     (selection SelectionPayload))
    -> SelectedItemResult
    (command-result execute_selected_item
      :argv ("python" "scripts/execute_selected_item.py" selection.item-id)
      :returns SelectedItemResult))
  (defworkflow gap-draft
    ((ctx DrainCtx)
     (gap GapPayload))
    -> GapDraftResult
    (command-result draft_gap_item
      :argv ("python" "scripts/draft_gap_item.py" gap.gap-id)
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
      :max-iterations 4)))
