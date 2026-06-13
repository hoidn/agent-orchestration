(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule std/drain)
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (BlockerClass WorkReport StateExisting SelectedItemResult))
  (export SelectionPayload
          GapPayload
          SelectionResult
          GapResult
          DrainResult
          DrainTerminalKind
          DrainLoopTerminal
          empty-drain-result-proc
          blocked-drain-result-proc
          completed-drain-result-proc
          finalize-drain-terminal
          backlog-drain)
  (defrecord SelectionPayload
    (item-id String)
    (item-state-root Path.state-root))
  (defrecord GapPayload
    (gap-id String))
  (defunion SelectionResult
    (EMPTY
      (run-state StateExisting))
    (GAP
      (gap GapPayload))
    (SELECTED
      (selection SelectionPayload)))
  (defunion GapResult
    (CONTINUE
      (run-state StateExisting))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defunion DrainResult
    (EMPTY
      (run-state StateExisting))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass))
    (COMPLETED
      (items-processed Int)
      (run-state StateExisting)))
  (defenum DrainTerminalKind
    empty
    blocked
    completed
    exhausted)
  (defunion DrainLoopTerminal
    (EMPTY
      (items_processed Int)
      (run_state StateExisting)
      (progress_report_path WorkReport))
    (BLOCKED
      (items_processed Int)
      (run_state StateExisting)
      (progress_report_path WorkReport)
      (blocker_class BlockerClass))
    (COMPLETED
      (items_processed Int)
      (run_state StateExisting)
      (progress_report_path WorkReport))
    (EXHAUSTED
      (items_processed Int)
      (run_state StateExisting)
      (progress_report_path WorkReport)
      (blocker_class BlockerClass)))
  (defrecord DrainOutcomeState
    (variant String)
    (items_processed Int)
    (run_state StateExisting)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool))
  (defrecord DrainOutcomeRequest
    (variant String)
    (items_processed Int)
    (run_state StateExisting)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool))
  (defrecord DrainOutcomeResult
    (variant String)
    (items_processed Int)
    (run_state StateExisting)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool))
  (defrecord DrainOutcomeAudit
    (variant String)
    (items_processed Int)
    (run_state StateExisting)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool))
  (defrecord DrainSummaryValue
    (variant String)
    (items_processed Int)
    (run_state StateExisting)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool))
  (defresource drain-run-state
    :state-type std/drain/DrainOutcomeState
    :backing state-layout)
  (deftransition record-drain-outcome
    :resource drain-run-state
    :request-type std/drain/DrainOutcomeRequest
    :result-type std/drain/DrainOutcomeResult
    :preconditions ((!= request.variant ""))
    :updates ((set-field variant request.variant)
              (set-field items_processed request.items_processed)
              (set-field run_state request.run_state)
              (set-field progress_report_path request.progress_report_path)
              (set-field blocker_class request.blocker_class)
              (set-field has_blocker request.has_blocker))
    :write-set (variant items_processed run_state progress_report_path blocker_class has_blocker)
    :idempotency-fields (variant items_processed run_state progress_report_path blocker_class has_blocker)
    :result (record std/drain/DrainOutcomeResult
      :variant request.variant
      :items_processed request.items_processed
      :run_state request.run_state
      :progress_report_path request.progress_report_path
      :blocker_class request.blocker_class
      :has_blocker request.has_blocker)
    :audit (record std/drain/DrainOutcomeAudit
      :variant request.variant
      :items_processed request.items_processed
      :run_state request.run_state
      :progress_report_path request.progress_report_path
      :blocker_class request.blocker_class
      :has_blocker request.has_blocker)
    :conflict-policy fail_closed
    :backend runtime_native)
  (defproc empty-drain-result-proc
    ((items-processed Int)
     (run-state StateExisting)
     (summary-target WorkReport))
    -> DrainResult
    :effects ((uses-command apply_resource_transition)
              (writes drain-summary))
    :lowering inline
    (let* ((outcome
             (resource-transition
               :transition record-drain-outcome
               :resource drain-run-state
               :request (record std/drain/DrainOutcomeRequest
                          :variant "EMPTY"
                          :items_processed items-processed
                          :run_state run-state
                          :progress_report_path summary-target
                          :blocker_class std/resource/BlockerClass.missing_resource
                          :has_blocker false)))
           (summary-path
             (materialize-view drain-summary
               :value (record std/drain/DrainSummaryValue
                        :variant outcome.variant
                        :items_processed outcome.items_processed
                        :run_state outcome.run_state
                        :progress_report_path outcome.progress_report_path
                        :blocker_class outcome.blocker_class
                        :has_blocker outcome.has_blocker)
               :renderer canonical-json
               :renderer-version 1
               :target summary-target
               :returns WorkReport)))
      (variant DrainResult EMPTY
        :run-state run-state)))
  (defproc blocked-drain-result-proc
    ((items-processed Int)
     (run-state StateExisting)
     (summary-target WorkReport)
     (blocker-class BlockerClass))
    -> DrainResult
    :effects ((uses-command apply_resource_transition)
              (writes drain-summary))
    :lowering inline
    (let* ((outcome
             (resource-transition
               :transition record-drain-outcome
               :resource drain-run-state
               :request (record std/drain/DrainOutcomeRequest
                          :variant "BLOCKED"
                          :items_processed items-processed
                          :run_state run-state
                          :progress_report_path summary-target
                          :blocker_class blocker-class
                          :has_blocker true)))
           (summary-path
             (materialize-view drain-summary
               :value (record std/drain/DrainSummaryValue
                        :variant outcome.variant
                        :items_processed outcome.items_processed
                        :run_state outcome.run_state
                        :progress_report_path outcome.progress_report_path
                        :blocker_class outcome.blocker_class
                        :has_blocker outcome.has_blocker)
               :renderer canonical-json
               :renderer-version 1
               :target summary-target
               :returns WorkReport)))
      (variant DrainResult BLOCKED
        :progress-report-path summary-path
        :blocker-class blocker-class)))
  (defproc completed-drain-result-proc
    ((items-processed Int)
     (run-state StateExisting)
     (summary-target WorkReport))
    -> DrainResult
    :effects ((uses-command apply_resource_transition)
              (writes drain-summary))
    :lowering inline
    (let* ((outcome
             (resource-transition
               :transition record-drain-outcome
               :resource drain-run-state
               :request (record std/drain/DrainOutcomeRequest
                          :variant "COMPLETED"
                          :items_processed items-processed
                          :run_state run-state
                          :progress_report_path summary-target
                          :blocker_class std/resource/BlockerClass.missing_resource
                          :has_blocker false)))
           (summary-path
             (materialize-view drain-summary
               :value (record std/drain/DrainSummaryValue
                        :variant outcome.variant
                        :items_processed outcome.items_processed
                        :run_state outcome.run_state
                        :progress_report_path outcome.progress_report_path
                        :blocker_class outcome.blocker_class
                        :has_blocker outcome.has_blocker)
               :renderer canonical-json
               :renderer-version 1
               :target summary-target
               :returns WorkReport)))
      (variant DrainResult COMPLETED
        :items-processed items-processed
        :run-state run-state)))
  (defproc finalize-drain-terminal
    ((terminal DrainLoopTerminal))
    -> DrainResult
    :effects ((uses-command apply_resource_transition)
              (writes drain-summary))
    :lowering inline
    (match terminal
      ((EMPTY empty)
       (let* ((result
                (empty-drain-result-proc
                  empty.items_processed
                  empty.run_state
                  empty.progress_report_path)))
         result))
      ((COMPLETED completed)
       (let* ((result
                (completed-drain-result-proc
                  completed.items_processed
                  completed.run_state
                  completed.progress_report_path)))
         result))
      ((BLOCKED blocked)
       (let* ((result
                (blocked-drain-result-proc
                  blocked.items_processed
                  blocked.run_state
                  blocked.progress_report_path
                  blocked.blocker_class)))
         result))
      ((EXHAUSTED exhausted)
       (let* ((result
                (blocked-drain-result-proc
                  exhausted.items_processed
                  exhausted.run_state
                  exhausted.progress_report_path
                  exhausted.blocker_class)))
         result))))
  (defmacro backlog-drain (name ctx-key ctx selector-key selector run-item-key run-item gap-drafter-key gap-drafter max-key max)
    (let* ((progress-report-target
             (__generated-relpath-seed__
               std/resource/WorkReport
               "artifacts/work/drain-progress-report.md"
               "stdlib_drain_progress_report_seed"))
           (initial-run-state
             (__generated-relpath-seed__
               std/resource/StateExisting
               "state/drain-run-state.json"
               "stdlib_drain_run_state_seed"))
           (terminal
             (loop/recur
               :max max
               :state (loop-state
                        (items-processed Int 0)
                        (run-state std/resource/StateExisting initial-run-state)
                        (progress-report-path std/resource/WorkReport progress-report-target))
               :on-exhausted
               (variant std/drain/DrainLoopTerminal EXHAUSTED
                 :items_processed state.items-processed
                 :run_state state.run-state
                 :progress_report_path state.progress-report-path
                 :blocker_class std/resource/BlockerClass.unrecoverable_after_fix_attempt)
               (fn (state)
                 (let* ((selection-result
                          (call selector
                            :ctx ctx)))
                   (match selection-result
                     ((EMPTY empty)
                      (done
                        (variant std/drain/DrainLoopTerminal EMPTY
                          :items_processed state.items-processed
                          :run_state state.run-state
                          :progress_report_path state.progress-report-path)))
                     ((GAP gap_case)
                      (let* ((gap-result
                               (call gap-drafter
                                 :ctx ctx
                                 :gap gap_case.gap)))
                        (match gap-result
                          ((CONTINUE continued)
                           (continue
                             (loop-state :like state
                               :run-state continued.run-state)))
                          ((BLOCKED blocked)
                           (done
                             (variant std/drain/DrainLoopTerminal BLOCKED
                               :items_processed state.items-processed
                               :run_state state.run-state
                               :progress_report_path blocked.progress-report-path
                               :blocker_class blocked.blocker-class))))))
                     ((SELECTED selected)
                      (let* ((selection-payload
                               selected.selection)
                              (item-ctx
                               (record std/context/ItemCtx
                                 :run ctx.run
                                 :item-id selected.selection.item-id
                                 :state-root selected.selection.item-state-root
                                 :artifact-root ctx.run.artifact-root
                                 :ledger ctx.ledger))
                              (selected-result
                               (call run-item
                                 :item-ctx item-ctx
                                 :selection selection-payload)))
                        (match selected-result
                          ((CONTINUE continued)
                           (done
                             (variant std/drain/DrainLoopTerminal COMPLETED
                               :items_processed 1
                               :run_state continued.run-state
                               :progress_report_path continued.summary-path)))
                          ((BLOCKED blocked)
                           (done
                             (variant std/drain/DrainLoopTerminal BLOCKED
                               :items_processed 1
                               :run_state blocked.run-state
                               :progress_report_path blocked.summary-path
                               :blocker_class blocked.blocker-class)))))))))))
           (result
             (std/drain/finalize-drain-terminal terminal)))
      result))
)
