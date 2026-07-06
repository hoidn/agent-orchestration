(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule std/drain)
  (import std/context :only (DrainCtx ItemCtx))
  (import std/resource :only (BlockerClass WorkReport SelectedItemResult))
  (export SelectionPayload
          GapPayload
          SelectionResult
          GapResult
          DrainResult
          DrainTerminalKind
          DrainLoopTerminal
          DrainLoopState
          empty-drain-result-proc
          blocked-drain-result-proc
          completed-drain-result-proc
          finalize-drain-terminal
          consume-drain-terminal-effects
          backlog-drain)
  (defrecord SelectionPayload
    (item-id String)
    (item-state-root Path.state-root))
  (defrecord GapPayload
    (gap-id String))
  (defunion SelectionResult
    (EMPTY)
    (GAP
      (gap GapPayload))
    (SELECTED
      (selection SelectionPayload))
    (BLOCKED
      (reason String)))
  (defunion GapResult
    (CONTINUE)
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defunion DrainResult
    (EMPTY)
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass))
    (COMPLETED
      (items-processed Int)))
  (defenum DrainTerminalKind
    empty
    blocked
    completed
    exhausted)
  (defunion DrainLoopTerminal
    (EMPTY
      (items_processed Int)
      (progress_report_path WorkReport))
    (BLOCKED
      (items_processed Int)
      (progress_report_path WorkReport)
      (blocker_class BlockerClass))
    (COMPLETED
      (items_processed Int)
      (progress_report_path WorkReport))
    (EXHAUSTED
      (items_processed Int)
      (progress_report_path WorkReport)
      (blocker_class BlockerClass)))
  (defrecord DrainLoopState
    (items-processed Int)
    (progress-report-path WorkReport))
  (defrecord DrainOutcomeState
    (variant String)
    (items_processed Int)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool))
  (defrecord DrainOutcomeRequest
    (variant String)
    (items_processed Int)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool))
  (defrecord DrainOutcomeResult
    (variant String)
    (items_processed Int)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool))
  (defrecord DrainOutcomeAudit
    (variant String)
    (items_processed Int)
    (progress_report_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool))
  (defrecord DrainSummaryValue
    (variant String)
    (items_processed Int)
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
              (set-field progress_report_path request.progress_report_path)
              (set-field blocker_class request.blocker_class)
              (set-field has_blocker request.has_blocker))
    :write-set (variant items_processed progress_report_path blocker_class has_blocker)
    :idempotency-fields (variant items_processed progress_report_path blocker_class has_blocker)
    :result (record std/drain/DrainOutcomeResult
      :variant request.variant
      :items_processed request.items_processed
      :progress_report_path request.progress_report_path
      :blocker_class request.blocker_class
      :has_blocker request.has_blocker)
    :audit (record std/drain/DrainOutcomeAudit
      :variant request.variant
      :items_processed request.items_processed
      :progress_report_path request.progress_report_path
      :blocker_class request.blocker_class
      :has_blocker request.has_blocker)
    :conflict-policy fail_closed
    :backend runtime_native)
  (defproc empty-drain-result-proc
    ((items-processed Int)
     (summary-target WorkReport))
    -> DrainResult
    :effects ()
    :lowering inline
    (variant DrainResult EMPTY))
  (defproc blocked-drain-result-proc
    ((items-processed Int)
     (summary-target WorkReport)
     (blocker-class BlockerClass))
    -> DrainResult
    :effects ()
    :lowering inline
    (variant DrainResult BLOCKED
      :progress-report-path summary-target
      :blocker-class blocker-class))
  (defproc completed-drain-result-proc
    ((items-processed Int)
     (summary-target WorkReport))
    -> DrainResult
    :effects ()
    :lowering inline
    (variant DrainResult COMPLETED
      :items-processed items-processed))
  (defproc finalize-drain-terminal
    ((terminal DrainLoopTerminal))
    -> DrainResult
    :effects ()
    :lowering inline
    (match terminal
      ((EMPTY empty)
       (empty-drain-result-proc
         empty.items_processed
         empty.progress_report_path))
      ((COMPLETED completed)
       (completed-drain-result-proc
         completed.items_processed
         completed.progress_report_path))
      ((BLOCKED blocked)
       (blocked-drain-result-proc
         blocked.items_processed
         blocked.progress_report_path
         blocked.blocker_class))
      ((EXHAUSTED exhausted)
       (blocked-drain-result-proc
         exhausted.items_processed
         exhausted.progress_report_path
         exhausted.blocker_class))))
  (defproc consume-drain-terminal-effects
    ((terminal DrainLoopTerminal))
    -> WorkReport
    :effects ((uses-command apply_resource_transition)
              (writes drain-summary))
    :lowering inline
    (match terminal
      ((EMPTY empty)
       (let* ((outcome
                (resource-transition
                  :transition record-drain-outcome
                  :resource drain-run-state
                  :request (record std/drain/DrainOutcomeRequest
                             :variant "EMPTY"
                             :items_processed empty.items_processed
                             :progress_report_path empty.progress_report_path
                             :blocker_class std/resource/BlockerClass.missing_resource
                             :has_blocker false)))
              (summary-path
                (materialize-view drain-summary
                  :value (record std/drain/DrainSummaryValue
                           :variant outcome.variant
                           :items_processed outcome.items_processed
                           :progress_report_path outcome.progress_report_path
                           :blocker_class outcome.blocker_class
                           :has_blocker outcome.has_blocker)
                  :renderer canonical-json
                  :renderer-version 1
                  :target empty.progress_report_path
                  :returns WorkReport)))
         summary-path))
      ((COMPLETED completed)
       (let* ((outcome
                (resource-transition
                  :transition record-drain-outcome
                  :resource drain-run-state
                  :request (record std/drain/DrainOutcomeRequest
                             :variant "COMPLETED"
                             :items_processed completed.items_processed
                             :progress_report_path completed.progress_report_path
                             :blocker_class std/resource/BlockerClass.missing_resource
                             :has_blocker false)))
              (summary-path
                (materialize-view drain-summary
                  :value (record std/drain/DrainSummaryValue
                           :variant outcome.variant
                           :items_processed outcome.items_processed
                           :progress_report_path outcome.progress_report_path
                           :blocker_class outcome.blocker_class
                           :has_blocker outcome.has_blocker)
                  :renderer canonical-json
                  :renderer-version 1
                  :target completed.progress_report_path
                  :returns WorkReport)))
         summary-path))
      ((BLOCKED blocked)
       (let* ((outcome
                (resource-transition
                  :transition record-drain-outcome
                  :resource drain-run-state
                  :request (record std/drain/DrainOutcomeRequest
                             :variant "BLOCKED"
                             :items_processed blocked.items_processed
                             :progress_report_path blocked.progress_report_path
                             :blocker_class blocked.blocker_class
                             :has_blocker true)))
              (summary-path
                (materialize-view drain-summary
                  :value (record std/drain/DrainSummaryValue
                           :variant outcome.variant
                           :items_processed outcome.items_processed
                           :progress_report_path outcome.progress_report_path
                           :blocker_class outcome.blocker_class
                           :has_blocker outcome.has_blocker)
                  :renderer canonical-json
                  :renderer-version 1
                  :target blocked.progress_report_path
                  :returns WorkReport)))
         summary-path))
      ((EXHAUSTED exhausted)
       (let* ((outcome
                (resource-transition
                  :transition record-drain-outcome
                  :resource drain-run-state
                  :request (record std/drain/DrainOutcomeRequest
                             :variant "BLOCKED"
                             :items_processed exhausted.items_processed
                             :progress_report_path exhausted.progress_report_path
                             :blocker_class exhausted.blocker_class
                             :has_blocker true)))
              (summary-path
                (materialize-view drain-summary
                  :value (record std/drain/DrainSummaryValue
                           :variant outcome.variant
                           :items_processed outcome.items_processed
                           :progress_report_path outcome.progress_report_path
                           :blocker_class outcome.blocker_class
                           :has_blocker outcome.has_blocker)
                  :renderer canonical-json
                  :renderer-version 1
                  :target exhausted.progress_report_path
                  :returns WorkReport)))
         summary-path))))
  (defmacro backlog-drain (name ctx-key ctx selector-key selector run-item-key run-item gap-drafter-key gap-drafter max-key max)
    (backlog-drain-callable-boundary name
      :ctx ctx
      :selector selector
      :run-item run-item
      :gap-drafter gap-drafter
      :max-iterations max))
)
