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
  - v2.17 provider-peer-group visits write exact attempt ledgers, member
    evidence, provisional bundles, and terminal group evidence under
    `RUN_ROOT/provider-peer-group/`. These are run-owned evidence, not
    additional workflow results.

- Provider observation (v2.16)
  - Ordinary provider observation is attempted by default at both workflow and
    provider executor boundaries. One private run-scoped tmux server owns
    unique, non-reused panes with a 1:1 invocation-to-pane relationship.
  - Ordinary manager creation, pane allocation, append, health, finalization,
    and teardown failures are best-effort observability failures and cannot
    change provider transport, timeout, metadata, bundle, or result semantics.
  - A `provider_supervision` node's two initial panes are load-bearing until a
    validated supervisor directive is committed to the serialized arbiter.
    Initial allocation failure or pre-directive observation loss fails the
    group and triggers member cleanup. The optional resume-turn pane and
    post-directive mirror/teardown are best effort because they cannot change
    the already selected control path.
  - Session-aware panes mirror normalized assistant text, never raw session
    JSONL. Pane bytes and transcripts are display evidence; parsers and result
    validation continue to consume the authoritative provider transport and
    declared output bundle.
  - Live tmux socket and target values are process-local. They may occur in the
    supervisor's composed prompt and debug prompt evidence but never enter
    workflow values, `state.json`, stable status records, checkpoints, or
    resume selection.

- Provider peer-group evidence (v2.17)
  - The `interactive_terminal_turn_queue.v1` adapter pane owns the actual
    provider client and is part of execution lifecycle, not a writable
    observation pane. Pane text, normalized display text, transcripts, and
    provider stdout/stderr remain non-authoritative views; typed direct-root
    bundle validation is result authority.
  - Each receiver attempt has one append-only
    `injected-messages.jsonl`. A durable header binds the exact group visit and
    receiver attempt even when no messages are sent. Canonical sequenced rows
    record `recorded`, `offered` or `offer_failed`, and
    `receiver_acknowledged` lifecycle events.
  - Ledger claims are intentionally narrow: `recorded` means validation
    passed and the receiver row is durable; `offered` means the exact adapter
    submitted literal input to the exact provider client; and
    `receiver_acknowledged` means the exact receiver returned the message id
    through its ordinary tool channel. No event or report may rename these
    claims as `seen`, `model_seen`, `understood`, or `applied`.
  - Terminal group evidence uses
    `provider_peer_group_terminal_evidence.v1` and reports the exact visit,
    authored-order member attempt identities, terminal member lifecycles,
    ledger digests/counts, frozen bundle digests, natural-shutdown or
    failed-cleanup evidence, endpoint drain/close/worker-join proofs, and
    either a settlement digest or bounded failure.
  - Endpoint paths, endpoint instance ids, opaque sender bindings, tmux
    targets, and live pane/server handles are process-local. They may appear in
    transient runtime diagnostics but never become workflow values, ordinary
    artifacts, stable report fields, checkpoint identity, or resume
    authority. A completed cleanup leaves no endpoint or adapter socket.

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
  - Reports and dashboards may project persisted legacy-run state without
    reopening the recorded workflow source. A non-`.orc` workflow path selects
    state-only compatibility: no authored YAML parsing, source-derived
    structure, or workflow execution is permitted.
  - Dashboard status projection is advisory and read-only: it may expose both persisted `state.status` and dashboard-derived `display_status`, but it must not reconcile stale running state, write `context.status_reconciled_*`, or otherwise mutate `state.json`.
  - The existing `orchestrate report` command may continue to self-heal stale running state when it derives a terminal status; dashboard routes must reuse only pure projection helpers, not the mutating report command path.
  - Dashboard run identity is the resolved workspace root plus the scanned run directory name. `state.run_id` is display metadata and mismatch context only.
  - Dashboard index and detail pages may support an optional `refresh=<seconds>` query parameter using page-level meta refresh. Invalid or out-of-range values are ignored, and refresh support must not add background workers or route-triggered state changes.
  - Dashboard file previews are observability views over existing artifacts and logs only; missing prompt audits, stdout/stderr spill files, provider-session files, and backups are display states rather than run failures.
  - Dashboard summary pages are read-only GUI views over `RUN_ROOT/summaries/index.json`, `RUN_ROOT/summaries/run-summary.md`, and request-time run state. They may link to detailed summary, snapshot, error, provider-session, and transport files through existing run-scoped file routes, but they must not parse summary prose as workflow state or execute recovery/control actions.
  - The dashboard summary live endpoint (`/runs/<workspace_id>/<run_dir>/summaries/live.json`) reports current-step metadata, summary index facts, and generated live-note artifacts when present. It may expose links to generated observability artifacts, but provider calls for live narration belong in runtime-side observers or sidecars, not dashboard page requests.
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
  - Status/report snapshots may expose `run.active_runtime_ms`, `run.active_runtime`, `run.executor_session_count`, `run.current_executor_session`, `run.excluded_suspended_ms`, and `run.suspended_gap_excluded` when executor-session accounting is available.
  - v2.10 status/report snapshots may expose:
    - bounded `provider_attempt_interrupted_rerun` context for a validated
      interrupted provider-session visit; it is a recovery diagnostic, not a
      run-level failure
    - `output.provider_session` step summaries including `mode`, `session_id`, `metadata_path`, and `publication_state`
  - v2.11 adjudicated provider snapshots may expose selected candidate id, selected score or null score, selection reason, run-local score ledger path, workspace-visible score ledger mirror path, promotion status, and adjudication failure type. Candidate workspaces, evaluator packets, and ledgers are observability sidecars, not ordinary artifact lineage.
  - v2.16 provider-supervision snapshots render one outer step with kind
    `provider_supervision`. Its ordinary artifacts are the settlement result;
    debug projection may expose only the selected worker-attempt and directive-
    attempt references plus bounded terminal metadata. Interrupted-visit
    recovery may expose `provider_attempt_interrupted_rerun` plus the discarded
    visit and fresh-visit coordinates, but member panes, targets, provisional
    bundles, and transcripts are not result or resume authority.
  - v2.17 provider-peer-group snapshots render one outer step with kind
    `provider_peer_group`. Its ordinary `output.artifacts` are the settlement
    projection. `output.debug.provider_peer_group` may expose only
    `terminal_evidence_path`, `terminal_evidence_schema_version`, and
    `outcome`; detailed members, ledgers, bundles, and lifecycle proof remain
    in the referenced run-owned evidence. Interrupted-visit recovery may
    expose `provider_attempt_interrupted_rerun` plus the discarded visit and
    fresh-visit coordinates. Message bodies, endpoint/binding handles, pane
    targets, and provisional member values are not stable report or result
    fields.
  - Target-2.23 phased recovery and v2.11 adjudication recovery may expose only
    their bounded named diagnostic, recovery family/mismatch class, and old/new
    visit coordinates. Prompt, candidate, score packet, ledger, and partial
    result content remain sidecar evidence and never report authority.

- Workflow monitor notifications
  - `orchestrator monitor` is a read-only observer over configured workspace roots. It scans `.orchestrate/runs/*/state.json` and must not mutate `state.json`, reconcile run status, resume runs, kill processes, or execute workflow control.
  - Monitor event kinds are:
    - `COMPLETED`: persisted `state.status` is `completed`.
    - `FAILED`: persisted `state.status` is `failed`.
    - `CRASHED`: persisted `state.status` is `running`, and run-local process metadata confirms the original process identity is no longer alive.
    - `STALLED`: persisted `state.status` is `running`, and the active execution cursor heartbeat or fallback `state.updated_at` is older than the configured stale threshold.
  - Freshness classification must prefer the deepest active execution cursor heartbeat, including heartbeats in running reusable call frames, over root `state.updated_at`.
  - A live PID alone is not sufficient process identity. When process identity cannot be confirmed, the monitor must fall back to heartbeat/stale classification rather than suppressing notifications.
  - The notification ledger is external to watched repositories by default and de-duplicates by resolved workspace path, run directory id, and event kind.
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

## Workflow Lisp Judgment Views

- Every JSON report has the exact additive top-level sibling below, including
  runs with no eligible result. The nested object and every row described in
  this section are closed; unknown keys and schema versions fail report
  validation.

  ```json
  {
    "judgment_views": {
      "schema_version": "workflow_judgment_views.v1",
      "judgments": [],
      "matrices": [],
      "disagreements": [],
      "iteration_series": []
    }
  }
  ```

  Markdown reports derive a sibling `Judgment views` section from the same
  validated projection.
- Every judgment coordinate is the closed object with exact fields
  `root_workflow_identity`, `call_frame_path`, `runtime_step_id`,
  `enclosing_step_id`, `enclosing_visit`, and `loop`.
  `root_workflow_identity` is the root state's canonical `workflow_checksum`;
  `call_frame_path` is the exact outermost-to-innermost array of persisted,
  non-empty call-frame IDs; and the step/visit values come from the validated
  provider-attempt scope. `loop` is null or the closed object with exact fields
  `kind`, `step_id`, and `iteration`, where `kind` is `for_each` or
  `repeat_until` and `iteration` is nonnegative. Coordinates are never
  reconstructed from display names, runtime-step spelling, or filesystem
  paths.
- An available judgment is the closed
  `workflow_judgment_inspection.v1` object with exact fields
  `schema_version`, `status: "available"`, `coordinate`,
  `attempt_ordinal`, `result`, and `provenance`.
  - `result` has exactly `declared_shape`, `contract_sha256`,
    `value_sha256`, `value`, and `comparison`.
    `declared_shape` is `root_value`, `record_value`, or `union_value`;
    `value` is the authoritative reached-state value revalidated against the
    exact persisted result contract. `comparison` is null or the closed
    `{kind, value}` object, whose kind is `canonical_value` or
    `union_variant`.
  - `provenance` has exactly `evidence_record_sha256`,
    `identity_schema_version`, `role_sha256`, `final_prompt_sha256`,
    `composition_sha256`, and `comparison`.
    `identity_schema_version` is exact
    `workflow_prompt_attempt_identity.v1`; `role_sha256` has exactly
    `fragment_program`, `resolved_bindings`, `injected_dependencies`,
    `runtime_contributions`, and `provider_policy`; and `comparison` reuses
    the closed Q3 comparison schema and reason set byte-for-byte.
- An unavailable judgment is the closed
  `workflow_judgment_inspection.v1` object with exactly
  `schema_version`, `status: "unavailable"`, `coordinate`, and `reason`.
  Its reason is exactly one of
  `judgment_result_binding_missing`, `judgment_result_binding_invalid`,
  `judgment_result_binding_ambiguous`, `judgment_result_scope_mismatch`,
  `judgment_result_attempt_mismatch`, `judgment_result_evidence_invalid`,
  `judgment_result_contract_mismatch`, `judgment_result_value_mismatch`,
  `judgment_result_coordinate_invalid`, or
  `judgment_view_group_invalid`. Unavailable rows remain ordered members but
  never count as votes.
- Comparison keys are structural. Exact `Bool`, `Int`, `Float`, `String`, and
  enum roots compare by canonical value; unions compare by selected variant
  name. Records, lists, maps, paths, `Value`, and other structured roots have
  no comparison key and are `not_comparable`; their canonical result digests
  remain visible. Conventional field names such as `decision`, `score`, or
  `approved` have no semantic role.
- Rows group only by `(root workflow identity, runtime step ID)`. A closed
  `workflow_judgment_matrix.v1` matrix has exactly `schema_version`, `group`,
  and `members`; `group` has exactly `root_workflow_identity` and
  `runtime_step_id`. Each member has exactly `coordinate`, `status`,
  `comparison`, `result_value_sha256`, `evidence_record_sha256`, and `reason`.
  Its status is:
  - `comparable`, with a non-null comparison, both digests, and null reason;
  - `not_comparable`, with null comparison, both digests, and null reason; or
  - `unavailable`, with null comparison and digests plus one closed Q4 reason.
- Each matrix has one closed `workflow_judgment_disagreement.v1` row with
  exactly `schema_version`, `group`, `status`, `available_member_count`,
  `comparable_member_count`, `not_comparable_member_count`,
  `unavailable_member_count`, and `distinct_comparison_key_count`.
  Classification is total in this order: fewer than two available rows is
  `insufficient_members`; otherwise any available row without a key is
  `not_comparable`; otherwise one distinct key is `agree`; otherwise two or
  more distinct keys is `disagree`. Unavailable members are counted only by
  `unavailable_member_count`. The `disagreements` array has exactly one row per
  matrix in matrix order.
- A closed `workflow_judgment_iteration_series.v1` row has exactly
  `schema_version`, `scope_sha256`, `coordinate`, and `attempts`. Each attempt
  has exactly `attempt_ordinal`, `record_status`, `record_sha256`,
  `comparison`, and `committed_result_status`, reusing Q3's closed record
  status, digest, and comparison contracts. `committed_result_status` is:
  - `bound` only for the one ordinal selected by a fully validated result
    binding;
  - `not_bound` only when another ordinal is validly bound in that scope or
    reached state proves the scope has no committed provider result; or
  - `unknown_pre_q4` for every ordinal when an otherwise-compatible pre-Q4
    reached result has no binding.
  At most one ordinal is `bound`, and the projector never infers a committing
  attempt from the newest record.
- Deterministic order is independent of discovery, filesystem enumeration, and
  provider completion timing. Judgments and matrix members sort by:
  root-workflow-identity bytes; runtime-step-ID UTF-8 bytes; canonical JSON
  UTF-8 bytes of `call_frame_path` using `ensure_ascii=False` and separators
  `(",", ":")`; enclosing-step-ID UTF-8 bytes; enclosing visit; loop kind
  then loop-step-ID UTF-8 bytes with non-loop before loop; loop iteration;
  attempt ordinal with missing before positive; and result-digest bytes with
  missing before present. Matrices sort by their two group coordinates.
  Attempts sort by ascending ordinal; iteration series sort by the full
  coordinate order and then scope-digest bytes.
- State-only and bundle-backed reports use the same
  `orchestrator.dashboard.compiled_workflow.load_persisted_compiled_workflow_surface`
  path, anchored by
  `state.runtime_observability.compiled_frontend.persisted_workflow_surface`,
  to resolve the exact run-bound, content-addressed result contract. They
  produce the same projection without recompiling retained/current source or
  trusting an unbound live bundle. A missing, ambiguous, digest-invalid, or
  coordinate-inconsistent persisted surface makes only the affected judgment
  unavailable.
- Judgment views are pure, read-only, and non-authoritative. Execution,
  resume, workflow parsers, and workflows do not consume them; they cannot
  route, retry, settle, score, promote, or mutate a workflow. Association,
  validation, grouping, ordering, and rendering are deterministic
  runtime/report obligations and add no provider-prompt instruction or input.

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
