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
    - v2.10 also uses this surface for provider-session quarantine failures (`type: "provider_session_interrupted_visit_quarantined"`)
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
  - v2.10 interrupted session-enabled visits are quarantined instead of replayed on resume; quarantine clears the matching `current_step`, preserves older same-name terminal results, and records a durable run-level error that points to the canonical metadata and transport-spool paths.

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

- A Workflow Lisp provider boundary with a typed prompt-dependency contract
  allocates its attempt ordinal in root `RunState.provider_attempt_allocations`.
  The member is omitted while empty. It is root-owned across ordinary, loop,
  call-frame, and adjudicated execution; nested state managers do not maintain
  competing counters.
- Allocation is a crash-durable state transition. The state file and containing
  directory are synchronized before the allocated ordinal is used, and the
  state-mutation lock serializes allocation with other root-state writers.
  Allocation events and later evidence-publication events form a closed,
  append-only per-scope sequence. Filesystem evidence paths never allocate or
  recover an ordinal.
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
  authority. Runtime does not enumerate or validate earlier records when
  resuming.
- A terminal-only offline validator may derive a content-addressed validated
  index from a frozen authoritative allocation projection and immutable record
  digests. That index is reproducible, non-authoritative evidence; runtime and
  resume never read it. A later authoritative state change makes an older
  index stale rather than changing runtime behavior.

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
- Resume must reconcile baseline manifest, candidate metadata, scorer snapshot or scorer-unavailable metadata, evaluation packets, ledger rows, and promotion manifests. Missing or mismatched state fails with `adjudication_resume_mismatch` unless a future explicit force-rerun path is used.
