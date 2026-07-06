(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath ArtifactNote
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
  (defrecord WrongRootCtx
    (note ArtifactNote))
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
    ((ctx WrongRootCtx))
    -> WorkflowOutput
    (read-note ctx)))
