(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath StateNote
    :kind relpath
    :under "state"
    :must-exist false)
  (defrecord RefinedCtx
    (note StateNote))
  (defrecord WorkflowOutput
    (status String))
  (defproc read-note
    :forall (CtxT)
    ((ctx CtxT))
    :where ((CtxT is-record)
            (CtxT has-field note Path.state-root))
    -> WorkflowOutput
    :effects ((uses-command run_checks))
    :lowering inline
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py")
      :returns WorkflowOutput))
  (defworkflow entry
    ((ctx RefinedCtx))
    -> WorkflowOutput
    (read-note ctx)))
