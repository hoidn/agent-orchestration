(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule phase_ctx_contract_invalid)
  (import std/phase :only (with-phase))
  (defenum BlockerClass
    missing_resource)
  (defenum ImplementationStateTag
    COMPLETED
    BLOCKED)
  (defpath WorkReportTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
  (defrecord RunCtx
    (run-id String)
    (state-root WorkReportTarget)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name String)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord ReportTargetOnly
    (report_path WorkReportTarget))
  (defworkflow invalid-phase-ctx
    ((phase-ctx PhaseCtx))
    -> ReportTargetOnly
    (with-phase phase-ctx implementation
      (record ReportTargetOnly
        :report_path (phase-target execution-report)))))
