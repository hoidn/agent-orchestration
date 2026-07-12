(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule backlog_drain_hidden_compatibility_bridge_public_boundary_invalid)
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (BlockerClass SelectedItemResult StateExisting WorkReport))
  (import std/drain :only
    (GapPayload GapResult DrainResult SelectionPayload SelectionResult backlog-drain))
  (export drain)

  (defrecord SelectedCompat
    (item-id String)
    (final-plan-gate-state StateExisting))

  (defproc selector-run
    ((ctx DrainCtx))
    -> SelectionResult
    :effects ((uses-command select_next_item))
    :lowering inline
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
     (max-iterations Int)
     (run_state_path StateExisting))
    -> DrainResult
    (let* ((compat-probe
             (call project-selected-compat
               :item-id "compat-probe"))
           (stdlib-result
             (backlog-drain neurips
               :ctx ctx
               :selector selector-run
               :run-item run-selected-item
               :gap-drafter gap-draft
               :max-iterations 4)))
      stdlib-result)))
