(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule minimal_caller_backlog_drain)
  (import std/context :only (RunCtx))
  (import std/drain :only (DrainResult backlog-drain-proc settle-drain-terminal))
  (import std/resource :only (BlockerClass WorkReport))
  (defrecord MinimalDrainCtx
    (run RunCtx)
    (state-root Path.state-root)
    (manifest Path.state-root)
    (ledger Path.state-root))
  (defrecord MinimalSelectionPayload
    (item-id String)
    (item-state-root Path.state-root))
  (defrecord MinimalGapPayload)
  (defunion MinimalSelection
    (EMPTY)
    (SELECTED
      (selection MinimalSelectionPayload))
    (GAP
      (gap MinimalGapPayload))
    (BLOCKED
      (reason String)))
  (defunion MinimalRunResult
    (CONTINUE
      (summary-path WorkReport))
    (BLOCKED
      (summary-path WorkReport)
      (blocker-class BlockerClass)))
  (defunion MinimalGapResult
    (CONTINUE)
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defproc select-minimal
    ((ctx MinimalDrainCtx))
    -> MinimalSelection
    :effects ((uses-command drain_select))
    :lowering inline
    (command-result drain_select
      :argv ("python" "scripts/select_next_item.py" ctx.manifest)
      :returns MinimalSelection))
  (defproc run-minimal
    ((item-ctx std/context/ItemCtx)
     (selection MinimalSelectionPayload))
    -> MinimalRunResult
    :effects ((uses-command drain_run_item))
    :lowering inline
    (command-result drain_run_item
      :argv ("python" "scripts/execute_selected_item.py" selection.item-id)
      :returns MinimalRunResult))
  (defproc draft-minimal
    ((ctx MinimalDrainCtx)
     (gap MinimalGapPayload))
    -> MinimalGapResult
    :effects ((uses-command drain_draft_gap))
    :lowering inline
    (command-result drain_draft_gap
      :argv ("python" "scripts/draft_gap_item.py" ctx.manifest)
      :returns MinimalGapResult))
  (defworkflow minimal-backlog-drain
    ((ctx MinimalDrainCtx))
    -> DrainResult
    (let* ((terminal (backlog-drain-proc
                       ctx
                       (proc-ref select-minimal)
                       (proc-ref run-minimal)
                       (proc-ref draft-minimal)
                       3
                       (__generated-relpath-seed__
                         WorkReport
                         "artifacts/work/drain-progress-report.md"
                         "minimal_backlog_drain_progress_report_seed"))))
      (settle-drain-terminal terminal))))
