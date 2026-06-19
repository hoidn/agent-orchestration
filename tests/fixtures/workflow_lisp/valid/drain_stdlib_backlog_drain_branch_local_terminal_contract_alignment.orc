(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule drain_stdlib_backlog_drain_branch_local_terminal_contract_alignment)
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (BlockerClass SelectedItemResult WorkReport StateExisting))
  (import std/drain :only
    (GapPayload GapResult DrainResult SelectionPayload SelectionResult backlog-drain))
  (export drain)
  (defunion ParentTerminalResult
    (DONE
      (items-processed Int)
      (run-state StateExisting))
    (BLOCKED
      (progress-report-path WorkReport)
      (reason BlockerClass)))
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
    -> GapResult
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
         :items-processed 0
         :run-state empty.run-state))
      ((COMPLETED completed)
       (variant ParentTerminalResult DONE
         :items-processed completed.items-processed
         :run-state completed.run-state))
      ((BLOCKED blocked)
       (variant ParentTerminalResult BLOCKED
         :progress-report-path blocked.progress-report-path
         :reason blocked.blocker-class))))
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
