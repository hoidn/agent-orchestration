(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lexical_checkpoint_restore_regions)
  (export orchestrate)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath MaterializedSummaryPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defunion BranchDecision
    (READY
      (label String)
      (report WorkReport))
    (RETRY
      (label String)
      (report WorkReport)))
  (defrecord LoopState
    (count Int)
    (label String))
  (defrecord LoopResult
    (count Int)
    (label String))
  (defrecord SummaryValue
    (status String)
    (count Int)
    (report WorkReport))
  (defrecord Output
    (summary_path MaterializedSummaryPath)
    (loop_count Int)
    (selected_label String))
  (defworkflow choose-branch
    ((report_path WorkReport))
    -> BranchDecision
    (variant BranchDecision READY
      :label "ready"
      :report report_path))
  (defworkflow orchestrate
    ((report_path WorkReport)
     (summary_target MaterializedSummaryPath))
    -> Output
    (let* ((decision
             (call choose-branch
               :report_path report_path))
           (selected_label
             (match decision
               ((READY ready)
                ready.label)
               ((RETRY retry)
                retry.label)))
           (selected_report
             (match decision
               ((READY ready)
                ready.report)
               ((RETRY retry)
                retry.report)))
           (loop_result
             (loop/recur
               :max 1
               :state (loop-state
                        (count Int 0)
                        (label String "seed"))
               :on-exhausted (record LoopResult
                               :count state.count
                               :label state.label)
                (fn (state)
                  (if false
                    (done
                      (record LoopResult
                        :count state.count
                        :label state.label))
                    (continue
                      (loop-state :like state
                        :count (+ state.count 1)
                        :label "tick"))))))
           (summary_status
             (if (= selected_label "ready")
               "ready-summary"
               "retry-summary"))
           (summary_value
             (record SummaryValue
               :status summary_status
               :count loop_result.count
               :report selected_report))
           (summary_path
             (materialize-view runtime-summary
               :value summary_value
               :renderer canonical-json
               :renderer-version 1
               :target summary_target
               :returns MaterializedSummaryPath)))
      (record Output
        :summary_path summary_path
        :loop_count loop_result.count
        :selected_label selected_label))))
