(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/runtime_view_fixture)
  (import lisp_frontend_design_delta/transitions :only
    (DrainStatusResult emit-drain-status-transition-audit))
  (import lisp_frontend_design_delta/types :only
    (DrainIterationStatus WorkReportTarget))
  (export run-summary-view)

  (defrecord DrainSummaryValue
    (drain_status DrainIterationStatus)
    (drain_status_reason String)
    (summary_target WorkReportTarget)
    (state_version String))

  (defrecord SummaryViewResult
    (summary_path WorkReportTarget)
    (pointer_path WorkReportTarget))

  (defworkflow run-summary-view
    ((drain_status DrainIterationStatus)
     (drain_status_reason String)
     (summary_path WorkReportTarget)
     (pointer_path WorkReportTarget))
    -> SummaryViewResult
    (let* ((transition_result
             (call emit-drain-status-transition-audit
               :summary_path summary_path))
           (rendered_summary_path
             (materialize-view drain-summary-view
               :value (record DrainSummaryValue
                        :drain_status drain_status
                        :drain_status_reason drain_status_reason
                        :summary_target summary_path
                        :state_version "lisp_frontend_autonomous_drain_run_state/v1")
               :renderer canonical-json
               :renderer-version 1
               :target summary_path
               :returns WorkReportTarget))
           (rendered_pointer_path
             (materialize-view drain-summary-pointer-view
               :value rendered_summary_path
               :renderer posix-path-line
               :renderer-version 1
               :target pointer_path
               :returns WorkReportTarget)))
      (record SummaryViewResult
        :summary_path rendered_summary_path
        :pointer_path rendered_pointer_path))))
