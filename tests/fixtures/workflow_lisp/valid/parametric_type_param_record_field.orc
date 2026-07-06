(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defrecord Item
    (item-id String))
  (defrecord Ctx
    (payload Item))
  (defrecord WorkflowOutput
    (status String))
  (defproc consume-item
    ((payload Item))
    -> WorkflowOutput
    :effects ()
    :lowering inline
    (record WorkflowOutput
      :status payload.item-id))
  (defproc read-payload
    :forall (CtxT PayloadT)
    ((ctx CtxT)
     (consume ProcRef[(PayloadT) -> WorkflowOutput]))
    :where ((CtxT is-record)
            (CtxT has-field payload PayloadT))
    -> WorkflowOutput
    :effects ((uses-command run_checks))
    :lowering inline
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py")
      :returns WorkflowOutput))
  (defworkflow entry
    ((ctx Ctx))
    -> WorkflowOutput
    (read-payload ctx (proc-ref consume-item))))
