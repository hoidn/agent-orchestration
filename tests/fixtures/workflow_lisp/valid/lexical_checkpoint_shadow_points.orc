(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lexical_checkpoint_shadow_points)
  (export orchestrate)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath MaterializedSummaryPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (report WorkReport))
  (defrecord LoopState
    (count Int)
    (label String))
  (defrecord LoopResult
    (count Int)
    (label String))
  (defrecord HelperResult
    (status String)
    (report WorkReport)
    (count Int))
  (defrecord SummaryValue
    (status String)
    (report WorkReport)
    (count Int))
  (defrecord OrchestrateResult
    (checked_report WorkReport)
    (summary_path MaterializedSummaryPath)
    (loop_count Int))
  (defworkflow pure-helper
    ((checks ChecksResult)
     (count Int))
    -> HelperResult
    (record HelperResult
      :status "ready"
      :report checks.report
      :count count))
  (defworkflow orchestrate
    ((report_path WorkReport)
     (summary_target MaterializedSummaryPath)
     (run_checks_now Bool))
    -> OrchestrateResult
    (let* ((checks
             (if run_checks_now
               (command-result run_checks
                 :argv ("python" "scripts/run_checks.py" report_path)
                 :returns ChecksResult)
               (record ChecksResult
                 :report report_path)))
           (helper
             (call pure-helper
               :checks checks
               :count 0))
           (summary_path
             (materialize-view runtime-summary
               :value (record SummaryValue
                        :status helper.status
                        :report helper.report
                        :count helper.count)
               :renderer canonical-json
               :renderer-version 1
               :target summary_target
               :returns MaterializedSummaryPath))
           (loop_result
             (loop/recur
                :max 4
                :state (record LoopState
                        :count 0
                        :label "seed")
                (fn (state)
                  (if (< state.count 1)
                    (continue
                     (record LoopState
                       :count (+ state.count 1)
                       :label "tick"))
                   (done
                     (record LoopResult
                       :count state.count
                       :label state.label)))))))
      (record OrchestrateResult
        :checked_report checks.report
        :summary_path summary_path
        :loop_count loop_result.count))))
