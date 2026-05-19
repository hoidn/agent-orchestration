(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReportTarget
    :kind relpath
    :under "artifacts/work"
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
  (defrecord ReportTargetOnly
    (report_path WorkReportTarget))
  (defworkflow invalid-phase-target
    ((phase-ctx PhaseCtx))
    -> ReportTargetOnly
    (with-phase phase-ctx implementation
      (record ReportTargetOnly
        :report_path (phase-target archive-report)))))
