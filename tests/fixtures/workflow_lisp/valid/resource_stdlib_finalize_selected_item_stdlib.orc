(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule resource_stdlib_finalize_selected_item_stdlib)
  ; Stdlib-route fixture paired with
  ; tests/fixtures/workflow_lisp/valid/resource_stdlib_finalize_selected_item.orc.
  (import std/context :only (ItemCtx))
  (import std/resource :only (BlockerClass SelectedItemResult WorkReport selected-item-outcome record-selected-item-outcome finalize-selected-item))
  (export run-selected-item)
  (defenum Queue
    active
    in_progress)
  (defenum LedgerEvent
    SELECTED)
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
  (defpath BacklogActivePath
    :kind relpath
    :under "docs/backlog/active"
    :must-exist true)
  (defpath BacklogInProgressPath
    :kind relpath
    :under "docs/backlog/in_progress"
    :must-exist true)
  (defrecord SelectedItem
    (item-id String)
    (item-path BacklogActivePath)
    (is-active Bool))
  (defrecord ResourceTransitionResult
    (resource-id String)
    (from Queue)
    (to Queue)
    (new-path BacklogInProgressPath)
    (transition-id String))
  (defrecord RoadmapSyncResult
    (status String))
  (defunion PlanGateResult
    (APPROVED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defunion ImplementationResult
    (COMPLETED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defworkflow roadmap-sync
    ((item-id String))
    -> RoadmapSyncResult
    (command-result resolve_roadmap_sync
      :argv ("python" "scripts/resolve_roadmap_sync.py" item-id)
      :returns RoadmapSyncResult))
  (defworkflow plan-run
    ((item-id String)
     (roadmap RoadmapSyncResult))
    -> PlanGateResult
    (command-result resolve_plan_gate
      :argv ("python" "scripts/resolve_plan_gate.py" item-id)
      :returns PlanGateResult))
  (defworkflow implementation-run
    ((item-id String))
    -> ImplementationResult
    (command-result execute_implementation
      :argv ("python" "scripts/execute_implementation.py" item-id)
      :returns ImplementationResult))
  (defworkflow run-selected-item
    ((item-ctx ItemCtx)
     (selected SelectedItem))
    -> SelectedItemResult
    (let* ((queue-transition
             (resource-transition backlog-item
               :ctx item-ctx
               :when selected.is-active
               :resource selected.item-id
               :from Queue.active
               :to Queue.in_progress
               :ledger item-ctx.ledger
               :event SELECTED))
           (roadmap
             (call roadmap-sync
               :item-id selected.item-id))
           (plan
             (call plan-run
               :item-id selected.item-id
               :roadmap roadmap))
           (implementation
             (call implementation-run
               :item-id selected.item-id)))
      (finalize-selected-item
        :ctx item-ctx
        :selected selected
        :queue-transition queue-transition
        :roadmap roadmap
        :plan plan
        :implementation implementation))))
