# Run Identity and State (Normative)

- Run identification
  - `run_id` format: `YYYYMMDDTHHMMSSZ-<6char>` (UTC timestamp + random suffix)
  - `RUN_ROOT`: `.orchestrate/runs/${run_id}` under WORKSPACE

- State file schema (authoritative record)
  - `schema_version: "2.1"`
  - `run_id`, `workflow_file`, `workflow_checksum`
  - Timestamps: `started_at`, `updated_at`
  - `status`: `running | completed | failed`
  - `context`: key/value map
  - `bound_inputs`: v2.1+ typed workflow inputs bound before execution starts
  - `workflow_outputs`: v2.1+ typed workflow outputs exported after successful workflow completion
  - `finalization`: v2.3+ workflow finalization bookkeeping (`status`, `body_status`, `current_index`, `completed_indices`, `workflow_outputs_status`, optional `failure`)
  - `error`: optional run-level error object for workflow-boundary failures such as output export contract violations
    - provider interruption recovery is not a run-level failure; a validated
      in-flight visit is discarded and re-run under the at-least-once contract
      below
  - `runtime_observability`: optional additive executor-session accounting used only for reports and status projections. It records one session per `run` or `resume` executor process under `executor_sessions[]`, with `session_id`, `entrypoint`, `pid`, optional `process_start_time`, `started_at`, `ended_at`, `status`, and `duration_ms`. Closed session durations contribute to active runtime; gaps between sessions do not.
  - `steps`: map of step results
  - `for_each`: loop bookkeeping: `items`, `completed_indices`, `current_index`
  - `repeat_until`: loop bookkeeping: `current_iteration`, `completed_iterations`, `condition_evaluated_for_iteration`, `last_condition_result`, optional `exhausted`
  - v2.5+ reusable-call fields:
    - `call_frames`: call-frame records keyed by durable `call_frame_id`, with caller step identity, import alias, callee workflow file, bound inputs, body/finalization/export status, current nested execution position, and nested call-frame-local state
  - v1.2+ runtime dataflow fields:
    - `artifact_versions`: `{artifact_name: [{version, value, producer, producer_name?, step_index}, ...]}`
    - `artifact_consumes`: `{consumer_identity: {artifact_name: last_consumed_version}}` with optional `__global__` aggregate entry
    - `private_artifact_versions`: additive executable-private lineage ledger for compiler-classified lowered-only artifacts; same row shape as `artifact_versions`, plus optional stable catalog metadata such as `catalog_ref`
    - `private_artifact_consumes`: additive executable-private freshness ledger for compiler-classified lowered-only artifacts; same shape as `artifact_consumes`
  - v1.8 control-flow fields:
    - `transition_count`: integer count of routed top-level step-to-step transfers
    - `step_visits`: `{step_name: visit_count}` for top-level non-skipped step entries
  - v2.0 identity fields:
    - `steps.<PresentationKey>.step_id`: durable internal identity for the recorded step result
    - `steps.<PresentationKey>.name`: human-facing display name retained for reports and compatibility views
    - `current_step.step_id`: durable identity for the currently running top-level step
    - `current_step.visit_count`: visit ordinal for the in-flight top-level step visit, when the runtime has already incremented `step_visits`
  - v2.10 provider-session observability:
    - canonical visit metadata records live under `.orchestrate/runs/<run_id>/provider_sessions/<step_id>__v<visit>.json`
    - stable masked transport spools live under `.orchestrate/runs/<run_id>/provider_sessions/<step_id>__v<visit>.transport.log`
    - successful fresh session steps may expose `steps.<Step>.debug.provider_session = {mode, session_id, metadata_path, publication_state, ...}`
  - v2.13 managed provider observability:
    - runtime-owned audit and recovery sidecars live under `.orchestrate/runs/<run_id>/managed_jobs/<step-id-or-name>/`
    - managed provider step results may expose `steps.<Step>.managed_jobs = {phase, audit_path, outcome, recovery_status, jobs, ...}`
    - outstanding managed jobs leave the provider step in a resumable recovery state so `resume <run_id>` re-enters recovery without relaunching the provider
  - v2.17 provider-peer-group evidence:
    - visit metadata lives under
      `.orchestrate/runs/<run_id>/provider-peer-group/<encoded-node>/visit-metadata/<visit>.json`
    - exact member attempt records live under
      `.orchestrate/runs/<run_id>/provider-peer-group/<encoded-node>/visits/<visit>/members/<member>/attempt-<ordinal>/`
    - terminal group evidence lives at the corresponding
      `visits/<visit>/evidence.json`
  - v2.14 declared resource-transition sidecars:
    - runtime-native resource/state transitions may own private generated `resource_state` documents outside `state.json`; native documents carry `transition_schema_version`, a runtime version token, resource identity metadata, and the typed resource state payload
    - resource transitions may also own append-only private generated `transition_audit` JSONL ledgers; audit rows record committed, replayed, rejected, and partial-failure outcomes together with idempotency evidence and request digest
    - resume/replay for declared resource transitions keys off audit-ledger idempotency evidence (`transition_schema_version`, idempotency key, request digest) rather than blindly reapplying the transition body
  - v2.2 structured-control additions:
    - lowered branch markers and lowered branch-body steps are recorded as ordinary top-level step entries under presentation keys such as `RouteReview.then` and `RouteReview.then.WriteApproved`
    - the lowered join node keeps the authored statement presentation key (for example `RouteReview`) and materializes branch outputs there
  - v2.6 structured enum-branching additions:
    - lowered case markers and lowered case-body steps are recorded as ordinary top-level step entries under presentation keys such as `RouteDecision.APPROVE` and `RouteDecision.APPROVE.WriteApprovedAction`
    - the lowered join node keeps the authored statement presentation key (for example `RouteDecision`) and materializes case outputs there
  - v2.7 structured looping additions:
    - `steps.<RepeatUntilStatement>` stores the loop-frame result and latest materialized loop outputs
    - `steps.<RepeatUntilStatement>[i].<StepName>` stores one iteration's nested step result using qualified per-iteration `step_id` ancestry
    - `repeat_until.<RepeatUntilStatement>` persists `current_iteration`, `completed_iterations`, `condition_evaluated_for_iteration`, `last_condition_result`, and optional `exhausted` for resume/debug
  - v2.3 finalization additions:
    - lowered finalization steps are recorded as ordinary top-level step entries under presentation keys such as `finally.ReleaseLock`
    - `finalization.workflow_outputs_status` records whether workflow outputs are `pending`, `completed`, `failed`, `suppressed`, or `not_configured`
    - workflow outputs remain `{}` until finalization succeeds
  - v2.5 reusable-call additions:
    - `call_frames` persist nested execution state for inline `call` steps under schema `2.1`.
    - callee-private `artifact_versions` / `artifact_consumes` and additive `private_artifact_versions` / `private_artifact_consumes` remain inside the call-frame-local nested state rather than leaking bare artifact names into the caller-global ledger.
    - caller-visible exported output provenance remains attached to the outer call step result and any published outer-step lineage entries.

- Step status semantics
  - Step `status`: `pending | running | completed | failed | skipped`.
  - `when` false → `skipped` with `exit_code: 0` and no process execution.
  - Step results may include `output`, `lines`, `json`, `text`, `error`, `debug`, and `artifacts`.
  - Step results may include `name` and `step_id`; the presentation key in `steps` remains compatibility-oriented, while `step_id` is the durable lineage/resume identity.
  - Step results for top-level steps may include `visit_count`, meaning the visit ordinal of the recorded completed/skipped/failed result stored at that presentation key.
  - Resume uses persisted state only to choose the initial top-level restart point. After the executor reaches that point, repeated visits to the same top-level step name follow normal control flow and are not auto-skipped solely because an earlier visit completed.
  - v1.6 step results may also include normalized `outcome`:
    - `status`: `completed|failed|skipped`
    - `phase`: `pre_execution|execution|post_execution`
    - `class`: normalized failure/success classification (for example `completed`, `assert_failed`, `command_failed`, `provider_failed`, `timeout`, `contract_violation`, `pre_execution_failed`)
    - `retryable`: boolean
  - `artifacts` is a map of typed values parsed from `expected_outputs` and is available at `steps.<Step>.artifacts` when `persist_artifacts_in_state` is not set to `false`.
  - v2.10 fresh provider-session steps publish their runtime-owned session handle on that same `steps.<Step>.artifacts.<publish_artifact>` surface only after the exact visit's atomic state finalization succeeds.
  - v1.7 `set_scalar` / `increment_scalar` reuse that same `steps.<Step>.artifacts` surface for local produced scalar values; successful publication still advances `artifact_versions` only through `publishes.from`.
  - v1.8 cycle-guard failures use `error.type: "cycle_guard_exceeded"` with `outcome.phase: "pre_execution"` and `outcome.class: "pre_execution_failed"`.
  - Tasks 1-5 of the DSL evolution roadmap were additive under schema `1.1.1`; v2.0 is the explicit stable-ID migration boundary.
  - Resume from pre-v2.0 state is rejected unless a dedicated upgrader is introduced in a later tranche.
  - v2.1 workflow signatures append `bound_inputs` / `workflow_outputs`; the later v2.5 reusable-call tranche moves the top-level schema to `2.1`.
  - v2.2 structured `if/else` also reuses schema `2.0`; lowered branch markers/join metadata are additive `steps.*` payload fields rather than a new schema boundary.
  - v2.6 structured `match` also reuses schema `2.0`; lowered case markers/join metadata are additive `steps.*` payload fields rather than a new schema boundary.
  - v2.3 structured finalization also reuses schema `2.0`; finalization bookkeeping and lowered `finally.*` step entries are additive fields.
  - v2.5 reusable `call` is the schema boundary that moves state to `2.1`, because bare artifact-name ledgers cannot preserve callee-private lineage or freshness safely.
  - v2.7 `repeat_until` extends schema `2.1` additively; loop-frame bookkeeping lives under the new top-level `repeat_until` map.
  - v2.13 managed provider jobs extend schema `2.1` additively; managed recovery metadata lives on the step result and run-owned sidecars rather than the artifact lineage surfaces.

- Output contract failure shape
  - If `expected_outputs`, `output_bundle`, or another deterministic structured
    output contract fails validation after a successful execution
    (`exit_code: 0`), the step is marked failed with:
    - non-zero `exit_code` (currently `2`)
    - `error.type: "contract_violation"`
    - `error.context.violations: []` describing individual contract violations

- Loop state representation
  - Per-iteration indexing: `steps.<LoopName>[i].<StepName>` stores step results for each iteration.
  - These indexed keys are presentation views. v2.0 lineage/freshness bookkeeping uses the qualified `step_id` embedded in each result payload (for example `root.loop_publish#0.produce_in_loop`).

- State integrity
  - Atomic writes: write temp file then rename.
  - Include workflow checksum to detect modifications.
  - On corruption: `resume --repair` attempts recovery from latest valid backup; `resume --force-restart` creates a new run.
  - Provider attempts are at-least-once. After all ordinary source, checksum,
    projection, bound-input, checkpoint, and completed-result guards pass, an
    exact interrupted in-flight visit is discarded and re-run; malformed,
    ambiguous, or checksum-incompatible state still fails closed.

- State backups and cleanup
  - When `--backup-state` is enabled or `--debug` is set, copy `state.json` to `state.json.step_<Step>.bak` before each step (keep last 3).
  - `clean --older-than <duration>` removes old run directories (see `cli.md`).

- Logs directory (see `observability.md`)
  - `logs/` contains `orchestrator.log`, `StepName.stdout` (when large or parse error), `StepName.stderr` (when non-empty), and optional debug artifacts.

## Provider-Call Policy Identity And Resume

- Present Workflow Lisp provider-call policy is execution input. Authored
  `:model`, `:effort`, and `:timeout-sec` syntax and the resulting executable
  provider-step fields participate in the existing authored-source, build,
  program, and workflow-checksum identity surfaces. Adding, removing, or changing
  a keyword or binding expression is program drift, not report, debug, or
  source-map-only drift.
- Runtime model/effort values remain ordinary bound workflow/procedure inputs and
  are governed by existing bound-input, checkpoint, and completed-boundary reuse
  validation. Timeout remains ordinary `timeout_sec`; no second timeout or state
  path is introduced.
- Public `.orc` resume rebuilds the candidate through the ordinary frontend build
  path before applying source/build/program identity, root and callee workflow
  checksum, bound-input, checkpoint, call-frame, and provider-step guards.
  Unchanged policy may reuse a completed provider boundary only through those
  normal guards. Changed policy is rejected; resume may not patch old state,
  ignore the difference, or manufacture a compatibility alias.
- Provider registry/template drift remains operational configuration and is not
  newly checksum-bound. No checksum exception, identity remap, migration upgrader,
  or family/provider-name special case is authorized by this policy surface.
- State, compiled Core/executable provider configuration, and existing identity
  guards remain authoritative. Runtime plans, semantic/runtime reports,
  dashboards, debug YAML, and source maps may describe the call but are not
  policy or resume authority.

## Provider Prompt-Dependency Attempt State And Resume

- Provider attempts are at-least-once across ordinary, session, supervision,
  peer-group, and phased provider execution. An exact interrupted in-flight
  visit is marked `interrupted` where truthful evidence is available, its
  partial result authority is discarded, and ordinary dispatch allocates a
  fresh attempt. The runtime emits the named operator-visible diagnostic
  `provider_attempt_interrupted_rerun` exactly once before re-paying the
  provider call. Provider prompts do not carry this runtime obligation.
- A Workflow Lisp provider boundary with a typed prompt-dependency contract
  allocates its attempt ordinal in root `RunState.provider_attempt_allocations`.
  The member is omitted while empty. It is root-owned across ordinary, loop,
  call-frame, phased, supervision, peer-group, and adjudicated execution;
  nested state managers do not maintain competing counters.
- Each allocation entry is a plain monotonic counter: its closed current form
  contains the exact scope plus `last_allocated_ordinal`, and a Q3-bound scope
  additionally retains its existing optional
  `prompt_fragment_identity_schema_version` authority. The current form never
  contains lifecycle events. One exclusive run-lifetime lock serializes all
  state writers for `run` or `resume`; inside it, an in-process lock increments
  the counter and the ordinary atomic state writer persists it. A discarded
  ordinal and any partial attempt directory are never reused for different
  execution content. Historical lifecycle-event lists may be read only to
  derive the same counter and are omitted by the next write; evidence paths and
  records never allocate an ordinal.
- The provider lexical checkpoint identity includes the typed dependency
  contract, including required/optional partition, position, and instruction.
  Changing that contract is incompatible program input. Mutable file-content
  digests observed by one attempt are not automatic invalidation input for a
  compatible completed result.
- Pending or failed execution allocates a new attempt and takes a fresh
  immutable dependency snapshot. Compatible completed-result reuse returns the
  committed structured result without reopening dependency files.
- Workflow Lisp attempt records are content-free evidence views derived from
  the immutable in-memory snapshot. They do not contain dependency bodies or
  prompt text and are not provider selection, execution, checkpoint, or resume
  authority. They are best-effort audit evidence: absence, truncation, or an
  incomplete record after interruption does not fail recovery. Runtime does
  not enumerate or validate earlier records when resuming.
- A terminal-only offline validator may derive a content-addressed validated
  index from a frozen authoritative allocation projection and immutable record
  digests. That index is reproducible, non-authoritative evidence; runtime and
  resume never read it. A later authoritative state change makes an older
  index stale rather than changing runtime behavior.
- Compatible completed-result reuse remains authoritative and returns the
  committed structured result without invoking the provider. At-least-once
  discard-and-rerun applies only to a validated in-flight visit. Missing,
  malformed, ambiguous, foreign, or checksum-incompatible state still fails
  closed before any provider launch.
- The Provider-Isolation Bundle-Transfer Journal section is not amended by this
  contract pivot. Its transfer reconciliation and implementation remain
  unchanged until the separately owner-gated ML-3 tranche; recovery may not
  discard or bypass isolation-transfer authority.

## Workflow Lisp Prompt Fragment Attempt State And Resume

- A target-2.20 fragment-backed provider boundary uses the same root-owned,
  monotonic provider-attempt allocation as typed prompt dependencies. Its
  compiler dependency contract has origin `workflow_lisp_prompt_fragment`;
  even a fragment with no document slots allocates and publishes an explicit
  prompt snapshot for the receiving attempt.
- The provider lexical checkpoint and executable provider configuration retain
  the paired `CompilerPromptFragmentContract` and
  `compiled_prompt_fragment_identity`. Construction, bundle validation, and
  pre-provider preparation reject an absent, malformed, or mismatched pair and
  reject disagreement with the Semantic IR carrier.
- The receiving attempt publishes one closed
  `workflow_prompt_fragment_snapshot.functional.v1` record with
  `record_kind: prompt_snapshot`. It extends the established functional
  prompt-dependency record with the required fragment identity while retaining
  the schema-2.1 allocator projection, immutable publication, and terminal
  validation owners. Extern-backed dependency records remain byte-compatible
  and do not acquire a fragment identity.
- Compatible completed-result reuse validates the ordinary source, program,
  call-frame, bound-input, lexical-checkpoint, and completed-boundary guards,
  then returns the committed structured result without reopening document
  fills or re-executing the provider. Missing or changed fragment carriage is
  incompatible program state, not a reason to reuse or reconstruct evidence.
- Runtime and resume do not read prompt snapshot evidence or its offline index.
  The record contains digests and closed attempt/compiler metadata, not
  semantic result authority. Schema 2.1 state remains authoritative; the
  fragment snapshot adds no state field, alternate checkpoint, or recovery
  channel.

## Target 2.21 Prompt Output-Position Attempt State And Resume

- A fragment application containing `:out` retains the paired
  `compiled_prompt_fragment_identity.v2` and
  `compiler_prompt_fragment_contract.v2` through Semantic IR, Executable IR,
  persisted configuration, lexical checkpoint, and runtime preparation.
- The carrier's declaration-ordered
  `output_positions[*].expected_output` objects must equal the provider
  configuration's `expected_outputs` rows exactly. Missing, extra, reordered,
  malformed, v1/v2-mixed, or unequal carriage is incompatible program state
  and fails before provider preparation.
- After a successful provider process, the output-position contract and the
  one prompt-owned structured-result contract validate into local mappings.
  The step commits neither mapping until both succeed, then merges the
  disjoint maps into one ordinary step-artifact update.
- Compatible completed result reuse applies the existing source, root,
  call-frame, bound-input, checkpoint, and completed-boundary guards and
  returns the committed result without a second provider call. Identity or
  projected-contract drift is ordinary program drift. Runtime does not reopen
  the output file or reconstruct the v2 carrier from current source.
- Target-2.20 Q1 applications retain exact v1 identity/carrier bytes,
  snapshot evidence, runtime behavior, and compatible completed result reuse.
  This additive contract does not change state schema `2.1` or create another
  result, artifact, checkpoint, snapshot, or recovery channel.

## Target 2.22 Prompt-Attempt Identity State And Resume

- The optional identity-version and compiler binding-plan carriers participate
  in ordinary target-2.22 program/configuration and lexical-checkpoint
  compatibility. A direct fragment-backed target-2.22 boundary requires the
  exact pair through persisted provider configuration and `RuntimeStep`.
- The root-owned counter-only provider-attempt allocation remains the sole
  ordinal authority. Each successfully prepared attempt writes one closed
  `workflow_prompt_fragment_snapshot.functional.v2` before launch. A provider
  policy that cannot be prepared publishes the closed Q3 preparation-failure
  record; failed publication leaves an ordinary allocation-only gap.
- The v2 snapshot retains and validates the complete v1 projection, then adds
  the five-role attempt identity with exact cross-field equality for final
  prompt, compiled fragment, document rows, shown groups, and injection.
  Content sealing and report-time loading both fail closed on a
  malformed, open, tampered, or mismatched record.
- Attempt identity records, role digests, comparisons, and `prompt_context`
  reports are non-authoritative. Compatible completed-result reuse uses the
  existing source, root, call-frame, bound-input, checkpoint,
  result-contract, and completed-boundary guards without reading Q3 evidence.
  A pending or failed boundary allocates a fresh attempt and evidence record.
- Target-2.20/2.21 state, checkpoints, functional-v1 evidence, and reuse stay
  byte-compatible. Q3 does not change state schema `2.1`.

## Workflow Prompt-Attempt Result Binding State And Resume

- State schema `2.1` is unchanged. A newly executed provider result that
  satisfies the complete ordinary identity-v1 eligibility predicate in
  `providers.md` carries one runtime-owned
  `StepResult.debug.prompt_attempt_result_binding`. The member is optional at
  the state-schema level so ineligible and pre-Q4 results remain valid, but it
  is required for every newly executed eligible result. The closed locator has
  exactly these fields:
  - `schema_version`:
    `workflow_prompt_attempt_result_binding.v1`;
  - `scope_sha256`: the canonical key of the root-owned provider-attempt
    scope;
  - `attempt_ordinal`: the positive ordinal of the successful attempt;
  - `evidence_relative_path`: the deterministic scope-and-ordinal
    run-relative evidence path;
  - `evidence_file_sha256`: the canonical digest of those exact evidence
    bytes; and
  - `record_kind`: exact `prompt_snapshot`.
  Other independently owned `debug` members remain admissible, but the closed
  locator admits no additional field and contains no result, prompt, role,
  score, provider-output, or report data.
- Runtime constructs the locator from the retained in-memory publication result
  only after the provider result and every
  prompt output-position and structured-result contract have passed the
  unchanged state-atomic Q2 validation boundary in `io.md`, and after the
  evidence path and digest agree with the retained scope and successful attempt
  ordinal. It attaches the locator to that same result dictionary before the
  normal reached-state commit. Top-level, call-frame, and generated loop-step
  persistence therefore commit the validated result, its artifacts, and its
  locator in the same state mutation; there is no separate result-commit
  event or second persistence authority.
- A failure before that reached-state mutation commits no binding. If the
  state mutation fails, neither the reached result nor its locator is
  available at that boundary. A completed-boundary resume reuses the
  co-persisted result and locator through the ordinary compatibility guards
  without preparing a provider or reopening evidence.
- The locator is optional, non-authoritative debug state and does not
  participate in source, program, checkpoint, result-contract, or
  completed-boundary compatibility. A compatible pre-Q4 completed result
  without it remains loadable and reusable. Its judgment view reports the
  association as unavailable; runtime and reporting never backfill the
  locator, select the last attempt, or make missing or damaged evidence
  invalidate that completed result.

## Target 2.23 Phased Contract Delivery State And Resume

- Phased delivery remains on state schema `2.1`. Persisted provider
  configuration and lexical checkpoint configuration carry the ordinary
  provider call policy extended by exact `delivery` and
  `materialization_attempts`, the exact
  `workflow_prompt_attempt_identity.v2` selection, and the retained
  `compiler_prompt_attempt_binding_plan.v1`. Missing, extra, downgraded, or
  unequal carriers fail closed before provider preparation and during
  checkpoint/completed-boundary compatibility validation.
- Runtime evidence and report surfaces form a separate version-closed family:
  `workflow_prompt_attempt_composition.v2`,
  `workflow_prompt_attempt_provider_policy.v2`,
  `provider_phased_protocol_frame.v1`,
  `workflow_prompt_fragment_snapshot.functional.v3`,
  `provider_phased_candidate_digest_manifest.v1`,
  `provider_phased_delivery_diagnostic.v1`, and
  `workflow_prompt_context_report.v2`. They are validated evidence or report
  schemas, not persisted provider-configuration/checkpoint carriers and not
  workflow-state authority. Missing, malformed, downgraded, or mixed-version
  evidence fails its owning validation boundary closed.
- Identity v2 preserves canonical-composed identity separately from its exact
  ordered `actual_deliveries`. A requested or offered turn is not an actual
  delivery until its durable receipt proves delivery. Functional-v3 evidence
  is content-free and validates this distinction; it never stores prompt,
  candidate, result, submit, command, or environment bytes.
- `workflow_prompt_context_report.v2` projects validated v1 attempts through
  nullable `legacy_final_prompt_sha256` and validated v2 attempts through
  `canonical_composed` plus ordered `actual_deliveries`. Comparison is
  version-strict and may report `actual_delivery_drift`; it never substitutes
  canonical composition for a delivered prompt. Reports remain
  non-authoritative.
- Each phased attempt owns one append-only
  `provider_prompt_phase_ledger.v1` JSONL sidecar. Its header is sequence zero,
  subsequent events are contiguous, and terminal rows close the grammar.
  Offline validation reads only ledger bytes and returns a closed validation
  status. The ledger, its digests, candidate manifests, diagnostics, receipts,
  and terminal events are evidence only and cannot satisfy a result,
  checkpoint, route, retry, or resume guard.
- Provider output positions and the structured result publish in one guarded
  state commit only after the candidate is jointly valid, frozen, naturally
  closed, restored, and verified. No provisional artifact map, bundle value,
  lineage row, success state, or route value enters authoritative state.
- Compatible completed-boundary reuse validates ordinary source, root,
  call-frame, bound-input, checkpoint, result-contract, completed-state, and
  persisted completed-boundary event invariants. It does not open the phase
  ledger, candidate files, or attempt-evidence records and does not reconstruct
  evidence from current source.
- An interrupted nonterminal phased visit is detected from authoritative
  `current_step` state. After ordinary guards validate the exact visit, its
  partial ledger/candidate authority is discarded and the whole phased visit
  re-enters at the task turn with a fresh attempt and
  `provider_attempt_interrupted_rerun`. Same-attempt materialization-only retry
  remains unchanged. Missing, malformed, conflicting, or ambiguous
  authoritative state needed to classify the boundary fails closed; missing
  or torn evidence alone does not.

## Workflow Lisp Typed Prompt-Input Evidence

- Each provider invocation's prompt composition returns one closed, validated
  evidence row for every lowered typed prompt input. Rows bind the input name,
  structural type/kind, renderer id/version, source-map origin, value digest,
  and rendered-byte digest.
- Evidence contains no raw typed value, prompt text, producer bundle, or bundle
  path authority. It is an audit view; authoritative typed values remain in
  ordinary step state and results.
- Evidence cardinality must exactly match the lowered binding set. Missing,
  duplicate, extra, reordered, or mismatched rows fail before provider launch.
- Root and nested calls write through the aggregate run-local diagnostic owner.
  Persistence is additive under state schema `2.1`; it adds no state field,
  attempt ledger, routing input, checkpoint input, or resume authority.

## Provider-Isolation Bundle-Transfer Journal

- Every published isolated workflow-provider bundle has one controller-owned,
  canonical `provider_isolation_bundle_transfer.v1` journal at the deterministic
  path for its exact provider-attempt `scope` and positive `ordinal`. The
  packaged schema is recursively closed. Its base fields are
  `schema_version`, `state`, `invocation_identity`, `scope`, `ordinal`,
  `staged_identity`, `target_identity`, `bundle_digest`, and `bundle_size`.
  Each file identity binds a bounded path plus device, inode, and mount ID; all
  digests are exact lowercase `sha256:` identities. `bundle_size` is bounded by
  `16777216`, and numeric identity fields and the ordinal are bounded unsigned
  64-bit integers.
- Journal state advances monotonically through the closed set `prepared`,
  `published`, `validated`, `rotation_pending`, and `rotated`. Exact replay of
  the current bytes is idempotent. State regression, state skipping, a changed
  immutable field, unknown field or state, conflicting duplicate, or
  scope/ordinal/invocation mismatch is
  `provider_isolation_bundle_broker_failed`.
- `prepared` and `published` contain no validation or archive fields.
  `validated` and every later state require `contract_digest` and the exact
  `validation_disposition: valid|invalid`. A `valid` disposition additionally
  requires `normalized_value_digest`; `invalid` forbids that field.
  `rotation_pending` and `rotated` are valid only for an `invalid` disposition
  and require `archive_identity`. Earlier states forbid `archive_identity`.
- Durability ordering is fixed:
  1. The broker writes and fsyncs the deterministic same-filesystem staged
     file, then atomically writes and fsyncs `prepared` with the exact staged
     and target identities, bundle digest, and size.
  2. It atomically renames the staged file to the canonical target, fsyncs the
     destination directory, revalidates the target identity and bytes, then
     atomically replaces and fsyncs the journal as `published`. Before
     returning success it reconciles that durable journal and target again.
  3. The existing typed validator may run idempotently over the immutable
     target and declared contract. Exactly one validation disposition is
     atomically written and fsynced as `validated`.
  4. An invalid result advances to and fsyncs `rotation_pending`, atomically
     renames the canonical target to the deterministic archive, fsyncs the
     containing directory, and atomically advances and fsyncs `rotated`.
- Recovery validates the journal, exact file identities, digest, size, and
  locations before mutation:
  - With no journal, staged, canonical, and archive paths must all be absent. An
    unexplained file fails closed.
  - `prepared` with only the exact staged file completes the canonical rename.
    `prepared` with only the exact canonical file advances to `published`.
    Both or neither location fails closed.
  - `published` requires only the exact canonical target. If no durable
    validation outcome exists, the idempotent validator may run again, but only
    one exact `validated` outcome may be persisted.
  - `validated(valid)` requires only the exact canonical target and never
    rotates it. `validated(invalid)` requires only the exact canonical target
    and may advance only to `rotation_pending`.
  - `rotation_pending` with only the exact canonical target completes the
    archive rename. With only the exact archive it advances to `rotated`. Both
    or neither location fails closed.
  - `rotated` requires only the exact archive; staged and canonical locations
    must be absent.
- Any wrong path, byte digest, size, device, inode, mount ID, illegal
  state/location combination, duplicate location, journal-byte change, or
  pre-existing target/archive not explained by the same scope and ordinal fails
  closed without unlinking, overwriting, or selecting one location by
  preference. A positive caller acknowledgement while the journal is
  `validated(invalid)` authorizes the broker to begin rotation; it is not retry
  authorization. The result must then reach `rotated` before the caller may
  authorize retry and before a new attempt can use the canonical target.
- Symlink or mount ancestry, and any product-visible symlink/hardlink alias of
  a staged, canonical, or archive authority, fails before transfer or
  reconciliation mutation.
- Missing, broker-rejected, and noneligible outcomes create no transfer journal:
  the journal explains canonical file movement only. A controller attempt with
  `result_channel: "none"` likewise has no bundle journal. The attempt owner,
  not the journal, remains responsible for execution eligibility, typed-value
  publication, retry authorization, and lifecycle closure.
- This sidecar contract does not itself add public executor/resume lifecycle
  state, atomically commit the validated value into `state.json`, or publish or
  finalize isolation attestation. Those integrations must not be inferred from
  a valid transfer journal.

## Provider-Supervision State And Resume (v2.16)

- State schema remains `2.1`. One running supervision group owns one ordinary
  live cursor whose `current_step` has `type: "provider_supervision"`, the
  generated step id, status `running`, and its visit count. The group is one
  atomic workflow step; its members do not publish independent workflow
  results or checkpoints.
- The group visit is not a provider attempt. Worker-fresh and
  supervisor-directive invocations each allocate a distinct root-owned
  root-owned provider-attempt ordinal; `STEER` allocates a third ordinal for
  the worker resume turn only after the prior boundary is validated. Attempt
  scopes are derived from group step id, visit, member id, and turn ordinal.
- Visit evidence lives below
  `provider-supervision/<encoded-node>/visits/<visit>/`. Its
  `metadata.json` progresses from pending/running evidence to a terminal
  disposition such as `committed_terminal_result`; provisional member bundles
  and transcripts remain secondary evidence. A completed node exposes only
  the selected worker-attempt and directive-attempt references in debug state,
  not member values or live targets as competing state authorities.
- The coordinator alone commits the validated settlement result, artifact and
  dataflow publications, terminal step result, selected-attempt references,
  and exact matching `current_step` clearance as one state transaction.
- If ordinary resume finds a matching running supervision visit without that
  visit's terminal group result, it first applies every ordinary integrity and
  projection guard. It then marks available visit evidence `interrupted`,
  clears only the exact matching `current_step`, preserves older terminal
  results, emits `provider_attempt_interrupted_rerun`, and enters a fresh group
  visit through ordinary dispatch. No member session, attempt, pane, or
  provisional result from the interrupted visit is reused.
- A mismatched or malformed supervision cursor/visit relationship fails with
  `provider_supervision_resume_state_integrity_error`. Ordinary resume never
  reuses an interrupted visit's member sessions. Existing root, callee,
  checkpoint, and projection-integrity guards remain unchanged.

## Provider-Peer-Group State And Resume (v2.17)

- State schema remains `2.1`. One running peer group owns one ordinary live
  cursor whose `current_step` has `type: "provider_peer_group"`, the generated
  step id, status `running`, and its visit count. The group is one atomic
  workflow step; members, messages, ledgers, and endpoints do not publish
  independent workflow results or checkpoints.
- The group visit is not a provider attempt. Every member allocates one
  distinct root-owned provider-attempt ordinal in authored order
  before member launch. Attempt scopes derive from the group step identity,
  visit, and member id. A peer group has no member resume turn and no
  fresh-to-resume attempt transition.
- The runtime preflights the complete visit root before allocation and the
  exact attempt-qualified path set after allocation. Each member attempt owns
  one immutable prompt-dependency snapshot, one append-only
  `injected-messages.jsonl` ledger with a durable header even when empty, one
  member terminal `evidence.json`, and one `provisional-result.json`.
  Preimages, collisions, missing identities, and authored-order/path-set
  mismatches fail closed.
- Receiver ledgers contain canonical monotonically sequenced `recorded`,
  `offered` or `offer_failed`, and `receiver_acknowledged` rows. Their terminal
  summaries bind the exact receiver attempt, canonical digest, row count, and
  lifecycle counts. Message content stays in the receiver ledger; it is not
  copied into `state.json`, result artifacts, Semantic IR, checkpoint
  identity, or prompt-dependency snapshots.
- Terminal group evidence uses
  `provider_peer_group_terminal_evidence.v1`. Completed evidence binds the
  exact visit, authored-order member attempts, each member's terminal
  lifecycle, ledger summary, frozen-bundle digest, complete natural-shutdown
  proof, endpoint drain/close/worker-join proofs, and settlement digest. Failed
  evidence has no settlement digest, carries a bounded failure code/message,
  and records available failed-cleanup proof instead of reclassifying forced
  cleanup as natural completion.
- On successful settlement, `steps.<Step>.artifacts` contains only the
  validated settlement projection. When the coordinator can close terminal
  group evidence, `steps.<Step>.debug.provider_peer_group` contains only the
  run-root-relative terminal evidence path, terminal evidence schema version,
  and `completed|failed` outcome. Endpoint paths/bindings, pane targets,
  message bodies, provisional member values, and member bundle paths are not
  competing state or resume authorities.
- For a reportable terminal group, the coordinator alone commits the validated
  settlement (when successful), ordinary artifact/dataflow publications,
  terminal step result, bounded evidence reference, and exact matching
  `current_step` clearance as one state transaction. Any
  member/protocol/delivery/bundle/settlement/endpoint/cleanup failure publishes
  no settlement. A startup cleanup failure that cannot truthfully construct
  complete terminal peer evidence propagates after cleaning all known
  resources; it must not fabricate a terminal evidence record.
- If ordinary resume finds a matching running peer-group visit without that
  visit's terminal group result, it first applies every ordinary integrity and
  projection guard. It then preserves partial ledgers as audit-only evidence,
  marks available visit evidence `interrupted`, clears only the exact matching
  `current_step`, emits `provider_attempt_interrupted_rerun`, and enters a
  fresh group visit through ordinary dispatch. No member attempt, endpoint,
  pane, bundle, provisional result, or settlement from the interrupted visit
  is reused.
- A mismatched or malformed peer-group cursor/visit relationship fails with
  `provider_peer_group_resume_state_integrity_error`. Ordinary resume never
  reuses an interrupted visit's attempts, endpoint, panes, bundles, or ledgers.
  Root/callee checksums, lexical checkpoint validation, and
  projection-integrity guards remain unchanged.

## Reusable-Call State Contract (v2.5)

- Caller-visible exports
  - Declared callee outputs materialize only on the outer call step as `steps.<CallStep>.artifacts.<name>`.
  - When an exported call output enters caller-visible lineage, the outer call step is the external producer identity.
  - The callee-internal `outputs[*].from` origin is preserved as secondary provenance/debug metadata and does not masquerade as the caller-visible producer.

- Callee-private lineage
  - Callee-private artifact names must not occupy bare names in the caller-global artifact ledger.
  - Internal publish/consume state, including additive executable-private ledgers, lives inside the call-frame-local state snapshot instead of the caller-global ledgers.
  - `since_last_consume` freshness inside a call frame is therefore enforced against the callee-private ledgers persisted under that frame.

- Resume boundary
  - Because call frames add new durable lineage and resume keys, resume from pre-`schema_version: "2.1"` state is rejected unless a tested upgrader ships with the same tranche.

## State File Schema (example)

The state file (`${RUN_ROOT}/state.json`) is the authoritative record of execution:

```json
{
  "schema_version": "2.1",
  "run_id": "20250115T143022Z-a3f8c2",
  "workflow_file": "workflows/pipeline.yaml",
  "workflow_checksum": "sha256:abcd1234...",
  "started_at": "2025-01-15T14:30:22Z",
  "updated_at": "2025-01-15T14:35:47Z",
  "status": "running",
  "context": { "key": "value" },
  "bound_inputs": {
    "max_cycles": 4
  },
  "workflow_outputs": {},
  "artifact_versions": {
    "execution_log": [
      {
        "version": 1,
        "value": "artifacts/work/latest-execution-log.md",
        "producer": "ExecutePlan",
        "step_index": 2
      }
    ]
  },
  "artifact_consumes": {
    "ReviewImplVsPlan": {
      "execution_log": 1
    },
    "__global__": {
      "execution_log": 1
    }
  },
  "private_artifact_versions": {
    "context_docs": [
      {
        "version": 1,
        "value": ["docs/design/state-layout.md"],
        "producer": "CollectContext",
        "step_index": 1,
        "catalog_ref": "context_docs"
      }
    ]
  },
  "private_artifact_consumes": {
    "ReviewImplVsPlan": {
      "context_docs": 1
    },
    "__global__": {
      "context_docs": 1
    }
  },
  "transition_count": 3,
  "step_visits": {
    "ExecutePlan": 1,
    "ReviewPlan": 2
  },
  "steps": {
    "StepName": {
      "status": "completed",
      "name": "StepName",
      "step_id": "root.step_name",
      "exit_code": 0,
      "started_at": "2025-01-15T14:30:23Z",
      "completed_at": "2025-01-15T14:30:25Z",
      "duration_ms": 2145,
      "output": "...",
      "truncated": false,
      "debug": {
        "command": ["echo", "hello"],
        "cwd": "/workspace",
        "env_count": 42
      },
      "artifacts": {
        "plan_path": "docs/plans/plan-a.md",
        "review_score": 82
      }
    }
  },
  "for_each": {
    "ProcessItems": {
      "items": ["file1.txt", "file2.txt"],
      "completed_indices": [0],
      "current_index": 1
    }
  },
  "repeat_until": {
    "ReviewLoop": {
      "current_iteration": 2,
      "completed_iterations": [0, 1],
      "condition_evaluated_for_iteration": 1,
      "last_condition_result": false,
      "exhausted": false
    }
  }
}
```

## State Integrity and Recovery

Corruption detection and backups:
- Include `workflow_checksum` to detect workflow modifications.
- Atomic updates: write to a temp file then rename.
- When `--backup-state` or `--debug` is enabled, before each step copy `state.json` to `state.json.step_<Step>.bak` and keep the last 3 backups.

Checksum and program-identity compatibility:
- The initial public CLI default-resume checksum precheck rejects a root workflow checksum mismatch before `WorkflowExecutor` construction and before any mutation of the persisted run tree.
- An imported-callee checksum mismatch rejects before child-workflow or child provider/command execution and must not remap child-state identities. The parent executor may already have been constructed, and ordinary parent-level metadata may already have been recorded before the child boundary rejects.
- Equality of step, checkpoint, call-frame, or other persisted identities is not by itself evidence that a run can resume across changed source. The root workflow checksum remains an independent compatibility guard.
- Any future cross-source compatibility mechanism must be a tested atomic upgrader that owns both checksum and program-identity compatibility, validates the complete old-to-new transition, and either commits the compatible state as one operation or leaves the old state unchanged. Evidence records, identity deltas, aliases, or partial remaps are not such an upgrader.

Checksum-compatible resume projection integrity:
- Scope ownership and ordering
  - After schema and root-checksum acceptance, every ordinary root resume validates the persisted root scope against the current entry workflow projection. The CLI performs this validation before observability overrides, executor-session/process metadata, executor construction, or execution prologue. A structurally root executor revalidates the authoritative checksum and root projection immediately before prologue; a child call-frame executor does not repeat the root guard.
  - A scope audit validates its locally stored call-frame shape, caller boundary, persisted alias, and deterministic cardinality/lineage before execution reaches future call binding. A reached call revalidates those properties so a checksum-compatible race cannot bypass them.
  - A reached call resolves its persisted caller identity against the current parent projection. Exactly one current parent call boundary owns the caller identity, and that boundary's current unique import alias selects the callee bundle; the persisted alias is validation input and cannot redirect selection. Duplicate authored import aliases are rejected before bundle construction, so a loaded import mapping is uniquely keyed.
  - The selected current callee projection owns frame-local state. Reached-callee validation occurs after ordinary parent call visit/start publication and the reached call's authored-input, managed/runtime-input, write-root, checksum, and applicable resume-bound-input validation, but before creation or mutation of the selected callee frame/state and before callee effects. Nested scopes apply the same rule recursively.
- Explicit identities and omission compatibility
  - Every present explicit durable step or call-boundary identity must resolve exactly to one candidate in its owning current scope. Stale, presentation-mismatched, out-of-scope, unclaimed, missing-required, or ambiguous identities fail closed before effects. Qualified loop/call identities are resolved through projection-owned candidates; resume validation does not split, normalize, prefix-match, reconstruct, remap, or backfill IDs.
  - An absent `step_id` remains compatible for every recognized schema-valid `steps.*` result row supported by the existing presentation/name/order fallback, regardless of result status, including supported completed, skipped, failed, and running loop-frame/result shapes. Resume leaves the field absent. A present `step_id` is always audited.
  - `current_step.step_id`, `call_frames.*.call_step_id`, call-frame current position, loop/current progress selectors, and other non-step-result identities required by schema remain mandatory.
- Loop projection integrity
  - Loop bookkeeping is shape- and domain-valid before it can generate qualified identity candidates. `for_each` indices are unique non-boolean nonnegative integers within `items`; the optional current index is in range and not completed.
  - `repeat_until` admits exactly four consistent progress forms: active; terminal condition success; terminal successful exhaustion with completed `on_exhausted` outputs; and terminal failed exhaustion without such outputs. Active progress has a nonnegative current iteration not in completed history and consistent condition/result fields. Every terminal form has `current_iteration: null`, retains completed-iteration identity candidates, and identifies the terminal completed/evaluated iteration. Success has `last_condition_result: true` and is not exhausted. Successful exhaustion covers the declared maximum range, has `last_condition_result: false`, `exhausted: true`, and a completed repeat frame. Failed exhaustion covers the declared maximum range, has `last_condition_result: false`, absent/false `exhausted`, and a failed repeat frame with `error.type: "repeat_until_iterations_exhausted"`.
  - Structurally valid bookkeeping does not excuse a stale or out-of-scope loop-local step or loop-contained call-boundary ID; exact generated-candidate resolution still applies before effects.
- Call frames and Workflow Lisp retry lineage
  - Every mapping frame validates caller identity, import alias, boundary ownership, and status. Completed frames are unlimited historical records and never resumable. A non-Workflow-Lisp boundary has at most one non-completed resumable frame; multiple candidates are ambiguous.
  - A Workflow Lisp boundary is identified only by typed loaded-bundle frontend capability and has one validated retry lineage, zero or one running member, and any number of failed predecessors. Retry lineage parsing and next-ID allocation are centralized and deterministic; mixed lineages, multiple running members, duplicate ordinals, malformed ordinals, or malformed statuses fail closed without mapping-order selection.
  - With a running Workflow Lisp member, its checksum and resume-bound-input validation run first and win on failure. If they pass, every failed predecessor is checksum-validated and recursively projection-audited in ordinal order, then the running member's local scope is audited and resumed. Without a running member, every failed predecessor is checksum-validated and recursively audited before deterministic fresh-retry allocation. Failed predecessor state is never exempt from audit.
- Failure and mutation envelopes
  - The initial CLI root-checksum precheck retains its existing byte-immutable exit-`1` behavior before session/executor creation.
  - A direct or post-CLI-race structurally root checksum recheck failure persists `error.type: "workflow_checksum_mismatch"` with message `"Workflow has been modified since the run started"` and context fields `workflow_file`, `persisted_checksum`, and `current_checksum` (each string or JSON `null`) plus `reason`, which is exactly one of `workflow_modified`, `missing_recorded_checksum`, `missing_workflow_path`, or `workflow_unavailable`. It changes root `status`, `error`, and `updated_at`, leaves current step/steps/visits/loops/frames unchanged, and stops before projection audit or prologue. Already-open session/process metadata may remain; failed session closure cannot replace the checksum diagnostic.
  - An early CLI or direct root projection failure changes only root `status`, `error`, and `updated_at`. A checksum-compatible identity race caught by the second root audit uses the same three-field projection delta, preserves already-open session/process metadata, stops before prologue, and closes the session failed without replacing the projection diagnostic. Run-level failed status/error are authoritative; an unchanged `current_step` is forensic and is not live for status, heartbeat, or stalled-run interpretation.
  - A reached-callee pre-construction projection failure becomes the current caller's failed call-step result and scope/run error. The selected callee frame/state remains untouched. Already-existing ancestor frames persist ordinary failed step/current/visit/frame snapshots while promoting the exact same diagnostic unchanged to the root.
  - `resume_projection_integrity_error` is a sticky, non-routable terminal failure after ordinary failure persistence: authored success/failure/`always` routes, `on_error=continue`, and loop/container continuation cannot consume it. Configured finalization may run under existing semantics, but any finalization failure remains supplemental and cannot wrap, replace, clear, or downgrade the projection diagnostic. Epilogue and session closure preserve it.
- Diagnostic, privacy, and compatibility
  - Projection-integrity diagnostics use `error.type: "resume_projection_integrity_error"`, a stable bounded `error.message`, and a stable bounded context. `diagnostic_schema` is exactly `"resume_projection_integrity_error.v1"`. `reason` is exactly one of `unknown_explicit_step_id`, `presentation_slot_mismatch`, `out_of_scope_step_id`, `unclaimed_explicit_step_row`, `missing_required_identity`, `missing_call_boundary`, `ambiguous_call_boundary`, `ambiguous_resumable_call_frame`, `persisted_import_alias_mismatch`, `missing_imported_bundle`, `unsupported_shape`, or `invalid_loop_progress`.
  - The context always includes ordered identity-only `scope_path`, `field`, `offending_value` (JSON `null` when absent), `expected_owner` with exactly `workflow_file`, `workflow_checksum`, and `projection_scope`, `candidate_count` (integer or JSON `null`), and `call_boundary_step_id` (string or JSON `null`). These fields are present rather than omitted.
  - Diagnostics do not expose bound inputs, context values, artifacts, prompts, provider output, secrets, whole frame state, or whole projections.
  - This contract is additive under state schema `2.1`. Pre-v2.0 state and pre-`schema_version: "2.1"` reusable-call state remain rejected unless a tested atomic upgrader ships with the same tranche.
  - Resume projection integrity does not read, require, or interpret procedure-migration, identity-retirement, or other migration evidence, and it does not select behavior by workflow/module/procedure name, basename, family, or persisted alias.

Workflow Lisp lexical-checkpoint default resume:
- Node-local restore selection is primary. A prior-boundary fallback is allowed only when the restart node owns lexical checkpoint metadata and restore selection positively reports typed `record_absent` for that node's next boundary.
- Only the canonical checkpoint index whose `program_point_id` matches the runtime-plan point and whose `storage_allocation_id` matches the canonical lexical-checkpoint-index allocation may establish absence. A missing canonical index or a valid canonical index with an empty `records` list is `record_absent`; a present unreadable, malformed, incomplete, foreign, stale, or otherwise invalid index is `record_present_unusable` and fails closed with a stable diagnostic.
- Every index `record_id` must be one safe filename component and cannot introduce absolute or relative path structure, separators, traversal components, NULs, or unsupported filename characters. Its record reference must equal the canonical workspace-relative record path derived from that ID, checkpoint point, and storage scope. The lexical path must be a direct child of the canonical record family; after normalization and symlink resolution it must remain a direct child of the resolved family and below the resolved workspace. Absolute paths, parent escapes, record-path symlinks, and symlinked components below the workspace fail closed before record I/O. Entry `record_id`, `program_point_id`, `point_kind`, and `frame_identity` must match the runtime-plan point and loaded record as applicable, and the loaded record plus restore payload must pass the ordinary checkpoint-record and restore validators.
- Canonical checkpoint index and record JSON must be read beneath a trusted workspace directory descriptor. Each parent component is opened descriptor-relative as a directory with no-follow semantics, and the final file is opened descriptor-relative with no-follow and nonblocking semantics, verified as a regular file with `fstat`, and decoded from that already-open descriptor; pathname validation followed by pathname reopen is not permitted. Nonblocking final-open support is required so a FIFO or other nonregular target is rejected without waiting for a peer; unavailable support fails closed. Missing canonical index state is `record_absent` only when the descriptor-relative open reports `FileNotFoundError`; symlink, permission, invalid-parent, nonregular target, unsupported descriptor-relative operation, or mutation-during-read state is present-unusable and fails closed. Record-side equivalents fail as reference-invalid or unreadable without weakening malformed-JSON diagnostics.
- The runtime must derive the complete nearest-prior effect-boundary candidate set only from canonical `runtime_plan.ordered_node_ids`. The restart node and every eligible point must be uniquely ordered, and exactly one nearest candidate is required. That candidate's checkpoint ID must occur exactly once across all `runtime_plan.lexical_checkpoint_points`, including older, later, and non-effect points; missing, unordered, duplicate, or ambiguous state fails closed before checkpoint-ID restore selection.
- The globally unique prior checkpoint ID must pass the same restore validator used for node-local selection. Root/callee checksum, checkpoint/program identity, effect policy, completed-effect reference, source lineage, binding schema, and authoritative-state validation remain unchanged.
- A successful prior-boundary selection activates its validated restore payload but preserves the original restart node. An invalid, unsafe, absent, or non-restorable nearest point fails closed; default resume never searches an older point. Any coarse or older-boundary recovery is explicit/operator-directed or future functionality.

Recovery mechanisms:
```bash
# Resume with state validation
orchestrate resume <run_id>

# Force restart ignoring corrupted state
orchestrate resume <run_id> --force-restart

# Attempt repair of corrupted state
orchestrate resume <run_id> --repair

# Archive old runs
orchestrate clean --older-than 7d
```

Schema boundary note:
- Post-v2.0 runtimes reject resume from pre-v2.0 state rather than silently remapping old name-keyed lineage/freshness data.
- Ordinary resumed execution clears `current_step` when it reaches terminal state. Accepted pre-prologue root checksum or projection failure envelopes may retain an unchanged forensic `current_step`; root failed `status`/`error` are authoritative, and that step is not live for status, heartbeat, or stalled-run interpretation.

## Adjudicated Provider State (v2.11)

- State schema remains `2.1`; adjudication state is an additive `steps.<Step>.adjudication` payload plus run-root sidecars.
- Normal artifact lineage contains only promoted selected outputs. Candidate outputs are not published as ordinary artifacts.
- `steps.<Step>.adjudication` records selected candidate id, selected score or `null`, selection reason, promotion status, scorer identity, evaluator prompt hash, evidence confidentiality, score ledger paths, scorer snapshot path, promotion manifest path, and per-candidate terminal metadata.
- Candidate/evaluator stdout-derived state is absent: `output`, `lines`, `json`, `truncated`, and `debug.json_parse_error` are not populated for adjudicated provider steps.
- Run-local score ledgers live under `.orchestrate/runs/<run_id>/adjudication/<frame_scope>/<step_id>/<visit_count>/candidate_scores.jsonl`. Workspace-visible ledgers configured by `score_ledger_path` are terminal mirrors only.
- Ledger rows are keyed by `candidate_run_key` and `score_run_key` and include candidate provider/model/prompt identity, scorer identity or scorer-unavailable metadata, packet hash when present, score status, selection status, promotion status, and attempt counts.
- Resume reconciles the baseline manifest, candidate metadata, scorer snapshot
  or scorer-unavailable metadata, evaluation packets, ledger rows, and
  promotion manifests. A fully consistent completed visit is reused without
  provider invocation. When inconsistent state can be bound to one exact
  run-owned step/visit scope, the runtime discards only that visit's partial
  adjudication state and sidecars, emits
  `adjudication_state_mismatch_rerun`, and re-enters ordinary adjudicated-step
  dispatch with fresh identities. Unknown, ambiguous, escaping, aliased, or
  otherwise unprovable cleanup scope fails closed without mutation or provider
  launch. Before removing one visit across its run-owned roots, the runtime
  writes a frame/step-scoped cleanup guard bound to the discarded and next
  visit coordinates. Successful cleanup removes that guard before dispatch; a
  surviving guard proves cleanup was interrupted and blocks later provider
  dispatch or publication with `adjudication_state_integrity_error`.
