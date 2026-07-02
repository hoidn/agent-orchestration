(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/runtime_transition_fixture)
  (import lisp_frontend_design_delta/transitions :only
    (DrainStatusResult emit-drain-status-transition-audit))
  (import lisp_frontend_design_delta/types :only
    (WorkReportTarget))
  (export run-runtime-transition-fixture)

  (defworkflow run-runtime-transition-fixture
    ((summary_path WorkReportTarget))
    -> DrainStatusResult
    (call emit-drain-status-transition-audit
      :summary_path summary_path)))
