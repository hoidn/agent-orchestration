(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule drain_stdlib_backlog_drain_hidden_compatibility_bridge)
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (BlockerClass SelectedItemResult StateExisting))
  (import std/drain :only
    (GapPayload GapResult DrainResult SelectionPayload SelectionResult backlog-drain))
  (export drain)

  (defrecord SelectedCompat
    (item-id String)
    (final-plan-gate-state StateExisting))

  (defworkflow selector-run
    ((ctx DrainCtx))
    -> SelectionResult
    (command-result select_next_item
      :argv ("python" "scripts/select_next_item.py" ctx.manifest)
      :returns SelectionResult))

  (defworkflow project-selected-compat
    ((item-id String)
     (run_state_path StateExisting))
    -> SelectedCompat
    (record SelectedCompat
      :item-id item-id
      :final-plan-gate-state run_state_path))

  (defworkflow run-selected-item
    ((item-ctx ItemCtx)
     (selection SelectionPayload))
    -> SelectedItemResult
    (let* ((selected
             (call project-selected-compat
               :item-id selection.item-id)))
      (command-result execute_selected_item
        :argv ("python" "scripts/execute_selected_item.py" selected.final-plan-gate-state)
        :returns SelectedItemResult)))

  (defworkflow gap-draft
    ((ctx DrainCtx)
     (gap GapPayload))
    -> GapResult
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
