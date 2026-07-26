# Step IO and Output Capture (Normative)

- Input handling
  - `input_file`: read literal contents; no substitution inside file contents.
    - Under reusable `call`, `input_file` remains workspace-relative and does not become import-local.
  - `asset_file` (v2.5): read literal contents from the authored workflow source tree; provider-only and mutually exclusive with `input_file`.
  - When using a provider, the composed prompt (after optional injection) is passed via argv `${PROMPT}` or piped to stdin per provider template.

- Output handling
  - `output_file`: STDOUT is tee'd to this file and to the orchestrator capture pipeline.
  - Stderr is captured separately and written to logs when non-empty.
  - v2.10 session-enabled provider steps normalize structured provider transport before ordinary output capture:
    - normalized assistant text becomes the step-visible stdout used by `output_capture` and `output_file`
    - raw metadata transport remains on the runtime-owned provider-session spool path under the run root
  - Deterministic artifact contracts:
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
      `value_guidance_example_unsupported`.
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
    - A compiled direct `Value` result uses one compiler-owned field named
      `__result__`, with `json_pointer: ""` and `type: value`. The bundle bytes
      are the JSON encoding of the value itself; neither the runtime nor the
      provider contract adds a `{"value": ...}` envelope.
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
- For v2.10 session-enabled provider steps, `--stream-output` and `--debug` stream only normalized assistant text to console stdout; raw session metadata transport never goes directly to the parent console.

## Line splitting and normalization

- Lines are split on LF (`\n`). CRLF (`\r\n`) is normalized to LF in the `lines[]` entries.
- The raw, unmodified stdout stream is preserved in `logs/<StepName>.stdout` when truncation occurs or when JSON parsing fails.

## Adjudicated Provider IO (v2.11)

- Candidate output validation runs in the candidate workspace. Downstream workflow state is not updated from candidate outputs until selection and promotion complete.
- Selected-output promotion copies only declared deterministic outputs:
  - non-`relpath` `expected_outputs`: the candidate value file at `expected_outputs.path`
  - `relpath` `expected_outputs`: the path-only value file and, when `must_exist_target: true`, the candidate target file named by that value
  - `output_bundle`: the bundle JSON file and, for required bundle `relpath` fields, the candidate target file named by the extracted field value
- Promotion is a staged transaction: prepare a manifest, stage source files, reject duplicate destinations with different sources/roles, compare parent destinations against baseline preimages, replace files with same-filesystem temp-file renames, revalidate the parent output contract, and mark the manifest `committed` only after parent validation succeeds.
- If parent output validation fails after commit, the runtime rolls back files touched by the transaction using recorded backups or absent-destination tombstones. Unsafe rollback conflicts fail with `promotion_rollback_conflict`.
- Resume interprets promotion manifests by state: `prepared` repeats preimage checks and commits, `committing` treats already-staged destinations as committed when hashes match, `rolling_back` completes rollback, `failed` returns the recorded failure without publishing, and `committed` revalidates parent outputs before publication.
- Candidate and evaluator stdout/stderr are runtime-owned logs and sidecars. Adjudicated steps do not populate `output`, `lines`, `json`, `truncated`, or `debug.json_parse_error` from those streams.
