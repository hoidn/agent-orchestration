(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule std_drain_exhaustion)
  (export WorkReport
          StateExisting
          GapPayload
          SelectionResult
          DrainLoopTerminal
          DrainTerminalResult
          emit-run-drain-like)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath StateExisting
    :kind relpath
    :under "state"
    :must-exist true)
  (defrecord SelectionPayload
    (item-id String))
  (defrecord GapPayload
    (gap-id String))
  (defunion SelectionResult
    (GAP
      (gap GapPayload))
    (SELECTED
      (selection SelectionPayload)))
  (defrecord DrainLoopTerminal
    (selected_id String)
    (run_state StateExisting)
    (progress_report_path WorkReport))
  (defunion DrainTerminalResult
    (EXHAUSTED
      (selected_id String)
      (report WorkReport)))
  (defmacro emit-run-drain-like (name)
    (defworkflow name
      ()
      -> std_drain_exhaustion/DrainLoopTerminal
      (let* ((progress-report-target
               (__generated-relpath-seed__
                 WorkReport
                 "artifacts/work/imported-stdlib-loop-exhaustion-unproved-variant.json"
                 "imported_stdlib_loop_exhaustion_unproved_variant_summary_seed"))
             (initial-run-state
               (__generated-relpath-seed__
                 StateExisting
                 "state/imported-stdlib-loop-exhaustion-unproved-variant.json"
                 "imported_stdlib_loop_exhaustion_unproved_variant_state_seed"))
             (selection-result
               (variant SelectionResult GAP
                 :gap (record GapPayload
                        :gap-id "gap-1"))))
        (loop/recur
          :max 1
          :state (loop-state
                   (run-state StateExisting initial-run-state)
                   (progress-report-path WorkReport progress-report-target))
          :on-exhausted
          (record std_drain_exhaustion/DrainLoopTerminal
            :selected_id selection-result.selection.item-id
            :run_state state.run-state
            :progress_report_path state.progress-report-path)
          (fn (state)
            (if false
              (done
                (record std_drain_exhaustion/DrainLoopTerminal
                  :selected_id ""
                  :run_state state.run-state
                  :progress_report_path state.progress-report-path))
              (continue state))))))))
