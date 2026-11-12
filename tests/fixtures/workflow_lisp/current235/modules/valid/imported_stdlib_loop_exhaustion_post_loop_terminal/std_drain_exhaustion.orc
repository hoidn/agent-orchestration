(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
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
  (defworkflow finalize-terminal
    ((terminal DrainLoopTerminal))
    -> DrainTerminalResult
    (variant DrainTerminalResult EXHAUSTED
      :items_processed terminal.items-processed
      :progress_report_path terminal.progress-report-path
      :blocker_class terminal.blocker-class
      :run_state terminal.run-state))
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
