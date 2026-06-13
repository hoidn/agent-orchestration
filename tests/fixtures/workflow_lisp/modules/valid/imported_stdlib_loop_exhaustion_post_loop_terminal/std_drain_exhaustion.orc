(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule std_drain_exhaustion)
  (export BlockerClass
          WorkReport
          StateExisting
          DrainLoopTerminal
          DrainTerminalResult
          finalize-terminal
          emit-run-drain-like)
  (defenum BlockerClass
    missing_resource
    unrecoverable_after_fix_attempt)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath StateExisting
    :kind relpath
    :under "state"
    :must-exist true)
  (defrecord DrainLoopTerminal
    (items-processed Int)
    (run-state StateExisting)
    (progress-report-path WorkReport)
    (blocker-class BlockerClass))
  (defunion DrainTerminalResult
    (EXHAUSTED
      (items_processed Int)
      (progress_report_path WorkReport)
      (blocker_class BlockerClass)
      (run_state StateExisting)))
  (defrecord TerminalOutcomeState
    (variant String)
    (items_processed Int)
    (run_state StateExisting)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass))
  (defrecord TerminalOutcomeRequest
    (variant String)
    (items_processed Int)
    (run_state StateExisting)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass))
  (defrecord TerminalOutcomeResult
    (variant String)
    (items_processed Int)
    (run_state StateExisting)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass))
  (defrecord TerminalOutcomeAudit
    (variant String)
    (items_processed Int)
    (run_state StateExisting)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass))
  (defrecord TerminalSummaryValue
    (variant String)
    (items_processed Int)
    (run_state StateExisting)
    (blocker_class BlockerClass))
  (defresource terminal-outcome
    :state-type std_drain_exhaustion/TerminalOutcomeState
    :backing state-layout)
  (deftransition record-terminal-outcome
    :resource terminal-outcome
    :request-type std_drain_exhaustion/TerminalOutcomeRequest
    :result-type std_drain_exhaustion/TerminalOutcomeResult
    :preconditions ((!= request.variant ""))
    :updates ((set-field variant request.variant)
              (set-field items_processed request.items_processed)
              (set-field run_state request.run_state)
              (set-field progress_report_path request.progress_report_path)
              (set-field blocker_class request.blocker_class))
    :write-set (variant items_processed run_state progress_report_path blocker_class)
    :idempotency-fields (variant items_processed run_state progress_report_path blocker_class)
    :result (record std_drain_exhaustion/TerminalOutcomeResult
      :variant request.variant
      :items_processed request.items_processed
      :run_state request.run_state
      :progress_report_path request.progress_report_path
      :blocker_class request.blocker_class)
    :audit (record std_drain_exhaustion/TerminalOutcomeAudit
      :variant request.variant
      :items_processed request.items_processed
      :run_state request.run_state
      :progress_report_path request.progress_report_path
      :blocker_class request.blocker_class)
    :conflict-policy fail_closed
    :backend runtime_native)
  (defworkflow finalize-terminal
    ((terminal DrainLoopTerminal))
    -> DrainTerminalResult
    (let* ((outcome
             (resource-transition
               :transition record-terminal-outcome
               :resource terminal-outcome
               :request (record std_drain_exhaustion/TerminalOutcomeRequest
                          :variant "EXHAUSTED"
                          :items_processed terminal.items-processed
                          :run_state terminal.run-state
                          :progress_report_path terminal.progress-report-path
                          :blocker_class terminal.blocker-class)))
           (summary-path
             (materialize-view terminal-summary
               :value (record std_drain_exhaustion/TerminalSummaryValue
                        :variant outcome.variant
                        :items_processed outcome.items_processed
                        :run_state outcome.run_state
                        :blocker_class outcome.blocker_class)
               :renderer canonical-json
               :renderer-version 1
               :target terminal.progress-report-path
               :returns WorkReport)))
      (variant DrainTerminalResult EXHAUSTED
        :items_processed terminal.items-processed
        :progress_report_path summary-path
        :blocker_class terminal.blocker-class
        :run_state terminal.run-state)))
  (defmacro emit-run-drain-like (name)
    (defworkflow name
      ()
      -> std_drain_exhaustion/DrainTerminalResult
      (let* ((progress-report-target
               (__generated-relpath-seed__
                 WorkReport
                 "artifacts/work/imported-stdlib-loop-exhaustion-summary.json"
                 "imported_stdlib_loop_exhaustion_summary_seed"))
             (initial-run-state
               (__generated-relpath-seed__
                 StateExisting
                 "state/imported-stdlib-loop-exhaustion-run-state.json"
                 "imported_stdlib_loop_exhaustion_run_state_seed"))
             (terminal
               (loop/recur
                 :max 1
                 :state (loop-state
                          (items-processed Int 0)
                          (run-state StateExisting initial-run-state)
                          (progress-report-path WorkReport progress-report-target))
                 :on-exhausted
                  (record std_drain_exhaustion/DrainLoopTerminal
                   :items-processed state.items-processed
                   :run-state state.run-state
                   :progress-report-path state.progress-report-path
                   :blocker-class BlockerClass.unrecoverable_after_fix_attempt)
                 (fn (state)
                   (if false
                     (done
                       (record std_drain_exhaustion/DrainLoopTerminal
                         :items-processed state.items-processed
                         :run-state state.run-state
                         :progress-report-path state.progress-report-path
                         :blocker-class BlockerClass.missing_resource))
                     (continue
                       (loop-state :like state
                         :items-processed (+ state.items-processed 1)))))))
             (result
               (call std_drain_exhaustion/finalize-terminal
                 :terminal terminal)))
        result)))
)
