(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
  (defpath StateExisting
    :kind relpath
    :under "state"
    :must-exist true)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord DrainCtx
    (run RunCtx)
    (state-root Path.state-root)
    (manifest StateExisting)
    (ledger StateFile))
  (defrecord SelectionPayload
    (item-id String)
    (item-state-root StateFile))
  (defunion SelectionResult
    (EMPTY
      (run-state StateExisting))
    (SELECTED
      (selection SelectionPayload)))
  (defrecord SelectedSummary
    (item-id String))
  (defworkflow selector-run
    ((ctx DrainCtx))
    -> SelectionResult
    (command-result select_next_item
      :argv ("python" "scripts/select_next_item.py" ctx.manifest)
      :returns SelectionResult))
  (defworkflow summarize-selection
    ((ctx DrainCtx))
    -> SelectedSummary
    (let* ((selection
             (call selector-run
               :ctx ctx)))
      (record SelectedSummary
        :item-id selection.selection.item-id))))
