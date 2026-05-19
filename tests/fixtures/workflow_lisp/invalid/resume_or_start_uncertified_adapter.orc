(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath PhaseStateBundle
    :kind relpath
    :under "state"
    :must-exist false)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord ResumeInputs
    (resume_from PhaseStateBundle)
    (report_path WorkReport))
  (defrecord ChecksResult
    (checks_report WorkReport))
  (defworkflow invalid-uncertified-loader
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> ChecksResult
    (with-phase phase-ctx checks
      (resume-or-start checks
        :ctx phase-ctx
        :resume-from inputs.resume_from
        :start
          (command-result load_canonical_phase_result__ChecksResult
            :argv ("python"
                   "-m"
                   "orchestrator.workflow_lisp.adapters.load_canonical_phase_result"
                   inputs.resume_from)
            :returns ChecksResult)
        :returns ChecksResult))))
