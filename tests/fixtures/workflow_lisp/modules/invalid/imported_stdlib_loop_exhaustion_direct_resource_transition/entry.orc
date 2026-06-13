(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry)
  (import std/resource :only (BlockerClass WorkReport StateExisting))
  (export run)
  (defrecord TerminalRequest
    (variant String))
  (defrecord TerminalState
    (variant String))
  (defrecord TerminalResultState
    (variant String))
  (defrecord TerminalAudit
    (variant String))
  (defunion DrainTerminalResult
    (EXHAUSTED
      (report WorkReport)
      (run_state StateExisting)
      (blocker_class BlockerClass)))
  (defresource terminal-outcome
    :state-type TerminalState
    :backing state-layout)
  (deftransition record-terminal-outcome
    :resource terminal-outcome
    :request-type TerminalRequest
    :result-type TerminalResultState
    :preconditions ((!= request.variant ""))
    :updates ((set-field variant request.variant))
    :write-set (variant)
    :idempotency-fields (variant)
    :result (record TerminalResultState
      :variant request.variant)
    :audit (record TerminalAudit
      :variant request.variant)
    :conflict-policy fail_closed
    :backend runtime_native)
  (defworkflow run
    ()
    -> DrainTerminalResult
    (let* ((progress-report-target
             (__generated-relpath-seed__
               WorkReport
               "artifacts/work/imported-stdlib-loop-exhaustion-direct-resource-transition.json"
               "imported_stdlib_loop_exhaustion_direct_resource_transition_summary_seed"))
           (initial-run-state
             (__generated-relpath-seed__
               StateExisting
               "state/imported-stdlib-loop-exhaustion-direct-resource-transition.json"
               "imported_stdlib_loop_exhaustion_direct_resource_transition_state_seed")))
      (loop/recur
        :max 1
        :state (loop-state
                 (items-processed Int 0)
                 (run-state StateExisting initial-run-state)
                 (progress-report-path WorkReport progress-report-target))
        :on-exhausted
        (let* ((outcome
                 (resource-transition
                   :transition record-terminal-outcome
                   :resource terminal-outcome
                   :request (record TerminalRequest
                              :variant "EXHAUSTED"))))
          (variant DrainTerminalResult EXHAUSTED
            :report state.progress-report-path
            :run_state state.run-state
            :blocker_class BlockerClass.unrecoverable_after_fix_attempt))
        (fn (state)
          (if false
            (done
              (variant DrainTerminalResult EXHAUSTED
                :report state.progress-report-path
                :run_state state.run-state
                :blocker_class BlockerClass.missing_resource))
            (continue
              (loop-state :like state
                :items-processed (+ state.items-processed 1)))))))))
