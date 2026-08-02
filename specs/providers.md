# Providers and Prompt Delivery (Normative)

Fresh authored workflows reach this contract through compiled `.orc` source
only. The mapping snippets below describe the validated Core/executable provider
shape; YAML-fenced snippets are schema notation, not accepted workflow files.

- Provider attempt lifecycle
  - At-least-once recovery applies to a validated interrupted in-flight
    ordinary, session, supervision, peer-group, or phased provider visit.
    Ordinary dispatch uses the next unused attempt ordinal and never reuses
    partial attempt content. Compatible completed-result reuse remains
    invocation-free.
  - Recovery is runtime control, not provider guidance. It emits
    `provider_attempt_interrupted_rerun` to the operator and does not add an
    instruction to the prompt.
  - Managed-job recovery, declared resource-transition replay, provider
    isolation transfer reconciliation, root/callee checksum guards, checkpoint
    validation, and atomic structured-result publication remain governed by
    their existing contracts.

- Provider templates
  - Define CLI command and input mode:
    - `command: string[]` may reference `${PROMPT}` in argv mode.
    - `input_mode: 'argv' | 'stdin'` (default: 'argv').
  - `defaults`: map of provider parameters (e.g., `model`).
  - v2.10 session-capable templates may also declare `session_support`:
    - `metadata_mode`
    - `fresh_command`
    - optional `resume_command`
    - optional boolean `turn_boundary_resume` (default `false`)
  - v2.17 peer-group-capable templates may also declare the closed
    `interactive_session_support` object:
    - `schema_version: "interactive_terminal_turn_queue.v1"`
    - `turn_boundary_messages: true`
    - `command`: non-empty ordered tokens containing exactly one unescaped
      `${PROMPT}` and no unescaped `${SESSION_ID}`
    - `message_submit_keys`: non-empty ordered tokens from the adapter's
      closed, non-forcing key vocabulary (v1 tokens are exactly `ENTER` and
      `TAB`)
    - `graceful_close_text`: non-empty ordinary provider-client command
    - `graceful_close_submit_keys`: non-empty ordered tokens from the same
      closed, non-forcing key vocabulary
  - `interactive_session_support` is an explicit structural capability. It is
    never inferred from provider name, argv/stdin mode, TTY behavior,
    observation support, `session_support`, or
    `session_support.turn_boundary_resume`. Its command, graceful-close
    command, and submit sequences are separate from the v2.16 resume/steering
    surface. Unknown capability fields, unsupported schema versions, malformed
    placeholders, and forcing key/action tokens reject the template.
  - `${SESSION_ID}` is legal only inside `session_support.resume_command`, which must contain exactly one placeholder when present.
  - `turn_boundary_resume: true` is a structural capability declaration. It
    is valid only when `fresh_command` and `resume_command` are non-empty
    string lists, the resume command contains exactly one unescaped
    `${SESSION_ID}`, neither command contains an exact `--ephemeral` argument,
    and the selected metadata codec can report one stable session identity and
    a validated preterminal resume boundary. Provider name, input mode, TTY
    behavior, or session support without that declaration never implies the
    capability.

- Step usage
  - `provider: <name>` uses the template; merge `defaults` overlaid by `provider_params` (step wins).
  - `provider` may contain `${run|context|inputs|steps.*}` substitutions. The resolved provider name is validated immediately before provider template lookup and execution.
  - Provider aliases resolve in the active workflow provider namespace. Imported workflows do not inherit or merge caller provider templates; pass role choices through declared inputs and define supported aliases inside the callee.
  - v2.10 top-level provider steps may also declare `provider_session` to select either `session_support.fresh_command` or `session_support.resume_command`.
  - In this tranche, `provider_session` steps require a static provider alias because frontend-build-time session-support validation must inspect the provider template.
  - Provider steps with `output_bundle.path` or `variant_output.path` receive the runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding for the resolved workspace-relative bundle target. The runtime creates or validates the declared parent directory before launch, and that declared bundle file remains the only structured-output authority.
  - For v2.15 contracts, provider prompt composition renders validated
    effect-boundary `guidance`, field guidance, ordered `guidance_context`, and
    discriminant-ordered `guidance_by_variant` as data in the output-contract
    suffix. It does not render top-level workflow `result_guidance`, and no
    guidance container changes the value schema or bundle authority.
  - For a target-2.19 `Value` result, the generated contract describes one
    opaque JSON document at the direct root. It may include authored
    description and format hint, but never a `Value` example, invented fields,
    the compiler-owned `__result__` name, or a `{"value": ...}` envelope.
  - `provider_session` command selection changes only the provider command template. It preserves any preexisting runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding on the prepared invocation.
  - v2.13 provider steps may declare `managed_jobs` as a step modifier. The provider template remains ordinary; after existing provider and provider-session command selection, the runtime wraps the selected invocation with the managed-job guard and owns audit/recovery state.
  - `managed_jobs` wrapping preserves any preexisting runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding while adding `MANAGED_JOB_*` transport metadata. Guard state, audit files, and provider-session spools are not alternate structured-output authorities.
  - In argv mode, `${PROMPT}` is replaced by the composed prompt (see below).
  - In stdin mode, the composed prompt is piped to the child stdin; provider templates MUST NOT include `${PROMPT}`.
  - Provider prompt sources are distinct from workflow-boundary `inputs` / `outputs`, runtime dependencies (`depends_on`, `consumes`), and artifact storage / lineage (`artifacts`, `expected_outputs`, `output_bundle`, `publishes`).
  - Reusable-workflow prompt assets:
    - `input_file` stays workspace-relative and is for workspace-owned or runtime-generated prompt material.
    - `asset_file` is the workflow-source-relative prompt/template surface for bundled reusable-workflow assets.

- Workflow Lisp call-local provider policy
  - Ordinary Workflow Lisp `provider-result` may author the closed canonical
    options `model` and `effort`, plus a positive literal timeout. Target 2.23
    additionally accepts explicit `delivery` and bounded literal
    `materialization_attempts`. The closed internal `provider_call_policy`
    mapping orders present keys as `model`, `effort`, `delivery`, then
    `materialization_attempts`; timeout remains the existing common
    `timeout_sec` field.
  - Model and effort are provider-bound. Delivery and materialization attempts
    are runtime-only call policy: they are not legal
    `call_policy_bindings`, are never merged into provider parameters, and
    never alter provider argv. Complete absence emits no policy mapping and
    preserves the provider template's existing defaults and argv behavior.
  - `ProviderTemplate.call_policy_bindings` is declarative provider data. Its
    keys are exactly `model` and `effort`, and each value must be a public
    `CallPolicyBinding(target_param: str, argv_fragment: Sequence[str] | None)`
    imported from `orchestrator.providers`. Programmatic custom templates must
    construct that dataclass; arbitrary dictionaries are invalid. Both built-in
    registry initialization and public registration run the same validation.
    The public construction contract is:
    ```python
    from orchestrator.providers import CallPolicyBinding, ProviderTemplate

    custom = ProviderTemplate(
        name="custom",
        command=["custom", "--model", "${model}"],
        call_policy_bindings={
            "model": CallPolicyBinding(target_param="model"),
        },
    )
    ```
  - `target_param` is one non-reserved bare provider-parameter identifier, not a
    `${...}` token. General command placeholder extraction continues to accept
    dotted runtime/context placeholders such as `${inputs.model}` and
    `${steps.Prepare.output}`; only `target_param` uses the separate bare-name
    validator. Targets are unique across one declaration and need not have a
    provider default.
  - Declaration validation counts unescaped placeholders after the ordinary
    command-token escape processing. A direct binding requires exactly one
    `${<target_param>}` in every applicable base, fresh-session, and
    resume-session command. A fragment binding requires zero such placeholders
    in those commands and exactly one dynamic placeholder—the matching target—in
    its ordered `argv_fragment`. Missing, duplicate, mismatched, extra, reserved,
    or non-string fragment placeholders reject registration.
  - Preparation translates provider-bound canonical values without
    substitution, then performs exactly one merge with precedence `provider
    defaults < provider_params < translated canonical overrides`. It applies
    the existing parameter substitution exactly once to that merged mapping,
    appends present fragments in canonical `model`, then `effort` order, and
    invokes the existing command builder. Runtime-only delivery values are
    consumed by the executor/coordinator before this translation and are
    excluded from it. The existing substitution owner retains
    `substitution_error`.
  - A present canonical option without a declared binding fails before process or
    session creation with exit `2` and
    `error.type: provider_call_policy_unsupported`. Its bounded context contains
    only the resolved provider identifier and canonical option; enclosing
    provider-result provenance may be retained, but policy values, prompts,
    secrets, and invented field spans may not be exposed.
  - Authored `.orc` cannot directly populate the internal step key
    `provider_call_policy` or provider-template key `call_policy_bindings`.
    Compiler lowering and validated provider externs own those surfaces.
    Lower-level Core `provider_params` behavior is unchanged.

- Shared unrestricted invocation profiles
  - `codex_unrestricted_workspace` has no defaults, uses stdin, binds
    `model -> model` and `effort -> reasoning_effort`, and has exact command
    `["codex", "exec", "--dangerously-bypass-approvals-and-sandbox",
    "--skip-git-repo-check", "--model", "${model}", "--config",
    "reasoning_effort=${reasoning_effort}"]`.
  - `claude_unrestricted_workspace` has no defaults, uses stdin, binds
    `model -> model` and `effort -> effort`, and has exact command
    `["claude", "-p", "--model", "${model}", "--effort", "${effort}",
    "--permission-mode", "bypassPermissions"]`.
  - These profiles are generic provider data. Their presence does not prove
    workflow-family parity or promotion eligibility.

- Provider-phase isolation policy (versioned contract; runtime integration pending)
  - `provider_phase_isolation.v1` is an external runtime-owned JSON policy,
    not provider-template data or authored workflow data. Its closed top-level
    fields are `schema_version`, `mode`, `backend`, `session_mode`,
    `workspace`, `provider_environment`, `process_environment`,
    `result_bundle`, `shared_network_review`, and `history_retrieval`; unknown
    fields and versions are rejected recursively.
  - V1 accepts only `mode: required`, `backend: bubblewrap.v1`, and
    `session_mode: fresh_only`. Candidate access is `read_write` while the
    runtime-owned `.orchestrate` subtree is masked. The selected provider
    environment is a sealed, digest-verified rootfs snapshot with a distinct
    absolute provider-visible build prefix; ambient host roots and mutable
    controller toolchains are not substitutes.
  - `provider_environment_manifest.v1` is the closed identity of that rootfs.
    It records the provider prefix, the root row, and every descendant in
    canonical UTF-8 path order. Rows bind kind, normalized read-only mode,
    provider-visible `uid: 0`/`gid: 0`, fixed zero timestamps, and either file
    size/content digest or original safe symlink text. Its canonical SHA-256 is
    the `provider_environment.digest`; it is distinct from the whole isolation
    policy digest.
  - Runtime snapshots are fresh, run-owned publications at exactly
    `provider_environment_snapshots/<provider_environment.digest>/rootfs`.
    Assembly copies from a descriptor-pinned admitted source into private
    staging, normalizes and durably verifies every inode, publishes
    atomically, and launches only from the pinned published root descriptor.
    Source mutation after publication cannot change the snapshot identity;
    mutation, metadata drift, an existing digest authority, or inability to
    preserve the fixed timestamp contract fails closed.
  - `bubblewrap.v1` launches directly as the unprivileged controller user; it
    must not depend on per-run `sudo`, `pkexec`, privileged `setpriv`, a
    set-id group-clearing helper, or a capability-bearing broker. Retained
    supplementary groups are not assumed harmless merely because the child
    renders them as the overflow GID: host-relative observation must bind the
    final child's underlying group multiset to the controller's prelaunch
    multiset, while the inner shim validates one-row maps,
    `setgroups: deny`, all-zero real/effective/saved/filesystem UID/GID
    columns, and primary/overflow-only normalized counts before reading
    credentials. The live overflow GID must be nonzero and distinct from
    provider primary GID `0`; otherwise the backend is unavailable. The
    positive mount allowlist, controller ownership
    of writable host-backed projections, and final `{0,1,2}` descriptor set
    are the actual no-additional-object-authority proof. Any mismatch or
    unsupported proc/user-namespace behavior fails closed.
  - Bubblewrap's reported child PID is identity input, not proof that the shim
    reached its final boundary. The shim emits one fixed readiness byte on a
    setup-only descriptor after inner validation and before reading credential
    fd 3. The controller releases no credential byte until it has both that
    signal and a pidfd/proc-start-bound host observation that passes the exact
    map, `setgroups`, and group-multiset checks. The readiness descriptor is
    then closed and cannot survive provider exec; any race, mismatch, malformed
    signal, or changed child identity fails closed.
  - The snapshot assembler reserves
    `<provider_prefix>/libexec/provider-launch-shim-v1.py` for the
    runtime-packaged shim. Its source bytes must match an independently pinned
    reviewed digest. Strict launch admission additionally requires the reviewed
    fixed `<provider_prefix>/bin/python -I -S` bootstrap and its manifest-backed
    interpreter, ELF loader/library, Python import, and startup configuration
    closure. Provider entrypoints receive the same non-executing shebang/ELF
    closure validation before launch; discovery never runs `ldd` or executes
    the target in the controller namespace.
  - Omitting the policy preserves the current unrestricted provider launcher,
    environment inheritance, and security claim. Once public run/resume
    integration is present, a required policy must fail before provider launch
    whenever its environment, backend, or requested capability cannot be
    enforced; it may never warn and fall back to the unrestricted launcher.
  - Direct provider credentials are exactly the intersection of
    `process_environment.credential_env` and the provider step's declared
    `secrets`. A policy-listed name that the step did not declare is not
    granted. A declared name outside the policy or absent from the controller
    environment fails before launch. Authored provider `env` is unsupported in
    v1 apart from runtime-owned bindings.
  - `history_retrieval` represents provider API transport separately from
    remote Git, browser, source-search, and repository-fetch retrieval. V1
    allows provider transport and requests denial of all four retrieval
    channels; `eligibility_requirement` is `classify` or `require_causal`.
    `shared_network_review` binds an absolute controller-private inventory
    path, its canonical SHA-256 identity, and the sole v1 decision
    `accept_unlisted_reachability`.
  - Built-in provider bypass flags do not establish this boundary. A copied
    workspace likewise remains only an orchestrator-managed validation and
    promotion boundary, not an OS sandbox.
  - This section defines the staged policy contract only. The policy loader and
    schema do not make provider execution isolated; the feature must not be
    described as available until the launcher, state, CLI, resume, and
    attestation integration gates land.

- Managed provider job policy JSON (v2.13)
  - `managed_jobs.policy` points to workspace-relative JSON that classifies payloads launched by the guarded provider process. It is separate from provider-template configuration.
  - Minimal explicit-metadata shape:
    ```json
    {
      "backend_defaults": {
        "backend": "local"
      },
      "entries": [
        {
          "id": "train_model",
          "mode": "force_managed",
          "path": "scripts/training/train.py",
          "backend": "slurm",
          "job": {
            "name_template": "train-{job_identity_hash}",
            "state_root_template": "state/managed_jobs/{entry_id}/{job_identity_hash}",
            "output_root_arg": "--output-dir",
            "verify_files": [
              "{output_root}/metrics.json"
            ],
            "snapshot_roots": [
              "scripts/training"
            ],
            "config_globs": [
              "configs/training/*.yaml"
            ]
          }
        }
      ]
    }
    ```
    `backend` accepts `auto`, `local`, or `slurm`; `mode` accepts
    `force_managed`, `auto_managed`, `force_local`, or `unmanaged`.
  - Named extractors may be declared under top-level `extractors` and referenced from an entry with `extractor: <name>` instead of inline `job` metadata.
  - Managed modes (`force_managed`, `auto_managed`) require complete `job` metadata or an `extractor` that derives the same metadata. Missing state root, verification targets, snapshot inputs, or extractor output is invalid before launch.
  - Unmanaged modes (`force_local`, `unmanaged`) run locally through the original payload path and do not append managed-job audit events.
  - `state_root_template` and snapshot/config paths are workspace-relative and path-safe. `state_root_template` may use `{entry_id}` and `{job_identity_hash}`.
  - Job identity includes normalized payload arguments, source hashes, config hashes, extractor identity/version, policy-entry hash, and snapshot manifest inputs.
  - `backend: local` executes the payload from the immutable snapshot workspace and records the same identity metadata as Slurm. `backend: slurm` generates a snapshot-bound submission script or a script with preflight source/config hash checks.
  - Supported shim payloads are direct `python`, `python3`, and `torchrun`; `conda run ... python|torchrun ...`; and `uv run python|torchrun ...`. Unsupported `conda`/`uv` forms fail closed unless explicitly classified unmanaged.

- Prompt composition
  - Read exactly one base prompt source:
    - `input_file` literally from WORKSPACE for workspace-owned or runtime-generated prompt material, or
    - `asset_file` literally from the directory containing the authored workflow file for bundled reusable-workflow assets.
  - `asset_depends_on` source assets are injected in-memory as deterministic content blocks in declared order.
  - Apply workspace dependency injection in-memory if `depends_on.inject` is enabled (see `dependencies.md`).
  - For `version: "1.2"` provider steps with `consumes`, inject a deterministic `Consumed Artifacts` block by default using resolved consume values from preflight (not prompt-authored paths).
    - Disable with `inject_consumes: false`.
    - Position with `consumes_injection_position: prepend|append` (default `prepend`).
    - Limit scope with `prompt_consumes: [artifact_name, ...]` to inject only selected consumed artifacts.
    - `prompt_consumes: []` suppresses the consumed-artifacts block entirely.
    - Each selected `consumes[*]` row may also declare `prompt.mode: content|reference|none` plus additive prompt guidance (`label`, `description`, `format_hint`, `example`, `role`).
    - Omitted `prompt.mode` defaults to `content`. Nested `prompt.*` guidance overrides row-level `description`, `format_hint`, and `example` when both are present.
    - `content` preserves ordinary consumed-artifact prompt rendering for the selected resolved value.
    - `reference` renders deterministic metadata only (`mode: reference`, artifact identity, optional label/role/guidance, and the resolved value/path). It must not read or embed relpath target body content in the candidate prompt.
    - `none` suppresses only candidate-prompt text for that consume row. It does not change consume selection, lineage, freshness, resolved values, or `consume_bundle`.
    - If every selected consume row resolves to `mode: none`, omit the consumed-artifacts block entirely.
    - Footer text depends on the rendered row mix:
      - content-only rows: use the consumed artifacts as prompt context
      - reference-only rows: open referenced artifacts only when needed
      - mixed content/reference rows: use embedded content as context and open references only when needed
    - Scalar values render directly; list/map consume values render as deterministic JSON text. Prompt rendering is a view over resolved consume values, not semantic authority.
    - These annotations and render modes are prompt guidance only and do not change runtime consume enforcement semantics.
    - v2.10 resume steps reserve the `session_id_from` consume for runtime `${SESSION_ID}` binding; that consume is excluded from prompt injection and `consume_bundle`.
  - If the step defines `expected_outputs`, `output_bundle`, or
    `variant_output` and `inject_output_contract` is not `false`, append the
    deterministic contract suffixes describing required artifacts (`name`,
    `path`, `type`, optional constraints) and/or the required JSON bundle
    (`path`, `fields[*].json_pointer`, `fields[*].type`, optional
    constraints). An admitted target-2.21 pair renders exactly two blocks in
    fixed `expected_outputs`-then-structured-contract order; a single contract
    continues to render one block.
    - An `output_bundle` whose sole field uses `json_pointer: ""` (a direct
      root value) renders a "write one JSON value" suffix describing the root
      type and its resolved path, not an object/`fields:` list — the prompt
      never claims a JSON object for a scalar/enum/relpath/optional/list/map
      root result, and never names or requests the compiler-owned `__result__`
      field key.
    - At v2.19, the same direct-root rendering applies to `type: value`
      regardless of whether the attempt returns `null`, a scalar, a list, or
      an object. The renderer does not infer or advertise a narrower schema
      from an example payload.
    - `expected_outputs.path`, `output_bundle.path`, and `variant_output.path` entries in this suffix are rendered after applying the same runtime variable substitution used for output-contract validation, so provider prompts show workspace-relative concrete paths rather than unresolved `${...}` templates.
    - Optional `expected_outputs` guidance annotations (`description`, `format_hint`, `example`) are included in this suffix when present.
    - These annotations and rendered concrete paths are prompt guidance only. Prompt text does not replace the runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding or change runtime contract validation semantics.
  - Do not modify files on disk; only the composed prompt is delivered to the provider.

- Workflow Lisp typed provider inputs
  - Every supported scalar, record, relpath, target-2.19 exact `Value`, or
    recursively renderer-admitted `List[T]` binding declared in
    `provider-result :inputs` lowers to one typed prompt-input row, including
    calls with no census, family-profile, or route metadata.
  - Static structural type/kind selects exactly one registered default
    renderer: canonical JSON for supported scalars, records, opaque `Value`,
    and recursively renderer-admitted `List[T]`; POSIX path-line rendering for
    relpaths. Rendering a `Value` preserves its JSON shape without granting
    field or collection semantics. Missing, unknown, shape-incompatible, or
    ambiguous selection fails before provider launch.
  - Ordinary calls lower each binding with a registered implicit default.
    Unsupported bindings do not acquire a renderer or prompt visibility merely
    because a supported binding is adjacent; they require a separately
    implemented checked route.
  - A phase lowering that owns a whole-input materialization fallback selects
    that fallback atomically when any binding lacks an implicit default. It
    never lets a supported typed subset suppress materialization of the
    unsupported remainder. A phase-derived lowering that has lost that fallback
    fails before provider launch instead of emitting a partial set.
  - Runtime resolves each lowered binding once and requires a one-to-one
    correspondence among lowered rows, resolved values, rendered blocks, and
    structured evidence. Missing values or evidence mismatches fail before
    invocation preparation.
  - Rendering is ephemeral and allocates no bridge or view file. Typed state
    remains semantic authority; rendered bytes and evidence never become
    provider-result, routing, checkpoint, or resume authority.
  - Root and nested provider calls use the same prompt-composition owner.
    `:prompt-dependencies` remains the separate mechanism for injecting a
    relpath target's contents.

- Workflow Lisp provider prompt dependencies
  - `provider-result :prompt-dependencies (:required ... :optional ...)` contributes typed required and optional exact workspace `relpath` operands to the ordinary workspace-dependency composition stage. Position defaults to `prepend`; `append` is the only alternative; an optional instruction is literal text and never provider-parameter substitution.
  - The composition pipeline first builds the base prompt plus source-relative `asset_depends_on`, applies the per-attempt dependency block at its declared position, then applies typed prompt inputs, consumed-artifact injection under its own position policy, and the output-contract suffix. Pipeline order does not override a stage's explicit prepend/append policy.
  - Ordinary and adjudicated provider execution use the same snapshot/render owner. Each relevant attempt receives exactly one immutable dependency snapshot shared by rendering and prompt finalization; no stage reopens a dependency. Each retry takes a fresh snapshot before provider preparation.
  - The completed provider result and its lexical checkpoint include the compiled dependency contract. Compatible completed-result reuse returns the committed structured result without reopening current dependency files. A pending or failed provider boundary takes a new snapshot for its new attempt.
  - The exact UTF-8 dependency block is limited to `262144` bytes as specified by `dependencies.md`; truncation is deterministic and explicit.
  - Prompt-dependency evidence is narrower than snapshot/render reuse: only an ordinary typed Workflow Lisp attempt carrying the validated compiler contract derives Workflow Lisp prompt-dependency evidence. Adjudicated paths without that ordinary typed carrier emit no such evidence; their existing debug/state output is separate. Historical YAML content-injection behavior remains comparison evidence only and is not reachable through fresh workflow execution.

- Workflow Lisp prompt fragments (target 2.20)
  - `defprompt` is a compile-time module declaration, not a runtime value,
    `ProcRef`, provider, or general callable. It may be used only as one direct,
    fully applied named application in `provider-result :prompt`.
  - The declaration owns one closed set of `doc`, `text`, `value`, and `path`
    fills plus the provider result `ReturnSpec`. A fragment-backed call must not
    also declare `:inputs`, `:prompt-dependencies`, or `:returns`. Existing
    extern-backed provider calls are unchanged.
  - The runtime renders `text` as raw UTF-8, selects the unique registered
    canonical-JSON renderer for supported `value` slots, and selects the
    existing POSIX path-line renderer for `path` slots. Target 2.20 admits
    recursive `List[T]` canonical JSON only when `T` is already in the closed
    supported fragment renderer set. Missing, incompatible, unsupported, or
    ambiguous renderer selection fails before provider launch.
  - `doc` fills lower to one required, fixed-`prepend` dependency contract with
    origin `workflow_lisp_prompt_fragment`; they do not render through template
    placeholders. The fragment base then reuses the ordinary dependency,
    consumed-artifact, output-contract, and provider-transport composition
    owners. The output contract is appended exactly once and the validated
    bundle remains result authority.
  - The compiler carries one closed `CompilerPromptFragmentContract` and one
    `compiled_prompt_fragment_identity.v1` SHA-256 identity through Semantic
    and Executable IR. The attempt publishes
    `workflow_prompt_fragment_snapshot.functional.v1` as
    `record_kind: prompt_snapshot` through the schema-2.1 attempt allocator.
    The fragment-contract, Semantic, Executable, and attempt identities must be
    present, well formed, and byte-equal before provider preparation.
  - Prompt snapshot records and indexes are non-authoritative evidence.
    Compatible completed-result reuse follows the existing program,
    checkpoint, bound-input, and completed-boundary guards and does not read
    evidence or execute the provider again. A changed fragment identity is
    ordinary program drift.

- Workflow Lisp prompt output positions (target 2.21)
  - `(slot-name :path :out [PathType])` retains ordinary POSIX path-line
    rendering and additionally projects one compiler-owned required UTF-8
    `expected_outputs` row from the same normalized slot and fill. The
    rendered path and resolved validation destination must be equal.
  - Before provider launch, the runtime resolves every output-position and
    structured-bundle destination, rejects duplicate artifact names,
    pairwise output-position aliases, and output-position/bundle aliases, and
    ensures no authored or provider environment can replace the runtime-owned
    bundle destination.
  - Prompt composition appends exactly one output-position block followed by
    exactly one structured-result block. The declared file and bundle paths
    remain semantic authority; provider prose and stdout do not.
  - Successful provider execution validates in the same
    output-position-then-structured-result order. Neither artifact mapping is
    published unless both contracts validate, after which their disjoint maps
    merge once into ordinary step artifacts.
  - Q2 applications carry `compiled_prompt_fragment_identity.v2` and
    `compiler_prompt_fragment_contract.v2`; every ordered
    `output_positions[*].expected_output` object must equal the corresponding
    executable provider-configuration `expected_outputs` row.
    Q1-only applications retain exact v1 bytes and behavior at targets 2.20
    and 2.21.

- Workflow Lisp prompt-attempt identity and diagnostics (target 2.22)
  - The surface is limited to a direct fragment-backed `provider-result`.
    It adds no authored prompt syntax, coordinated-provider support, or
    identity for arbitrary provider calls.
  - The unchanged compiled fragment identity is the `fragment_program` role.
    Four additional closed roles identify declaration-ordered resolved
    bindings (`resolved_bindings`), exact shown dependency material
    (`injected_dependencies`), exact runtime contribution segments
    (`runtime_contributions`), and the effective prepared provider policy
    (`provider_policy`). The record also seals the exact prepared final-prompt
    bytes and the five-role composition.
  - Provider policy is projected from the exact prepared invocation as
    provider name, canonical model/effort, timeout, and input mode. It is
    never parsed from argv and contains no command or environment values.
  - Target 2.22 renders fragment and contribution owners once, successfully
    prepares the invocation, validates/seals
    `workflow_prompt_fragment_snapshot.functional.v2`, publishes it through
    the ordinary attempt allocator, and only then launches the provider.
    Preparation or publication failure launches no provider.
  - The fixed drift order is `instruction_drift`, `input_drift`,
    `dependency_content_drift`, `runtime_prelude_drift`, then
    `provider_policy_drift`; equality emits
    `prompt_context_unchanged`. Equal role digests with unequal final-prompt
    digests fail closed as `prompt_identity_composition_mismatch`.
  - Records and comparisons are content-free provenance only. They do not
    select providers, settle attempts, validate business results, or
    participate in checkpoint/resume compatibility. Targets 2.20 and 2.21
    preserve their existing invocation and functional-v1 evidence bytes.

- Workflow Lisp ordinary identity-v1 judgment association
  - A provider call is eligible for the generic attempt/result association if
    and only if all of these structural conditions hold:
    - it is a direct fragment-backed provider call with a compiled fragment
      contract;
    - its effective delivery is ordinary composed delivery: omitted on the
      pre-2.23 surface or exact `:delivery :composed`, never phased;
    - its compiled carrier is exact
      `workflow_prompt_attempt_identity.v1`;
    - its published evidence is exact
      `workflow_prompt_fragment_snapshot.functional.v2` and embeds that same
      identity-v1 schema;
    - it has one root-owned provider-attempt scope and one unique immutable Q3
      evidence record at that scope and ordinal's deterministic path; and
    - it has one validated committed provider result after the unchanged Q2
      output-position and structured-result validation in `io.md`.
    Target version, workflow/module/provider/step/family names, result type,
    and field spelling never establish eligibility. Unknown delivery,
    identity, or evidence versions are ineligible rather than inferred.
  - One eligible committed result receives one association with the exact
    successful attempt ordinal and that ordinal's exact validated Q3 record.
    Every attempted launch retains its ordinary Q3 evidence, but a
    failed-then-successful retry binds only the successful attempt ordinal.
    The runtime never selects the newest, last allocated, or
    successful-looking attempt by proximity.
  - A target-2.23 phased call carries
    `workflow_prompt_attempt_identity.v2` and
    `workflow_prompt_fragment_snapshot.functional.v3`; it is Q4-ineligible
    before locator construction, receives no association, and does not later
    appear as a missing-binding judgment row. A target-2.23 explicit composed
    call remains eligible only when it satisfies the complete identity-v1 and
    functional-v2 predicate above.

- Workflow Lisp phased contract delivery (target 2.23)
  - Omitted delivery and explicit composed delivery use the ordinary composed
    provider path and never construct the phased coordinator. Explicit phased
    delivery requires the exact structural
    `interactive_terminal_turn_queue.v1` capability; capability absence,
    malformed capability, or runtime drift fails closed with no composed
    fallback.
  - One `timeout_sec` owns the whole attempt deadline. The coordinator shortens
    each adapter or local operation to the remaining budget and does not
    authorize a later action or commit after an operation crosses that
    deadline.
  - The compiler/runtime composes canonical `C` once. It delivers exact prefix
    `T1` as task ordinal zero, then the separator-inclusive suffix `T2` as
    materialization ordinal/submission one, with `T1 || T2 == C`. A retry keeps
    `T2` byte-identical, adds separately accounted diagnostic framing, and uses
    submission two or three. Protocol, submit, and diagnostic frames are
    outside `C`. One provider-attempt ordinal, one provider process, and one
    task delivery own the complete sequence.
  - Before launch, every bound candidate path must be distinct and absent. The
    provider receives an opaque attempt-bound submit binding and a content-free,
    argument-free submit signal. Binding and endpoint-locator derivation is
    inert; actual endpoint allocation/bind begins only after successful
    provider start.
  - On each accepted submit the runtime snapshots candidate bytes, validates
    output-position files first and the structured result second, and publishes
    neither surface. An invalid candidate records a complete content-free
    manifest and resets every bound path to exact absence before a permitted
    retry. A valid candidate is frozen; no further submit can replace it.
  - Success first durably records close intent, then resolves and flushes the
    active submit request's exact `accepted_closing` receipt before offering
    any close bytes. Receipt-flush failure terminalizes without calling
    `offer_close`. Only after a successful flush does the runtime offer and
    durably record natural close, disable and drain ingress, close and join the
    endpoint, validate natural zero-exit provider shutdown, publish terminal
    evidence, restore and verify the frozen candidate, and perform one guarded
    atomic state commit. Only validated output files and the structured bundle
    become workflow authority. Provider stdout, submit receipts, protocol
    frames, phase ledgers, reports, and provisional files are
    non-authoritative.
  - Failed start uses the closed `InteractiveTerminalStartOutcome` and
    handle-free `NoBackendAllocationProof|PhasedFailedCleanupEvidence`
    projection. A later abort still returns the unchanged target-2.17
    handle-bound proof; exact active-handle identity is validated before its
    content-free projection. Missing or mismatched proof identity fails closed.
  - Every failure follows the closed T0–T4 terminal grammar. An allocated
    endpoint has at most one ingress start and one finished-or-failed outcome;
    every pre-natural-proof path has exactly one cleanup outcome overall.
    Receipt of a validated natural proof moves the attempt to
    `JOINED_PENDING_COMMIT`; later evidence, restoration, verification, or
    state-commit failure never aborts the now-terminal provider.

- Workflow Lisp live-provider supervision (v2.16)
  - `with-live-providers` is a `.orc`-only form with exactly two bindings and
    exactly one `:observes` edge. The observer is the supervisor and its peer
    is the worker.
  - Each member is either a direct `provider-result` expression or a direct
    call to a recursively inline-normalizable `defproc :lowering inline`.
    After specialization and inline expansion, each member must contain
    exactly one unconditional provider perform followed by a pure result
    projection. Branches, loops, residual calls, private workflow boundaries,
    additional effects, and multiple provider performs are rejected.
  - The worker may return any transportable type. The supervisor returns the
    reserved compiler-owned `ProviderSteeringDirective`, whose only accepted
    wire objects are exactly `{"variant":"CONTINUE"}` and
    `{"variant":"STEER","guidance":<non-empty string>}`. Unknown fields,
    missing or cross-variant fields, and empty guidance are rejected. Runtime
    control interprets only the validated discriminant; guidance remains
    free-form provider content.
  - The settlement body is pure over the two validated member values, and the
    form returns that body's type. The compiler lowers the whole form to one
    `provider_supervision.v1` executable node with bounded initial overlap,
    one workflow-state/result boundary, and `max_steers: 1`.
  - Static and runtime validation both require the worker's resolved template
    to have valid `turn_boundary_resume: true` support and use the cancellable
    provider process-group lifecycle. The supervisor needs no session
    capability. `STEER` may launch exactly one resume turn only after the
    codec and process lifecycle prove the accepted boundary and exact
    same-session identity; otherwise the group fails closed.
  - The runtime composes the supervisor's structural observation injection
    after ordinary source/dependency/input/consume composition and before the
    output-contract suffix. Its tmux socket and worker target are
    process-local execution data: they may occur in debug prompt evidence but
    never become workflow values, output bundles, persisted state, or resume
    authority.

- Workflow Lisp live-provider peer groups (v2.17)
  - `with-live-provider-peers` is a `.orc`-only form with a literal,
    authored-order list of two through eight uniquely named members. Each
    member is a direct `provider-result` or a direct call that recursively
    specializes through `defproc :lowering inline` to exactly one
    unconditional provider perform followed by a pure projection. Sibling
    results, branches, loops, residual calls, and additional member effects
    are rejected.
  - Every member result may be any transportable type. The settlement body is
    pure, may read exactly the complete member-result environment, and must
    produce a transportable value. The compiler lowers the form to one closed
    `provider_peer_group.v1` executable node with messaging policy
    `all_other_members`, `interactive_session_schema_version:
    "interactive_terminal_turn_queue.v1"`, and `max_steers: 0`.
  - Static and runtime validation require every resolved member provider to
    declare the exact structural `interactive_session_support` capability.
    Providers without it remain valid outside a peer-group member position.
    The interactive adapter owns the provider client pane; the observation
    manager and its display pane are not an input path.
  - One runtime endpoint is created per group visit and is bound to the exact
    run, step, node, visit, and endpoint instance. After root-owned monotonic
    member attempt allocation, each provider receives an opaque binding that
    resolves server-side to one exact member id, attempt scope, attempt
    ordinal, and endpoint instance. The endpoint and opaque bindings are
    process-local handles, not workflow values, result state, checkpoint
    identity, or reusable evidence.
  - The member-visible client surface is exactly:
    `orchestrator peer-ready`, `orchestrator peer-send <target-binding>
    <message>`, `orchestrator peer-ack <message-id>`, and
    `orchestrator peer-finish`. Clients submit one bounded request through
    their runtime-provided endpoint/binding and return its receipt; they cannot
    choose a sender, run root, arbitrary endpoint, state path, ledger path, or
    pane, and cannot write state, ledgers, bundles, or terminal results.
    Messages are non-empty UTF-8 of at most 65,536 encoded bytes; newlines and
    ordinary Unicode are preserved.
  - `peer-ready` is an all-members barrier. Only after every exact member
    attempt is ready does one coordinator transition make the group active.
    Sends while the group is not active, self sends, and sends involving
    stale, closing, terminal, unknown, ambiguous, or cross-group
    member/attempt identities fail without delivery.
  - For an accepted send, the single-writer coordinator durably appends the
    receiver's `recorded` ledger row before asking the exact receiver adapter
    to offer the message at its next natural turn boundary. It then durably
    appends `offered` or `offer_failed`; client success requires `offered`.
    `peer-ack` appends `receiver_acknowledged` only for the exact receiver
    attempt and message id. Exact request-id replay returns the prior durable
    receipt; reuse with a different payload fails closed.
  - `peer-finish` is cooperative and separate from messaging. It is retryable
    with `pending_messages` while any accepted incoming message lacks an
    acknowledgement. Once eligible, it validates and freezes the member's
    exact typed bundle bytes, offers the declared graceful-close command, and
    returns success so the current provider turn can finish naturally. A
    member is terminal only after the client, pane, helper, and process
    boundary are joined with a complete natural-shutdown proof.
  - A peer message cannot cancel, resume, steer, replace, select, settle, or
    directly publish a member. There is no peer-group forcing edge,
    provider-session resume delivery, dynamic membership, cross-run messaging,
    or YAML spelling. Any member, protocol, delivery, bundle, deadline,
    endpoint, or cleanup failure fails the whole group, performs failed
    cleanup, and publishes no settlement.

- Adjudicated provider prompt and evaluator delivery (v2.11)
  - Each candidate uses the ordinary provider prompt composition contract, including step-wide `asset_depends_on`, `depends_on`, `consumes` injection, and deterministic output-contract suffixes. A candidate `asset_file` or `input_file` override replaces only the base prompt source.
  - Candidate provider commands run with `cwd` set to that candidate's isolated workspace. Provider templates, provider params, env, secrets, and prompt transport otherwise follow the normal provider contract.
  - The evaluator prompt is composed from the declared evaluator prompt source plus one runtime-built `Evaluator Packet` block. The evaluator output is strict JSON and does not use the adjudicated step's `output_capture`, `allow_parse_error`, `expected_outputs`, or `output_bundle` settings.
  - Evaluator scoring uses the persisted scorer snapshot and complete embedded score-critical evidence only: rendered candidate prompt, declared output value files, required relpath targets, bundle JSON and required bundle targets, optional rubric content, and selected consume values plus consume relpath target content when applicable.
  - Candidate-prompt consume rendering modes do not weaken evaluator evidence. After reserved-session exclusion and `prompt_consumes` filtering choose the selected consume rows, evaluator packets continue to carry the normalized selected consume values and any selected relpath target file content even when the candidate prompt rendered a row as `reference` or suppressed it with `none`.
  - Evaluators must not depend on reading candidate or parent workspace files, bounded prompt previews, candidate stdout/stderr, transport logs, or other non-scoring sidecars. Those paths may be retained for audit, but they are not score-critical evidence.

- Workflow Lisp trial evaluator delivery (target 2.25)
  - Evaluation begins only after the coordinator freezes the complete admitted
    `(arm, rep)` outcome set and its digest. Deterministic checks then run in
    declared authority order before any judgment call. The runtime constructs
    one closed `trial.evaluation_packet.v1` for each opaque evaluation label;
    neither authored prompts nor evaluator behavior may construct, widen, or
    filter score-critical evidence.
  - A packet contains only the observation members explicitly selected from
    `task_spec`, `validated_result`, `workspace_delta`, `check_results`,
    `declared_artifacts`, and `failure_evidence`. A completed cell may include
    its validated result, bounded normalized E1 workspace delta, permitted
    declared artifacts, and deterministic check results. A failed cell
    includes only explicit failure evidence and other selected facts that
    actually exist. Every item has one unique citable ID.
  - Packet projection always excludes treatment and authored arm IDs; the
    authored `run-ref` source locator, program selector, workflow source text,
    and authored workflow filenames that identify an arm; proposer and
    candidate lineage; child or evaluator completion order; mutable run logs;
    `.orchestrate` state and sidecars; previous scores; and provider/model
    identity. This exclusion does not redact normalized changed-file paths,
    diff content, or declared-artifact relpaths carried inside a selected,
    bounded `workspace_delta` or `declared_artifacts` member: those bytes are
    the evidence being judged and remain subject to the closed packet schema
    and byte limits. Full lineage and the opaque label binding stay sealed in
    the trial ledger and are joined only after score settlement.
    `reveal-provider-identity` is false in v1 and cannot override these
    exclusions.
  - Canonical UTF-8 packet items must not exceed `max_item_bytes`; the complete
    canonical packet must not exceed `max_packet_bytes`, and the packet limit
    is at least the item limit. Oversize, malformed, excluded, duplicate, or
    uncitable evidence fails closed before provider launch. Every evaluator
    citation must name a citable item in that exact packet; an unknown or
    cross-packet citation fails as `trial_packet_citation_invalid`.
  - One resolved provider, rubric asset, persisted scorer snapshot, and
    `same_trust_boundary` confidentiality declaration apply to every cell.
    Scorer identity reuses the adjudication scorer-identity algorithm and
    binds provider policy, evaluator prompt and rubric identities, strict
    output contract, packet schema, evidence limits, confidentiality, and
    secret-detection policy. Reusing these primitives does not reuse
    candidate fan-out, single-winner selection, candidate-shaped packet rows,
    or artifact promotion.
  - Evaluator stdout is one strict JSON object containing `candidate_id`, a
    finite numeric `score` in `[0.0, 1.0]`, a non-empty `summary`, and a
    `citations` string list. `candidate_id` must equal the packet's opaque
    evaluation label. The runtime validates JSON, label, score, summary, and
    citations before recording the closed `trial.score.v1` row. That row
    contains only trial-request, evaluation-label, packet, scorer, score,
    summary, and citation facts; it contains no arm/treatment, source,
    provider/model, candidate, promotion, or completion-order field.
  - Repetitions combine by median and ties resolve by authored-order only
    after all required score or failure rows settle. Failures remain outcomes.
    The total evaluator-attempt and evaluator-concurrency limits are runtime
    ceilings: once the attempt ceiling or trial deadline is exhausted,
    pending evaluations settle as failures, while already running evaluator
    attempts finish and remain charged. A late result never erases its cost or
    displaces a previously committed score row.
  - Packet construction, exclusion, canonical byte limits, scorer identity,
    strict output parsing, citation validation, attempt accounting,
    aggregation, and the sealed join are deterministic runtime obligations,
    not provider instructions. Source promotion is excluded: E2 emits one
    validated verdict artifact and publishes no candidate workspace or source
    change.

- Reusable-call provider boundary
  - `asset_file` and `asset_depends_on` resolve relative to the authored workflow file and must stay within that workflow source tree.
  - `input_file` and plain `depends_on` remain workspace-relative, even under `call`.
  - Imported workflows bring private `providers` namespaces; caller/callee provider-template name collisions do not merge unless a later contract adds explicit binding rules.
  - The first `call` tranche is inline and non-isolating: provider child processes may still perform undeclared filesystem reads/writes permitted by the OS.
  - Caller and callee are expected to use the same DSL version in the first tranche.

- Placeholder and parameter substitution
  - Substitution pipeline:
    1) Compose prompt from the selected base prompt source plus any source/workspace dependency injection.
    2) Translate any compiler-owned canonical call policy declaratively, without substitution.
    3) Merge `providers.<name>.defaults`, then `step.provider_params`, then translated canonical overrides (rightmost wins).
    4) Substitute inside the one merged parameter mapping exactly once (strings only; recursively visit arrays/objects; non-strings unchanged).
    5) Select the command variant and append any present canonical fragments in `model`, then `effort` order.
    6) Protect each selected command-template token with the provider command escape processing before any placeholder scan: escaped `$$` and `$${...}` become protected literal tokens rather than substitution candidates.
    7) Extract only unescaped placeholders from that protected representation. Provider declaration validation uses this same extraction to enforce exact binding consumption. Invocation substitutes the command template once: `${SESSION_ID}` only for a resume command, merged `${<provider_param>}` and `${run|context|loop|steps.*}` values, then literal `${PROMPT}` delivery in argv mode after other substitutions so prompt content is not rescanned.
    8) Restore the protected escaped dollar and braced-dollar literals only after command-template substitution. Any unresolved unescaped `${...}` fails validation (exit 2) and records bounded `error.context.missing_placeholders` (bare keys); `${PROMPT}` in stdin mode records `invalid_prompt_placeholder`.

- Exit codes
  - 0 = success
  - 1 = retryable API error
  - 2 = invalid input (non-retryable)
  - 124 = timeout (retryable)

- Arg length guidance
  - Large prompts or content injection may exceed argv limits; prefer `input_mode: 'stdin'` for such cases.
  - The orchestrator does not auto-fallback; input mode is explicit per template.

- Timeouts
  - When `timeout_sec` is set, the orchestrator enforces it: sends a graceful termination signal and then a hard kill after a short grace period. Records exit code `124` and timeout context in state.
  - Managed provider invocations run in a process group/session boundary so a timeout terminates the guard and its provider child process tree. Already-submitted managed jobs are recovered from persisted managed-job state rather than by relaunching the provider.

- Examples
- Claude: `command: ["claude","-p","${PROMPT}","--model","${model}"]`, defaults `{ model: "claude-opus-4-6" }`.
- Claude summary alias: `command: ["claude","-p","${PROMPT}","--model","${model}"]`, defaults `{ model: "claude-sonnet-4-6" }`.
- Codex CLI: `command: ["codex","exec","--dangerously-bypass-approvals-and-sandbox","--model","${model}","--config","reasoning_effort=${reasoning_effort}"]`, `input_mode: 'stdin'` (prompt via stdin).
- Canonical Codex session-capable CLI (v2.10/v2.16):
  `session_support.fresh_command: ["codex","exec","--json",...]`,
  `session_support.resume_command:
  ["codex","exec","resume","${SESSION_ID}","--json",...]`, and
  `session_support.turn_boundary_resume: true`. This is an explicit property
  of that template, not a capability inferred from the `codex` name.

## Direct CLI Integration (details)

Core provider-template mapping (schema notation, not authored workflow source):
```yaml
providers:
  claude:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}"]
    defaults:
      model: "claude-opus-4-6"
  gemini:
    command: ["gemini", "-p", "${PROMPT}"]
  codex:
    command: ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--model", "${model}", "--config", "reasoning_effort=${reasoning_effort}"]
    input_mode: "stdin"
    defaults:
      model: "gpt-5.4"
      reasoning_effort: "high"
```

Core provider-step mapping (schema notation, not authored workflow source):
```yaml
steps:
  - name: Analyze
    provider: "claude"
    provider_params:
      model: "claude-3-5-sonnet"
    input_file: "prompts/analyze.md"
    output_file: "artifacts/architect/analysis.md"

  - name: ManualCommand
    command: ["claude", "-p", "Special prompt", "--model", "claude-opus-4-1-20250805"]

  - name: PingWithCodex
    provider: "codex"
    input_file: "prompts/ping.md"
    output_file: "artifacts/codex/ping_output.txt"
```

Parameter handling: If a provider template does not reference a given `provider_params` key, the parameter is ignored with a debug log entry; not a validation error.

## Provider File Operations

Providers can read and write files directly from/to the filesystem while also outputting to STDOUT. These capabilities coexist:

1. Direct File Operations: Providers may create, read, or modify files anywhere in the workspace based on prompt instructions.
2. STDOUT Capture: The `output_file` parameter captures STDOUT (typically logs, status messages, or reasoning process).
3. Simultaneous Operation: A provider invocation may write multiple files AND produce STDOUT output.

Core mapping example (schema notation, not authored workflow source):
```yaml
steps:
  - name: GenerateSystem
    agent: "architect"
    provider: "claude"
    input_file: "prompts/design.md"
    output_file: "artifacts/architect/execution_log.md"  # Captures STDOUT
    # Provider may also create files directly:
    # - artifacts/architect/system_design.md
    # - artifacts/architect/api_spec.md
    # - artifacts/architect/data_model.md
```

### Best Practices

- Use `output_file` to capture execution logs and agent reasoning for debugging.
- Design prompts to write primary outputs as files to appropriate directories.
- Use subsequent steps to discover and validate created files.
- Document expected file outputs in step comments for clarity.

## Provider Templates — Quick Reference

| Provider | Command template | Input mode | Notes |
| --- | --- | --- | --- |
| claude | `claude -p ${PROMPT} --model ${model}` | argv | Default model via provider defaults (e.g., `claude-opus-4-6`) or CLI config/env. |
| claude_sonnet_summary | `claude -p ${PROMPT} --model ${model}` | argv | Built-in observability summary alias. Default model: `claude-sonnet-4-6`. Advisory only; not for control-flow gates. |
| claude_haiku_summary | `claude -p ${PROMPT} --model ${model}` | argv | Built-in low-cost observability summary alias. Default model: `claude-3-5-haiku-20241022`. Advisory only; not for control-flow gates. |
| gemini | `gemini -p ${PROMPT}` | argv | Model selection may not be supported via CLI; rely on CLI configuration if applicable. |
| codex | `codex exec --dangerously-bypass-approvals-and-sandbox --model ${model} --config reasoning_effort=${reasoning_effort}` (prompt via stdin) | stdin | Reads prompt from stdin; `${PROMPT}` must not appear in template. Built-in defaults are `model: gpt-5.4`, `reasoning_effort: high` (can be overridden in workflow/defaults/provider_params). Use only for trusted workflow workspaces because it disables Codex's own approval and sandbox layer. |

Exit code mapping:
- 0 = Success
- 1 = Retryable API error
- 2 = Invalid input (non-retryable)
- 124 = Timeout (retryable)
