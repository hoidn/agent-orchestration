(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry)
  (import std/resource :only (BlockerClass WorkReport StateExisting))
  (export run)
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
               "artifacts/work/imported-stdlib-loop-exhaustion-direct-command-result.json"
               "imported_stdlib_loop_exhaustion_direct_command_result_summary_seed"))
           (initial-run-state
             (__generated-relpath-seed__
               StateExisting
               "state/imported-stdlib-loop-exhaustion-direct-command-result.json"
               "imported_stdlib_loop_exhaustion_direct_command_result_state_seed")))
      (loop/recur
        :max 1
        :state (loop-state
                 (items-processed Int 0)
                 (run-state StateExisting initial-run-state)
                 (progress-report-path WorkReport progress-report-target))
        :on-exhausted
        (command-result run_checks
          :argv ("python" "scripts/run_checks.py" state.progress-report-path)
          :returns DrainTerminalResult)
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
