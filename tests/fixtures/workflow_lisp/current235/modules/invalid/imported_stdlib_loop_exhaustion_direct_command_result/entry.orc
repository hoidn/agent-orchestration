(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule entry)
  (export run)
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
  (defworkflow run
    ()
    -> DrainTerminalResult
    (let* ((progress-report-target
             (path/join-under WorkReport "imported-stdlib-loop-exhaustion-direct-command-result.json"))
           (initial-run-state
             (path/join-under StateExisting "imported-stdlib-loop-exhaustion-direct-command-result.json")))
      (loop/recur ((state (loop-state
                            (items-processed Int 0)
                            (run-state StateExisting initial-run-state)
                            (progress-report-path WorkReport progress-report-target))))
        :max 1
        :on-exhausted
        (command-result run_checks
          :argv ("python" "scripts/run_checks.py" state.progress-report-path)
          :returns DrainTerminalResult)
        (if false
          (done
            (variant DrainTerminalResult EXHAUSTED
              :report state.progress-report-path
              :run_state state.run-state
              :blocker_class BlockerClass.missing_resource))
          (continue
            (loop-state :like state
              :items-processed (+ state.items-processed 1))))))))
