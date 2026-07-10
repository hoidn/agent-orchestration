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
  (defrecord GapPayload
    (gap-id String))
  (defunion SelectionResult
    (EMPTY)
    (GAP
      (gap GapPayload))
    (SELECTED
      (selection SelectionPayload))
    (BLOCKED
      (reason String)))
  (defrecord ProbeOutcome
    (status String))
  (defproc probe-selector
    ((ctx DrainCtx))
    -> SelectionResult
    :effects ((uses-command probe_select))
    :lowering inline
    (command-result probe_select
      :argv ("python" "scripts/select_next_item.py" ctx.manifest)
      :returns SelectionResult))
  (defproc probe-generic
    :forall (CtxT SelectionT)
    ((ctx CtxT)
     (selector ProcRef[(CtxT) -> SelectionT]))
    :where ((CtxT is-record)
            (SelectionT is-union)
            (SelectionT has-union-variant EMPTY)
            (SelectionT has-union-variant SELECTED)
            (SelectionT has-union-variant GAP)
            (SelectionT has-union-variant BLOCKED (reason String)))
    -> String
    :effects ()
    :lowering inline
    (match (selector ctx)
      ((EMPTY e) "empty")
      ((SELECTED s) "selected")
      ((GAP g) "gap")
      ((BLOCKED b) b.reason)))
  (defworkflow probe-drain
    ((ctx DrainCtx))
    -> ProbeOutcome
    (let* ((status (probe-generic ctx (proc-ref probe-selector))))
      (record ProbeOutcome
        :status status))))
