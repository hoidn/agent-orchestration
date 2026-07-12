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
          backlog-drain
          backlog-drain-proc
          settle-drain-terminal)
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
    (let* ((terminal (std/drain/backlog-drain-proc
                       ctx
                       (proc-ref selector)
                       (proc-ref run-item)
                       (proc-ref gap-drafter)
                       max
                       (__generated-relpath-seed__
                         std/resource/WorkReport
                         "artifacts/work/drain-progress-report.md"
                         "backlog_drain_progress_report_seed"))))
      (std/drain/settle-drain-terminal terminal)))
  ; Generic drain loop body (the backlog-drain macro above expands onto it).
  ; Signature is the Tranche 2 flagship from
  ; docs/design/workflow_lisp_parametric_type_system.md (:where copied
  ; verbatim, including the G2 SelPayloadT field clauses). Reality anchors
  ; mirror the frozen intrinsic `_phase_stdlib_lower_backlog_drain_impl`
  ; (lowering/phase_drain.py): item-context projection (item-id /
  ; item-state-root), selector-BLOCKED -> user_decision_required,
  ; on-exhausted -> unrecoverable_after_fix_attempt, EMPTY-with-work ->
  ; COMPLETED, and the caller-supplied initial progress-report seed.
  (defproc backlog-drain-proc
    :forall (CtxT SelectionT SelPayloadT GapPayloadT RunResultT GapResultT)
    ((ctx CtxT)
     (selector ProcRef[(CtxT) -> SelectionT])
     (run-item ProcRef[(std/context/ItemCtx SelPayloadT) -> RunResultT])
     (gap-drafter ProcRef[(CtxT GapPayloadT) -> GapResultT])
     (max-iterations Int)
     (initial-progress-report WorkReport))
    :where ((CtxT is-record)
            (CtxT has-field run std/context/RunCtx)
            (CtxT has-field state-root Path.state-root)
            (CtxT has-field manifest Path.state-root)
            (CtxT has-field ledger Path.state-root)
            (SelectionT is-union)
            (SelectionT has-union-variant EMPTY)
            (SelectionT has-union-variant SELECTED (selection SelPayloadT))
            (SelectionT has-union-variant GAP (gap GapPayloadT))
            (SelectionT has-union-variant BLOCKED (reason String))
            (SelPayloadT is-record)
            (SelPayloadT has-field item-id String)
            (SelPayloadT has-field item-state-root Path.state-root)
            (GapPayloadT is-record)
            (RunResultT has-union-variant CONTINUE (summary-path WorkReport))
            (RunResultT has-union-variant BLOCKED
              (summary-path WorkReport) (blocker-class BlockerClass))
            (GapResultT has-union-variant CONTINUE)
            (GapResultT has-union-variant BLOCKED
              (progress-report-path WorkReport) (blocker-class BlockerClass)))
    -> std/drain/DrainLoopTerminal
    :effects ()
    :lowering inline
    (loop/recur
      :max max-iterations
      :state (loop-state
               (items-processed Int 0)
               (progress-report-path WorkReport initial-progress-report))
      :on-exhausted (variant std/drain/DrainLoopTerminal EXHAUSTED
                      :items_processed state.items-processed
                      :progress_report_path state.progress-report-path
                      :blocker_class std/resource/BlockerClass.unrecoverable_after_fix_attempt)
      (fn (state)
        (match (selector ctx)
          ((EMPTY empty)
           (if (= state.items-processed 0)
             (done
               (variant std/drain/DrainLoopTerminal EMPTY
                 :items_processed state.items-processed
                 :progress_report_path state.progress-report-path))
             (done
               (variant std/drain/DrainLoopTerminal COMPLETED
                 :items_processed state.items-processed
                 :progress_report_path state.progress-report-path))))
          ((SELECTED selected)
           (let* ((item-ctx (record std/context/ItemCtx
                              :run ctx.run
                              :item-id selected.selection.item-id
                              :state-root selected.selection.item-state-root
                              :artifact-root ctx.run.artifact-root
                              :ledger ctx.ledger)))
             (match (run-item item-ctx selected.selection)
               ((CONTINUE continued)
                (continue (loop-state :like state
                            :items-processed (+ state.items-processed 1)
                            :progress-report-path continued.summary-path)))
               ((BLOCKED blocked)
                (done (variant std/drain/DrainLoopTerminal BLOCKED
                        :items_processed state.items-processed
                        :progress_report_path blocked.summary-path
                        :blocker_class blocked.blocker-class))))))
          ((GAP gapped)
           (match (gap-drafter ctx gapped.gap)
             ((CONTINUE continued)
              (continue (loop-state :like state
                          :items-processed state.items-processed)))
             ((BLOCKED blocked)
              (done (variant std/drain/DrainLoopTerminal BLOCKED
                      :items_processed state.items-processed
                      :progress_report_path blocked.progress-report-path
                      :blocker_class blocked.blocker-class)))))
          ((BLOCKED blocked)
           (done (variant std/drain/DrainLoopTerminal BLOCKED
                   :items_processed state.items-processed
                   :progress_report_path state.progress-report-path
                   :blocker_class std/resource/BlockerClass.user_decision_required)))))))
  ; Monomorphic terminal settlement: consume terminal effects, then finalize
  ; the terminal into the public DrainResult. Composes the existing helpers;
  ; it does not re-implement them.
  (defproc settle-drain-terminal
    ((terminal DrainLoopTerminal))
    -> DrainResult
    :effects ((uses-command apply_resource_transition)
              (writes drain-summary))
    :lowering inline
    (let* ((consumed-summary-path (consume-drain-terminal-effects terminal)))
      (finalize-drain-terminal terminal)))
)
