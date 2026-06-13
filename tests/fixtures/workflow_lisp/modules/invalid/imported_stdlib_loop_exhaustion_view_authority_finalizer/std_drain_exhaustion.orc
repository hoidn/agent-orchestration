(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule std_drain_exhaustion)
  (import std/phase :only (with-phase))
  (export BlockerClass
          PhaseCtx
          PhaseStateBundle
          ResumeStateValue
          ChecksResult
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
  (defpath PhaseStateBundle
    :kind relpath
    :under "state"
    :must-exist false)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord DrainLoopTerminal
    (items-processed Int)
    (run-state StateExisting)
    (progress-report-path WorkReport)
    (blocker-class BlockerClass))
  (defrecord ResumeStateValue
    (status String))
  (defrecord ChecksResult
    (report WorkReport))
  (defunion DrainTerminalResult
    (EXHAUSTED
      (report WorkReport)
      (run_state StateExisting)
      (blocker_class BlockerClass)))
  (defworkflow finalize-terminal
    ((phase-ctx PhaseCtx)
     (terminal DrainLoopTerminal))
    -> DrainTerminalResult
    (with-phase phase-ctx checks
      (let* ((rendered-state
               (materialize-view generated-state
                 :value (record ResumeStateValue
                          :status "EXHAUSTED")
                 :renderer canonical-json
                 :renderer-version 1
                 :returns PhaseStateBundle))
             (checks
               (resume-or-start checks
                 :ctx phase-ctx
                 :resume-from rendered-state
                 :start
                   (command-result run_checks
                     :argv ("python" "scripts/run_checks.py" terminal.progress-report-path)
                     :returns ChecksResult)
                 :returns ChecksResult)))
        (variant DrainTerminalResult EXHAUSTED
          :report checks.report
          :run_state terminal.run-state
          :blocker_class terminal.blocker-class))))
  (defmacro emit-run-drain-like (name)
    (defworkflow name
      ((phase-ctx PhaseCtx))
      -> std_drain_exhaustion/DrainTerminalResult
      (let* ((progress-report-target
               (__generated-relpath-seed__
                 WorkReport
                 "artifacts/work/imported-stdlib-loop-exhaustion-view-authority-finalizer.json"
                 "imported_stdlib_loop_exhaustion_view_authority_summary_seed"))
             (initial-run-state
               (__generated-relpath-seed__
                 StateExisting
                 "state/imported-stdlib-loop-exhaustion-view-authority-finalizer.json"
                 "imported_stdlib_loop_exhaustion_view_authority_state_seed"))
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
             (rendered-state
               (call std_drain_exhaustion/finalize-terminal
                 :phase-ctx phase-ctx
                 :terminal terminal))
             (result
               rendered-state))
        result)))
)
