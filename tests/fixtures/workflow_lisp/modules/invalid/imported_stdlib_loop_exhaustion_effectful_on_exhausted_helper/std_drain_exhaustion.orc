(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule std_drain_exhaustion)
  (export BlockerClass
          WorkReport
          StateExisting
          DrainTerminalResult
          pure-exhausted-terminal
          effectful-exhausted-terminal
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
  (defrecord SummaryValue
    (variant String))
  (defunion DrainTerminalResult
    (EXHAUSTED
      (report WorkReport)
      (run_state StateExisting)
      (blocker_class BlockerClass)))
  (defproc effectful-exhausted-terminal
    ((report_path WorkReport)
     (run_state StateExisting))
    -> DrainTerminalResult
    :effects ((writes terminal-summary))
    :lowering inline
    (let* ((rendered
             (materialize-view terminal-summary
               :value (record SummaryValue
                        :variant "EXHAUSTED")
               :renderer canonical-json
               :renderer-version 1
               :target report_path
               :returns WorkReport)))
      (variant DrainTerminalResult EXHAUSTED
        :report rendered
        :run_state run_state
        :blocker_class BlockerClass.unrecoverable_after_fix_attempt)))
  (defproc pure-exhausted-terminal
    ((report_path WorkReport)
     (run_state StateExisting))
    -> DrainTerminalResult
    :effects ()
    :lowering inline
    (variant DrainTerminalResult EXHAUSTED
      :report report_path
      :run_state run_state
      :blocker_class BlockerClass.missing_resource))
  (defmacro emit-run-drain-like (name)
    (defworkflow name
      ()
      -> DrainTerminalResult
      (let* ((progress-report-target
               (__generated-relpath-seed__
                 WorkReport
                 "artifacts/work/imported-stdlib-loop-exhaustion-effectful-helper.json"
                 "imported_stdlib_loop_exhaustion_effectful_helper_summary_seed"))
             (initial-run-state
               (__generated-relpath-seed__
                 StateExisting
                 "state/imported-stdlib-loop-exhaustion-effectful-helper.json"
                 "imported_stdlib_loop_exhaustion_effectful_helper_state_seed")))
        (loop/recur
          :max 1
          :state (loop-state
                   (items-processed Int 0)
                   (run-state StateExisting initial-run-state)
                   (progress-report-path WorkReport progress-report-target))
          :on-exhausted
          (std_drain_exhaustion/effectful-exhausted-terminal
            state.progress-report-path
            state.run-state)
          (fn (state)
            (if false
              (done
                (std_drain_exhaustion/pure-exhausted-terminal
                  state.progress-report-path
                  state.run-state))
              (continue
                (loop-state :like state
                  :items-processed (+ state.items-processed 1))))))))))
