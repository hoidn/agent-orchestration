(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule backlog_drain_gap_drafter_non_record_payload_invalid)
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (BlockerClass SelectedItemResult))
  (import std/drain :only (backlog-drain))
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath StateExisting
    :kind relpath
    :under "state"
    :must-exist true)
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
  (defrecord SelectionPayload
    (item-id String)
    (item-state-root Path.state-root))
  (defrecord GapPayload
    (gap-id String))
  (defunion SelectionResult
    (EMPTY
      (run-state StateExisting))
    (GAP
      (gap GapPayload))
    (SELECTED
      (selection SelectionPayload))
    (BLOCKED
      (reason String)))
  (defunion GapResult
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
  (defproc selector-run
    ((ctx DrainCtx))
    -> SelectionResult
    :effects ((uses-command select_next_item))
    :lowering inline
    (command-result select_next_item
      :argv ("python" "scripts/select_next_item.py" ctx.manifest)
      :returns SelectionResult))
  (defproc run-selected-item
    ((item-ctx ItemCtx)
     (selection SelectionPayload))
    -> SelectedItemResult
    :effects ((uses-command execute_selected_item))
    :lowering inline
    (command-result execute_selected_item
      :argv ("python" "scripts/execute_selected_item.py" selection.item-id)
      :returns SelectedItemResult))
  (defproc gap-draft
    ((ctx DrainCtx)
     (gap String))
    -> GapResult
    :effects ((uses-command draft_gap_item))
    :lowering inline
    (command-result draft_gap_item
      :argv ("python" "scripts/draft_gap_item.py" gap)
      :returns GapResult))
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
