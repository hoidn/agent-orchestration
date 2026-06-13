(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule resume_or_start_record_valid_when_invalid)
  (import std/phase :only (with-phase))
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
  (defworkflow invalid-record-valid-when
    ((phase-ctx PhaseCtx)
     (inputs ResumeInputs))
    -> ChecksResult
    (with-phase phase-ctx checks
      (resume-or-start checks
        :ctx phase-ctx
        :resume-from inputs.resume_from
        :valid-when (REUSE)
        :start
          (command-result run_checks
            :argv ("python" "scripts/run_checks.py" inputs.report_path)
            :returns ChecksResult)
        :returns ChecksResult))))
