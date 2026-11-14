(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
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
  (defunion DrainTerminalResult
    (EXHAUSTED
      (report WorkReport)
      (run_state StateExisting)
      (blocker_class BlockerClass)))
  (defproc effectful-exhausted-terminal
    ((report_path WorkReport)
     (run_state StateExisting))
    -> DrainTerminalResult
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path run_state)
      :returns DrainTerminalResult))
  (defproc pure-exhausted-terminal
    ((report_path WorkReport)
     (run_state StateExisting))
    -> DrainTerminalResult
    (variant DrainTerminalResult EXHAUSTED
      :report report_path
      :run_state run_state
      :blocker_class BlockerClass.missing_resource))
  (defmacro emit-run-drain-like (name)
    (defworkflow name
      ()
      -> DrainTerminalResult
      (let* ((progress-report-target
               (path/join-under WorkReport "imported-stdlib-loop-exhaustion-effectful-helper.json"))
             (initial-run-state
               (path/join-under StateExisting "imported-stdlib-loop-exhaustion-effectful-helper.json")))
        (loop/recur ((state (loop-state
                              (items-processed Int 0)
                              (run-state StateExisting initial-run-state)
                              (progress-report-path WorkReport progress-report-target))))
          :max 1
          :on-exhausted
          (std_drain_exhaustion/effectful-exhausted-terminal
            state.progress-report-path
            state.run-state)
          (if false
            (done
              (std_drain_exhaustion/pure-exhausted-terminal
                state.progress-report-path
                state.run-state))
            (continue
              (loop-state :like state
                :items-processed (+ state.items-processed 1)))))))))
