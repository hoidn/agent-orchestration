(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule backlog_drain_gap_drafter_non_record_payload_invalid)
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (BlockerClass SelectedItemResult))
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
     (gap String))
    -> GapResult
    (command-result draft_gap_item
      :argv ("python" "scripts/draft_gap_item.py" gap)
      :returns GapResult))
  (defworkflow drain
    ((ctx DrainCtx)
     (max-iterations Int))
    -> DrainResult
    (backlog-drain-callable-boundary neurips
      :ctx ctx
      :selector selector-run
      :run-item run-selected-item
      :gap-drafter gap-draft
      :max-iterations 4)))
