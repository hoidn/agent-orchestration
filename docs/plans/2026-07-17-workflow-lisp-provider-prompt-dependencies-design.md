# Workflow Lisp Provider Prompt Dependencies Design

## Metadata

- **Status:** proposed
- **Kind:** feature / architecture decision
- **Owner:** Workflow Lisp frontend and shared workflow-runtime maintainers
- **Reviewers:** independent specification and implementation-quality reviewers
- **Created:** 2026-07-17
- **Last material update:** 2026-07-17
- **Related docs:**
  - `docs/workflow_yaml_orc_gap_list.md`
  - `docs/design/workflow_language_design_principles.md`
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/design/workflow_lisp_semantic_workflow_ir.md`
  - `docs/design/workflow_lisp_executable_ir.md`
  - `specs/dependencies.md`
  - `specs/providers.md`
  - `specs/security.md`
- **Implementation target:** a generic `provider-result :prompt-dependencies`
  surface plus shared dependency-content read hardening and structured runtime
  evidence

## Summary

Workflow Lisp `provider-result` can select a provider prompt source and can
render typed values into a provider request, but it cannot currently declare
workspace files whose contents must be present in the composed provider prompt.
This prevents a `.orc` port from preserving a YAML provider step that uses
`depends_on.required` or `depends_on.optional` with content injection.

Add one narrow, generic `:prompt-dependencies` option to `provider-result`.
The option accepts ordered required and optional operands that already have a
declared workspace-relpath type, a `prepend` or `append` position, and an
optional literal instruction. It always requests content injection. Lowering
projects the option onto the existing shared `depends_on`
dependency-resolution and prompt-composition contract. It does not introduce
path-literal syntax, a new runtime prompt transport, provider kind, renderer,
command adapter, or family-specific compiler route.

The shared content-read boundary is also strengthened. Every resolved content
dependency must be a stable, regular, UTF-8 file inside the resolved workspace
when it is read. A required file that is missing, unreadable, unsafe, unstable,
or invalid fails before provider launch. Structured evidence records the exact
ordered inputs and content digests that produced the prompt without copying
file bodies into an additional evidence artifact.

This approach intentionally makes arbitrary binary injection, wildcard
authoring, dynamic instruction text, and custom renderer behavior harder to add
later. Those are excluded so the first tranche remains one typed authoring
surface over one existing normative runtime contract.

## Context And Authority

Normative behavior belongs to `specs/`. This design selects a Workflow Lisp
authoring and lowering route for that behavior; it does not redefine the YAML
dependency contract.

The governing rules are:

- `specs/dependencies.md` owns workspace-relative dependency resolution,
  required versus optional matching, content formatting, deterministic
  lexicographic resolved-path ordering, the approximately 256 KiB injection
  cap, and prompt-only mutation.
- `specs/providers.md` owns prompt composition order and keeps base prompt
  sources, workspace dependencies, source assets, consumed artifacts, typed
  prompt inputs, and output contracts distinct.
- `specs/security.md` requires absolute paths and `..` traversal to be rejected,
  requires resolved symlinks to remain inside the workspace, and requires path
  checks both during validation and immediately before filesystem operations.
- `docs/design/workflow_language_design_principles.md` requires generic
  composition, visible effects, structured authority, and source provenance;
  it rejects hidden command glue as a substitute for a language or runtime
  contract.
- `docs/workflow_yaml_orc_gap_list.md` requires provider-input evidence to prove
  that required dependency content and ordering are preserved. Compile success,
  a path-only request, or an undeclared ambient file read is insufficient.

The relevant current implementation path is:

```text
provider step
  -> PromptComposer reads asset_file or input_file
  -> asset_depends_on content is prepended in declared order
  -> DependencyResolver resolves workspace depends_on
  -> DependencyInjector composes list/content injection
  -> typed prompt inputs are appended
  -> consumed artifacts are injected
  -> output-contract guidance is appended
  -> provider invocation is prepared and launched
```

Current shared Core AST, executable IR, persisted surface, and lexical provider
checkpoint digests already carry `depends_on`. The missing surface is the
typed Workflow Lisp authoring path into that existing shared field. The current
content injector also catches read errors and skips a file; that behavior is
not adequate for a contract that says required content is present.

One terminology conflict must be resolved explicitly: plain workspace
`depends_on` uses **lexicographic resolved-path order**. Declared order belongs
to `asset_depends_on`. This design follows the normative dependency spec rather
than treating the order of authored `:required` operands as final prompt order.

### Feasibility Findings

The design relies on existing generic ownership points rather than an unproven
family route:

- `orchestrator/workflow_lisp/expressions.py` already represents
  `ProviderResultExpr` as the owner of provider, prompt, input, and return
  operands. The new clause is one additional typed child specification.
- `orchestrator/workflow_lisp/wcc/elaborate.py` carries provider operations as
  `WccPerform`, and `orchestrator/workflow_lisp/wcc/defunctionalize.py` rebuilds
  `LowerableProviderResult` before calling the shared owner emitter. This is the
  existing generic preservation route that the new operands must join.
- `orchestrator/workflow_lisp/lowering/effects.py` owns provider-result step
  construction. It can project the new spec onto the same provider-step
  mapping where it already projects the prompt source and result contract.
- `orchestrator/workflow/core_ast.py`,
  `orchestrator/workflow/executable_ir.py`, and
  `orchestrator/workflow/persisted_surface.py` already carry provider
  `depends_on` values through shared validation and persistence.
- `orchestrator/workflow/prompting.py` and
  `orchestrator/workflow/executor.py` already compose workspace dependency
  injection before provider preparation. `orchestrator/deps/resolver.py`
  already owns required/optional resolution and lexicographic ordering, while
  `orchestrator/deps/injector.py` already owns content headers and truncation.
- `orchestrator/workflow_lisp/lexical_checkpoints.py` already includes
  `depends_on` in the provider prompt-input contract digest and revalidates that
  digest before completed-effect reuse.
- `tests/test_dependency_injection.py` and
  `tests/test_prompt_contract_injection.py` already exercise the shared YAML
  content and composition paths.

These findings establish that no new executable node, provider transport, or
resume policy is required. They do not establish the missing frontend syntax,
classified exact-path projection, stable read boundary, Semantic IR extension,
or structured evidence. Those remain explicit implementation obligations and
must be proven by the integration fixture described below before the surface is
classified as implemented.

The shared per-attempt snapshot/render owner is specifically an open
prerequisite, not an existing capability claim. The current ordinary retry and
adjudicated composition paths sequence resolution/injection separately, and
ordinary composition occurs outside the retry attempt boundary. Before
frontend parity evidence is accepted, implementation must consolidate both
paths and pass a focused spy/capturing-provider fixture proving one snapshot,
one render, and zero evidence reopens per attempt in both paths.

Crash-durable attempt allocation is also an implementation prerequisite. The
current `StateManager` temp-file replacement is atomic but does not `fsync` the
file and parent directory, and there is no persisted provider-attempt ordinal.
Implementation must add the narrowly scoped allocator and durable state-write
boundary described below, with fault injection at every named crash point,
before evidence paths can be considered collision-safe.

`ResumeScopePath.call_frame_ids` and nested call-frame `RunState` snapshots
already provide the ordered recursive call identity required below; the new
allocator must reuse them rather than invent a flat current-frame token.
Conversely, the current `Path.read_text` injector has no descriptor-relative
safe-open capability. The implementation must prove the workspace-dir-fd,
no-follow component walk and nonblocking final-open contract with the FIFO,
device-mode, symlink, and race fixtures below; unsupported platforms remain an
explicit fail-closed prerequisite rather than an implicit pathname fallback.

## Problem

`provider-result :inputs` and prompt externs cannot express the missing
behavior:

- `PromptExtern` selects exactly one `asset_file` or `input_file` base prompt.
- A typed prompt input using the `posix-path-line` renderer renders a path, not
  the target file's contents.
- Canonical typed-value rendering is a pure value view. It has no workspace
  authority and must not acquire hidden filesystem reads.
- `consumes` provides artifact lineage and renders resolved values. Its
  `content` prompt mode does not mean “open this relpath and inject the target
  bytes.”
- A prompt that merely tells the provider to open paths relies on provider-side
  filesystem behavior and does not prove that the orchestrator supplied the
  required dependency content.
- A command adapter that reads files would add a second effect, bundle,
  checkpoint, security implementation, and possible stale interval between the
  adapter and provider launch.

Without a generic surface, individual migrations would need a family-specific
lowering branch, prompt prose that changes transport semantics, or an adapter
that duplicates a runtime facility the orchestrator already owns.

## Goals

- Let any authored `provider-result` declare required and optional workspace
  files whose UTF-8 contents enter the provider prompt.
- Require typed relpath operands and preserve their type/source provenance.
- Reuse the shared `depends_on` resolver and injector, including content
  headers, position, size cap, truncation reporting, and lexicographic resolved
  ordering.
- Fail before provider launch when required content cannot be read safely and
  stably.
- Emit structured, digest-bound evidence for the actual dependency snapshot
  used in one provider invocation.
- Preserve effect visibility through typed frontend AST, WCC, Core AST,
  semantic IR, executable IR, source maps, persistence, and resume validation.
- Keep the mechanism free of workflow-family, module, provider, or compiler
  name branches.
- Preserve existing behavior when `:prompt-dependencies` is absent.

## Non-Goals

- Do not add arbitrary prompt renderers or a workspace-aware `render_view`.
- Do not add binary-file injection, character-set selection, directory
  injection, URL fetching, or external storage reads.
- Do not expose dependency globs in this first typed surface.
- Do not add dynamic instruction expressions or prompt-text interpolation.
- Do not turn `depends_on` into artifact lineage or replace `consumes`.
- Do not turn prompt text or prompt-dependency evidence into semantic state.
- Do not invalidate or re-execute an already completed provider result merely
  because a dependency file later changes.
- Do not add a provider-specific or migration-family-specific compatibility
  branch.
- Do not change source-relative `asset_depends_on` ordering or ownership.

## Decision

Add a closed `:prompt-dependencies` clause to `provider-result`:

```lisp
(provider-result providers.worker
  :prompt prompts.work
  :inputs (request)
  :prompt-dependencies
    (:required (work-order-path target-design-path ledger-path)
     :optional (prior-findings-path prior-check-log-path)
     :position prepend
     :instruction "Use these files as authoritative inputs:")
  :returns WorkResult)
```

The clause has these rules:

- At least one of `:required` or `:optional` must be present and non-empty.
- Each list contains inline-lowerable expressions whose static type is a
  declared workspace `relpath` path type.
- Each expression must lower to an existing typed runtime binding reference.
  It may not introduce another effect, closure, command, provider call, hidden
  materialization, or new public path-literal form.
- Content injection is intrinsic to this form; there is no authored `:mode` in
  the first tranche.
- `:position` is optional and defaults to `prepend`; only `prepend` and
  `append` are accepted.
- `:instruction` is optional. When present it must be a literal UTF-8 string.
  It is not subject to workflow-variable or provider-parameter substitution.
- The compiler rejects authored or runtime-resolved glob metacharacters for
  this exact-path surface. The ordinary YAML `depends_on` glob surface remains
  unchanged.

Lowering emits the equivalent shared provider-step configuration:

```yaml
depends_on:
  required:
    - ${...work-order-path...}
    - ${...target-design-path...}
    - ${...ledger-path...}
  optional:
    - ${...prior-findings-path...}
    - ${...prior-check-log-path...}
  inject:
    mode: content
    position: prepend
    instruction: "Use these files as authoritative inputs:"
```

Exact mode is not selected by a string inside the untyped `depends_on` mapping.
The Workflow Lisp compiler constructs a separate typed
`CompilerPromptDependencyContract` IR field:

```text
CompilerPromptDependencyContract
  schema: "compiler_prompt_dependency_contract.v1"
  origin_kind: WORKFLOW_LISP_PROVIDER_RESULT_PROMPT_DEPENDENCIES
  path_interpretation: EXACT
  evidence_required: true
  source_origin_key: non-empty source-map origin key
  source_workflow_sha256: digest of accepted `.orc` source
  normalized_contract_sha256: digest of classified rows + injection policy
```

`normalized_contract_sha256` covers canonical JSON
`{schema, required_binding_refs, optional_binding_refs, position,
instruction_utf8_sha256_or_null}` with both binding arrays in authored order.
`source_workflow_sha256` covers the accepted `.orc` source bytes exactly.

The typed enum values have no public string-to-enum coercion. Only the shared
Workflow Lisp owner emitter receives the validated compiler-origin capability
needed to construct this dataclass. Both WCC and classic lowering call that
owner. The YAML surface schema has no corresponding field and explicitly
rejects `path_interpretation`, `compiler_prompt_dependency_contract`, or
lookalike keys at the step, `depends_on`, and `depends_on.inject` levels.
Ordinary YAML therefore carries no marker at all; its resolver mode is selected
by its typed YAML-origin execution path, not by an authored `"glob"` value.

Core and executable IR carry the typed optional field separately from
`depends_on`. Persisted-surface serialization uses a dedicated closed member,
not an arbitrary mapping: its loader accepts it only when loaded-bundle
provenance identifies Workflow Lisp, the bundle/build checksum authenticates
the serialized IR, the source digest and source-map origin match the build
manifest, and `normalized_contract_sha256` recomputes from the typed
configuration. Otherwise loading fails. Runtime enables exact mode/evidence
only from that validated typed field; it never inspects an untyped mapping for
an origin marker. The field is compiler/runtime infrastructure, not a public
YAML key, family name, second prompt transport, or runtime-plan field.
Here “authenticated origin” means bound to the repository's checksum-validated
compiler build/provenance chain, not merely carrying a caller-supplied origin
string and not claiming an external cryptographic signer.

### Alternatives Rejected

**Workspace-file-content typed renderer.** Rejected. The current renderer is a
pure `typed value -> bytes` boundary. Giving it a workspace, path resolution,
filesystem errors, symlink policy, injection position, and truncation would
mix runtime I/O authority into the value-view subsystem and duplicate the
dependency injector.

**`consumes` injection.** Rejected. `consumes` means producer/consumer artifact
lineage. Reusing it for arbitrary workspace reads would blur authority and
still would not make a relpath's target body the resolved artifact value.

**Certified file-reading adapter.** Rejected. It would create an unnecessary
effect and result bundle, duplicate path and truncation policy, complicate
resume identity, and permit the file snapshot to become stale before the
provider boundary.

**Prompt prose plus declared paths.** Rejected as the parity mechanism. It can
be useful prompt guidance, but it makes the provider responsible for acquiring
content and cannot prove the orchestrator delivered the dependency snapshot.

## Design Details

### Typed Frontend Surface

Introduce one immutable `PromptDependencySpec` owned by `ProviderResultExpr`:

```text
PromptDependencySpec
  required: tuple[ExprNode, ...]
  optional: tuple[ExprNode, ...]
  position: prepend | append
  instruction: literal string | absent
  span/form-path/expansion provenance
```

Expression elaboration parses the nested keyword sections, rejects unknown or
duplicate keys, preserves authored operand order for diagnostics and source
maps, and applies the defaults above. Expression traversal, normalization,
procedure specialization, local binding substitution, and dependency analysis
must visit every path operand. No path operand may disappear because it sits in
configuration rather than `:inputs`.

Typechecking requires each operand to resolve to a `PathTypeRef` whose path
definition is `kind=relpath`. A plain `String`, provider ref, prompt ref, list,
record, optional value, or unresolved union field is rejected. There is no
contextual conversion from `String` and no public path-literal syntax in this
design. The private `__generated-relpath-seed__` compiler form is not an
authoring surface and cannot be used to satisfy this clause.
Optional means that an exact file may be absent at runtime; it does not mean the
operand itself has type `Optional<Path>`.

Under current language surfaces, eligible values arise from typed workflow or
procedure parameters, local aliases of those parameters, loop-carried relpath
fields, or validated command/provider result fields declared with a relpath
path type. Inline-lowerable means a reference to one of those existing typed
bindings through ordinary runtime substitution. Arbitrary nested computation
must first become an ordinary typed binding through the existing generic
pure-value route. The prompt-dependency clause neither creates a literal nor
synthesizes a hidden command or materialization step.

### WCC And Lowering

WCC/schema 2 is the default route and must retain the complete spec. The WCC
provider operation carries:

- every required and optional path as a typed WCC value with stable authored
  ordering;
- required/optional partition counts or explicit row roles;
- the literal position and instruction;
- the source span, form path, and expansion stack of the enclosing clause and
  each operand.

Defunctionalization reconstructs the same `PromptDependencySpec` before the
shared provider-result owner emitter runs. Classic/direct compatibility
lowering and WCC lowering call the same owner-level projection. A
`LowerableProviderResult` therefore includes the normalized prompt-dependency
spec; neither route independently invents YAML-shaped mappings.

The owner emitter projects typed operands through the existing reference
template machinery, adds ordinary `depends_on` data to the generated provider
step, and constructs the separate typed compiler contract with authenticated
origin. It does not add a new executable node. The workspace reads and prompt
composition are part of the atomic provider effect and remain visible as a
prompt surface on that effect.

### Shared IR And Source Maps

The shared Core and executable provider-step configurations already contain
`depends_on`; they gain the optional typed
`CompilerPromptDependencyContract | None` field described above. The new
lowering uses both fields and follows ordinary shared validation. No
frontend-to-executor shortcut or mapping-to-contract coercion is permitted.

Semantic IR must expose a normalized prompt-dependency contract on the
provider's `SemanticPromptSurface`, including required and optional typed
source references, position, instruction digest, exact-path mode, and the
source-map origin key. This is an additive optional member under the current
Semantic IR schema version: its serializer omits the member when absent, and
the change does not justify a global version bump that would alter every
keyword-free artifact. The reviewed schema definition still must document and
validate the member. It must not be inferred later from debug YAML or prompt
evidence.

Source maps bind:

- the `:prompt-dependencies` clause to the provider step's prompt-dependency
  surface;
- each operand to its required or optional row and lowered runtime reference;
- `:position` and `:instruction` to the normalized injection policy.

Executable IR remains runtime authority. Semantic IR and source maps explain
the contract but do not decide which bytes are read.

The normalized dependency configuration is owned by the executable/runtime
provider step and retained by the existing Core, executable, and persisted
surfaces as typed values across every round trip. Tests must deserialize into
the dataclass/enum, reject hand-built mappings and YAML-origin bundles, and
recompute both source and normalized-contract digests. `runtime_plan` remains
topology/checkpoint planning only: it does not
gain path operands, injection policy, exact-path metadata, or any other
dependency configuration. A debug projection may reference the executable
step, but it is not an additional owner.

### Runtime Resolution And Composition

Both ordinary retry execution and adjudicated provider prompt construction
must call one shared per-attempt API. Conceptually, that API is:

```text
snapshot_and_render_content_dependencies(
  workspace,
  classified_dependency_rows,
  injection_policy,
  runtime_variables,
) -> PromptDependencySnapshot
```

`PromptDependencySnapshot` contains the classified authored rows, absent rows,
canonical resolved groups, immutable rendered injection-block bytes, stable
read metadata, truncation metadata, and the digest inputs required by evidence.
It owns resolution, stable open/read, UTF-8/newline normalization, de-duplication,
ordering, and rendering as one operation. Evidence is derived from this object;
it never reopens a dependency. No other executor path may sequence
`DependencyResolver` and `DependencyInjector` independently for content mode.

Inside each retry, the ordinary provider executor first requires successful
safe-I/O preflight, then allocates an attempt identity when the typed compiler
contract requires one, then calls the API once before provider preparation.
Each retry gets exactly one fresh snapshot and render. The adjudicated
prompt-composition path uses the same preflight/allocation/API order once for
each candidate attempt/workspace. Existing YAML dependencies use the shared
preflight/API but allocate no Workflow Lisp attempt evidence. Only
compiler-produced Workflow Lisp configuration can request exact-path mode.
After the immutable dependency block is inserted, the remaining composition
stages run and the final prompt digest is finalized before provider
preparation.

For a provider step with prompt dependencies, prompt construction remains:

1. read the declared base prompt source;
2. prepend source-relative `asset_depends_on` content in declared order;
3. resolve and inject workspace prompt dependencies at their declared
   `prepend` or `append` position;
4. append typed prompt-input rendering;
5. apply consumed-artifact prompt injection;
6. append output-contract guidance;
7. prepare and launch the provider.

Required and present optional exact paths are combined, de-duplicated, and
sorted by canonical resolved workspace-relative POSIX target before content
rendering. Symlink and lexical aliases of one target render once. If any alias
is required, the canonical group is required. Every authored alias and role
remains in evidence. This preserves the normative plain-`depends_on` ordering;
authored list order remains provenance, not final prompt order. The canonical
resolved target is also the identity printed in the existing file header.

The content block uses the existing header and cap contract:

```text
<instruction>

=== File: relative/path (shown_bytes/total_bytes) ===
<UTF-8 content>
```

Omitting `:instruction` preserves the current injector's compatibility label:
if at least one authored required row exists, the combined block starts with
the existing required-dependencies default instruction; otherwise it starts
with the existing optional-dependencies default instruction. Thus a mixed
required/optional block uses the required label even though evidence retains
each row's true role. An optional-only no-match still emits the same
instruction-only block as current YAML behavior. A literal authored
instruction replaces that default. Header syntax, spacing, UTF-8-safe prefix
selection, and truncation summary remain owned by the content renderer; the
approximately 256 KiB cap becomes the exact hard boundary clarified below.
Truncation is valid
generic runtime behavior, but a migration parity gate may require
`truncated=false` when the old workflow's semantic input would otherwise be
incomplete.

### Instruction And Injection Cap

The content block has a hard `MAX_INJECTION_BYTES=262144` limit over the exact
UTF-8 bytes returned by the injector, excluding the prompt composer's outer
two-newline separator. `TRUNCATION_SUMMARY_RESERVE_BYTES=512`; therefore an
authored instruction may contain at most `261630` UTF-8 bytes
(`262144 - 2 - 512`). Workflow Lisp enforces this after strict UTF-8 encoding at
compile time with diagnostic code
`prompt_dependency_instruction_exceeds_byte_limit`. Runtime repeats the check
against persisted IR and applies the same limit to YAML custom instructions;
failure is `invalid_injection_contract` with detail code
`dependency_instruction_exceeds_byte_limit`, before dependency reads or
provider preparation. Default instructions are constants covered by the same
runtime assertion.

Rendering accounts exact encoded bytes for the instruction, every separator,
header, shown UTF-8-safe content prefix, inline truncation marker, and aggregate
summary. The summary is rendered before prefix budgeting and must be at most
512 bytes; otherwise runtime fails with
`dependency_truncation_summary_exceeds_reserve`. Full groups are admitted while
the complete final block fits. The first partial group receives the largest
strict UTF-8 prefix that leaves room for its exact header, inline marker, and
aggregate summary; if no positive prefix fits, that and remaining groups are
omitted. No later group is rendered after a truncated or omitted group. The
final block is asserted `<=262144`; exceeding it is an internal contract
failure, never silent overrun.

For YAML, stable blocks below the cap remain byte-identical. Two boundary cases
are deliberate compatibility tightenings: a custom instruction above 261630
bytes now fails instead of producing an oversized block, and legacy approximate
header accounting at the cap is replaced by exact accounting. Tests cover
instruction byte lengths 261629, 261630, and 261631; multi-byte code points at
the boundary; blocks at 262143, 262144, and 262145 pre-truncation bytes; a
header that leaves no useful prefix; a 512-byte summary; and a rejected
513-byte summary. Differential tests still require exact legacy bytes whenever
the legacy block is strictly below the new truncation boundary.

### Stable Fail-Closed Read Boundary

The current “catch and skip” content read is replaced for every selected
content dependency. Before any provider process starts, the runtime must:

1. Substitute each runtime binding. Reject undefined variables and reject a
   result containing any residual `${...}` expression; exact-path mode has no
   escape that can make such a residual valid. Exact-path
   values reject NUL, backslash, empty or `.` values, absolute paths, a `..`
   component, and any `*`, `?`, or `[` glob-magic character. They are parsed
   and normalized as workspace-relative POSIX paths.
2. Open the trusted, already resolved workspace root as a directory descriptor
   with `O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW`; verify it by `fstat`, and
   retain it for the whole snapshot. All subsequent lookups are descriptor
   relative. String-prefix containment and pathname `open(workspace / path)`
   are forbidden.
3. Resolve each authored alias component-by-component relative to the trusted
   descriptor. Use no-follow `stat`/`readlink` operations, a bounded symlink-hop
   count, and a component stack that rejects escape above the workspace. An
   absolute symlink target is converted to workspace-relative components only
   when component-aware comparison places it beneath the already resolved
   workspace root; otherwise it fails. `ENOENT` on a direct non-symlink
   component of an optional path is `status=absent`; `ENOENT` after following a
   symlink is a broken-link error. Every other lookup error fails. This yields
   a canonical physical workspace-relative target without trusting
   `Path.resolve` as the security decision.
4. Group aliases by that canonical target, apply required-wins, and
   lexicographically sort targets. For each target, walk every parent component
   from the workspace descriptor with
   `O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW`, retaining the descriptor and an
   identity tuple `(st_dev, st_ino, stat.S_IFMT(st_mode), st_mtime_ns,
   st_ctime_ns)` for each directory.
5. Open the final component relative to its verified parent descriptor with
   `O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK` before inspecting it. This prevents
   a FIFO from blocking the runtime before type validation. Immediately
   `fstat` the descriptor, capture `(st_dev, st_ino, stat.S_IFMT(st_mode),
   st_size, st_mtime_ns, st_ctime_ns)`, and require `stat.S_ISREG(st_mode)`.
   FIFOs, directories, sockets, devices, and other non-regular modes close and
   fail without reading.
6. Re-resolve every authored alias by the same descriptor-relative algorithm,
   re-walk the canonical parent components, and require every retained
   directory identity plus the final `(st_dev, st_ino)` to match the opened
   descriptor chain. A disappearing, retargeted, or parent-component-swapped
   alias fails.
7. Clear no safety flags and stream the verified regular-file descriptor from
   offset zero exactly once. Compute the raw digest
   over the exact bytes returned by the descriptor and decode with a strict
   incremental UTF-8 decoder. Normalize newlines exactly like the current
   text-mode reader: CRLF and lone CR become LF, including across chunk
   boundaries. Re-encoding that normalized Unicode as UTF-8 defines the
   renderer's full content bytes and preserves successful YAML prompt bytes for
   the same dependency snapshot.
8. Capture the same post-read file and parent-directory `fstat` tuples and
   require exact equality. Re-resolve every alias and descriptor-walk the target
   once more, requiring the same component and final identities. Any identity,
   type, size, timestamp, component, or alias-target change fails the attempt.
9. Close every file, component, and workspace descriptor before evidence
   publication, provider preparation, or launch. The snapshot retains only the
   bounded normalized prefix needed by the renderer plus counts/digests for the
   full stream. That immutable prefix is the only dependency content available
   to the renderer; evidence receives metadata and digests, never bodies. Every
   failure exit closes all descriptors in a `finally`-equivalent cleanup path.

The bytes retained from the verified open descriptor are the only bytes added
to the prompt. A later workspace mutation does not alter the already composed
prompt. If the platform cannot establish the identity checks needed for this
contract, it fails closed rather than falling back to an unchecked `read_text`.

A missing optional exact path produces an evidence row with `status=absent` and
is omitted from canonical groups. Once an optional path resolves to an existing
target, unsafe, non-regular, unreadable, unstable, or invalid UTF-8 content is
an error rather than a silent omission. Optional weakens existence only, not
content safety. Platforms that cannot provide descriptor-relative open/stat,
`O_DIRECTORY`, `O_NOFOLLOW`, `O_NONBLOCK`, the required descriptor identity, or
nanosecond mutation metadata fail closed; there is no unchecked fallback.

### Platform Capability Gate

The first content-injection attempt for each `(workspace st_dev, aggregate run
root st_dev)` pair runs and caches an operational
`prompt_dependency_safe_io.v1` capability probe. Constant presence alone is
insufficient. In private probe directories beneath the workspace and aggregate
run root, the probe must demonstrate all of the following and clean every probe
entry before returning:

- `open`, `stat`, `readlink`, `link`, and `unlink` descriptor-relative support;
- `O_DIRECTORY`, `O_CLOEXEC`, `O_NOFOLLOW`, and `O_NONBLOCK` behavior, including
  no-follow rejection of a symlink and nonblocking read-open of a FIFO;
- stable nonzero `st_dev`/`st_ino`, `stat.S_IFMT`, `st_mtime_ns`, and
  `st_ctime_ns` on files/directories;
- file and directory `fsync`, atomic hard-link no-clobber with observable
  `EEXIST`, and exclusive `flock` on the aggregate lock filesystem.

The probe result records only capability booleans, platform/OS identifier,
filesystem device identifiers, and a stable failure code—never host paths. Any
failed check yields `unsupported_safe_read_platform`; no partial safe-reader,
pathname fallback, evidence publication, or provider preparation occurs.

Ordering is mandatory. For a loaded typed compiler contract, preflight runs
immediately after aggregate run-root/bundle resolution and before fresh
`RunState` initialization or any resume/status/current-step mutation. Legacy
YAML, which has no allocator/evidence contract, runs the same preflight before
its first content snapshot. In both cases, resolve the aggregate owner/device
pair, run or load a successful capability-cache entry, and only then acquire an
attempt ordinal.
The probe itself never reads or writes `provider_attempt_allocations`. A failed
or interrupted probe returns `unsupported_safe_read_platform` through the
ordinary pre-execution failure channel with no allocator member creation,
ordinal/event, evidence file, retry-counter advance, dependency open, or
provider preparation. Negative cache entries may avoid repeating a known
failure for the same process/device pair, but only a complete successful probe
authorizes allocation. Ordinary and adjudicated paths call the same preflight.

This first tranche therefore supports only POSIX-style native filesystems that
pass the operational probe. Native Windows and other platforms lacking these
semantics change from possible legacy YAML content injection to a stable
fail-closed result. WSL is supported only according to the mounted filesystems'
actual probe result. CI must run the positive probe and FIFO/no-follow/link/lock
integration checks on each claimed POSIX platform, run a forced-negative probe
test everywhere, and on native non-POSIX verify the stable failure occurs before
dependency open/provider preparation. The capability status matrix must list
this platform boundary; support cannot be claimed from mocked constants alone.

### Crash-Consistent Visit And Attempt Allocation

Evidence paths never allocate attempt identity. Add one narrowly owned,
optional `provider_attempt_allocations` member to root `RunState`. It is omitted
when empty so workflows without the new surface retain byte compatibility.
`StateManager.allocate_provider_attempt` is the sole writer and performs an
atomic, file- and directory-`fsync`ed root-state transition under the successful
preflight and cross-process lock order defined below. Call-frame state managers
delegate allocation to this root owner rather than maintaining a second
counter.

`resolve_aggregate_run_owner(manager)` is the single resolver used by ordinary,
loop, call-frame, and adjudicated paths. It follows `parent_manager` links while
recording object identities, rejects a cycle or a non-`StateManager` terminal,
and at every hop requires the same non-empty `run_id`, workspace device/root,
and an expected call-frame `run_root` beneath the eventual aggregate run root.
It returns the terminal root `StateManager`, its ordered `ResumeScopePath`, and
the aggregate run root. The collected nested roots must match the deterministic
call-frame roots for that path and remain beneath the aggregate root. The
call-frame path is then recursively validated against root state as described
below. Allocation and publication each perform exactly one transition through
this returned root;
nested managers never mirror `provider_attempt_allocations` into nested
`RunState` or write a second manifest event.

The caller supplies a `ProviderAttemptScope` assembled from existing persisted
execution identity, not evidence:

```text
{
  run_id: non-empty string from RunState.run_id,
  resume_scope: {
    root_workflow_file: non-empty ResumeScopePath.root_workflow_file,
    call_frame_ids: [non-empty string, ...]
  },
  runtime_step_id: non-empty validated RuntimeStepInput step id,
  enclosing_step: {
    step_name: non-empty root/call-frame topology step name,
    step_id: non-empty validated enclosing RuntimeStepInput step id,
    visit_count: positive leaf RunState.step_visits[step_name]
  },
  loop_iteration:
    {kind: "for_each", loop_step_id: non-empty string,
     iteration: non-negative leaf RunState.for_each[loop_name].current_index}
    | {kind: "repeat_until", loop_step_id: non-empty string,
       iteration: non-negative
         leaf RunState.repeat_until[loop_name].current_iteration}
    | null,
  adjudication_subject: {candidate_id: non-empty validated string} | null
}
```

This is a closed JSON object: no omitted, additional, or alternate-key form is
accepted. `call_frame_ids` may be empty only for root scope.

The singular current-frame id is not sufficient for nested calls. The allocator
uses the existing ordered `ResumeScopePath.call_frame_ids`. Starting at root
`RunState`, validation requires `root_workflow_file` to match, then recursively
looks up each id at `current_state.call_frames[id]`, requires that snapshot's
`call_frame_id` to equal the path component, parses its closed nested `state` as
the next `RunState`, and descends. Missing, malformed, extra, truncated,
reordered, or ambiguous frame paths fail. The resulting leaf `RunState` is the
only owner consulted for the enclosing step's visit and loop fields.

`step_visits` counts topology-step entry, not nested loop-body steps. Therefore
a provider directly in a root/call workflow uses its own topology step as
`enclosing_step`, while a provider inside a loop body uses the enclosing loop
step and its persisted visit count. That count must be a positive integer and
must agree with leaf `current_step.{name,step_id,visit_count}` when
`current_step` represents the enclosing step. For a loop body,
`runtime_step_id` is the existing
`loop_projection.runtime_step_id(iteration, node_id)`, and the iteration must
equal the named persisted leaf loop field.

Current Workflow Lisp rejects nested loops, and `ProviderAttemptScope` carries
exactly one loop-iteration object. This design does not add nested-loop support:
the frontend continues to reject a loop nested in another loop, and runtime
scope validation rejects a synthetic multi-iteration or nested-loop shape.
Supporting nested loops would require a separate ordered loop-scope-path design.

Adjudicated candidate attempts add the already validated candidate id;
ordinary provider attempts use null. Any missing, malformed, or contradictory
scope field fails before allocation. The canonical JSON object containing these
exact fields is the visit-key input described above.

The optional state member is a map keyed by the full
`sha256:<lowercase-hex>` digest of canonical `ProviderAttemptScope` bytes. Each
entry stores the complete scope, a positive
`last_allocated_ordinal`, and per-ordinal append-only event rows. Under the
state-mutation, aggregate-evidence, and root in-process locks, allocation
validates the stored scope against the key, increments the
ordinal, appends `{ordinal, event: "allocated"}`, persists the whole state
transition atomically, and only then returns the ordinal. Gaps are valid. The
next ordinal is never inferred from evidence files, a validator index, provider
logs, or a process-local retry counter.

After immutable current-record publication, a second atomic state transition
appends exactly one `{ordinal, event: "evidence_published", relative_path,
file_sha256, record_kind: "prompt_snapshot" | "failure"}` event after the
matching allocation event. Duplicate, reordered, or conflicting events are
invalid allocator state. This binding is an
append-only expected-attempt manifest for offline completeness validation.
Runtime may append events but must never read a bound evidence path or digest
to choose, prepare, retry, resume, or reuse a provider boundary. Invalid
allocator structure is invalid authoritative runtime state and fails closed;
missing or invalid evidence content is not.

Crash behavior is exact:

- Before the allocation state transition is durable, no ordinal exists and no
  record may be published. Resume may allocate the same next integer.
- After allocation but before record publication, only the durable `allocated`
  event exists. The unused ordinal is a disclosed gap; retry or resume allocates
  a strictly larger ordinal.
- After record publication but before the `evidence_published` event transition,
  the file is an orphan record. Provider preparation has not occurred. Retry or
  resume allocates a larger ordinal; the offline validator reports the orphan
  rather than promoting it into the manifest.
- After the `evidence_published` event but before provider preparation, the
  record is an expected, validatable attempt snapshot, but it does not prove
  provider launch. Retry or resume allocates a larger ordinal without opening
  that record.
- A crash during provider preparation/execution follows existing provider
  interruption policy. If the boundary is retried or resumed as pending, a new
  ordinal and fresh snapshot are allocated; a validated completed boundary is
  reused unchanged and allocates nothing.

Ordinary retries and each adjudicated candidate retry call this same allocator
immediately before their single snapshot/render operation. Local retry indexes
remain provider-policy inputs only and are not evidence identities.

### Structured Evidence

Every provider attempt that reaches the preparation boundary and whose
executable dependency specification carries the compiler-produced
exact-path/evidence contract publishes one
immutable `workflow_prompt_dependency_evidence.v1` record before provider
preparation. Ordinary YAML uses the same snapshot/render API and hardening but
does not acquire this new evidence side effect. Let `step_key` be the first 24
lowercase hex characters of the SHA-256 of the UTF-8 runtime-step identity. Let
`visit_key` be the first 24 lowercase hex characters of the SHA-256 of the
canonical JSON bytes for the persisted provider-attempt scope defined above.
The attempt ordinal is a positive integer formatted with a minimum width of six
decimal digits. The deterministic path is:

```text
<aggregate-run-root>/workflow_lisp/prompt_dependencies/
  <step_key>/<visit_key>/attempt-<attempt-ordinal-as-%06d>.json
```

The record repeats every unhashed identity component so a key collision is
detected and rejected. Retries and repeated visits therefore cannot overwrite
one another. Runtime does not maintain or read an evidence index. The offline
evidence validator derives
`<aggregate-run-root>/workflow_lisp/prompt_dependencies/validated-indexes/<allocator-projection-sha256-hex>.json`
from the persisted allocation manifest and immutable records after execution. It
contains record path and file-digest entries sorted by full runtime-step
identity, canonical visit identity, and numeric attempt ordinal. It is a
validator output, may be regenerated, and is never provider-execution or resume
input.

Success evidence is this closed object. Every displayed object has exactly the
shown keys; arrays may be empty only where stated, fields labelled `integer`
are JSON integers, byte/count/index fields are non-negative, ordinals are
positive, digest strings use
`sha256:<64-lowercase-hex>`, and unknown or missing keys fail validation:

```text
{
  schema: "workflow_prompt_dependency_evidence.v1",
  record_kind: "prompt_snapshot",
  run: {run_id: string, workflow_file: string, workflow_checksum: string},
  compiler_contract: {
    schema: "compiler_prompt_dependency_contract.v1",
    origin_kind: "workflow_lisp_provider_result_prompt_dependencies",
    path_interpretation: "exact",
    evidence_required: true,
    source_origin_key: non-empty string,
    source_workflow_sha256: digest,
    normalized_contract_sha256: digest
  },
  attempt: {
    scope: ProviderAttemptScope,
    scope_sha256: digest,
    step_key: 24 lowercase hex,
    visit_key: 24 lowercase hex,
    attempt_ordinal: positive integer
  },
  authored_rows: [
    {
      row_id: digest,
      role: "required" | "optional",
      authored_index: non-negative integer,
      binding_ref: non-empty string,
      evaluated_relpath: safe workspace-relative POSIX string,
      status: "present" | "absent",
      canonical_target: safe workspace-relative POSIX string | null
    }
  ],
  canonical_groups: [
    {
      order_index: non-negative integer,
      canonical_target: safe workspace-relative POSIX string,
      effective_role: "required" | "optional",
      authored_row_ids: [digest, ...],
      alias_checks: [
        {
          row_id: digest,
          before_open_target: safe workspace-relative POSIX string,
          after_open_target: safe workspace-relative POSIX string,
          post_read_target: safe workspace-relative POSIX string
        }
      ],
      stability: {
        parent_components: [
          {
            component_relpath: safe workspace-relative POSIX string,
            pre: DirectoryStat,
            post: DirectoryStat
          }
        ],
        file: {pre: FileStat, post: FileStat}
      },
      bytes: {raw_total: integer, normalized_total: integer, shown: integer},
      digests: {
        raw_content: digest,
        normalized_full_content: digest,
        rendered_shown_content: digest,
        rendered_file_section: digest | null
      },
      truncation: {
        status: "complete" | "truncated" | "omitted",
        reason: null | "injection_cap",
        inline_marker_utf8_bytes: integer,
        inline_marker_sha256: digest | null
      }
    }
  ],
  instruction: {
    source: "authored" | "default_required" | "default_optional",
    utf8_bytes: integer,
    sha256: digest
  },
  injection: {
    mode: "content",
    position: "prepend" | "append",
    cap_bytes: 262144,
    instruction_max_bytes: 261630,
    truncation_summary_reserve_bytes: 512,
    block_utf8_bytes: integer,
    block_sha256: digest,
    raw_total_bytes: integer,
    normalized_total_bytes: integer,
    shown_content_bytes: integer,
    truncation: {
      was_truncated: boolean,
      files_total: integer,
      files_shown: integer,
      files_truncated: integer,
      files_omitted: integer,
      summary_utf8_bytes: integer,
      summary_sha256: digest | null
    }
  },
  final_prompt: {utf8_bytes: integer, sha256: digest},
  record_sha256: digest
}

DirectoryStat = {
  st_dev: integer, st_ino: integer, mode_type: integer,
  st_mtime_ns: integer, st_ctime_ns: integer
}
FileStat = {
  st_dev: integer, st_ino: integer, mode_type: integer, st_size: integer,
  st_mtime_ns: integer, st_ctime_ns: integer
}
```

`authored_rows` sort by role rank (required before optional) and then authored
index; at least one row exists. Its `row_id` is SHA-256 over canonical JSON
`{source_origin_key, role, authored_index, binding_ref}`. Absent rows must be
optional with `canonical_target=null`; present rows must name exactly one group.
`canonical_groups` may be empty only when every row is optional/absent;
`parent_components` may be empty only for a workspace-root-level file;
`authored_row_ids` and `alias_checks` are non-empty for every group.
Groups sort by canonical target, `order_index` is contiguous from zero,
`authored_row_ids` and `alias_checks` follow authored-row order, and required
wins. All three alias targets equal the group target. Parent components are in
root-to-leaf order; pre/post stat objects must compare exactly, as must file
pre/post. Directory `mode_type` must be `stat.S_IFDIR`, file `mode_type` must be
`stat.S_IFREG`, and device/inode values must be positive. `shown <=
normalized_total`; raw and normalized totals may differ only by the specified
UTF-8 newline normalization.

Complete groups have `reason=null`, zero inline-marker bytes, a null marker
digest, and a non-null file-section digest. Truncated groups use
`reason=injection_cap`, have positive shown and inline-marker bytes, and
non-null marker/file-section digests. Omitted groups use that reason, `shown=0`,
zero inline-marker bytes, a null marker digest, and
`rendered_file_section=null`. The aggregate truncation summary is present with
positive bytes/non-null digest exactly when `was_truncated=true`; otherwise its
bytes are zero and digest null. Aggregate file counts and byte totals must
recompute exactly from rows/groups, the block must not exceed its cap, and
`was_truncated` is true exactly when any group is not complete.
Specifically, `files_total` equals group count, `files_shown` counts complete
plus truncated groups, and truncated/omitted counts match their statuses.

Validation recomputes `scope_sha256`, `step_key`, `visit_key`, every row id,
all aggregate counts, and `record_sha256`; it also requires the compiler
contract digests/origin to equal validated executable IR and the record path to
equal the recomputed attempt path. A mismatch rejects the record before it can
enter the offline index.

Canonical JSON is UTF-8 `json.dumps` output with `sort_keys=true`,
`separators=(",", ":")`, `ensure_ascii=true`, and no trailing newline. Digests
use the `sha256:<lowercase-hex>` form. The canonical evidence-record digest is
computed over the canonical object with its own digest member omitted; the
index binds the SHA-256 of the complete final record-file bytes.

Digest domains are exact: raw-content covers descriptor bytes before decoding;
normalized-full-content covers all strict-UTF-8 decoded, newline-normalized,
UTF-8 re-encoded bytes; rendered-shown-content covers only the UTF-8-safe prefix
actually shown for that file; rendered-file-section covers the exact header,
separators, shown bytes, and any truncation marker returned for that file;
instruction covers the exact selected instruction UTF-8 bytes; injection-block
covers the exact block returned by the injector without the composer's
surrounding separator; and final-composed-prompt covers the exact UTF-8 bytes
passed to `ProviderExecutor.prepare_invocation`. Evidence stores no dependency
body or prompt text. Relative paths and hashes can still be sensitive and
inherit the run root's trust and retention boundary.

Failure evidence uses the separate closed
`workflow_prompt_dependency_failure_evidence.v1` object and rejects unknown or
missing members:

```text
{
  schema: "workflow_prompt_dependency_failure_evidence.v1",
  record_kind: "failure",
  run: {run_id, workflow_file, workflow_checksum},
  scope: ProviderAttemptScope,
  scope_sha256: "sha256:<digest-of-canonical-scope-bytes>",
  step_key,
  visit_key,
  attempt_ordinal,
  source_map_origin_key: non-empty string,
  failure: {
    category: missing_required_dependency | invalid_or_unsafe_path
      | escaping_or_broken_symlink | non_regular_dependency
      | unreadable_dependency | invalid_utf8_dependency
      | dependency_changed_during_read | invalid_injection_contract
      | unsupported_safe_read_platform,
    operation: substitute | resolve | component_walk | final_open | fstat
      | read | decode | stability_check | render,
    authored_row_id: string | null,
    evaluated_relpath: safe workspace-relative POSIX string | null
  },
  provider_calls: {preparation: false, execution: false},
  record_sha256: "sha256:<canonical-record-with-this-member-omitted>"
}
```

The failure record's `scope_sha256` covers the canonical JSON bytes of the full
`ProviderAttemptScope`; its `record_sha256` follows the same self-member
exclusion and canonical-byte rules as success evidence. It contains no raw OS
error text, errno-dependent message, absolute path, file bytes, prompt bytes,
or partial content digest. Validation recomputes its scope/step/visit/path and
requires the origin key to match the typed compiler contract. The complete-file
digest bound by the allocation manifest covers the final canonical record
including `record_sha256`.

Every manifest `relative_path` is a normalized POSIX path relative to the
aggregate run root returned by `resolve_aggregate_run_owner`, never a nested
manager root. It must be non-empty, non-absolute, contain no `.`/`..`, NUL, or
backslash component, and begin exactly
`workflow_lisp/prompt_dependencies/<step_key>/<visit_key>/`. Publication opens
the aggregate run root as a trusted directory descriptor and creates/walks
these fixed/generated components descriptor-relatively with no-follow
semantics; neither manifest paths nor destination parents may be symlinks.

Current-record publication uses this exact no-clobber protocol under the
aggregate prompt-dependency OS lock:

1. create a sibling `.<destination>.tmp.<pid>.<128-bit-random-hex>` with
   `openat(parent_fd, O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW, 0o600)`;
2. write all canonical bytes with short-write handling, `fsync` the file, and
   close it;
3. publish with `linkat(parent_fd, temp, parent_fd, destination, 0)`, which is
   atomic and fails with `EEXIST` rather than replacing a destination;
4. `fsync` the parent directory, unlink the temporary, and `fsync` the parent
   directory again.

All non-crash exits unlink the known temporary in a `finally` path. An `EEXIST`,
unsupported hard-link/no-follow primitive, cleanup failure, or any `fsync`
failure is a hard current-attempt failure before provider preparation. A crash
may leave the linked destination, temporary, or both. Runtime never enumerates
old directories to clean these. During the offline terminal validation window,
the validator recognizes only the exact sibling-temp grammar, verifies that a
temp is not manifest-bound, removes it under the same OS lock, `fsync`s its
parent, and reports the cleanup; any other unexpected entry rejects validation.

Runtime does not enumerate, open, hash, or validate any earlier evidence record
and does not build the offline index. After current-record publication, it
performs one atomic root-state transition appending that attempt's publication
event and binding the aggregate-root-relative path and final file digest. If
that transition fails, provider preparation does not occur. These writes do not
enter the provider checkpoint, and later runtime decisions never validate the
bound evidence file.

On dependency failure under that exact-path/evidence contract, the runtime
makes a best-effort atomic failure record at the same attempt identity when the
safe run-relative path is known, records a stable dependency error in step
state, and proves that provider preparation and execution were not called. A
failure record contains no unsafe absolute path or partial content. Failure
publication appends the same `evidence_published` manifest event with
`record_kind="failure"`; successful snapshot publication uses
`record_kind="prompt_snapshot"`. Failure between file publication and that
event leaves an offline-rejected orphan. Failure evidence never converts the
failed provider effect into a completed checkpoint.
YAML hardening failures retain their existing run-state error surface and do
not acquire Workflow Lisp evidence files.

### Offline Validated Index Schema

Two distinct cross-process locks are owned by the aggregate root:

- `<aggregate-run-root>/.state-mutation.lock` serializes every root
  `StateManager` write, including status/current-step changes, resume startup,
  nested call-frame projection writes, allocator events, and terminal updates;
- `<aggregate-run-root>/workflow_lisp/prompt_dependencies/.aggregate.lock`
  serializes prompt-dependency record/index publication and crash-temp cleanup.

Both are opened/created descriptor-relatively with
`O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC`, mode `0o600`, regular-file `fstat`
validation, and exclusive `flock`. Once a run has a validated typed compiler
contract or non-empty provider-attempt allocator state, every process loading
that run enables the state-mutation lock before its first root-state mutation.
Nested managers delegate through the root writer and never lock independently.

The only lock order is state-mutation `flock`, aggregate-evidence `flock`, then
the root `StateManager` in-process `RLock`; release is the exact reverse.
Ordinary root writes take the first and third locks, skipping the middle lock.
Allocation and the publication-manifest transition take all three. Record-only
filesystem publication holds the first two. No path may acquire a skipped lock
later while retaining a lower-ranked lock. Probe/preflight occurs before this
protocol and must succeed before allocator mutation as specified above.

Offline validation is allowed only while continuously holding both
cross-process locks in that order. After acquisition it reads root state,
requires status `completed` or `failed`, and records the SHA-256 of the complete
state-file bytes. It then cleans recognized crash temporaries, freezes the
allocator projection, scans and validates records, and builds the candidate
index without releasing either lock. Immediately before publication it
re-reads root state and requires the same full state-file digest, terminal
status, run identity, and allocator-projection digest. A mismatch discards the
candidate and fails `run_not_quiescent`; there is no best-effort index. Both
locks remain held through index temporary creation, file `fsync`, atomic
publication, temp cleanup, and directory `fsync`, then release in reverse order.
The validator performs one final full-state/status/projection recheck after the
directory `fsync` and before releasing either lock. A mismatch removes and
directory-`fsync`s any index newly linked by this pass, returns
`run_not_quiescent`, and never reports acceptance; a pre-existing immutable
index is left as stale evidence but is not accepted. Thus resume/status/root
writes cannot cross the validation window, and the before/during/after rechecks
detect a writer that violated the lock contract.

Runtime and resume never acquire the aggregate-evidence lock to read
index/evidence content—only to serialize their own publication mutation. They
do acquire the state-mutation lock for every root-state write in affected runs.

The validator freezes this closed allocator projection from authoritative run
state; it does not include unrelated run-state members:

```text
{
  schema: "workflow_provider_attempt_allocation_projection.v1",
  run: {run_id, workflow_file, workflow_checksum},
  scopes: [
    {
      scope_sha256,
      scope: ProviderAttemptScope,
      last_allocated_ordinal,
      events: [closed allocated/evidence_published events]
    }
  ]
}
```

The only event objects are
`{ordinal: positive integer, event: "allocated"}` and
`{ordinal: positive integer, event: "evidence_published", relative_path: safe
aggregate-root-relative POSIX string, file_sha256: digest, record_kind:
"prompt_snapshot" | "failure"}`. They have no other or nullable keys.

Scopes sort by full `scope_sha256`. Events sort by numeric ordinal and then
event rank (`allocated` before `evidence_published`); any input whose persisted
order, counter, or event pairing disagrees is invalid rather than silently
normalized. Every integer from 1 through `last_allocated_ordinal` has exactly
one `allocated` event and at most one following `evidence_published` event; no
other event member or ordinal is accepted. The allocator-projection SHA-256
covers exactly the canonical JSON bytes of this entire object. The validator
holds those frozen bytes for the validation pass so a concurrent state change
cannot produce a mixed view.

After completeness and digest validation, it writes this closed object at the
deterministic validated-index path; unknown or missing members are invalid:

```text
{
  schema: "workflow_prompt_dependency_validated_index.v1",
  run: {run_id, workflow_file, workflow_checksum},
  allocator_projection: {
    schema: "workflow_provider_attempt_allocation_projection.v1",
    sha256,
    scope_count,
    event_count
  },
  publications: [
    {
      scope_sha256,
      runtime_step_id,
      visit_key,
      attempt_ordinal,
      record_kind: "prompt_snapshot" | "failure",
      relative_path,
      record_sha256,
      record_file_sha256
    }
  ],
  allocation_only_gaps: [
    {scope_sha256, runtime_step_id, visit_key, attempt_ordinal}
  ],
  index_sha256
}
```

Publication and gap rows sort by UTF-8 bytewise `runtime_step_id`, ASCII
`visit_key`, then numeric `attempt_ordinal`; duplicate sort keys are invalid.
Every publication row comes from one paired `evidence_published` event and its
validated record. Every gap comes from one ordinal with only an `allocated`
event. `index_sha256` is SHA-256 over the canonical JSON bytes of the whole
index object with only `index_sha256` omitted. The final index file is the
canonical JSON bytes including that digest and no trailing newline. The index,
allocator projection digest, publication rows, gaps, and record digests are
offline evidence only and are never read by provider execution or resume. An
offline parity consumer must re-freeze terminal run state and require its
allocator-projection digest to equal the index before using the index; a later
resume makes the old index stale evidence rather than runtime input.

Index publication uses the allocator-projection digest hex as the immutable
filename under `validated-indexes/` and the same mode-0600
openat/write/fsync/close/linkat-no-clobber/unlink-temp/directory-fsync protocol
as record publication. Both cross-process locks remain continuously held. If
the destination already exists, the validator may accept it only after the
still-locked offline path proves its complete bytes equal the newly built
canonical bytes; otherwise validation fails and never replaces it. A later
resume produces a different allocator projection and therefore a different
index filename.

### Resume And Checkpoint Semantics

The provider lexical checkpoint's prompt-input contract digest already includes
the lowered `depends_on` mapping. The new exact-path and injection-policy
metadata must be included in the same digest. Changing any dependency operand,
required/optional role, position, or instruction therefore invalidates reuse of
an incompatible completed provider checkpoint.

Resume behavior is otherwise unchanged:

- A pending or failed provider boundary re-resolves paths, takes a fresh stable
  content snapshot, emits new attempt evidence, and then launches the provider.
- A validated completed provider boundary reuses its committed structured
  result without reopening current dependency files. The original invocation's
  evidence remains the record of the supplied snapshot.
- Dependency-content digests are evidence, not a new automatic invalidation
  input for an already completed provider result.
- Prompt-dependency evidence is never resume authority. Missing, malformed,
  tampered, or ambiguous evidence makes the evidence validator reject the
  artifact and any parity claim that depends on it, but runtime resume neither
  enumerates the evidence directory nor reads or gates on any record or derived
  index. This is true for a pending provider boundary as well as downstream
  reuse of a completed boundary. Resume authority remains validated
  executable configuration, checkpoint metadata, runtime state, result
  bundles, the provider-attempt allocator state, and the existing checksum
  guards. The allocator decides only a fresh attempt identity; it does not prove
  prompt content or provider completion.
- `.orc` resume continues through the checksum-guarded build/reconstruction
  path. Persisted surface and executable IR round trips must retain the exact
  lowered dependency contract.
- Missing, malformed, or ambiguous prompt-dependency configuration in
  authoritative checkpoint/executable metadata fails closed under the existing
  structured-provider checkpoint validation rules.

This preserves the distinction between a provider call's compiled input
contract and mutable workspace bytes observed for one actual invocation.

## Contracts And Interfaces

### Authoring Contract

`provider-result` gains one optional keyword, `:prompt-dependencies`, with the
closed syntax described above. It remains an effectful form and may not be
introduced invisibly by a macro under the existing hidden-effect rules.

The first tranche accepts only exact typed relpaths. Globs remain available to
legacy YAML `depends_on` but are not smuggled through `String` or dynamic path
values in Workflow Lisp.

### Runtime Contract

The shared dependency resolver/injector remains the single owner of workspace
dependency content composition through the per-attempt snapshot/render API.
The implementation must accept classified required/optional exact-path rows
rather than collapsing them into one unclassified file list before reads and
evidence are complete. Both ordinary retry and adjudicated composition must use
that API; no path may reopen a snapshot to render or write evidence.

Stable runtime failure categories must distinguish at least:

- missing required dependency;
- invalid or unsafe path;
- escaping or broken symlink;
- non-regular dependency;
- unreadable dependency;
- invalid UTF-8 dependency;
- dependency changed during read;
- invalid injection position, instruction/cap, or normalized contract;
- unsupported safe-I/O platform.

Every category fails before provider launch and includes only safe relative
path context.

### Evidence Contract

`workflow_prompt_dependency_evidence.v1` is an evidence view, not semantic or
executable authority. A schema validator and digest verifier own its acceptance.
Prompt-parity tooling may consume it, but runtime routing and typed provider
results may not. Because records intentionally omit content bodies, the
validator can recompute canonical record and index hashes and validate all
declared domains and relationships, while source/rendered-byte digests are
recomputed in capturing integration tests from the in-memory snapshot and
provider invocation. It must not pretend to reconstruct omitted bytes.

Offline validation reads a frozen copy of `RunState.provider_attempt_allocations`
and the evidence directory. Every `evidence_published` event must resolve to
exactly one safe relative immutable record whose complete-file digest and
embedded run identity, scope, ordinal, and record kind match; missing, extra,
duplicate, malformed, or tampered records reject the evidence set. An
allocation with only an `allocated` event is a permitted disclosed gap and
expects no record. A record with no matching `evidence_published` event is an
orphan and rejects the evidence set. Only after these checks pass may the
validator publish the content-addressed validated index through the locked
temporary/linkat/fsync protocol above. This acceptance affects evidence/parity
claims only.

## Invariants And Failure Modes

- The provider result remains one atomic visible provider effect.
- Validated executable IR remains execution authority.
- Prompt dependencies never become provider result data, artifact lineage, or
  workflow output by implication.
- No file outside the workspace contributes bytes to the prompt.
- No directory, device, pipe, socket, or invalid UTF-8 file contributes bytes.
- No required path failure is converted into an empty or partial successful
  provider prompt.
- All provider invocations see deterministic lexicographic dependency order.
- Truncation is explicit in prompt text, state debug information, and
  structured evidence.
- Source files are never modified.
- An absent optional file is not an error; a present but unsafe optional file
  is an error.
- Retries and loop/call visits retain distinct evidence.
- Attempt ordinals come only from durable runtime state; evidence paths and
  offline indexes are never enumerated to allocate or resume an attempt.
- A completed provider result is not invalidated by post-completion file drift.
- No adapter, mock, family profile, or debug-YAML projection can satisfy the
  implementation contract by itself.

## Security, Operations, And Performance

This surface grants no new child-process authority. Providers already run with
the operating-system permissions of their invocation. It does make selected
workspace content an explicit orchestrator-managed prompt input, so path and
content handling must be treated as security-sensitive.

All validation errors and evidence paths must use workspace-relative display
values. Absolute resolved paths and file contents must not be written to state,
logs, or the structured evidence record. Prompt audit retains its existing
confidentiality rules.

The runtime reads and hashes each canonical selected target once per provider
attempt.
Memory use remains bounded by the injection cap plus small streaming buffers;
the full file is streamed for strict UTF-8 validation and digest computation.
Very large declared files therefore add linear read time even when rendered
content is truncated. That cost is accepted because the evidence digest binds
the actual source file and because dependency files are explicit authoring
choices.

## Evidence And Implementation Boundaries

The implementation is the ordinary `.orc` compile path plus the shared
provider prompt-composition path. It is not:

- a family-profile-only typed prompt row;
- a provider mock that manually opens files;
- a prompt edit that names workspace paths;
- a command-result adapter that returns file text;
- a debug YAML fixture containing hand-authored `depends_on`;
- migration tooling that computes digests without executing the provider
  boundary.

A feasibility fixture must compile one generic `.orc` provider result through
WCC/schema 2, inspect the shared Core and executable `depends_on` contract, run
the loaded bundle with a capturing provider, and validate the resulting
structured prompt-dependency evidence. A classic/direct compatibility fixture
must prove both lowering routes call the same owner projection.

## Compatibility And Migration

When `:prompt-dependencies` is absent:

- existing `.orc` source behavior is unchanged;
- `ProviderResultExpr` and the Semantic prompt surface omit their optional
  prompt-dependency members rather than serializing `null` or an empty object;
- no `depends_on` mapping is added to its provider step;
- no typed compiler prompt-dependency contract, source-map row, or persisted
  dependency metadata is added;
- `RunState.provider_attempt_allocations` is absent rather than an empty map;
- no prompt-dependency evidence is emitted;
- `runtime_plan` remains byte- and schema-identical because it never owns this
  configuration;
- the existing provider prompt-input checkpoint digest and all keyword-free
  compiled artifact bytes remain unchanged for the same source and executable
  provider configuration.

Existing YAML syntax remains unchanged. For a stable dependency workspace,
each attempt's successful YAML prompt bytes remain identical to the current
renderer. Two runtime behaviors intentionally change:

- a matched content dependency that was previously silently skipped when it
  could not be read safely and stably now fails before provider launch; and
- ordinary YAML currently composes dependency content once before its retry
  loop, whereas the shared per-attempt contract takes a fresh snapshot for each
  retry. If a dependency changes after one failed provider attempt, a later
  successful retry receives the new stable bytes and computes a new snapshot
  digest; ordinary YAML still emits no Workflow Lisp evidence file.

The second item is a successful-path compatibility change under concurrent
workspace mutation, accepted because each invocation's evidence and prompt
must describe one contemporaneous snapshot. Focused YAML compatibility tests
must differentially compare the legacy and consolidated paths for stable
successful prompt bytes without embedding production prompt phrases. They
cover lexicographic ordering, truncation, optional no-match behavior,
CRLF/lone-CR normalization, and required-versus-optional default-instruction
selection for mixed inputs. A separate capturing-provider test mutates a
dependency between a retryable failed attempt and the next attempt and proves
the second prompt contains only the new snapshot, has a distinct digest, and
does not reuse the first prompt.

The instruction/cap boundary and native-platform compatibility changes are
also explicit: oversized/near-cap YAML inputs follow the exact limits above,
and native filesystems that fail the operational safe-I/O probe reject content
injection. Neither case may fall back to the legacy unchecked reader.

No new public YAML authoring key is required. The separately serialized typed
compiler contract is authenticated against Workflow Lisp bundle provenance and
cannot be copied into YAML or recovered from an untyped mapping.

## Verification Strategy

### Frontend And Type Tests

- Accept required-only, optional-only, and mixed clauses.
- Apply default `position=prepend` and default instruction behavior.
- Reject an empty clause, duplicate/unknown keys, invalid position, dynamic
  instruction, every literal `String` (including a path-looking string), and
  optional/list/record operands. Reject runtime relpath values that are empty,
  absolute, traversing, non-POSIX, unresolved-variable-bearing, or contain glob
  magic.
- Verify expression traversal, normalization, procedure specialization, and
  dependency discovery visit every path operand.
- Run `pytest --collect-only` for new or renamed modules before execution.

### WCC, Lowering, IR, And Source-Map Tests

- Prove WCC elaboration/defunctionalization preserves order, classification,
  literal policy, type metadata, and provenance.
- Prove WCC and classic/direct lowering produce the same normalized shared
  provider configuration.
- Prove Core AST, executable IR, persisted surface, Semantic IR, source maps,
  and debug view carry or explain the normalized contract through their owned
  boundaries. Prove `runtime_plan` remains topology-only and contains no
  dependency configuration.
- Prove only the compiler-origin owner can construct the typed exact-mode
  contract; YAML rejects marker/lookalike keys, untyped mappings never coerce,
  and persisted round trips authenticate source/build/origin/contract digests
  before reconstructing the enum/dataclass.
- Prove Semantic IR validates the prompt surface and source-map origin.
- Prove the absence case adds no executable dependency mapping or optional-null
  serialization and is byte-identical across keyword-free build artifacts.
- Prove no workflow, family, module, provider, or compiler name appears in the
  mechanism.

### Runtime And Security Tests

- Use generated sentinel file bodies to prove every selected file's content is
  delivered in normalized lexicographic order.
- Use arbitrary fixture instructions rather than assertions over production
  prompt phrasing; prove prepend/append placement relative to an arbitrary base
  prompt and the output-contract suffix.
- For omitted instructions, spy on the required/optional selector and compare
  old/new renderer output rather than asserting a literal production phrase.
- Prove required missing, delete-between-steps, directory, unreadable,
  invalid-UTF-8, broken symlink, escaping symlink, FIFO, device-mode, and
  changed-during-read cases fail without blocking or calling provider
  preparation/execution. Device-mode coverage may use a controlled `fstat`
  double where fixture creation is not permitted.
- Prove undefined and residual `${...}` values, every closed-set glob-magic
  character, an open/resolve identity swap, and each pre/post `fstat` mutation
  field fail closed.
- Swap a parent directory for an in-workspace or escaping symlink between
  component resolution and final open, and between open and post-read
  validation; prove descriptor-relative `O_NOFOLLOW` walking rejects both.
- Run the operational capability probe on the real test filesystem, verify its
  cleanup/cache key, and force each negative capability independently. Native
  non-POSIX verification must assert the stable unsupported-platform failure
  before dependency/provider access.
- Spy on allocation in ordinary and adjudicated paths: a successful probe/cache
  hit precedes the first ordinal, while every probe failure/interruption leaves
  `provider_attempt_allocations` absent and produces no attempt/evidence side
  effect.
- Prove a stable in-workspace symlink succeeds and evidence binds both the
  authored path and safe resolved target.
- Prove optional no-match is omitted and recorded, while a present unsafe
  optional target fails.
- Prove lexical and symlink aliases de-duplicate by canonical real target,
  required wins, canonical target ordering and header identity are stable, and
  every authored alias remains in evidence.
- Differentially prove CRLF and lone-CR input produces the same prompt bytes as
  the current successful YAML text reader.
- Prove truncation remains bounded, UTF-8-safe, and fully disclosed.
- Prove ordinary retries and adjudicated prompt composition each call the
  shared snapshot/render owner exactly once per attempt and never reopen for
  evidence.
- Prove root, call-frame, for-each, repeat-until, and adjudicated-candidate
  scopes bind only the named persisted fields and reject mismatches. Prove both
  ordinary and adjudicated retries allocate monotonically through the root
  state owner rather than local retry indexes.
- Prove a loop body inside a call frame uses the enclosing loop step's leaf
  `step_visits` count and persisted iteration. Prove a two-level nested call
  uses the exact ordered `ResumeScopePath.call_frame_ids`, recursively reaches
  the leaf state, and rejects missing, swapped, truncated, or extended paths.
- Preserve the frontend's nested-loop rejection and prove the allocator rejects
  a hand-built scope carrying more than one loop iteration; do not add a nested
  loop runtime fixture as a supported case.
- Mutate a YAML content dependency after a retryable failed provider attempt;
  prove the next attempt takes one fresh snapshot, observes only the new bytes,
  and differs from the first prompt/digest as disclosed.
- Inject crashes before allocation persistence, after allocation/before
  record, after record/before manifest event, after manifest event/before
  preparation, and during provider execution. Prove the exact gap/orphan/new
  ordinal behavior and that completed-boundary reuse allocates nothing.
- From two nested managers, prove aggregate-owner resolution emits one root
  allocation/publication transition and uses only aggregate-root-relative safe
  manifest paths. Reject cycles, mismatched run/workspace identity, absolute or
  traversing paths, and symlinked destination parents.
- Exercise `linkat` no-clobber `EEXIST`, every write/fsync/link/unlink failure,
  normal temporary cleanup, crash-remnant cleanup under terminal validation,
  and unexpected sibling entries. Prove no provider preparation after any
  incomplete publication protocol.
- Hold/mutate the root state around offline validation and prove nonterminal
  start, lock failure, or before/after state/projection mismatch rejects index
  publication as `run_not_quiescent`.
- In separate processes, hold terminal validation across record scanning and
  index link/fsync: conforming resume/status/nested-frame writers must block on
  the state-mutation lock and then proceed after release; an injected writer
  that bypasses the lock must be detected by the full-state recheck. Run a
  lock-order stress test proving no allocation/publication/state-write deadlock.
- Recompute every raw, normalized-full, shown, file-section, instruction,
  injection-block, final-prompt, evidence-record, and index digest from the
  captured snapshot/invocation and evidence artifact. Prove no bodies are
  stored.
- Validate the closed success-record key sets, types/nullability, row-id
  derivation, row/group ordering, alias/stability equality, truncation-state
  cross-fields, aggregate counts, compiler-contract binding, path identity, and
  self-digest; reject each one-direction tamper.
- Validate the closed failure-record schema in every stable category; reject
  unknown/missing fields, unsafe paths, non-false provider-call flags, wrong
  record kind, and self-digest tampering.
- Delete a manifest-bound record and add an orphan record; prove offline
  validation rejects each and emits no validated index. Prove an
  allocation-only gap is accepted and disclosed.
- Reject allocator-projection digest tampering, run-identity mismatch,
  unsorted/duplicate publication or gap rows, wrong counts, extra fields, and
  an index self-digest computed over any domain other than the specified
  exclusion object.

### Resume Tests

- Persist and reload a compiled surface with prompt dependencies.
- Interrupt before provider completion, resume, and prove a fresh snapshot and
  distinct attempt evidence.
- For a pending provider boundary, separately delete, corrupt, and schema-tamper
  a prior evidence record and derived index; prove resume does not enumerate or
  open them, allocates from authoritative state, and takes a fresh snapshot.
- Tamper with the authoritative allocation counter/scope/event ordering and
  prove pending resume fails closed as invalid runtime state without consulting
  evidence.
- Complete the provider, mutate or delete a dependency, resume downstream, and
  prove the validated completed provider result is reused without reopening the
  file.
- Change required/optional membership, position, or instruction and prove the
  prior completed checkpoint is rejected by prompt-input contract mismatch.
- Tamper with persisted authoritative dependency metadata and prove resume
  rejects it. Separately tamper with evidence and prove the evidence validator
  rejects the artifact while otherwise-valid pending and completed resume
  decisions and semantic output state remain unchanged.

### Compatibility And Breadth

- Preserve existing dependency-injection and prompt-composition tests for YAML.
- Add a real `.orc` compile/load/runtime smoke rather than a hand-built provider
  mapping alone.
- After focused selectors, run the broad suite using the repository-prescribed
  parallel pytest command.

Tests must assert behavioral structure, digests, dataflow, and lineage. They
must not assert literal production prompt wording.

## Declarative Acceptance Scenarios

### Positive: Mixed Required And Optional Content

Given a `.orc` workflow with three required relpath operands and two optional
relpath operands, one optional target absent, and a capturing provider:

1. compile through WCC/schema 2 and shared validation;
2. execute the loaded bundle;
3. observe exactly four present files in lexicographic resolved-path order;
4. observe their sentinel bodies in the captured prompt at the declared
   position;
5. observe no body for the absent optional path;
6. validate one attempt-specific evidence record whose source and prompt
   digests recompute;
7. complete the provider through its real structured-result bundle contract.

This scenario proves the public `.orc` surface, shared dependency boundary,
provider transport, output contract, and evidence path together.

### Negative: Required Path Swapped Before Read

Given a required typed relpath that is replaced by an escaping symlink after an
earlier step completes but before the provider boundary:

1. execute the `.orc` workflow through the ordinary runtime;
2. observe a path-safety/content-read failure with only safe relative context;
3. observe failure evidence when safely writable;
4. prove provider preparation and execution were never called;
5. prove no completed provider checkpoint or result bundle was accepted.

### Resume: Completed Boundary Reuse

Given a completed provider result and valid completed-effect reference whose
prompt-input contract digest includes the dependencies:

1. mutate one dependency after completion;
2. resume at a downstream interruption;
3. validate and reuse the completed provider result without reopening the
   mutable file;
4. retain the original invocation evidence as the supplied-input snapshot;
5. prove a source edit changing the dependency contract rejects the old
   checkpoint.

## Success Criteria

- The syntax and type rules are implemented without family/provider name
  branches.
- WCC/schema 2 and compatibility lowering share one owner emitter.
- Shared validated executable IR carries the dependency contract.
- Semantic IR and source maps expose typed prompt-dependency provenance.
- Required content read failures fail before provider launch.
- Structured evidence is complete, digest-verifiable, attempt-specific, and
  content-free.
- Stable-workspace successful YAML injection behavior and absent `.orc`
  behavior remain compatible; retry-time dependency mutation follows the
  disclosed fresh-snapshot change.
- Positive, negative, race/security, truncation, and resume scenarios pass.
- Independent specification and implementation-quality reviews approve the
  implementation and evidence claims.

## Stop / Revise Criteria

Revisit this design if implementation requires any of the following:

- a family, workflow, module, provider, or compiler-name branch;
- filesystem access inside the pure typed-value renderer;
- a hidden command/materialization step or file-reading adapter;
- making prompt evidence semantic or executable authority;
- weakening workspace containment, regular-file, stable-read, or UTF-8 checks;
- invalidating completed provider results from ordinary post-completion file
  drift;
- interpreting typed exact paths as globs without an explicit revised design;
- a platform fallback that reads bytes without the required identity checks.

## Documentation Impact

Implementation requires reviewed updates to:

- `docs/design/workflow_lisp_frontend_specification.md` for syntax, typing,
  lowering, effect, and resume behavior;
- `docs/design/workflow_lisp_semantic_workflow_ir.md` for the prompt-surface
  schema extension;
- `docs/lisp_workflow_drafting_guide.md` for authoring guidance and examples;
- `docs/capability_status_matrix.md` after implementation evidence exists;
- `specs/dependencies.md`, `specs/providers.md`, and `specs/security.md` for the
  stable-read failure and evidence obligations shared with YAML;
- the relevant docs indexes after the durable contract is accepted.

Roadmap, queue, stage, and live blocker status do not belong in those durable
contract updates.

## Implementation Handoff

A later implementation plan should separate work into these dependency-ordered
slices:

1. frontend syntax, typed AST, diagnostics, traversal, and typechecking;
2. WCC/schema-2 preservation, owner-level lowering, source maps, and classic
   equivalence;
3. shared Core/executable/persisted/Semantic IR validation and build artifacts;
4. stable classified dependency reads and prompt composition;
5. crash-consistent persisted attempt allocation, immutable current-record
   publication, and offline evidence/index validation;
6. resume/checkpoint tests and compatibility tests;
7. generic `.orc` end-to-end smoke, broad verification, documentation, and
   independent reviews.

The plan must use test-driven implementation and must not begin workflow-family
port evidence until this generic mechanism and its reviews are complete.
