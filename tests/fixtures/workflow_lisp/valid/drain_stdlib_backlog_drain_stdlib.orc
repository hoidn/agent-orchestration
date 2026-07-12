(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule drain_stdlib_backlog_drain_stdlib)
  ; Stdlib-route fixture paired with
  ; tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc.
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (BlockerClass SelectedItemResult))
  (import std/drain :only
    (GapPayload GapResult DrainResult SelectionPayload SelectionResult backlog-drain))
  (export drain)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
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
     (gap GapPayload))
    -> GapResult
    :effects ((uses-command draft_gap_item))
    :lowering inline
    (command-result draft_gap_item
      :argv ("python" "scripts/draft_gap_item.py" gap.gap-id)
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
