(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule drain_stdlib_backlog_drain_parent_terminal_reprojection)
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (BlockerClass SelectedItemResult WorkReport StateExisting))
  (import std/drain :only
    (GapPayload GapResult DrainResult SelectionPayload SelectionResult backlog-drain))
  (export drain)
  (defunion ParentTerminalResult
    (DONE
      (items-processed Int))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
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
  (defproc project-parent-drain-result
    ((result DrainResult))
    -> ParentTerminalResult
    :effects ()
    :lowering inline
    (match result
      ((EMPTY empty)
       (variant ParentTerminalResult DONE
         :items-processed 0))
      ((COMPLETED completed)
       (variant ParentTerminalResult DONE
         :items-processed completed.items-processed))
      ((BLOCKED blocked)
       (variant ParentTerminalResult BLOCKED
         :progress-report-path blocked.progress-report-path
         :blocker-class blocked.blocker-class))))
  (defworkflow drain
    ((ctx DrainCtx)
     (max-iterations Int))
    -> ParentTerminalResult
    (let* ((stdlib-result
             (backlog-drain neurips
               :ctx ctx
               :selector selector-run
               :run-item run-selected-item
               :gap-drafter gap-draft
               :max-iterations 4))
           (parent-result
             (project-parent-drain-result stdlib-result)))
      parent-result)))
