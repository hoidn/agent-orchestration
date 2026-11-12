# Observability and Status JSON (Normative parts noted)

- Debug mode
  - `--debug` enables verbose logging: substitution traces, dependency resolution details, command construction, environment snapshot (masked), and file ops.
  - Prompt audit: with `--debug`, composed prompt text is written to `logs/<Step>.prompt.txt` with known secret values masked.
  - `--stream-output` live-streams provider stdout/stderr to the parent console without enabling prompt audit, verbose debug logging, or state backups.

- Execution logs
  - Under `RUN_ROOT/logs/`: `orchestrator.log`, `StepName.stdout` (>8 KiB or JSON parse error), `StepName.stderr` (when non-empty), `StepName.debug` (when enabled).
  - v2.10 provider-session visits also create visit-scoped metadata and optional retained transport spools under `RUN_ROOT/provider_sessions/`.
  - Provider observation writes invocation-local normalized display streams
    and finalized transcripts under `RUN_ROOT/provider-observation/display/`
    and `RUN_ROOT/provider-observation/transcripts/`.
  - v2.17 provider-peer-group visit evidence under `RUN_ROOT/provider-peer-group/`
    was removed with its executor on 2026-11-11 (git tag
    `archive/dead-executors-2026-11-11`).

- Provider observation (v2.16)
  - Ordinary provider observation is attempted by default at both workflow and
    provider executor boundaries. One private run-scoped tmux server owns
    unique, non-reused panes with a 1:1 invocation-to-pane relationship.
  - Ordinary manager creation, pane allocation, append, health, finalization,
    and teardown failures are best-effort observability failures and cannot
    change provider transport, timeout, metadata, bundle, or result semantics.
  - Session-aware panes mirror normalized assistant text, never raw session
    JSONL. Claude and Codex session transports additionally display bounded
    tool-activity notices (tool name/kind and started, completed or error status)
    as events arrive. The same notices appear on the parent console when
    `--stream-output` is enabled. Raw arguments, command bodies, tool results
    and thinking/reasoning payloads are omitted. Notices use the same session
    identity eligibility and terminal sanitization as assistant text; an
    unknown/malformed activity payload or display callback failure does not
    change transport validation. Activity is separate from normalized assistant
    stdout and never enters a workflow result. Pane bytes and transcripts remain
    display evidence; parsers and result validation continue to consume the
    authoritative provider transport and declared output bundle.
  - Live tmux socket and target values are process-local. They never enter
    workflow values, `state.json`, stable status records, checkpoints, or
    resume selection.
  - An evaluated run whose checked program contains `agent`/`agent_turn`
    effects constructs the run-scoped observation manager best-effort;
    evaluated runs of programs without agents keep observation disabled as
    before, so 2.35–2.37 behaviour is unchanged: observation is enabled only
    where an agent instance needs a durable view. Within an agent-bearing
    run, ordinary `provider-result` effects keep the one-invocation/one-pane
    contract.
  - Each agent instance owns one logical read-only view: every turn of that
    agent appends to the same pane and transcript, with
    `--- turn <identity> attempt <n> ---` and `--- idle ---` boundary lines;
    invoking the agent again never opens a second pane. If an agent's view
    cannot open, that agent stays unobserved for the rest of the process: its
    turns never fall back to ordinary per-invocation panes and the open is not
    retried each turn. View files are unique per process, so a resumed run
    opens fresh views beside the earlier ones. Attach is read-only
    (`tmux -S <socket> attach -r -t <session>`); the session is logged once per
    run at manager creation and each agent view's socket and pane target are
    logged when that view opens. They are transient: a runtime restart may
    allocate a different pane/socket for the same logical agent, and targets
    never enter `Agent`, the memo or `state.json`.
  - The agent view is derived from invocation-local streams and can never
    authorize, reconcile or dispatch a turn; every observation failure is
    best-effort. Parallel workers keep observation disabled.
  - Agent result-validation diagnostics, derived state and reports use only
    logical agent identity and safe code, without raw provider/result detail,
    exit information or violations ([State](state.md#memo-records)); ordinary
    provider failure diagnostics retain their existing detail.

- Provider peer-group evidence (v2.17): its executor, adapter pane lifecycle
  and message ledgers were removed on 2026-11-11 (git tag
  `archive/dead-executors-2026-11-11`); see the
  [salvage record](../docs/design/live_provider_supervision_and_peers_salvage.md).

- Error context (normative)
  - On step failure, record message, exit code, tails of stdout/stderr, and error context details (undefined variables, missing deps, substituted command, missing secrets, etc.).
  - v1.5 gate failures use `error.type: "assert_failed"` and `exit_code: 3`.
  - v1.6 typed predicate resolution/evaluation failures use `error.type: "predicate_evaluation_failed"` with structured predicate context.
  - v1.8 cycle guards use `error.type: "cycle_guard_exceeded"` with structured context (`guard`, `limit`, `observed`, `step`).

- Progress and metrics
  - Optional `--progress` renders `[n/N] StepName: Running (Xs)...` and loop progress `[i/total]`.
  - State includes timing metrics: step duration, provider time, wait duration, file I/O counts where applicable.
  - Active runtime may be derived from run-level executor sessions in `state.runtime_observability`. Active runtime is the sum of closed executor-session durations plus the age of a currently live executor session whose process identity can be confirmed. It excludes time between a stopped, interrupted, or abandoned executor process and a later resume process.
  - Active runtime is observability-only. It must not drive `when`, `assert`, `goto`, retry, provider timeout, or workflow deadline behavior unless a future control-flow spec explicitly defines such behavior.
  - Advisory agent summaries:
    - `--step-summaries` may emit deterministic summary snapshots and agent-drafted Markdown under the execution root that produced them. Top-level steps write under `RUN_ROOT/summaries/`; reusable-call steps may write detailed records under `RUN_ROOT/call_frames/<frame>/summaries/`.
    - `--summary-profile basic` preserves the legacy factual per-step summary behavior.
    - `--summary-profile phase-performance` emits summaries for provider-like steps and phase boundaries, including advisory performance judgments.
    - `--live-agent-notes` may enable a runtime-side observer that reads a bounded tail of the current tmux pane output, calls a configured note provider at a throttled interval, and writes `RUN_ROOT/summaries/live-current-step.md` plus `RUN_ROOT/summaries/live-current-step.json`. The default live-note provider is `claude_haiku_summary`. Provider-session transport may be used as a fallback when tmux pane capture is unavailable.
    - `RUN_ROOT/summaries/` is the user-facing summary hub for the whole run. It contains an aggregate `index.json`, plus generated `README.md` and `run-summary.md` navigation files that link to detailed summaries across call frames.
    - Summary files, live-note files, summary indexes, `README.md`, and `run-summary.md` are observability artifacts only. They are not workflow artifacts, are not published through artifact lineage, and must not drive routing, retries, assertions, or status reconciliation.
    - Phase boundaries are currently reusable `call` steps and `repeat_until` frames.

- Trace context
  - Steps may include trace IDs in commands using variable substitution.

- Status JSON (normative schema; orchestrator does not consume)
  - Recommended path: `artifacts/<agent>/status_<step>.json`.
  - Example fields: `schema: "status/v1"`, `correlation_id`, `agent`, `run_id`, `step`, `timestamp`, `success`, `exit_code`, `outputs[]`, `metrics{}`, `next_actions[]`, `message`.
  - All file paths within a status JSON must be relative to WORKSPACE.

Orchestrator interaction: The orchestrator does not consume or act on status
JSON files. They are for observability and external tooling only; control flow
derives solely from the validated `.orc` executable and `state.json`.

- Status/report surfaces
  - `report` and the dashboard read evaluated runs only: the checked authority
    (`run.json`, `closed_program.json`, `memo.jsonl`) and the view derived from
    it, without reopening the workflow source. The view reads nothing under
    `effects/`; `report` additionally reads only `attempt-<n>/usage.json` of
    provider-class steps ([usage](#report-usage)), never a recipe, prompt,
    stdout or result file. A run directory with a
    `state.json` entry and no evaluated authority was written by the retired
    runtime; both refuse it with `workflow_execution_profile_retired` and the
    git tag `archive/retired-run-readers-2026-11-11` that keeps the old readers (see
    [the CLI contract](cli.md#evaluated-readers)). Its `state.json` is not read
    beyond the view-hint check.
  - Dashboard status projection is advisory and read-only: it shows the derived
    view's status and never writes to a run directory.
  - Dashboard run identity is the resolved workspace root plus the scanned run directory name. `state.run_id` is display metadata and mismatch context only.
  - Dashboard index and detail pages may support an optional `refresh=<seconds>` query parameter using page-level meta refresh. Invalid or out-of-range values are ignored, and refresh support must not add background workers or route-triggered state changes.
  - Dashboard file previews are observability views over existing artifacts and logs only; missing prompt audits, stdout/stderr spill files, provider-session files, and backups are display states rather than run failures.
  - Step snapshots may include normalized `output.outcome` fields when present in `state.json`.
  - The normalized outcome surface is intended for human-readable reports and typed routing; it does not replace the underlying `status`, `exit_code`, or `error` fields.
  - v1.7 scalar bookkeeping steps report distinct kinds (`set_scalar`, `increment_scalar`) and expose their local produced values through the normal `output.artifacts` surface.
  - v1.8 status/report snapshots expose workflow-level `transition_count` / `max_transitions` and step-level `visit_count` / `max_visits` when present.
  - When a top-level step name is revisited, step snapshots may expose:
    - `visit_count`: total top-level visit count from `state.step_visits`
    - `current_visit_count`: visit ordinal of the in-flight `current_step` when that step name is currently running
    - `last_result_visit_count`: visit ordinal recorded on the latest persisted result at `steps.<StepName>`
  - v2.0 status/report snapshots may expose `step_id` alongside display `name`; display names remain the human-facing label, while `step_id` is the durable lineage/resume identity.
  - v2.1 status/report snapshots may expose `bound_inputs`, `workflow_outputs`, and any run-level workflow-boundary `error` object.
  - Target 2.38 confined-child cleanup projection:
    evaluated views and reports include `run_ref_cleanup`, exposed as
    `run.run_ref_cleanup` in report JSON, whenever pending obligations exist,
    and omit it otherwise. It is an array ordered by coordinator `identity`
    and `attempt`; each entry has those existing coordinates,
    `status: "pending"`, and `error`, either `null` when no cleanup outcome is
    durable or the latest durable cleanup diagnostic as `{code, message}`;
    when cleanup moved a replacement, its message includes the preserved
    private location. Markdown renders the same pending obligations and
    reasons. The projection comes from validated coordinator ledger
    authority, never from `state.json`; readers neither repair nor execute
    cleanup. Cleanup does not change the workflow terminal, suppress outputs
    or populate the run-level error. No completed cleanup history is required
    in this projection. Rendering the report is not a full revalidation of
    export bytes; settlement and resume retain that responsibility.
  - <a id="report-usage"></a>Token usage and cost (`report`). Each
    provider-class step (`provider`, `provider_phased`, `agent_turn`,
    `run_ref`) has `usage`, summed over all its attempts (`attempt-1` to its
    latest, beside its `result_path`), and the run has `run.usage`, the same sum
    over every such step's attempts plus `price_table: {source, date}` of the
    table used:
    `{"tokens": {"input", "output", "cache_read", "cache_write"} | null,
    "cost_usd": float | null, "attempts": n, "unknown_attempts": k,
    "partial": bool}`. Other steps have no `usage`; a run with no
    provider-class step has no `run.usage` key and its markdown no `## Usage`
    section.
    - Unknown attempts: an attempt whose `usage.json` is absent (killed before
      writing it, still running, or recorded before `usage.json` existed, so
      a run recorded before metering shows `unknown` for every provider step),
      not a readable regular file, `unknown`, or not well-formed `reported`
      usage counts in `unknown_attempts`, never as zero. A `run_ref` step's
      attempts always do, since its child run's spend is in the child's own
      report.
    - `tokens` sums the reported attempts; null when none reported.
    - `cost_usd` is the list-price equivalent at the table's ordinary rates
      (`pricing.priced`), summed over the attempts that can be priced: an
      attempt whose model has no rates adds nothing, and a reported attempt
      with no token rows but a positive `reported_cost_usd` (Claude's `result`
      line with an empty `modelUsage`) adds that cost, as the spend cap does.
      It is null only when no attempt could be priced, or when the sum leaves
      the float range (JSON never carries `Infinity` or `NaN`). The ordinary
      rates understate a request priced at a model's `long_context` tier; the
      spend cap prices conservatively instead (the larger of the CLI's cost
      and the highest tier, [providers](providers.md#metered-templates-and-usage)),
      so the two figures differ by design.
    - `partial` is true when the figures are a lower bound: some attempt is
      unknown, unpriced, priced from `reported_cost_usd` alone, or its usage
      is `complete: false`.
    - Markdown prints a step's `usage` line and a `## Usage` section with the
      run total and the table's source and date: `unknown` when no attempt
      reported, `cost_usd unknown` when nothing could be priced, a leading `≥`
      on partial figures, and never `0` for an unmetered step.
    - `usage` is a view of the attempt files, not memo authority
      ([providers](providers.md#metered-templates-and-usage)).
  - The executor-session accounting fields (`run.active_runtime_ms` and its
    siblings) and the v2.10 `provider_attempt_interrupted_rerun` and
    `output.provider_session` projections came from the retired-run report;
    `report` no longer produces them (kept at the git tag `archive/retired-run-readers-2026-11-11`).
  - v2.11 adjudicated provider snapshots: no step of this kind can be produced since its
    executor was removed on 2026-11-12 (see the
    [salvage record](../docs/design/trial_and_adjudication_salvage.md)).
  - v2.16 provider-supervision and v2.17 provider-peer-group snapshots: no
    step of either kind can be produced since their executors were removed on
    2026-11-11 (see the
    [salvage record](../docs/design/live_provider_supervision_and_peers_salvage.md)).
  - Target-2.23 phased recovery may expose only its bounded named diagnostic,
    recovery family/mismatch class, and old/new visit coordinates. Prompt, ledger,
    and partial result content remain sidecar evidence and never report authority.
    The v2.11 adjudication recovery was removed with its executor on 2026-11-12.

- Workflow monitor notifications
  - `orchestrator monitor` is a read-only observer over configured workspace roots. It enumerates run directories under `.orchestrate/runs/` and must not mutate `state.json`, reconcile run status, resume runs, kill processes, or execute workflow control.
  - Monitor event kinds are:
    - `SUSPENDED`: an evaluated authoritative view has an active durable host request; this intentional stop takes precedence over crash classification, regardless of whether a writer still holds the lock.
    - `COMPLETED`: persisted `state.status` is `completed`.
    - `FAILED`: persisted `state.status` is `failed`.
    - `CRASHED`: persisted `state.status` is `running`, and run-local process metadata confirms the original process identity is no longer alive.
    - `STALLED`: persisted `state.status` is `running`, and the active execution cursor heartbeat or fallback `state.updated_at` is older than the configured stale threshold.
    - For evaluated authority (profile `evaluated_execution.v1`) the monitor selects the checked header/program/memo route independently of `state.json`, even when that derived file is missing or malformed. It reconstructs the view with the writer lock (`run.lock`): `CRASHED` is that view's `interrupted` status (no writer holds `run.lock` and the run has not ended), and `STALLED` is not emitted. The state-file, process-identity and heartbeat rules apply only to historical flat-route runs. Malformed evaluated authority surfaces a read error and never falls back to historical state.
  - Freshness classification must prefer the deepest active execution cursor heartbeat, including heartbeats in running reusable call frames, over root `state.updated_at`.
  - A live PID alone is not sufficient process identity. When process identity cannot be confirmed, the monitor must fall back to heartbeat/stale classification rather than suppressing notifications.
  - The notification ledger is external to watched repositories by default and de-duplicates by resolved workspace path, run directory id, and event kind; `SUSPENDED` additionally includes exact `request_id`, so sequential requests notify separately and repeated scans do not. Existing event keys and ledger entries retain their meaning.
  - Email bodies must use bounded run-local log previews, exclude prompt audits and provider-session transport logs by default, and redact configured SMTP secrets plus simple secret-looking key/value lines.
  - v2.2 lowered structured-control nodes appear in snapshots as ordinary top-level entries:
    - branch markers use kind `structured_if_branch`
    - statement join nodes use kind `structured_if_join`
    - join-node `output.error` / `output.artifacts` / `output.debug.structured_if` show selected-branch materialization status
  - v2.6 lowered enum-branching nodes appear in snapshots as ordinary top-level entries:
    - case markers use kind `structured_match_case`
    - statement join nodes use kind `structured_match_join`
    - join-node `output.error` / `output.artifacts` / `output.debug.structured_match` show selected-case materialization status
  - v2.7 structured loop nodes appear in snapshots as ordinary top-level entries with kind `repeat_until`.
    - the loop frame keeps the authored step name
    - `output.artifacts` exposes the latest materialized loop-frame outputs
    - `output.debug.structured_repeat_until` may expose `current_iteration`, `completed_iterations`, `condition_evaluated_for_iteration`, and `last_condition_result`
  - v2.3 status/report snapshots may expose `run.finalization` bookkeeping and render lowered finalization steps as ordinary top-level entries with kind `finally`.
  - When finalization is present, `run.workflow_outputs` stays empty until cleanup completes successfully; failed cleanup reports `workflow_outputs_status: suppressed|failed` in `run.finalization`.
  - v2.5 reusable-call surfaces:
    - outer call steps render as ordinary top-level entries with kind `call`
    - outer call-step results may expose `output.call` metadata including `call_frame_id`, import alias, callee workflow file, bound inputs, export status, and exported-output provenance
    - nested callee execution is persisted under `state.call_frames` without changing the caller-visible outer step key
    - caller-visible exported outputs remain absent until callee body and callee finalization both succeed
    - report/debug surfaces may show secondary provenance for exported call outputs, but the caller-visible producer remains the outer call step

- Reusable-call diagnostics
  - Frontend/build-facing failures should distinguish:
    - unknown import alias
    - caller/callee version mismatch
    - missing required `with:` bindings
    - missing or colliding reusable-workflow write-root bindings
    - source-asset path traversal outside the imported workflow source tree
  - Runtime-facing failures should distinguish:
    - `call_failed` outer-step failures when the callee run fails
    - callee output export contract failures
    - callee finalization failure with exports suppressed
    - call-frame resume/export state when a run is interrupted mid-call

<a id="target-225-trial-observability"></a>

## Target 2.25 Trial Observability (Historical)

The trial executor, its run-owned sidecars and its projections were removed on 2026-11-12. Its
packages are kept at git tag `archive/dead-executors-2026-11-11`; the last tree with the
whole runtime is commit `08cdd59b`. See the
[salvage record](../docs/design/trial_and_adjudication_salvage.md).
`report` and the dashboard refuse a retained trial run with
`workflow_execution_profile_retired`; the old state-only report is kept at the git tag
`archive/retired-run-readers-2026-11-11`.

## Workflow Lisp Judgment Views (Historical)

The read-only judgment views that `report` derived from the old runtime's
state (the `judgment_views` JSON sibling and the Markdown `Judgment views`
section) are removed: they read only runs the retired runtime wrote, which
`report` now refuses. No evaluated producer supplies their inputs. The
contract and its implementation are kept at the git tag
`archive/retired-run-readers-2026-11-11`
(`specs/observability.md` and `orchestrator/workflow/judgment_views.py` there).

## Error Context (shape)

On step failure, record a structured error object similar to:

```json
{
  "error": {
    "message": "Command failed with exit code 1",
    "exit_code": 1,
    "stdout_tail": ["last", "10", "lines"],
    "stderr_tail": ["error", "messages"],
    "context": {
      "undefined_vars": ["${context.missing}"],
      "failed_deps": ["data/required.csv"],
      "substituted_command": ["cat", "data/file_20250115.csv"]
    }
  }
}
```

## Progress and Metrics

- `--progress` renders `[n/N] StepName: Running (Xs)...` and loop progress `[i/total]`.
- State includes: step duration, wait duration, provider time, and file I/O metrics where applicable.

## Evaluated Host-Input Observation (Target 2.40)

Checked program/header and memo own request/report/dashboard meaning. Pending
readers validate complete answer/reply contracts and active lineage against
the checked request site without source compilation, repair or publication.
Missing/stale request view files are harmless; malformed evaluated authority
fails closed rather than falling back to historical readers.

A durable suspension projects `status: suspended` before generic running or
no-writer/interrupted states, even while its publisher holds the lock. No
terminal is appended. `pending_host_input` is the frozen payload plus effect
`identity`, `attempt`, conventional `result_path` and observational
`deadline_elapsed` while a request is suspended; the field is absent otherwise.
It includes exact request ID, rendered question,
answer/reply contracts, evidence paths/hashes and frozen deadline. A deadline
elapsed in wall-clock time is not a committed `EXPIRED` result; only resume
writes expiration. Host answer/cancel commits leave the run `interrupted`,
requiring explicit resume, and committed request effect rows expose typed
`value`, `host_reply` provenance and `host_settlement` attribution. Exact fields
are owned by [State](state.md#evaluated-durable-host-input-target-240).

Reports and dashboard remain read-only and expose no settlement endpoints.
Runtime workflow attribution for Python-authored runs is the retained generated
`.orc` in `workflow_file`; effect/request and reply attribution use the ordinary
evaluated rows. The original Python declaration/line lives in the retained
supplementary `source-map.json` and initial mapped compiler diagnostics, not a
new runtime source-map reader or execution authority.

Monitor `SUSPENDED` email includes request ID, deadline and inspection,
answer/cancel and resume command shapes. It excludes question/evidence bodies,
attestation strings and suspension log previews. The monitor never settles,
expires or resumes the run and uses existing delivery configuration; there is
no notification daemon or selected live-mail acceptance requirement.
