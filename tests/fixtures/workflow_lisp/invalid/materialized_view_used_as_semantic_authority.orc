(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule materialized_view_used_as_semantic_authority)
  (export invalid-materialized-view-authority)
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
    (report_path WorkReport))
  (defrecord ResumeStateValue
    (status String))
  (defrecord ChecksResult
    (checks_report WorkReport))
  (defworkflow invalid-materialized-view-authority
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> ChecksResult
    (with-phase phase-ctx checks
      (let* ((resume_state
               (materialize-view generated-state
                 :value (record ResumeStateValue
                          :status "READY")
                 :renderer canonical-json
                 :renderer-version 1
                 :returns PhaseStateBundle)))
        (resume-or-start checks
          :ctx phase-ctx
          :resume-from resume_state
          :start
            (command-result run_checks
              :argv ("python" "scripts/run_checks.py" inputs.report_path)
              :returns ChecksResult)
          :returns ChecksResult)))))
