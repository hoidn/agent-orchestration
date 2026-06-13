(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry)
  (import std/resource :only (BlockerClass WorkReport StateExisting))
  (export run)
  (defrecord SummaryValue
    (status String))
  (defunion DrainTerminalResult
    (EXHAUSTED
      (report WorkReport)
      (run_state StateExisting)
      (blocker_class BlockerClass)))
  (defworkflow run
    ()
    -> DrainTerminalResult
    (let* ((progress-report-target
             (__generated-relpath-seed__
               WorkReport
               "artifacts/work/imported-stdlib-loop-exhaustion-direct-materialize-view.json"
               "imported_stdlib_loop_exhaustion_direct_materialize_view_summary_seed"))
           (initial-run-state
             (__generated-relpath-seed__
               StateExisting
               "state/imported-stdlib-loop-exhaustion-direct-materialize-view.json"
               "imported_stdlib_loop_exhaustion_direct_materialize_view_state_seed")))
      (loop/recur
        :max 1
        :state (loop-state
                 (items-processed Int 0)
                 (run-state StateExisting initial-run-state)
                 (progress-report-path WorkReport progress-report-target))
        :on-exhausted
        (let* ((rendered
                 (materialize-view terminal-summary
                   :value (record SummaryValue
                            :status "EXHAUSTED")
                   :renderer canonical-json
                   :renderer-version 1
                   :target state.progress-report-path
                   :returns WorkReport)))
          (variant DrainTerminalResult EXHAUSTED
            :report rendered
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
