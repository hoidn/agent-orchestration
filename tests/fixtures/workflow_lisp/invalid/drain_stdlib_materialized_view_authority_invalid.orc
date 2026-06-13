(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule drain_stdlib_materialized_view_authority_invalid)
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (SelectedItemResult))
  (import std/drain :only (SelectionResult GapResult DrainResult backlog-drain))
  (export drain)
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
  (defpath StateExisting
    :kind relpath
    :under "state"
    :must-exist true)
  (defrecord SelectionPayload
    (item-id String)
    (item-state-root StateExisting))
  (defrecord GapPayload
    (gap-id String))
  (defworkflow selector-run
    ((ctx DrainCtx))
    -> SelectionResult
    (let* ((summary-state
             (materialize-view selector-summary
               :value (record GapPayload
                        :gap-id "gap-1")
               :renderer canonical-json
               :renderer-version 1
               :returns StateExisting)))
      (variant SelectionResult EMPTY
        :run-state summary-state)))
  (defworkflow run-selected-item
    ((item-ctx ItemCtx)
     (selection SelectionPayload))
    -> SelectedItemResult
    (variant SelectedItemResult CONTINUE
      :summary-path item-ctx.artifact-root
      :run-state selection.item-state-root))
  (defworkflow gap-draft
    ((ctx DrainCtx)
     (gap GapPayload))
    -> GapResult
    (variant GapResult BLOCKED
      :progress-report-path ctx.manifest
      :blocker-class BlockerClass.missing_resource))
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
