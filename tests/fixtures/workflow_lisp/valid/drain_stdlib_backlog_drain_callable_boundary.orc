(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule drain_stdlib_backlog_drain_callable_boundary)
  ; Shared-route fixture that proves imported std/drain backlog-drain survives
  ; as a callable boundary and can be bound before any later reprojection work.
  ; It calls the helper head directly so the proof does not inherit ambient
  ; std/drain macro rewrites from the checkout.
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (BlockerClass SelectedItemResult))
  (import std/drain :only
    (GapPayload GapResult DrainResult SelectionPayload SelectionResult))
  (export drain)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
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
  (defproc identity-drain-result
    ((result DrainResult))
    -> DrainResult
    :effects ()
    :lowering inline
    result)
  (defworkflow drain
    ((ctx DrainCtx)
     (max-iterations Int))
    -> DrainResult
    (let* ((stdlib-result
             (backlog-drain-callable-boundary neurips
               :ctx ctx
               :selector selector-run
               :run-item run-selected-item
               :gap-drafter gap-draft
               :max-iterations 4))
           (preserved-result
             (identity-drain-result stdlib-result)))
      preserved-result)))
