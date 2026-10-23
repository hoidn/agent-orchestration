# Step IO and Output Capture (Normative)

Execution scope follows the [CLI support boundary](cli.md#executable-support-boundary)
and [evaluated IO](#evaluated-command-and-provider-io-target-235). The retirement
cutoff follows the selected retirement contract; implementation and delivery
status live in the [closeout](../docs/reports/2026-10-13-best-of-n-and-executor-retirement-closeout.md).
Old-profile IO/persistence details below are historical contracts, while shared validation and provider
services remain in use for admitted evaluated effects. Historical definitions of
session, supervision, peers, target-2.23 phased or adjudicated IO do not admit
those retired profiles. Target-2.39 phased delivery uses the existing IO
validators with the separate [provider publication contract](providers.md#evaluated-phased-provider-delivery-target-239).
Targets 2.35/2.36 retain current support; registered 2.37
and bounded 2.38 (Agent Sessions and command-only confined run-ref children) retain only their
[bounded qualification](versioning.md#version-gating-summary).
Target 2.39 retains these IO and qualification contracts; its procedure
authoring changes do not introduce a new result-acceptance profile.

- Input handling
  - `input_file`: read literal contents; no substitution inside file contents.
    - Under reusable `call`, `input_file` remains workspace-relative and does not become import-local.
  - `asset_file` (v2.5): read literal contents from the authored workflow source tree; provider-only and mutually exclusive with `input_file`.
  - When using a provider, the composed prompt (after optional injection) is passed via argv `${PROMPT}` or piped to stdin per provider template.

- Output handling
  - `output_file`: STDOUT is tee'd to this file and to the orchestrator capture pipeline.
  - Runtime result-file operations use a workspace directory descriptor pinned
    before effects. It covers `output_file` tee writes, `expected_outputs`
    values and required targets, `output_bundle` and variant bundles, and
    result payloads while staging, backing up, promoting, rolling back, or
    discarding them. When run-owned result bundles live outside the workspace,
    the executor pins one aggregate run-root owner before effects; call-frame
    and per-attempt roots are short independent descendant leases, and
    promotion opens a fresh descendant from that same owner. Borrowed helpers
    never return the cached owner itself. Ordinary state metadata, logs, and
    external adapter inputs remain outside this result-file boundary.
  - Stderr is captured separately and written to logs when non-empty.
  - v2.10 session-enabled provider steps normalize structured provider transport before ordinary output capture:
    - normalized assistant text becomes the step-visible stdout used by `output_capture` and `output_file`
    - non-OMP metadata codecs use a masked runtime-owned provider-session
      transport spool under the run root, retained on failure or in debug mode
    - `omp_json_stdout` transport is processed in memory. Its compatibility
      spool stays empty and is removed when a fresh visit finalizes, on either
      success or failure, including debug mode. Persisted parent metadata is
      the credential-minimized projection; OMP journals remain separate
      observations as defined in `state.md`.
  - Deterministic artifact contracts:
    - Admitted evaluated command boundary manifests accept `closure`, an array of
      literal file or directory paths for both `external_tool` and
      `certified_adapter`. C1 requires it on every supplied declaration
      (including unused rows) and every used compiler-injected binding;
      omission refuses with `command_boundary_closure_missing`. An explicit
      `[]` is valid; `null`, non-arrays, non-string entries, empty strings and
      NUL refuse with `command_boundary_manifest_invalid`. In the historical
      through-2.34 build contract, the valid field was accepted and ignored by
      binding serialization and effect identity. Existing raw-manifest cache hashing stays unchanged; editing
      the manifest can still change the build key.
      At build, C2 means canonical logical declarations enter configuration
      and program identity; compilation does not read, traverse, resolve
      symlinks or hash closure file bytes. Content hashes, the per-run
      interpreter pin and the read-only check belong to the run and resume
      entries: see
      [evaluated command and provider IO](#evaluated-command-and-provider-io-target-235)
      and
      [command closure declaration](../docs/design/workflow_command_adapter_contract.md#command-closure-declaration),
      `closed/effects.py::require_command_closures`,
      `closed/program.py::_canonical_closure` (under
      `orchestrator/workflow_lisp/`) and
      `tests/test_workflow_lisp_command_boundary_closure.py`;
      `tests/test_workflow_lisp_closed_program_compile_cli.py` checks that
      changed closure bytes do not change compile identity.
    - `expected_outputs`: file-per-value contract validation (v1.1+).
    - `output_bundle`: JSON-bundled field extraction/validation (v1.3+).
    - v2.15 guidance is metadata only. Bundle `guidance` and top-level
      `result_guidance` are closed non-empty objects with any of
      `description`, `format_hint`, and JSON-compatible `example`. A field may
      carry those keys directly, ordered ancestor rows in `guidance_context`,
      or (for a shared variant field) discriminant-ordered
      `guidance_by_variant`; direct and variant guidance are mutually
      exclusive. Field examples must satisfy the field schema. Relpath
      examples are path-safety checked but `must_exist_target` is not enforced
      for an example. These containers are rejected before v2.15.
    - v2.19 `type: value` is an opaque strict-JSON contract. Bundle parsing
      rejects `NaN`, positive or negative infinity, and malformed JSON as
      `invalid_json_document`. Recursive validation independently rejects
      non-finite in-memory floats, non-string object keys, cycles, and other
      non-JSON leaves with `invalid_transportable_value` and the first invalid
      RFC 6901 value path. A present JSON `null` succeeds; it is distinct from
      a missing file or pointer. `description` and `format_hint` guidance are
      allowed, but `example` is rejected with
      `value_guidance_example_unsupported`. From target 2.34 the non-finite
      constants are refused per field instead, as below.
    - Target 2.34 finite values (numeric surface rule N6): a `Float` that
      enters a run is finite. Workflow inputs, fields of command and provider
      result bundles (plain, variant and nested in a record, union, list or
      map) and expected output files refuse, with the violation
      `float_not_finite`:
      - the JSON tokens `NaN`, `Infinity` and `-Infinity`;
      - a string that reads as a non-finite number, such as `"nan"`, `"inf"`
        or `"Infinity"`, where a string is read as a `Float`;
      - a number too large for a double, such as `1e400` or an integer beyond
        the double range.
      The violation context prints the value as the double it reads as
      (`nan`, `inf`, `-inf`). A bundle refusal names the field by its
      `json_pointer` and, inside a nested value, its `value_path`; a refused
      workflow input is named in the binding error, before the run exists.
      A bundle is decoded with the non-finite tokens so that the refusal
      names the field, and every non-finite number inside a `value` or nested
      structural field is refused with the same code. In a direct structural
      record/union contract, including one beneath a container, a string in a
      `Float` position remains a type error (`invalid_transportable_value`).
      Scalar bundle fields and `optional`/`list`/`map` schemas without a
      record/union retain their numeric-string parsing and finite-value checks.
      The target is the one of the workflow whose step or input is validated.
      Historically, resume of a 2.34 run with a non-finite saved value refused
      with `float_not_finite`, naming its JSON pointer in `state.json`. The
      retirement cutoff instead rejects that profile before the numeric state
      validator, without mutation. The historical validator refused only
      non-finite values; a finite value edited into saved state was trusted. The rule covers the values the orchestrator serialises and
      commits (state, checkpoints, records); a result file written by a command
      or provider is that effect's file and stays, as evidence, when refused.
    - Historical targets 2.33 and older accepted non-finite
      values in workflow inputs, plain `float` bundle fields, variant fields
      and expected output files, and wrote them to `state.json` as the tokens
      `NaN`, `Infinity` and `-Infinity`. An integer too large for a double in
      a `float` position failed the run with an uncaught `OverflowError`.
  - Command structured-bundle environment:
    - For command steps with `output_bundle.path` or `variant_output.path`, the
      runtime resolves the workspace-relative bundle path before launch and sets
      `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` to that target.
    - The runtime-owned value wins over any caller-provided environment value
      for the same name.
    - After path-safety validation, the runtime creates or validates the parent
      directory before launching the command.
    - The bundle file, not stdout JSON, is semantic authority for the structured
      result. Stdout remains ordinary captured output or debug/log material.
    - If the command exits `0` but the bundle is missing or invalid, the step
      fails as an output-contract failure. If the command exits non-zero, the
      command failure remains primary.
    - `variant_output.path` adds tagged-union validation and projection on top
      of this same runtime-owned explicit-path bundle contract.
    - On the target-2.35 evaluated route the same variable names the
      attempt's own `result.json` under the run root, workspace-relative; see
      [evaluated command and provider IO](#evaluated-command-and-provider-io-target-235).
  - Target-2.29 projection contract:
    - Pure bundles remain canonical sparse values. Generated bundle pointers
      use declared source paths, not flattened artifact-name guessing. Resolve
      each group's discriminant before reading or validating its active fields;
      fresh and reused bundles follow the same rule.
    - Variant availability retains declared group/discriminant identity through
      shared contract normalization and materialization. Exact scoped
      `requires_variant: {ref, allowed}` checks authorize only that group's
      fields; an independent group's tag is not proof.
    - Loop boundaries may totalize proven inactive fields with existing typed
      internal placeholders through guarded conditional projections. Final
      authored outputs remain sparse and active fields remain strictly
      validated. Missing/invalid discriminants never authorize placeholders.
      Prior-target extraction and guard behavior remain unchanged.
  - Provider structured-bundle environment:
    - For provider steps with `output_bundle.path` or `variant_output.path`, the
      runtime resolves the workspace-relative logical bundle path before
      invocation and exposes that logical value as
      `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. An unrestricted invocation uses the
      resolved host target directly; an isolated workflow-provider invocation
      maps the same logical value to the private scratch projection specified
      below.
    - The runtime-owned value wins over authored step environment values or
      provider-template environment values for the same name.
    - Prompt contract text may repeat the same path and schema, but prompt text
      is guidance. The declared bundle file remains the semantic authority.
    - Effect-boundary `guidance`, field guidance, `guidance_context`, and
      `guidance_by_variant` are rendered as provider output instructions.
      Workflow-level `result_guidance` is not: it describes the callable's
      overall return and is carried only in workflow IR/artifact metadata.
    - If the provider exits `0` but writes the bundle to any other path, the
      step fails as an output-contract failure.
    - On the target-2.35 evaluated route the variable is the absolute path of
      the attempt's `result.json`, as [Providers](providers.md) states; the
      prompt still shows the workspace-relative spelling.
    - A compiled direct `Value` result uses one compiler-owned field named
      `__result__`, with `json_pointer: ""` and `type: value`. The bundle bytes
      are the JSON encoding of the value itself; neither the runtime nor the
      provider contract adds a `{"value": ...}` envelope.
  - Workflow Lisp portable-context capture (target 2.31):
    - For an ordinary portable capture whose declared
      model result is `T`, the provider-facing `output_bundle` has exactly one
      mandatory compiler-owned `__result__` field at JSON pointer `""`, with
      the complete recursive schema of `T`. The provider writes `T` directly;
      it never writes `{result, context}`, a context envelope, or a conditional
      variant projection.
    - The existing bundle validator first validates that whole `T` document.
      The existing codec then captures and validates the settled portable
      Context, and the existing finalization transaction validates the complete
      `Contextual[T]` pair before atomically publishing its two typed artifacts,
      `result: T` and `context: Context`. A failure before that commit publishes
      neither successful member. Provider-created files and diagnostics may
      remain; this is not rollback of provider side effects.
    - The complete pair, including wrapper nesting, remains subject to the
      ordinary recursive transport limits: maximum depth 64 and maximum value
      size 16 MiB. Separately valid result/context members do not bypass those
      limits. Capture failure is an ordinary failed boundary and does not
      silently rerun a successful provider merely to obtain context.
    - A compatible completed boundary reuses the committed pair without a
      provider call or history export. Pending/interrupted calls retain the
      existing discard-and-rerun behavior. Context content and selection take
      part in the ordinary input/program identity; a changed Context is not a
      patch to an existing checkpoint.
    - Uncaptured providers and commands retain their prior bundle and artifact
      contracts. The portable pair does not introduce a second state store,
      an alternate result channel, or native-resume persistence.
  - Workflow Lisp prompt output-position composition (target 2.21):
    - A fragment-backed provider step may combine compiler-owned
      `expected_outputs` rows with exactly one prompt-owned `output_bundle` or
      `variant_output`. Every other multi-contract combination remains
      invalid.
    - Before provider launch, artifact names across both contracts must be
      disjoint, resolved output-position destinations must be pairwise
      distinct, and every output-position destination must differ from the
      structured bundle destination. The rendered path value and resolved
      expected-output path must be the same canonical workspace-relative POSIX
      path.
    - Prompt composition emits the output-position contract first and the
      structured-result contract second. After a successful provider process,
      validation uses that same output-position-first order.
    - Both validations finish into local mappings before state mutation.
      Failure of either contract commits neither mapping; successful disjoint
      mappings merge once into the existing step-artifact map. This is
      state-atomic and does not roll back provider-written files.
    - The output-position row requires one UTF-8 string file at the exact
      resolved path. Existing `invalid_output_path` and
      `missing_output_file` violations remain the runtime failure surface.
  - Workflow Lisp prompt-attempt evidence and report IO (target 2.22):
    - A direct fragment-backed attempt renders each slot and each runtime
      contribution exactly once. Immutable in-memory traces identify only
      canonical values, selected bytes, ordering, and digests; prompt bodies,
      resolved values, dependency content, argv, and environment are not
      persisted in Q3 evidence.
    - After successful invocation preparation and before provider launch, the
      attempt publishes one closed
      `workflow_prompt_fragment_snapshot.functional.v2` record. Invocation
      preparation failure publishes the closed
      `workflow_prompt_fragment_preparation_failure.functional.v1` record;
      either publication failure launches no provider.
    - `orchestrator report` JSON always includes the additive top-level
      `prompt_context` object, including for older targets and unqualified
      runs. Its Markdown projection contains status labels, role digests, and
      fixed comparison classifications only; neither report projection is a
      provider result or execution/resume input.
  - Result-file freshness (every target):
    - Before each command call, and each provider call with composed delivery,
      that has `output_bundle.path` or `variant_output.path`, including each
      retry attempt and each call run again on resume, the runtime creates the
      bundle parent and removes any file at the resolved bundle path. A file
      left there by an earlier iteration, an earlier run, or an interrupted or
      failed attempt is never read as the result of the new call.
    - The creation and removal start from the workspace root the run's
      executor opened when it was created (a call frame uses the same one),
      never from the workspace path looked up again, so a workspace root
      replaced by a symbolic link during the run cannot move them. Each parent
      directory is created when missing and opened without following a
      symbolic link, and the last path component is removed relative to the
      last parent, so they never act outside the workspace. A symbolic link at
      the bundle path is removed, never its target.
    - A result path never passes through a symbolic link, whether it points
      inside or outside the workspace. If a parent on the path is a symbolic
      link or not a directory, or the path cannot be cleared (for example
      because a directory is there), the step fails before launch with the
      output-contract violation `stale_bundle_removal_failed`, which names the
      path and the cause and carries the step's source origin, also for a step
      of a called workflow.
    - A workspace whose `.orchestrate` is a symbolic link is refused at run
      start, before the build or any other effect, with `state_root_symlink`
      naming the link.
    - If the call exits `0` and the bundle file is absent, the step fails with
      the output-contract violation `missing_bundle_file`, with the same
      source origin.
    - These calls keep their own rule instead: a provider call with phased
      delivery rejects a pre-existing bundle file with
      `candidate_path_preexisting` (an exact rerun of an interrupted attempt
      first discards that attempt's own candidates); provider-supervision and
      provider-peer-group invocations below require their provisional paths to
      be absent, and a pre-existing file fails before launch.
  - Provider-supervision IO (v2.16):
    - Provider stdin/stdout/stderr, the selected metadata codec, and validated
      output bundles remain the execution and result transports. Observation
      panes, display bytes, transcripts, raw logs, cancellation records, and
      timing metadata are observability evidence only.
    - Worker-fresh, supervisor-directive, and optional worker-resume
      invocations each receive a distinct visit/member/turn-qualified
      provisional bundle path under the run root. The runtime requires the
      file to be absent and creates its parent before launch; a pre-existing
      file is a prelaunch failure. No member writes the group result directly.
    - `CONTINUE` validates the supervisor directive and fresh-worker bundle.
      `STEER` validates the directive and resumed-worker bundle; it never
      reads, promotes, or infers success from the fresh worker's business
      bundle.
    - Only the selected worker value and validated directive enter the pure
      settlement expression. The validated settlement value alone becomes
      the node result and ordinary artifacts/dataflow publication.
  - Provider-peer-group IO (v2.17):
    - Each member invocation receives one distinct attempt-qualified
      `provisional-result.json` path under the group visit root and the
      runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` binding for that exact
      path. The file must be absent before launch. A pre-existing file or
      member/path mismatch fails before provider execution.
    - Every member bundle is a direct JSON root value: the provider writes the
      JSON encoding of its declared transportable return value directly,
      whether that value is a scalar, enum, relpath, optional, list, map,
      record, or union. The compiler-owned internal result name does not
      introduce a `{"result": ...}` or `{"value": ...}` wire envelope.
    - Provider stdout/stderr, interactive pane bytes, transcripts, peer
      receipts, message text, and ledger rows are execution or observability
      evidence only. They are never parsed or promoted as a member's typed
      result.
    - An eligible `peer-finish` reads and validates only the exact bound bundle
      against that member's declared result contract, verifies its bytes
      remain unchanged during validation, and freezes those exact bytes and
      their digest in coordinator-owned memory/evidence. Later path mutation
      cannot change the frozen member value.
    - No member writes the group result directly. After every member has a
      complete natural-shutdown proof, the coordinator evaluates the pure
      settlement over the authored-order frozen member values, validates the
      settlement's transportable type, and commits only that settlement as the
      node result and ordinary artifacts/dataflow publication.
    - Any invalid/missing member bundle, bundle mutation, non-natural member
      exit, peer-protocol failure, failed delivery, failed close, or failed
      cleanup fails the whole node. Provisional member bundles and message
      ledgers remain run evidence and no settlement is published.
  - Reusable-call boundary:
    - `output_file`, `expected_outputs.path`, `output_bundle.path`, `consume_bundle.path`, and all deterministic `relpath` outputs stay workspace-relative whether a workflow runs top-level or under `call`.
    - `call` namespaces runtime-owned identities, provenance, and logs; it does not namespace authored output paths.

## Evaluated Command And Provider IO (target 2.35)

This contract applies to admitted evaluated effects at 2.35/2.36, bounded
2.37 and bounded 2.38 Agent Sessions and command-only confined run-ref children.
The [confined-command recipe](../docs/lisp_workflow_drafting_guide.md#confined-workflow-children-target-238-command-only)
records host/image prerequisites; public confined providers remain closed. W3 changes
authoring, not command/provider IO or the public lifecycle; 2.37 registration
does not imply general parallel qualification. For Agent Sessions,
[PQ-1a](../docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md) records
deterministic proofs and bounded adapter smokes; the real-provider comparison
(PQ-1c) has not run and requires separate owner authorization. See
[versioning](versioning.md#version-gating-summary) for the target limits.

This section owns the request a target-2.35 command or provider receives,
the evidence the run binds for it and the files each attempt leaves. The
effect identity, the memo records and the attempt directory layout are owned
by [State](state.md#evaluated-execution-persistence-profile-target-235); the
closure rules C1–C7 by
[evaluated execution §7.3](../docs/design/workflow_lisp_evaluated_execution.md#73-what-a-command-boundary-declares),
the request fields R1–R12 by
[§9.4](../docs/design/workflow_lisp_evaluated_execution.md#94-the-request-contract)
and typed input documents by
[§9.1.1](../docs/design/workflow_lisp_evaluated_execution.md#911-typed-command-input-documents).
Availability: implemented at target 2.35; Phase 3 is complete and delivered
at `06130a53` ([closeout report](../docs/reports/2026-10-02-workflow-lisp-evaluated-execution-phase-3-closeout.md)). Owners:
`orchestrator/workflow/evaluated/{commands,providers,closure,closure_evidence,inputs,runtime}.py`.
Evidence: `tests/test_workflow_evaluated_command_templates.py`,
`tests/test_workflow_evaluated_resume_retry.py`,
`tests/test_workflow_evaluated_resume_replay_boundary.py`,
`tests/test_workflow_evaluated_provider_lifecycle.py` and
`tests/test_workflow_evaluated_invalidate_smoke.py`.

- Resolved input and the limits of the promise
  - An effect's resolved input is bound by content before its `started`
    record: a command's argv, contract, closure declaration,
    implementation-file evidence and, when present, input document; a
    provider's declaration, values, policy, params, assembled prompt,
    dependency rows, prompt source and dependency file digests. The
    environment, the clock, modification times, the provider template and
    model behind a provider id, files no boundary declares and `__pycache__`
    contents are outside the promise (C5): a command whose behaviour depends
    on them may be reused with a result a fresh run would not give. The
    closure is the author's declaration, not a sandbox, a filesystem capture,
    a determinism guarantee or a rollback.
  - Provider prompt sources (`asset_file`, `input_file`, `defprompt` document
    fills) and prompt dependency files are read once per attempt and bound
    by digest (C6): the memo parts carry `source:<kind>:<path>` and one
    `dependency:<path>` per declared dependency, with raw file digests. A
    changed, missing or unreadable file at resume refuses the committed
    effect with `effect_input_diverged` before any launch; a pending
    provider start re-reads its sources in memory and may retry with
    changed bytes, while a missing or unreadable source refuses without any
    write. An ordinary path value in a program is a value, not a
    declared read: it creates no file-content dependency, and `depends_on`
    records value lineage only. Artifact handoff between effects follows
    [§9.1.2](../docs/design/workflow_lisp_evaluated_execution.md#912-artifact-handoff-within-the-admitted-release):
    declared result paths keep their roots and `must_exist` checks, and an
    attempt's `result.json` does not replace them.
- Result decoding and structured acceptance
  - The checked result contract selects decoding and projection. Flattened
    bundle fields retain leaf parsing: an integer field can decode `"5"` to
    `5`, and undeclared object fields are not projected into the result.
    Declared fields belonging only to an inactive union variant are rejected.
    Direct structural record/union descriptors instead reject numeric strings
    in numeric positions and reject extra fields, including inside containers.
    Scalar/list/map leaf schemas retain their documented coercions; the
    distinction is the descriptor, not merely nesting depth.
  - Evaluated command and provider result ingestion requires finite floats.
    Sharing equivalent leaf parsers does not unify JSON budgets, numeric
    domains, path checks or diagnostics across output decoding, direct
    transport validation and evaluated-value coercion.
  - Resume reuses recorded typed values through the memo/replay contract. It
    does not re-decode their original result files or apply a newly tightened
    acceptance profile. Existing replay coercion and integrity checks remain
    required; parser consolidation does not change their acceptance.
- Command closure enforcement (C2–C4, C7)
  - At run and resume the C2 evidence is resolved live for the reached
    command only: automatic selection of workspace-spelled stable-command
    tokens plus every explicit closure entry, unioned with the pertinent
    prior map (the active commit for reuse, the latest uncommitted `started`
    for retry), file bytes hashed, directories hashed as flat sorted row
    lists, symlink targets recorded and `__pycache__` skipped. A missing,
    unreadable, cyclic or unsupported entry refuses with
    `command_closure_unreadable` before a first attempt and with
    `effect_input_diverged` when a prior start or commit exists.
  - C3: a bare first token launches through the header pin's recorded path;
    the interpreter enters no effect identity.
  - C4 is local and minimal: immediately before each reached command that
    needs a new attempt, and only then, the runtime checks that the attempt's
    concrete destinations (the attempt directory, `result.json`, `stdout.txt`,
    `stderr.txt`, `inputs.json` when applicable, and `memo.jsonl`) are
    disjoint from that command's closure files, directory roots and resolved
    symlink targets, refusing before `started` with
    `command_closure_unreadable` (reason `runtime destination overlaps
    command closure`). `state.json` needs no entry of its own: any directory
    that covers it also covers `memo.jsonl` beside it, which is checked, and
    the view file itself can be named only by its per-run path, which no
    static declaration carries. After the command exits the
    runtime rehashes the closure and fails the attempt with
    `command_closure_written` when the evidence changed. There is no startup scan of all effects or
    routes, no protection of a closure from other effects or from run-root
    bookkeeping, and no rollback. A memo hit creates no attempt and performs
    no destination check. Commands run with `PYTHONDONTWRITEBYTECODE=1`.
  - C7: a changed manifest or stable command changes the program digest and
    refuses resume with `resume_program_changed`; a changed bound file
    diverges only the effects that bind it, `effect_input_diverged` at the
    first such commit in journal order, before any launch.
- Command request and attempt files
  - argv: the stable command with its interpreter replaced by the pinned
    path, then the rendered authored arguments; a certified adapter's inline
    JSON document is appended as the last token; an external tool with
    `:inputs` receives the workspace-relative path of the attempt's
    `inputs.json` as its last token. Environment: `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`
    set to the workspace-relative path of the attempt's `result.json`, and
    `PYTHONDONTWRITEBYTECODE=1`; the working directory is the workspace. A
    template lookup that misses refuses `undefined_variables` before `started`.
  - Result: the file at the attempt's `result.json`, validated against the
    declared contract and projected to the declared type; stdout and stderr
    are captured to `stdout.txt` and `stderr.txt` and are never a result
    channel. A nonzero exit is `command_exit_nonzero` with
    `exit_info {exit_code, error}` (no timeout is applied to an evaluated
    command, so `command_timeout` is not raised); an exit `0` with an absent
    or unreadable result file is `command_result_missing` or
    `command_result_unreadable`; a file that fails its declared contract
    fails the attempt with `evaluated_execution_failed` and the contract
    `violations`; an unsupported contract kind or an invalid checked
    projection is `command_result_contract` or `command_result_projection`;
    a builtin adapter whose module resolves outside its declared package
    tree is `command_module_origin_mismatch`. One memo attempt
    is one external dispatch: internal executor retries are bypassed, and
    `--max-retries` and `--retry-delay` are not read.
- Typed command input documents (external tools)
  - `:argv` plus `:inputs ((field expression) ...)` is admitted only at
    evaluated targets and only for `external_tool` bindings; `certified_adapter`
    keeps its signature-ordered inline JSON document and empty authored argv;
    `:argv`-only forms of either kind are unchanged. Omitting `:inputs` sends
    no document and no token; `:inputs ()` sends `{}`.
  - Operand effects in argv and input fields run once, in expanded structural
    source order; keyword order does not reorder argv or JSON keys.
  - The document is the canonical finite JSON encoding of the checked field
    values (UTF-8, sorted keys, compact separators, no trailing newline); its
    byte digest is the `document` input part and the ordered field contract's
    digest the `input_contract` part, neither including the attempt path. A
    value violating its checked contract refuses with `effect_input_invalid`
    (field, value path and violation code) before `started`; on reuse of a
    committed effect the same check reports `effect_input_diverged`.
  - After exclusive attempt allocation the runtime writes `inputs.json`
    exclusively (mode `0600`) through the pinned run-root owner and passes its
    workspace-relative path; a memo hit neither reads nor regenerates it, and
    editing a generated document authorizes nothing.
  - This is distinct from the CLI `--input-file` (workflow parameter binding,
    read when `run` or `resume` binds inputs), from provider `input_file` and
    `asset_file` (prompt sources bound by digest under C6) and from prompt
    dependencies and artifact reads; none is renamed, rebased or converted
    into another.
- Provider request and attempt files
  - The prompt is assembled through the ordinary composition pipeline
    ([Providers](providers.md)) from the extern source or `defprompt` base,
    dependencies at their declared positions, the typed prompt-input block
    and the output contract; the contract's `- path:` line is the attempt's
    `result.json` relative to the workspace (R3), and the prompt is written
    to `prompt.txt` before launch.
  - Environment: `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` with the spelling
    [Providers](providers.md) gives this route, and
    `ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY` as `sha256:` of the identity's
    UTF-8 bytes (R5); the working directory is the workspace; no run context,
    session, managed job or secrets (R1, R8). Policy is the effect node's
    `model`, `effort` and `timeout_sec` (R7).
  - Result: the bundle at the attempt's `result.json`; `provider_result_missing`
    when absent, `provider_result_invalid` with `violations` when it fails
    the declared contract (the file is kept as evidence),
    `provider_exit_nonzero` or `provider_timeout` with
    `exit_info {exit_code, error}` on a failed process,
    `provider_preparation_failed` with `exit_info {error}` when the
    invocation cannot be prepared, and `provider_result_contract` or
    `provider_result_projection` as the provider spellings of the command
    result codes; `stdout.txt` and `stderr.txt` are evidence only. Attempt files are created exclusively and
    never overwritten by a later attempt.
- Agent turn request and attempt files (target 2.38)
  - The request is the ordinary provider request of the agent's pinned
    template with session request `fresh` (first turn) or `resume <locator>`
    (later turns); policy is the allocation's `model`/`effort` plus the
    turn's `timeout_sec`; environment and prompt as for providers, run from
    the workspace (the allocation pins that directory). The delivery
    rendering is selected structurally from the template's metadata mode
    (`legacy` for OMP JSON, else the current file rendering). A committed
    turn replays with its committed rendering and its inline proof alone: no
    current template, session support or native store is consulted.
  - Resolved input parts are the provider parts plus `agent` (digest of the
    Agent descriptor, which carries the pinned configuration digest) and
    `predecessor` (digest of `{turn, proof}` of the agent's previous
    committed turn, or of `null`). The predecessor is also a `depends_on`
    entry. A template, default or working-directory change since
    allocation, or a provider outside the node's `origins`, refuses
    `agent_policy_mismatch` before `started`.
  - Before `started` and again before launch, the runtime reads the native
    store head and refuses `agent_session_unavailable` (missing, ambiguous or
    unreadable store) or `agent_session_diverged` (head differs from the
    predecessor's committed position, or an open turn). It writes
    `receipt.json` (`intent`) before launch; the receipt records `launching`
    with the child's process group and the group leader's start time
    (`/proc/<pid>/stat` field 22) as soon as the executor binds it, then
    `completed` with the native locator and position once the store shows
    exactly one completed turn after the predecessor whose user message
    carries this attempt's `result.json` path. Receipt updates are monotone:
    binding fields never change and `completion` moves only `intent` ->
    `launching` | `not_dispatched` | `unknown`, `launching` -> `unknown` |
    `completed` | `not_dispatched`, `unknown` -> `completed` | `abandoned`,
    `completed` -> `completed` (adding the result digest) | `abandoned`
    (`not_dispatched` and `abandoned` are final); a malformed receipt is
    `memo_inconsistent`.
  - Commit requires that exact native completion and the ordinary
    typed-result validation; a result file alone is never a result, and a
    Claude `result` with `is_error: true` is an invalid result. An invalid
    typed result closes the attempt `failed` with `provider_result_invalid`
    (first turn) or `agent_turn_result_invalid` (later turns). These Agent
    validation errors expose only logical agent identity and safe code, with
    `exit_info {}` and no `violations`; raw provider/result detail is not copied
    into public diagnostics, state or reports ([State](state.md#memo-records)). A failed
    process closes `failed` with its provider code only when no child was
    spawned or the adapter proves a resumed conversation's head unchanged
    (receipt `not_dispatched`). Every other exception after `launching`
    keeps the `started` row pending with `agent_turn_unresolved` (receipt
    `unknown` before the adapter confirmed completion, `completed` after
    it), including a failure to record that state and a failed memo commit
    after the prepared proof; no `failed` or terminal is appended and resume
    reconciles the same ordinal without redispatch.
- Run references: the resolved input parts are `config` (the step-config
  digest) and `inputs`; the child runs in its clone workspace under the
  ledger of [State](state.md#target-224-run-ref-state-settlement-and-resume)
  and the [coordinator records](state.md#coordinator-records-and-child-runs).

## Provider-Phase-Isolated Bundle Brokerage

- An isolated `workflow_provider` attempt with a typed-bundle result channel
  retains its logical `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. Inside the provider
  namespace, the parent of that logical path is an invocation-private scratch
  directory rather than the host runtime directory. The provider can write the
  active basename but cannot enumerate or read prior or sibling host bundles.
- Brokerage begins only after the provider and every descendant are quiescent.
  It uses the already-held prelaunch scratch-directory descriptor together
  with its exact runtime-relative path and device/inode/mount binding. The
  publication request is created only from that exact revalidated
  post-quiescence authority; callers cannot independently compose its runtime
  descriptor, invocation identity, scope, ordinal, target path, or captured
  bytes. Production capture derives the size bound from that authority and
  binds the capture classification, digest, size, source scratch identity, and
  configured limit to it. A raw descriptor capture, a capture from another
  attempt, a capture taken with a caller-selected larger limit, or altered
  captured bytes are not publication authority. A combined request/capture
  binding is revalidated when the request is constructed and again before
  publication, so independently valid request and capture objects from
  different attempts cannot be paired. The
  broker pins the active basename descriptor-relatively with no-follow
  `O_PATH` semantics, classifies it with `fstat` before any readable open, and
  accepts only a regular file. It then reads the same pinned inode, verifies
  type, device, inode, and mount identity before and after the bounded copy,
  and has no pathname-reopen fallback. Directory, FIFO, device, symlink, swap,
  mutation, alias, or mount-crossing observations fail closed without a
  blocking or device-readable open. Unavailable required Linux descriptor,
  mount-identity, atomic-rename, or fsync machinery fails as
  `provider_isolation_bundle_broker_failed`; v1 has no fallback.
- Symlink or mount ancestry, or any product-visible symlink/hardlink alias of a
  staged, canonical, or archived bundle authority, fails before transfer. The
  broker never selects among aliased locations.
- `result_bundle.max_bytes` is a non-boolean integer in the inclusive range
  `1..16777216`. An empty regular bundle and a bundle whose size is exactly the
  configured limit are eligible for transfer. A bundle larger than that limit
  is rejected as `provider_isolation_bundle_oversized`; the broker never
  transfers or publishes more than the configured bound. A read of at most one
  sentinel byte beyond the bound is permitted only to classify oversize or
  concurrent growth, and that byte is never staged or published.
- The broker transfers bytes only. The declared `output_bundle` or
  `variant_output` contract and the existing typed bundle validator remain the
  sole semantic authority. Journal state, a successful copy, stdout, and
  provider prose do not validate or publish a workflow value.
- Retention is fixed:
  - For a quiescent zero exit eligible for typed validation, an exact regular
    bounded bundle is atomically published at the runtime-owned canonical host
    target and retained even if typed validation later reports `invalid`.
  - If eligible output is absent, the canonical target remains absent and the
    existing `missing` output-contract outcome remains authoritative. No
    publication or transfer journal is fabricated.
  - If eligible output is rejected by broker admission, no canonical target is
    published and no transfer journal is fabricated. The owning per-ordinal
    lifecycle records the `rejected` outcome; the broker establishes only the
    absence invariant. The rejected object and scratch siblings are never
    copied.
  - A retryable nonzero exit, timeout, or cancellation is not eligible for
    typed validation. When the exact held active basename is an admitted
    regular bundle, the broker records its bounded metadata and digest; it
    publishes no canonical target and creates no transfer journal.
  - A validated `valid` target remains at the canonical runtime-owned path. A
    validated `invalid` target must rotate atomically to its deterministic
    provider-masked archive before another attempt may launch or reuse the
    canonical target.
- Every attempt receives a fresh empty scratch root. After the broker has
  captured the required bounded evidence, the complete scratch tree, including
  sibling files, may be removed only after the owning caller confirms that the
  evidence and any publication are durably accounted for. Ordinary execution
  may acknowledge cleanup only after finalized attestation. Each twice-proved
  entry is atomically moved without replacement to a controller-private
  quarantine name and revalidated against its held descriptor immediately
  before removal. A final-boundary replacement therefore remains quarantined
  and fails cleanup rather than being deleted. No later provider receives or
  mounts a prior attempt's scratch.
- A `controller_attempt` with `result_channel: "none"` has no result scratch,
  bundle environment binding, broker invocation, canonical bundle target, or
  transfer journal.
- V1 has no retention-policy knob. These rules are not alterable by workflow,
  provider-template, policy, or caller configuration.
- This section specifies the bundle-broker substrate. It does not by itself
  select the isolated launcher from public execution, commit a typed workflow
  value, finalize an isolation attestation, or make public run/resume
  integration complete.

<a id="proposed-run-ref-confined-child-io-target-238"></a>

## Run-Ref Confined Child IO (target 2.38)

This IO and typed-export contract applies to the admitted command-only confined
profile. Provider-specific transport below is a requirement for separately
qualified public provider admission. Evaluated host command/provider and path-mode
run-reference IO above is unchanged. Authority:
[run-ref confined child environments](../docs/design/workflow_lisp_run_ref_expression_environments.md#results-paths-and-lifetime).

- Result transport (R2/R3 guest spelling): for a confined attempt both
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` and the prompt's `- path:` line name
  `/result/<attempt-relative>`, so prompt identity of confined attempts
  differs from host attempts by design. Before each leaf the host empties
  `/tmp`, `/dev/shm` and `/result` and creates `/result/<leaf>` exclusively;
  after leaf quiescence the result broker copies validated bytes from it into
  the protected attempt through the retained descriptor. Host absolute paths,
  run-root descriptors and host interpreter pins never cross.
- Leaf IO: cwd `/workspace`, stdin from the host-written leaf file,
  stdout/stderr into `/result/<leaf>/`, bounded. Exit status and output are
  untrusted guest data from the candidate's trust domain; provider stderr is
  bounded evidence, not the typed result. Before importing/publishing these
  bytes or checkpointing workspace content, require irreversible capability
  revocation, closed/reaped transport owners, quiescence and verified private
  script retirement under [Security](security.md#confined-capability-retention-and-transport-teardown).
  A failed teardown blocks those boundaries; active guest output is not teed to
  durable host evidence. Structural, byte-limit, type and lineage validation
  does not prove absence of secrets. Guest-authored literal, split or encoded
  copies of its issued capability, including permitted names/targets, remain
  ordinary untrusted data after revocation, with existing bounds/truncation and
  exact admitted bytes. This extends to derived snapshots, manifests, result
  memo, exports and later inputs; none restores authority. No production token
  scanner, coincidence rejection or sanitizer is selected. Runtime-authored
  control/configuration/diagnostic fields remain subject to token exclusion;
  arbitrary names/targets cannot be copied into persisted error details. The
  separate prohibitions on authfiles, upstream bearers, permanent credentials
  and native auth RPC remain intact.
- Typed path inputs are copied into a child-owned location that still
  satisfies each input descriptor; unsafe links refuse, and the copy is
  revalidated before launch. They are never host mounts.
- Typed export: each returned path leaf of a descriptor with a nonempty
  workspace-relative `:under` (outside reserved control/Git roots) and
  `:must-exist true` must exist below that root as a regular file or bounded
  tree without symlinks, special files, unsafe hardlinks or nested mounts.
  The host copies it from the clone after the final checkpoint to
  `<under>/.run-ref-exports/<parent-run>/<activation>/<attempt>/<path relative to under>`
  with retained roots, no-follow traversal, the exact byte bound
  `:output-mib`, bounded file count and depth, and atomic no-overwrite
  publication. Identical child paths
  share one copy; conflicting descriptors, roots or destinations refuse.
  Aliases require the same canonical complete path descriptor and retain all
  result field locations. Overlapping returned trees share each source
  object once only when they use the same `under` and induce the same
  destination mapping; otherwise they refuse before publication. Distinct
  source paths are not aliases merely because their bytes match. Every
  exported regular file must have a link count of one. Validate every source
  and destination component and reject nested mounts, including bind mounts
  on the same device. Atomic publication is per non-overlapping subtree on
  its destination filesystem; parent commitment waits for the complete
  validated set. Before rename, durably bind the staged object's identity
  to the attempt and the staging/destination roots and parents, including
  device, inode and mount identity. Recovery may reuse an existing
  publication only by proving it is that same staged object under the bound
  parents/mounts, and validating its inventory and bytes. A pathname
  reservation and matching content do not establish ownership: refuse an
  identical foreign destination created before rename or substituted after
  rename, without changing it. The coordinator owns the durable binding's
  representation; this adds no separate publication ledger.
  The boundary validator checks the original child value and the rebased parent
  value against the same complete descriptor; this is not prefix replacement
  or a nominal cast. Destinations, original paths, field locations, sizes and
  digests are recorded in the settlement proof. A corrupted, missing,
  oversized or unrebaseable export refuses with `run_ref_export_invalid` and
  is never regenerated by rerunning the child. `FAILED` exports nothing.
- Export structural limits are the fixed `run_ref_confinement.v1` workspace
  tree limits: 262,144 unique source entries and 128 directory levels. The
  checkpoint policy owns these values; export applies them to the combined
  inventory of all returned paths, not separately per path or `under`.
  Count regular files and directories, including empty directories, returned
  directory roots and source ancestors needed to materialize the exported
  suffixes, once each. A declared `under` used only as an anchor and the
  synthetic export namespace directories are not copied source entries.
  Directory depth is relative to `under` at level zero; directories through
  level 128 and files immediately within them are allowed. The clone's own
  checkpoint limits still apply independently. Record the effective bounds
  in protected admission/settlement evidence; there is no authored override.
  `:output-mib` is the aggregate regular-file byte bound over this same unique
  inventory. Exceeding an export bound refuses with `run_ref_export_invalid`.
- Export lifetime: exports are never removed automatically and share the
  parent run's retention lifetime. Retiring a run means removing its run
  root, which holds the child control roots, and its
  `<under>/.run-ref-exports/<parent-run>` directories. `invalidate` never
  reaches an export, because exports exist only after the coordinator
  commits and K8 refuses superseding it. No new command is introduced.
- Workspace delta is collected from the clone after the final checkpoint
  through the existing tree-manifest path; it is a bounded description, not
  authority to read clone files.

## Source-Relative vs Workspace-Relative Taxonomy

- Workflow-source-relative reads:
  - `imports`
  - nested import targets
  - `asset_file`
  - `asset_depends_on`

- Workspace-relative runtime reads/writes:
  - `input_file`
  - `depends_on`
  - `output_file`
  - `expected_outputs.path`
  - `output_bundle.path`
  - `consume_bundle.path`
  - authored `state/*`, `artifacts/*`, and other deterministic `relpath` paths

- First-tranche reusable-library rule
  - Do not treat `input_file` or plain `depends_on` as workflow-bundled asset mechanisms.
  - Use the source-relative asset surface for library-owned prompts, rubrics, templates, and schemas.

- Output capture modes
  - `text` (default): store up to 8 KiB in `state.json`. If exceeded, set `truncated: true` and write full stdout to `logs/<Step>.stdout`.
  - `lines`: split on LF; store up to 10,000 lines. On overflow, set `truncated: true` and spill full stdout to `logs/<Step>.stdout`.
  - `json`: parse stdout as JSON up to 1 MiB buffer. Parse failure or overflow → exit 2 unless `allow_parse_error: true`.
  - When `allow_parse_error: true` in json mode, the step completes with `exit_code: 0`, stores raw `output` (subject to 8 KiB limit), omits `json`, and records `debug.json_parse_error`.

- State fields
  - For `lines`/`json`, omit raw `output` to avoid duplication; include `truncated` flag and mode-specific fields.
  - Deterministic artifacts parsed from `expected_outputs` or `output_bundle` are exposed under `steps.<Step>.artifacts` (unless artifact persistence is disabled).
  - This applies unchanged to an `output_bundle` whose sole field uses
    `json_pointer: ""` (see `specs/dsl.md`): the artifact value is the whole
    parsed JSON document, and `output_capture`/stdout are never consulted for
    it — the bundle file is the only structured-output authority regardless
    of field shape.
  - Runtime parsing, routing, artifact projection, exit behavior, checkpoint
    identity, and resume ignore all v2.15 guidance keys.
  - At v2.19, `kind: value` artifacts and public outputs retain the recursively
    validated payload in the existing artifact, workflow-output, report, and
    dashboard projections. Checkpoint/resume compatibility compares the
    declared `value` contract, not a prior payload's incidental shape.

## Recommended Strictness Split

- Heavy implementation/fix steps:
  - Prefer `output_capture: text` (or `lines`) with minimal deterministic artifacts.
- Assessment/review/gate steps:
  - Prefer `output_capture: json` with `allow_parse_error: false`.
- Workflow control flow:
  - Branch on strict published artifacts from assessment/review steps rather than free-form execution prose logs.

## Tee semantics details

- With `output_file` set, the file receives the full stream while state/log limits apply.
- `text`: up to 8 KiB retained in state; full stdout goes to `logs/<StepName>.stdout` when truncated.
- `lines`: up to 10,000 lines retained in state; full stdout goes to `logs/<StepName>.stdout` when truncated.
- `json`: buffer up to 1 MiB for parsing; on overflow or invalid JSON, exit 2 unless `allow_parse_error: true`. The `output_file` always receives the full stream.
- Stderr is captured separately and written to `logs/<StepName>.stderr` when non-empty.
- For session-enabled provider steps, console streaming displays normalized assistant text and, for Claude and Codex sessions, bounded tool-activity notices described in [Observability](observability.md). Raw session metadata transport never goes directly to the parent console. Tool notices are display-only; step-visible stdout used by `output_capture` and `output_file` remains normalized assistant text.

## Line splitting and normalization

- Lines are split on LF (`\n`). CRLF (`\r\n`) is normalized to LF in the `lines[]` entries.
- The raw, unmodified stdout stream is preserved in `logs/<StepName>.stdout` when truncation occurs or when JSON parsing fails.

## Adjudicated Provider IO (v2.11)

Historical execution contract: adjudicated workflow execution/promotion and
its old-profile recovery are retired, with no evaluated port selected. Shared
validation helpers retain their admitted callers; this format is not a launch
or repair recipe for the current package.

- Candidate output validation runs in the candidate workspace. Downstream workflow state is not updated from candidate outputs until selection and promotion complete.
- Selected-output promotion copies only declared deterministic outputs:
  - non-`relpath` `expected_outputs`: the candidate value file at `expected_outputs.path`
  - `relpath` `expected_outputs`: the path-only value file and, when `must_exist_target: true`, the candidate target file named by that value
  - `output_bundle`: the bundle JSON file and, for required bundle `relpath` fields, the candidate target file named by the extracted field value
- Promotion is a staged transaction: prepare a manifest, stage source files, reject duplicate destinations with different sources/roles, compare parent destinations against baseline preimages, replace files with same-filesystem temp-file renames, revalidate the parent output contract, and mark the manifest `committed` only after parent validation succeeds.
- If parent output validation fails after commit, the runtime rolls back files touched by the transaction using recorded backups or absent-destination tombstones. Unsafe rollback conflicts fail with `promotion_rollback_conflict`.
- Resume interprets promotion manifests by state: `prepared` repeats preimage checks and commits, `committing` treats already-staged destinations as committed when hashes match, `rolling_back` completes rollback, `failed` returns the recorded failure without publishing, and `committed` revalidates parent outputs before publication.
- Candidate and evaluator stdout/stderr are runtime-owned logs and sidecars. Adjudicated steps do not populate `output`, `lines`, `json`, `truncated`, or `debug.json_parse_error` from those streams.

## Evaluated Host Input IO (Target 2.40)

The [DSL](dsl.md#evaluated-durable-host-input-target-240) admits typed host
questions independently of providers. Runtime rendering reuses typed prompts
and document snapshots, then appends the answer contract without provider
output-file instructions. The memo holds the complete frozen question and
answer/reply descriptors; no provider adapter or result-file parser is involved.

Question text, prompt source/`:doc` reads, answer/reply contracts, timeout
duration, ordered evidence paths/contracts and ordinary operand dependencies
are semantic inputs. Source/manifest changes obey normal rebuild refusal;
changed runtime documents/producers obey `effect_input_diverged`. An evidence
override cannot waive these rules, including `must-exist` workflow input
preflight for a path also present in `:show`.

`:show` bytes are presentation evidence. Creation safely snapshots regular
readable files and records ordered `{path, contract, sha256}` rows in the start.
Settlement safely rehashes the current files; changed, missing or unreadable
presentation evidence refuses `shown_evidence_changed` by default. With explicit
`accept_changed_evidence=True`, a host may accept those differences. Each
`evidence_changes` row has exactly `index`, `path`, `original_sha256`, `observed`:
`observed` is `{status: present, sha256}` or `{status: missing|unreadable, errno}`.
The ordinal index distinguishes repeated paths in the authored list. Unsafe
paths, forbidden links or non-file objects are unconditional refusals, never
waived. The override boolean is stored even when there are no differences.
The safe snapshot is repeated immediately before publication; the contract
records bytes actually read, not protection against subsequent external writes.

After commit, replay validates frozen request and accepted snapshot from memo;
it does not require current show-only bytes to match. Independent `:doc`, input
or producer checks still apply to the same file. The original request snapshot
is never rewritten to pretend changed evidence was original.

Under `effects/<sha256(identity)>/attempt-N/`, `request.prompt.txt`, `request.json`
and `reply.json` are safely atomically published, rebuildable views. The memo's
conventional `result_path` remains `.../result.json`; no result file is required
or written for this inline-only effect. Both typed value and its canonical
result digest live in the commit. Missing views do not authorize dispatch,
settlement or recovery. Read-only pending/report/dashboard never repair files.
