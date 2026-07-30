# Versioning and Migration (Normative)

- Tracks
  - DSL version: governs available fields and validation behavior.
  - State schema version: `schema_version` stored in `state.json`.

- ML-0 contract pivot (provider attempts)
  - Provider attempt recovery changes from exactly-once quarantine to
    at-least-once discard-and-rerun without changing the DSL version or state
    schema version. This applies uniformly to ordinary, session, supervision,
    peer-group, phased, and exact-scope adjudication recovery.
  - The normative contract was accepted before its runtime tranches. ML-1,
    ML-2, and ML-4 are now historical complete, so the at-least-once runtime
    contract is implemented across the named provider families and exact-scope
    adjudication recovery. This closure does not select a successor phase.
  - Compatible completed-result reuse, managed jobs, declared resource
    transitions, source/checkpoint guards, lineage, atomic publication, and
    peer message ledgers remain unchanged.
  - The provider-isolation transfer journal remains unchanged. Its separately
    owner-gated ML-3 simplification is deferred and no security surface is
    selected by this pivot.

- v1.1 baseline
  - Core DSL: steps with provider/command/wait_for, conditionals, for_each.
  - No dependency injection.

- v1.1.1 additions (dependency injection)
  - `depends_on.inject`: shorthand `true` or object form `{ mode, instruction?, position? }`.
  - Validation is strict: workflows using injection MUST set `version: "1.1.1"` or any later supported DSL version.
  - Migration from 1.1 to 1.1.1
    - Before: duplicate file lists in prompt and depends_on.
    - After: declare files once in `depends_on`; orchestrator injects into the prompt.
    - Benefits: DRY, glob support, maintainability, generic prompts.

- v1.2 additions (artifact dataflow contracts)
  - Top-level `artifacts` registry with `kind: relpath|scalar` contracts.
    - `relpath` (default) retains canonical pointer-file materialization.
    - `scalar` supports typed values (`enum|integer|float|bool`) without pointer-file indirection.
  - Step-level `publishes` and `consumes` for producer/consumer linkage.
  - Provider prompt convenience controls for consume dataflow:
    - `inject_consumes` (default true)
    - `consumes_injection_position` (`prepend|append`, default `prepend`)
    - `prompt_consumes` (optional subset of consumes to inject into prompt)
  - Runtime enforcement:
    - publication ledger in state (`artifact_versions`)
    - consume preflight (`latest_successful`) with optional freshness (`since_last_consume`)
    - deterministic contract failures (`exit_code: 2`, `error.type: "contract_violation"`).

- v1.3 additions (JSON-bundled deterministic I/O)
  - Step-level `output_bundle` allows one JSON file to publish multiple deterministic artifacts with typed validation.
  - Step-level `consume_bundle` writes resolved consumes into one JSON file after consume preflight.
  - `publishes.from` may reference either `expected_outputs.name` or `output_bundle.fields[*].name`.
  - Existing v1.2 behavior remains valid; relpath consume pointer materialization still applies in v1.3.
  - Recommended workflow policy:
    - Heavy execution/fix steps: keep flexible (`output_capture: text|lines`), minimal deterministic outputs.
    - Assessment/review/gate steps: keep strict (`output_capture: json`, `allow_parse_error: false`), publish decision artifacts.
    - Control flow should branch on strict published artifacts, not raw prose logs.

- v1.4 additions (read-only consume pointer semantics)
  - Relpath consume preflight no longer mutates registry pointer files.
  - Consumed values continue to resolve through runtime state (`_resolved_consumes`) and optional `consume_bundle`.
  - Backward compatibility: v1.2/v1.3 workflows retain legacy pointer-materialization consume behavior.
  - Migration recommendation for command steps: read consumed artifact values from `consume_bundle` JSON rather than relying on consume-time pointer rewrites.

- v1.5 additions (first-class gates)
  - Step-level `assert` becomes a first-class execution form.
  - `assert` reuses the legacy `equals|exists|not_exists` condition surface and is exclusive with `provider|command|wait_for|for_each`.
  - False assertions fail with `exit_code: 3` and `error.type: "assert_failed"`.
  - Assertion failure remains observable to normal `on.failure.goto` routing.

- v1.6 additions (typed predicates and normalized outcomes)
  - `when` and `assert` accept typed predicates:
    - `artifact_bool`
    - `compare` with `eq|ne|lt|lte|gt|gte`
    - `all_of|any_of|not`
  - Typed predicates use structured `ref:` operands and do not reuse legacy `${...}` string interpolation.
  - Initial structured refs are limited to `root.steps.<Step>...` and reject bare `steps.`, `self.`, `parent.`, and untyped `context.*`.
  - Step results gain normalized `outcome.{status,phase,class,retryable}` fields for observable results.
  - This tranche remains on state schema `1.1.1`; the added `outcome` object is an additive field under existing step results.

- v1.7 additions (scalar bookkeeping runtime primitive)
  - Step-level `set_scalar` emits one declared scalar artifact as a local step result without shelling out.
  - Step-level `increment_scalar` reads the latest published version of the same declared scalar artifact, adds a numeric literal, and emits the updated local step artifact.
  - Both forms are exclusive with `provider|command|wait_for|assert|for_each`.
  - Publication still happens only through `publishes.from`; scalar bookkeeping does not mutate the top-level artifact ledger directly.
  - This tranche remains on state schema `1.1.1`; local scalar artifacts reuse the existing `steps.<Step>.artifacts` and `artifact_versions` surfaces.

- v1.8 additions (cycle guards)
  - Workflow-level `max_transitions` bounds routed transfers between settled top-level steps.
  - Step-level `max_visits` bounds top-level non-skipped step entries after `when` evaluation.
  - Guard failures use `error.type: "cycle_guard_exceeded"` and fail the target step in pre-execution state.
  - Guard failures stop the run even when the guarded step declares `on.failure.goto` and even when CLI `--on-error continue` is set.
  - `transition_count` and `step_visits` persist under state schema `1.1.1`; skipped steps do not consume visit budget and internal retries do not consume extra visits.
  - The first tranche rejects nested/`for_each` `max_visits` usage until stable internal IDs land.

- v2.0 additions (scoped refs and stable internal step ids)
  - Steps may declare an authored stable `id` distinct from display `name`.
  - The loader assigns internal `step_id` values to every step; authored ids stabilize those values across sibling insertion, while compiler-generated ids are only checksum-stable.
  - Typed predicates extend structured refs to `self.steps.<Step>...` and `parent.steps.<Step>...`.
  - State schema moves to `schema_version: "2.0"` and persists `step_id` on step/current-step records.
  - Artifact lineage/freshness bookkeeping moves to qualified internal identities, including per-iteration `for_each` producer/consumer keys.
  - Resume from pre-v2.0 state is rejected unless a future tranche ships an explicit upgrader.

- v2.1 additions (workflow signatures)
  - Top-level `inputs` and `outputs` declare typed workflow-boundary contracts without pointer-file semantics.
  - CLI `run` supports `--input name=value` and `--input-file <json>` binding for top-level workflow inputs.
  - Successful binding is exposed inside the workflow through `${inputs.<name>}` and typed `ref: inputs.<name>`.
  - Successful workflow completion may export `workflow_outputs` by validating each declared `outputs.<name>.from` binding against the same typed contract family.
  - This tranche remains on state schema `2.0`; `bound_inputs` and `workflow_outputs` are additive top-level state fields.

- v2.2 additions (structured `if/else`)
  - Top-level steps may use structured `if` / `then` / `else` instead of raw `goto` diamonds.
  - `if` reuses the existing condition surface (`equals|exists|not_exists` or typed predicates).
  - `then` and `else` accept either a bare `Step[]` list or an object with:
    - optional stable `id`
    - required `steps`
    - required `outputs` for this tranche when statement outputs are exposed downstream
  - Branch-local steps are not addressable from the root workflow scope; downstream refs must target the statement node itself.
  - Branch outputs are materialized onto the statement node and become available at `root.steps.<Statement>.artifacts.<name>`.
  - The loader lowers the authored statement into stable branch markers, lowered branch-body steps, and a join node whose `step_id` derives from the authored statement/branch ancestry.
  - The first tranche is conservative:
    - only top-level structured `if/else` is accepted
    - `goto` / `_end` routing inside branch steps is rejected
    - state schema remains `2.0`; lowered-node metadata is additive under existing step results

- v2.3 additions (structured finalization)
  - Workflows may declare a top-level `finally` block as either `Step[]` or `{ id?, steps: Step[] }`.
  - Finalization steps are lowered into stable top-level execution nodes under `finally.<StepName>` presentation keys and `root.finally.<block-id-or-finally>.*` durable ancestry.
  - Finalization runs once after the workflow body settles on either success or failure.
  - Resume restarts from the first unfinished finalization step instead of replaying completed cleanup.
  - When the workflow body succeeds and finalization fails, the run fails with `error.type: "finalization_failed"`.
  - When the workflow body already failed and finalization also fails, the original body failure remains primary and the finalization failure is recorded as secondary diagnostic state under `finalization.failure`.
  - Workflow `outputs` remain withheld until finalization succeeds and are suppressed on finalization failure.
  - This tranche remains on state schema `2.0`; `finalization` bookkeeping and lowered cleanup-step metadata are additive top-level fields.

- v2.4 contract boundary (reusable-call docs lock; not executable by itself)
  - Reserves the future reusable-workflow path taxonomy before runtime support lands:
    - workflow-source-relative `imports`, nested imports, `asset_file`, and `asset_depends_on`
    - workspace-relative runtime paths unchanged for `input_file`, `depends_on`, `output_file`, deterministic relpath outputs, and bundle paths
  - Locks the first `call` tranche as inline and non-isolating.
  - Requires reusable workflows to surface DSL-managed write roots as typed `relpath` inputs and requires call sites to bind distinct values where multiple invocations could alias the same managed paths.
  - Locks the first-tranche same-version caller/callee rule and callee-private `providers` / `artifacts` / `context` defaults.
  - Schedules a state-schema bump for Task 11 because the current bare artifact-name ledger cannot represent call-scoped internal lineage and freshness safely.
  - Current loader/runtime support still stops at the implemented v2.3 surface; `v2.4` is a contract boundary, not an already-executable workflow version.

- v2.5 additions (imports + `call`)
  - Top-level `imports` plus step-level `call` / typed `with:` binding.
  - Only declared callee outputs cross the boundary and materialize on the outer call step.
  - State schema moves to `schema_version: "2.1"` with persisted `call_frames`, deferred export state, and preserved internal provenance for exported outputs.
  - Callee-private artifact lineage and freshness stay inside the call-frame-local nested state rather than the caller-global ledgers.

- v2.6 additions (structured `match`)
  - Top-level steps may use structured `match` over a typed enum ref.
  - `match.cases` must cover every allowed enum value on the selected artifact or input.
  - Cases reuse the same block/output pattern as v2.2 `if/else`: `Step[]` or `{ id?, steps, outputs }`.
  - Case-local steps stay scoped to the selected case; downstream refs target the statement node outputs.
  - This tranche remains on state schema `2.0`; lowered case markers/join metadata are additive `steps.*` payload fields.

- v2.7 additions (post-test `repeat_until`)
  - Top-level steps may use structured `repeat_until` with `{ id?, outputs, condition, max_iterations, steps }`.
  - Iteration `0` always executes once; `condition` is evaluated only after each completed iteration.
  - `condition` reads loop-frame outputs through `self.outputs.<name>` and must not read inner multi-visit body steps directly.
  - Loop-frame outputs materialize on the authored step itself, so downstream refs target `root.steps.<Statement>.artifacts.<name>`.
  - Resume persists `repeat_until` iteration bookkeeping (`current_iteration`, `completed_iterations`, `condition_evaluated_for_iteration`, `last_condition_result`) under state schema `2.1`.
  - First tranche remains conservative: body steps reject `goto`, nested `for_each`, and nested `repeat_until`.
  - Direct nested `call`, `match`, and `if/else` bodies are allowed and lower into loop-local executable nodes that keep body-local structured refs on `self.steps.*` and outer lexical refs on `parent.steps.*`.

- v2.8 additions (score-aware gates)
  - Typed predicates also accept `score: { ref, gt?, gte?, lt?, lte? }` for benchmark-style threshold and band checks.
  - `score` remains predicate sugar over numeric typed refs; it does not add a separate routing or decision surface.
  - `score` requires a numeric structured ref, at least one bound, and rejects mixed `gt`+`gte` or `lt`+`lte` declarations.

- v2.9 additions (authoring linting and normalization)
  - CLI dry-run and report surfaces may emit advisory lint warnings without turning them into validation failures.
  - Initial warnings cover shell gates that should become `assert`, stringly `when.equals` routing that should become typed predicates, raw `goto` diamonds that should become structured control, and imported/exported output-name collisions.
  - Advisory lint also warns when top-level workflow-boundary `inputs` or `outputs` redundantly declare `kind: relpath` together with `type: relpath`; prefer `type: relpath` alone on workflow boundaries.
  - This warning is intentionally scoped away from top-level `artifacts`, `expected_outputs`, and `output_bundle`, where relpath/storage semantics still rely on artifact-style contracts.
  - Warning presence does not change runtime or workflow-load exit codes in the first pass.

- v2.10 additions (provider-session resume)
  - Scalar `string` becomes a general typed scalar contract for workflow `inputs`/`outputs`, top-level scalar `artifacts`, `expected_outputs`, `output_bundle.fields`, and scalar bookkeeping.
  - `type: string` preserves exact values end-to-end; unlike the older text-backed scalar types, the runtime does not trim leading/trailing whitespace.
  - Provider steps authored directly under the root workflow `steps:` list may declare `provider_session`:
    - `mode: fresh` requires `publish_artifact`
    - `mode: resume` requires `session_id_from`
  - Provider templates may declare `session_support` with:
    - `metadata_mode`
    - `fresh_command`
    - optional `resume_command`
  - `${SESSION_ID}` is legal only inside `session_support.resume_command`, which must contain exactly one placeholder when present.
  - Fresh session handles are runtime-owned publications: the handle is materialized on `steps.<Step>.artifacts.<publish_artifact>` and appended to `artifact_versions` only after the exact visit's final step result, same-visit lineage appends, and matching `current_step` clearance are committed together.
  - Resume consumes still participate in ordinary lineage selection, but the reserved `session_id_from` consume is excluded from prompt injection and `consume_bundle`.
  - Session-enabled visits create canonical observability artifacts under `.orchestrate/runs/<run_id>/provider_sessions/`.
  - The original v2.10 release quarantined interrupted session-enabled visits.
    The ML-0 contract pivot supersedes that recovery policy with validated
    discard-and-rerun; the session schema and completed-result reuse are
    unchanged.

- v2.11 additions (adjudicated provider steps)
  - Step-level `adjudicated_provider` runs one logical artifact-producing provider step through one or more isolated candidates, scores output-valid candidates with an evaluator provider, selects the highest finite score, and promotes only the selected candidate's declared deterministic outputs.
  - `adjudicated_provider` is mutually exclusive with `provider`, `command`, `wait_for`, `assert`, scalar bookkeeping, structured control forms, and `call`.
  - Adjudicated steps must declare `expected_outputs` or `output_bundle`, must not use stdout-derived step capture surfaces, and do not populate `steps.<Step>.output`, `.lines`, or `.json` from candidate/evaluator stdout.
  - Candidate workspaces are copied from one immutable frame/step/visit baseline using `adjudicated_provider.baseline_copy.v1`; V1 supports artifact promotion only, not arbitrary source-edit patch promotion.
  - Evaluator scoring requires `evaluator.evidence_confidentiality: same_trust_boundary`, complete bounded UTF-8 score-critical evidence packets, and strict JSON evaluator output with `candidate_id`, finite `score` in `[0.0, 1.0]`, and `summary`.
  - Selected outputs are promoted through a manifest-backed transaction with preimage checks, staged replacements, rollback metadata, parent output revalidation, and publication withholding until promotion and any score-ledger mirror finalization succeed.
  - State schema remains `2.1`; adjudication state is additive under `steps.<Step>.adjudication` and run-owned sidecars under `.orchestrate/runs/<run_id>/adjudication/`, `candidates/`, and `promotions/`.

- v2.12 additions (`repeat_until.on_exhausted`)
  - `repeat_until.on_exhausted.outputs` lets an authored loop complete with literal scalar loop-frame output overrides when the loop body succeeds but the post-test condition remains false through `max_iterations`.
  - The feature is opt-in. Existing `repeat_until` loops without `on_exhausted` retain the prior `repeat_until_iterations_exhausted` failure behavior.
  - Exhaustion overrides apply only to condition non-convergence after successful body execution and output resolution. Body-step failures, output contract failures, and predicate failures still fail the loop.
  - State schema remains `2.1`; loop-frame debug state adds `debug.structured_repeat_until.exhausted`.

- v2.16 additions (Workflow Lisp provider supervision)
  - Target DSL `2.16` installs the reserved non-shadowable prelude union
    `ProviderSteeringDirective` and accepts the `.orc`-only
    `with-live-providers` form.
  - The form permits exactly one worker and one supervisor, one observation
    edge, bounded overlap inside one atomic `provider_supervision.v1` node,
    and at most one validated same-session worker resume.
  - The worker must resolve to a provider template with structurally valid
    `session_support.turn_boundary_resume: true`; the supervisor needs no
    session capability. Provider observation is attempted by default, while
    the group's two initial panes are required through directive arbitration.
  - Targets below `2.16` neither accept the form nor reserve the prelude name.
    An older module's authored type with the same name therefore retains its
    prior meaning. There is no YAML spelling.
  - State schema remains `2.1`; the node's required
    `provider_supervision.v1` config tag provides the additive compatibility
    boundary. The original interrupted-visit quarantine policy is superseded
    by the ML-0 at-least-once recovery contract.

- v2.17 additions (Workflow Lisp provider peer groups)
  - Target DSL `2.17` reserves and accepts the `.orc`-only
    `with-live-provider-peers` form. It declares an authored-order static group
    of two through eight provider members, all-other-members messaging, and one
    pure transportable settlement.
  - The form lowers through ordinary specialization and WCC to one separate
    `provider_peer_group.v1` executable node. The closed node config binds the
    complete member set/order, typed member and settlement contracts,
    messaging policy, path plan, source ownership, target version,
    `interactive_terminal_turn_queue.v1` capability requirement, and
    `max_steers: 0` into checkpoint identity.
  - Provider templates used by peer members must declare the closed structural
    `interactive_session_support` capability. Provider name, stdin/argv mode,
    observation, session support, or v2.16 turn-boundary resume support cannot
    imply it.
  - The runtime exposes only exact-attempt `peer-ready`, `peer-send`,
    `peer-ack`, and `peer-finish` ingress. Receiver ledgers are durable before
    message offer; member output uses typed direct-root JSON bundles; and only
    the validated pure settlement crosses the node's single atomic
    workflow-result boundary.
  - Target `2.17` continues to accept `with-live-providers` without upgrading
    or rewriting its `provider_supervision.v1` artifact. Existing target-2.16
    source, artifacts, state, and behavior remain unchanged. Targets below
    `2.17` do not reserve the peer-group form, so an older authored binding or
    macro of the same name retains its prior meaning. There is no YAML
    spelling.
  - `workflow_executable_ir.v1`, runtime-plan v1, Semantic IR v1, source-map
    v1, and state schema `2.1` remain their envelope versions. Older runtimes
    reject the unknown peer-group node kind. The original additive peer-group
    quarantine policy is superseded by ML-0 at-least-once recovery without a
    schema migration.

- v2.18 additions (Workflow Lisp bounded list traversal)
  - Target `2.18` adds the `(list ...)` constructor; total
    `list/head`, `list/rest`, `list/empty?`, `list/append`, and `list/length`
    operators; pure `list/map`; bounded `list/map-effect :max`; pure
    `path/join-under`; and eligible `List[T]` loop-state slots.
  - Both map surfaces are lexical binder forms rather than function values.
    `list/map-effect` erases to the existing bounded loop/call/checkpoint
    machinery and fails closed with `list_map_effect_cap_exceeded`; it adds no
    Core, Executable IR, runtime-plan, scheduling, or checkpoint node kind.
  - Collection eligibility is exactly the shared whole-list predicate
    `is_transportable_result_type(List[T])`. Unsupported list shapes fail
    closed; record/union elements, higher-order mapping, indexing, broader
    effect bodies, and unbounded traversal remain excluded.
  - `path/join-under` proves rooted lexical containment without checking
    filesystem existence; existing path-boundary contracts own later
    existence checks.
  - Pure payloads that use the new forms select
    `pure_expr_schema_version: 2`; payloads using only the older surface
    retain schema 1 byte-for-byte. State schema remains `2.1`, and targets
    below `2.18` do not reserve the new forms.

- v2.19 additions (Workflow Lisp transportable `Value`)
  - Target `2.19` reserves compiler-owned `Value` as an exact opaque transport
    contract over recursively valid strict JSON. It is distinct from
    non-transportable `Json` and from every concrete record, union, scalar,
    path, optional, list, and map contract; source compatibility is exact in
    both directions.
  - Direct results use the existing sole compiler-owned `__result__` field
    with `json_pointer: ""` and `type: value`, so the wire document is the
    value itself rather than a `{"value": ...}` envelope. Public workflow and
    artifact contracts use `kind: value`, `type: value`.
  - `Value` is valid in the shared transportable function, procedure,
    provider-result, command-result, workflow-call, public-workflow,
    record/union payload, and supported `Optional`/`List`/`Map` positions.
    There is no implicit narrower-to-`Value` or `Value`-to-narrower conversion.
  - Strict file-backed parsing rejects malformed JSON and non-standard
    non-finite constants. In-memory validation rejects non-finite floats,
    non-string object keys, cycles, and other non-JSON leaves with the first
    invalid path. `description` and `format_hint` guidance are accepted;
    `example` is rejected.
  - Classic and WCC preserve the same literal descriptor through compiled
    contracts, state, checkpoint identity, and resume. State schema remains
    `2.1`; payload shape does not specialize the contract. Targets below
    `2.19` reject the source type or descriptor, and v2.15 narrower returns
    and result guidance remain unchanged.

- v2.20 additions (Workflow Lisp prompt fragments)
  - Target `2.20` admits importable `defprompt` declarations with the closed
    `doc`, `text`, `value`, and `path` slot kinds, fully applied named fills,
    prompt-owned structured returns, and byte-stable
    `compiled_prompt_fragment_identity.v1` /
    `compiler_prompt_fragment_contract.v1` carriage.
  - Fragment snapshots remain non-authoritative schema-2.1 attempt evidence.
    Compatible completed-result reuse validates the ordinary program and
    checkpoint guards and does not execute the provider again.

- v2.21 additions (Workflow Lisp prompt output positions)
  - Target `2.21` adds exactly `(slot :path :out [PathType])`. One authored
    fill drives both POSIX path rendering and one compiler-owned required
    UTF-8 `expected_outputs` row.
  - A fragment containing `:out` uses
    `compiled_prompt_fragment_identity.v2` and
    `compiler_prompt_fragment_contract.v2`; every ordered
    `output_positions[*].expected_output` object must equal the corresponding
    provider-configuration `expected_outputs` row exactly at every compiler,
    persisted, runtime, checkpoint, and resume boundary.
  - The generated file contract may coexist with exactly one prompt-owned
    `output_bundle` or `variant_output`. Names and resolved destinations must
    be disjoint before provider launch. Prompt blocks and post-attempt
    validation use output-position-then-structured-result order, and neither
    artifact mapping enters state unless both validations pass.
  - Target-2.20 source, diagnostics, v1 carrier/identity bytes, runtime
    behavior, and compatible completed-result reuse remain unchanged.
    State schema remains `2.1`.

- v2.22 additions (Workflow Lisp prompt-attempt identity and diagnostics)
  - Direct fragment-backed `provider-result` calls require the exact
    `workflow_prompt_attempt_identity.v1` version carrier and
    `compiler_prompt_attempt_binding_plan.v1` declaration-ordered plan.
    Targets 2.20 and 2.21 omit both fields.
  - Each successfully prepared attempt publishes closed
    `workflow_prompt_fragment_snapshot.functional.v2` evidence before launch,
    separating fragment program, resolved bindings, injected dependencies,
    runtime contributions, and prepared provider policy. The exact prepared
    final-prompt and composition digests close the record without persisting
    prompt or role bytes.
  - A pure fixed-order comparator and the additive `prompt_context` JSON and
    Markdown report projections remain provenance only. The report key is
    present for every target; older valid fragment snapshots project as
    `legacy_snapshot`, and unqualified runs project an empty attempt list.
  - Compiled fragment identities/contracts remain v1 or v2 according to the
    existing Q1/Q2 shape. Target-2.20/2.21 compiler, runtime, checkpoint,
    provider, evidence, and completed-result reuse bytes remain unchanged.
    State schema remains `2.1`.

- v2.23 additions (Workflow Lisp phased contract delivery)
  - Target `2.23` adds the optional direct-fragment provider-call policy
    `:delivery :composed|:phased` and the phased-only non-boolean literal
    `:materialization-attempts 1..3`, defaulting to `2` only when phased
    delivery is explicit. Omitted delivery remains composed and carries
    neither key.
  - Omitted and explicit composed calls retain the ordinary route,
    attempt-identity-v1, and functional-v2 evidence. Explicit phased delivery
    requires `interactive_terminal_turn_queue.v1`, has no composed fallback,
    and requires attempt-identity-v2 plus functional-v3 evidence.
  - The phased runtime partitions one canonical composition as exact
    `T1 || T2 == C`, delivers the task once, permits bounded
    materialization-only correction in the same provider process, validates
    output positions then the structured result, and publishes one jointly
    valid candidate only after natural shutdown and one guarded state commit.
  - `provider_phased_protocol_frame.v1`,
    `provider_prompt_phase_ledger.v1`,
    `provider_phased_candidate_digest_manifest.v1`,
    `provider_phased_delivery_diagnostic.v1`, and
    `workflow_prompt_context_report.v2` are additive, content-free,
    non-authoritative evidence/report surfaces. Completed reuse does not read
    the ledger; ML-0 supersedes sticky quarantine for interrupted nonterminal
    phased visits with whole-visit discard and a fresh attempt.
  - The closed `provider_call_policy` ordering becomes `model`, `effort`,
    `delivery`, `materialization_attempts`. Only model/effort are
    provider-bound; delivery/attempts are runtime-only, and `timeout_sec`
    remains the one whole-attempt deadline outside the mapping.
  - State schema remains `2.1`. Target-2.22 and earlier source, omitted/composed
    invocation bytes, compiled Q1/Q2 identities, and completed-result reuse
    remain compatible.

- DSL evolution rollout roadmap
  - `v1.5`: D1 `assert`
  - `v1.6`: D2 typed predicates + structured `ref:` + normalized outcomes
  - `v1.7`: D2a scalar bookkeeping
  - `v1.8`: D3 cycle guards
  - `v2.0`: D4-D5 scoped refs + stable internal IDs
  - `v2.1`: D6 workflow signatures
  - `v2.2`: D7 structured `if/else`
  - `v2.3`: D8 `finally`
  - `v2.4` (docs/contract boundary): D9 reusable-call contract
  - `v2.5`: D10 imports + `call`
  - `v2.6`: D11 `match`
  - `v2.7`: D12 `repeat_until`
  - `v2.8`: D13 score-aware gates
  - `v2.9`: D14 authoring linting and normalization
  - `v2.10`: first-class provider-session resume
  - `v2.11`: adjudicated provider steps
  - `v2.12`: deterministic repeat-until exhaustion outputs
  - `v2.13`: managed provider jobs
  - `v2.14`: materialization, snapshots, and variant-output contracts
  - `v2.15`: native transportable returns and typed result guidance
  - `v2.16`: bounded Workflow Lisp provider supervision
  - `v2.17`: static Workflow Lisp provider peer groups and recorded
    turn-boundary messaging
  - `v2.18`: bounded Workflow Lisp list traversal, mapping, list loop state,
    and rooted path joining
  - `v2.19`: exact opaque transportable `Value`
  - `v2.20`: Workflow Lisp prompt fragments
  - `v2.21`: Workflow Lisp prompt output positions
  - `v2.22`: Workflow Lisp prompt-attempt identity and diagnostics
  - `v2.23`: Workflow Lisp phased contract delivery

- Ordering note
  - D2a scalar bookkeeping is intentionally sequenced before D3 cycle guards.
  - Rationale: scalar bookkeeping only extends the current top-level name-keyed execution/result shape, while cycle guards introduce persisted counters and resume-sensitive control-flow state.
  - The first durable identity and schema migration remains reserved for the later D4-D5 tranche.

- Planned future (declarative per-item lifecycle)
  - `for_each.on_item_complete` with `success.move_to` / `failure.move_to` directories.
  - Version gating and rollout details are deferred until feature implementation.

## Declarative Task Lifecycle for for_each (Planned)

Status: Planned future feature. Opt‑in, version-gated. Does not change current defaults.

Version gating:
- To be finalized at implementation time.

Purpose:
- Reduce boilerplate by declaratively moving a per‑item task file after an iteration completes, based on item success/failure.

Schema (inside `for_each`):
```yaml
on_item_complete?:
  success?:
    move_to?: string   # Destination directory under WORKSPACE; variables allowed
  failure?:
    move_to?: string   # Destination directory under WORKSPACE; variables allowed
```

Semantics:
- Trigger timing: Evaluated once per item after its `steps` finish.
- Success: All executed steps ended with `exit_code: 0` after retries, and no `goto` escaped the loop before finishing.
- Failure: Any step failed after retries, or a timeout (124) remained, or a `goto` jumped outside the loop/`_end` before finishing.
- Recovery: If a step fails but is recovered by `on.failure` and the item completes, the item counts as success.
- Variable substitution: `${run.*}`, `${loop.*}`, `${context.*}`, `${steps.*}` are supported in `move_to`.
- Path safety: `move_to` follows the same rules as other paths and must resolve within WORKSPACE. Absolute/parent‑escape paths are rejected.
- Missing source: If the original item path no longer exists when applying the action, record a lifecycle error; do not change the item's result.
- Idempotency/resume: Lifecycle is idempotent; on resume, previously applied actions are not repeated.

State recording (per iteration):
```json
{
  "lifecycle": {
    "result": "success|failure",
    "action": "move",
    "from": "inbox/engineer/task_001.task",
    "to": "processed/20250115T143022Z/task_001.task",
    "action_applied": true,
    "error": null
  }
}
```

Example:
```yaml
version: "1.2"
steps:
  - name: CheckEngineerInbox
    command: ["find", "inbox/engineer", "-name", "*.task", "-type", "f"]
    output_capture: "lines"

  - name: ProcessEngineerTasks
    for_each:
      items_from: "steps.CheckEngineerInbox.lines"
      as: task_file
      on_item_complete:
        success:
          move_to: "processed/${run.timestamp_utc}"
        failure:
          move_to: "failed/${run.timestamp_utc}"
      steps:
        - name: Implement
          provider: "claude"
          input_file: "${task_file}"

        - name: CreateQATask
          command: ["bash", "-lc", "echo 'Review ${task_file}' > inbox/qa/$(basename \"${task_file}\").task"]

        - name: WaitForQAVerdict
          wait_for:
            glob: "inbox/qa/results/$(basename \"${task_file}\").json"
            timeout_sec: 3600

        - name: AssertQAApproved
          command: ["bash", "-lc", "jq -e '.approved == true' inbox/qa/results/$(basename \"${task_file}\").json >/dev/null"]
          on:
            failure: { goto: _end }  # Forces item failure; lifecycle will move to failed/
```

Planned acceptance:
1. Success path moves to `processed/…`; failure path moves to `failed/…`.
2. Failure recovered by `on.failure` and item completes → success move.
3. `goto` escaping the loop triggers failure move.
4. Unsafe `move_to` (outside WORKSPACE) rejected at validation.
5. Variable substitution in `move_to` resolves correctly.
6. Idempotent on resume; no double move.
7. Missing source logs lifecycle error; item result unchanged.

- Future planned (JSON stdout validation assertions)
  - For steps with `output_capture: json`: optional `output_schema` and `output_require[...]` assertions.
  - Incompatible with `allow_parse_error: true`.
  - Version-gating target will be finalized when implemented.

## Version Gating Summary

| DSL version | Key features enabled | Notes |
| --- | --- | --- |
| 1.1 | Baseline DSL; providers (argv/stdin), `wait_for`, `depends_on` (required/optional), `when` (equals/exists/not_exists), retries/timeouts, strict path safety | State schema initially 1.1.1 (separate track). Unknown DSL fields rejected. |
| 1.1.1 | `depends_on.inject` (list/content/none), injection truncation recording | Workflows must declare `version: "1.1.1"` or a later supported version to use `inject`. |
| 1.2 | `artifacts(kind=relpath|scalar)`, `publishes`, `consumes`, `prompt_consumes` with runtime publish/consume enforcement | Keeps `expected_outputs` as file-validation primitive; adds provenance/freshness guarantees plus optional prompt-noise reduction and scalar consume flow. |
| 1.3 | `output_bundle`, `consume_bundle`, and `publishes.from` support for bundle fields | Reduces deterministic I/O fragmentation while preserving v1.2 publish/consume guarantees. |
| 1.4 | Read-only relpath consume semantics (no consume-time pointer mutation) | Preserves v1.2/v1.3 behavior by version; command steps should prefer `consume_bundle` for deterministic consumed values. |
| 1.5 | `assert` gate steps with dedicated `assert_failed` failure channel | First-class control-flow gates without shell glue; still uses legacy condition forms. |
| 1.6 | Typed predicates, structured `ref:`, normalized `outcome.*` fields | Opt-in typed gate surface; no reinterpretation of legacy `${steps.*}` semantics. |
| 1.7 | `set_scalar`, `increment_scalar` | Narrow runtime primitive for local scalar artifact production plus normal `publishes.from` lineage. |
| 1.8 | `max_transitions`, `max_visits` | Resume-safe cycle guards for top-level raw-graph workflows with persisted transition/visit counters. |
| 2.0 | Stable step `id`, scoped `self.steps.*` / `parent.steps.*` refs, qualified lineage/freshness | Establishes the durable internal identity boundary and the `schema_version: "2.0"` state model. |
| 2.1 | Top-level `inputs`/`outputs`, `${inputs.*}`, `ref: inputs.*`, and CLI input binding | Typed workflow-boundary signatures layered on top of the v2.0 identity/state model. |
| 2.2 | Top-level structured `if/else` with lowered branch markers/join nodes | Branch-local work stays scoped to `then` / `else`; downstream refs target statement outputs on the join node. |
| 2.3 | Top-level `finally` with resume-safe cleanup progress and deferred workflow outputs | Cleanup runs once after body success/failure, keeps stable finalization ids, and suppresses workflow outputs on cleanup failure. |
| 2.4 | Reusable-call contract boundary only (not executable by itself) | Locks path taxonomy, same-version rule, write-root parameterization, and accepted operational-risk language before runtime work lands. |
| 2.5 | `imports` + inline `call` with typed `with:` binding | Uses `schema_version: "2.1"` for persisted call-frame lineage/export state. |
| 2.6 | Top-level structured `match` with exhaustive enum case coverage | Case-local work stays scoped to the selected case; downstream refs target statement outputs on the join node. |
| 2.7 | Top-level post-test `repeat_until` with loop-frame outputs and resume-safe iteration bookkeeping | Loop conditions read only `self.outputs.*`; downstream refs target the loop frame outputs on the authored step; direct nested `call`, `match`, and `if/else` bodies are allowed. |
| 2.8 | Score-aware predicate helper `score` for thresholds and score bands | Thin sugar over numeric typed predicates; keeps benchmark gating inside the existing `when` / `assert` / structured-control surfaces. |
| 2.9 | Advisory authoring linting / normalization hints surfaced in CLI dry-run and report output | Warns about migration candidates without turning valid workflows into validation failures. |
| 2.10 | Scalar `string` contracts and first-class provider-session resume | Adds runtime-owned fresh/resume session handles for root-level provider steps. Its original interrupted-visit quarantine is superseded by the ML-0 at-least-once recovery contract. |
| 2.11 | `adjudicated_provider` steps | Runs isolated artifact-producing candidates, scores valid outputs through a same-trust-boundary evaluator, promotes the selected declared outputs, and records adjudication ledgers/state without stdout-derived step output. |
| 2.12 | `repeat_until.on_exhausted.outputs` | Lets bounded post-test loops route deterministic non-convergence through authored scalar loop-frame outputs while preserving hard failures for body, output, and predicate errors. |
| 2.13 | `managed_jobs` provider-step modifier | Adds runtime-owned managed job interception, guard/shim execution, watcher classification, audit/recovery state, and managed outcome routing for provider-launched training jobs. |
| 2.14 | `materialize_artifacts`, `pre_snapshot`, `variant_output`, `select_variant_output`, and `requires_variant` | Adds deterministic typed materialization, durable snapshot-diff evidence, tagged-union output validation, atomic variant bundle selection, and author-time variant availability proof. |
| 2.15 | Direct JSON root results (`output_bundle` fields with `json_pointer: ""`), public `optional\|list\|map` output and structured-result schemas, strict effect-boundary `guidance` / `guidance_context` / `guidance_by_variant`, and top-level workflow `result_guidance` | Promoted after the combined native-transportable-return and typed-result-guidance gate. Ordinary loader entrypoints, Workflow Lisp shared validation, CLI run/resume/report, dashboard projection, and imported-bundle loading accept the same version. v2.14 rejects the new guidance containers and retains its existing record/union contracts. Guidance is non-runtime metadata and does not change artifact names, value validity, source identities, checkpoint identities, or resume behavior. |
| 2.16 | `.orc` `with-live-providers`, reserved `ProviderSteeringDirective`, structural `session_support.turn_boundary_resume`, default provider observation, and `provider_supervision.v1` | Adds exactly-two-member bounded provider overlap inside one atomic workflow node, one validated observation edge, pure settlement, and at most one exact-session resume. Its original interrupted-visit quarantine is superseded by ML-0 at-least-once recovery. General authored concurrency and parallel blocks remain unsupported. State schema remains `2.1`. |
| 2.17 | `.orc` `with-live-provider-peers`, structural `interactive_session_support`, exact-attempt peer ingress, and `provider_peer_group.v1` | Adds static two-through-eight-member bounded provider overlap with durable record-before-offer receiver ledgers, cooperative acknowledgement/finish, typed direct-root member bundles, pure atomic settlement, natural-shutdown proof, and failed cleanup. Its original interrupted-visit quarantine is superseded by ML-0 at-least-once recovery. It adds no forcing edge and leaves target-2.16 supervision artifacts unchanged. State schema remains `2.1`. |
| 2.18 | Workflow Lisp bounded list traversal, mapping, list loop state, and rooted path joining | Adds `(list ...)`, five total list operators, pure `list/map`, bounded `list/map-effect`, structurally eligible `List[T]` loop state, and pure containment-checked `path/join-under`. New pure expressions use payload schema 2 and effectful mapping erases to existing loop/call/checkpoint machinery; state schema remains `2.1`. |
| 2.19 | Compiler-owned exact `Value`, `type: value`, and public `kind: value` | Adds an opaque strict-JSON transport contract with exact source compatibility, sole direct-root `__result__` carriage and no envelope, recursive failure paths, description/format-hint guidance without examples, and unchanged state schema `2.1`. Classic/WCC, state, checkpoint, and resume preserve the declared type rather than payload shape; targets below 2.19 reject it. |
| 2.20 | Workflow Lisp `defprompt`, closed fragment slots, and prompt-owned structured returns | Adds fully applied importable fragments, exact v1 fragment identity/carriage, schema-2.1 prompt snapshots, and compatible completed-boundary reuse. |
| 2.21 | Workflow Lisp `(slot :path :out [PathType])`, `compiled_prompt_fragment_identity.v2`, and `compiler_prompt_fragment_contract.v2` | One authored path fill drives rendering plus one required UTF-8 file contract. The generated file contract composes with exactly one prompt-owned structured result in fixed order, rejects name/destination collisions before launch, and commits both artifact maps state-atomically. |
| 2.22 | Workflow Lisp direct-fragment prompt-attempt identity, functional-v2 evidence, and additive prompt-context reports | Requires the compiler-owned identity-version/binding-plan pair, seals five content-free roles plus exact prepared-prompt composition after invocation preparation and before launch, classifies retry drift in fixed order, and preserves target-2.20/2.21 execution and evidence bytes. |
| 2.23 | Workflow Lisp explicit phased contract delivery | Adds optional `:delivery :composed|:phased` and phased-only literal materialization attempts, exact `T1 || T2 == C` delivery inside one provider process, bounded same-client correction, identity-v2/functional-v3/phase-ledger evidence, and report-v2 actual-delivery comparison. Omitted/explicit composed calls preserve the ordinary path and identity-v1/functional-v2 bytes; state schema remains `2.1`. |
| future (planned) | `for_each.on_item_complete` declarative per-item lifecycle (move_to on success/failure) | Opt-in lifecycle automation; detailed gating/version target will be set when implemented. |
| future (planned) | JSON stdout validation: `output_schema`, `output_require` for steps with `output_capture: json` | Enforces schema and simple assertions; incompatible with `allow_parse_error: true`. |
