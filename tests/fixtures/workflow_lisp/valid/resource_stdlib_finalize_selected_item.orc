(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defenum Queue
    active
    in_progress)
  (defenum LedgerEvent
    SELECTED)
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
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
  (defpath StateExisting
    :kind relpath
    :under "state"
    :must-exist true)
  (defpath BacklogActivePath
    :kind relpath
    :under "docs/backlog/active"
    :must-exist true)
  (defpath BacklogInProgressPath
    :kind relpath
    :under "docs/backlog/in_progress"
    :must-exist true)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord ItemCtx
    (run RunCtx)
    (item-id String)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root)
    (ledger StateFile))
  (defrecord SelectedItem
    (item-id String)
    (item-path BacklogActivePath)
    (is-active Bool)
    (final-plan-gate-state StateExisting))
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
  (defunion SelectedItemResult
    (CONTINUE
      (summary-path WorkReport)
      (run-state StateExisting))
    (BLOCKED
      (summary-path WorkReport)
      (blocker-class BlockerClass)
      (run-state StateExisting)))
  (defworkflow roadmap-sync
    ((item-ctx ItemCtx)
     (selected SelectedItem))
    -> RoadmapSyncResult
    (record RoadmapSyncResult
      :status selected.item-id))
  (defworkflow plan-run
    ((item-ctx ItemCtx)
     (selected SelectedItem)
     (roadmap RoadmapSyncResult))
    -> PlanGateResult
    (command-result resolve_plan_gate
      :argv ("python" "scripts/resolve_plan_gate.py" selected.item-id)
      :returns PlanGateResult))
  (defworkflow implementation-run
    ((item-ctx ItemCtx)
     (selected SelectedItem))
    -> ImplementationResult
    (command-result execute_implementation
      :argv ("python" "scripts/execute_implementation.py" selected.item-id)
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
               :item-ctx item-ctx
               :selected selected))
           (plan
             (call plan-run
               :item-ctx item-ctx
               :selected selected
               :roadmap roadmap))
           (implementation
             (call implementation-run
               :item-ctx item-ctx
               :selected selected)))
      (finalize-selected-item
        :ctx item-ctx
        :selected selected
        :queue-transition queue-transition
        :roadmap roadmap
        :plan plan
        :implementation implementation))))
