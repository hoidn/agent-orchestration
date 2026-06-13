(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule phase_scope_stdlib_targets)
  ; Stdlib-route fixture paired with the intrinsic `with-phase` vector in
  ; tests/test_workflow_lisp_phase_stdlib.py.
  (import std/context :only (PhaseCtx))
  (import std/phase :only (PhaseScopeTargets WorkReportTarget ChecksReport ReviewReportTarget phase-scope))
  (export PhaseScopeSurface phase-scope-demo)
  (defrecord PhaseScopeSurface
    (execution-report-target WorkReportTarget)
    (progress-report-target WorkReportTarget)
    (checks-report-target ChecksReport)
    (review-report-target ReviewReportTarget)
    (last-review-report-target ReviewReportTarget))
  (defworkflow phase-scope-demo
    ((phase-ctx PhaseCtx))
    -> PhaseScopeSurface
    (let* ((scope
             (phase-scope implementation-scope
               :ctx phase-ctx
               :phase implementation)))
      (record PhaseScopeSurface
        :execution-report-target scope.execution-report-target
        :progress-report-target scope.progress-report-target
        :checks-report-target scope.checks-report-target
        :review-report-target scope.review-report-target
        :last-review-report-target scope.last-review-report-target))))
