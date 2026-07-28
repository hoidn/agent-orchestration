# Workflow Lisp Language Server

- **Status:** implemented
- **Kind:** feature / developer tooling architecture decision
- **Owner:** Workflow Lisp frontend (tooling consumer)
- **Reviewers:** independent specification rereview
  `STAGE8_DESIGN_SPEC_APPROVED`, then independent quality rereview
  `STAGE8_DESIGN_QUALITY_APPROVED` (2026-07-25); L1 independent specification
  review `L1_DESIGN_SPEC_APPROVED`, then independent quality review
  `L1_DESIGN_QUALITY_APPROVED` (2026-07-26); L2 final specification review
  `L2_FINAL_SPEC_APPROVED`, then independent final quality review
  `L2_FINAL_QUALITY_APPROVED` (2026-07-27)
- **Created:** 2026-07-13
- **Last material update:** 2026-07-27
- **Review history:** earlier design and quality changes-required rounds,
  including the F2 source-root, payload-based read-only build, and optional
  authored-call-provenance corrections, are incorporated. The latest quality
  review additionally required a single-workspace-root v1 and exact-byte
  compiler read tracing, then identified the production-injected builtin
  stdlib root as the one required containment exception. The final correction
  preserves current `Path.read_text(encoding="utf-8")` parser semantics,
  including text I/O's implicit `newline=None` universal-newline translation,
  while retaining raw-byte digest/editor identity. Ordered final rereviews
  approved the exact amended design:
  `STAGE8_DESIGN_SPEC_APPROVED`, then
  `STAGE8_DESIGN_QUALITY_APPROVED`.
- **Related docs / plans:**
  - `docs/design/workflow_lisp_frontend_specification.md` §76.1 "Editor And
    Lint Tooling Compatibility" (parent authority for this design)
  - `docs/design/workflow_lisp_frontend_mvp_specification.md` §9.1 "Linter And
    LSP Compatibility" (historical prerequisite; current v1 status lives here)
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/`
    (predecessor: built the machine-readable diagnostics surface "suitable for
    future lint/LSP tooling" while explicitly excluding "editor/LSP
    implementation, background daemons, or persistent compile servers")
  - `docs/design/workflow_lisp_source_map.md` (source-map component contract)
  - `docs/design/workflow_language_design_principles.md`
  - `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
    (governing roadmap; see Dependencies And Sequencing)
- **Implementation record:** Stage 8 (the final stage) is complete under
  `docs/plans/2026-07-25-workflow-lisp-language-server-implementation-plan.md`.
  The 2026-07-13 roadmap amendments initially named it Stage 7 and renumbered
  it when provider live binding was inserted ahead of it. Generic client setup
  lives in `docs/workflow_lisp_language_server_setup.md`. The bounded L0
  reliability/actionability successor is also implemented under
  `docs/plans/2026-07-26-workflow-lisp-language-server-l0-implementation-plan.md`;
  L1 authored symbols and callable signatures are implemented under
  `docs/plans/2026-07-26-workflow-lisp-language-server-l1-implementation-plan.md`
  through `f1eecf65`, `ec2328dd`, `d174faf2`, and `66163dc0` plus its reviewed
  repository-real stdio/status closure. L2 recovery-safe static completion is
  implemented through `70b83f32`, `b399c041`, `ee213a43`, and `10e3ccc3`
  under its reviewed five-task implementation plan, then closed by ordered
  `L2_FINAL_SPEC_APPROVED` and `L2_FINAL_QUALITY_APPROVED`. L5 authored
  reference navigation is implemented through `95e05c01`, `042c0bc3`,
  `870f7db2`, `7233138a`, and `041754e6` under
  `docs/plans/2026-07-27-workflow-lisp-l5-authored-reference-navigation-implementation-plan.md`.

## Summary

`.orc` authors can now use an **LSP (Language Server Protocol) server for
`.orc`**: a
stdio server in a new `orchestrator/lsp/` package that is a **pure consumer**
of the existing compile entry points, exactly as the frontend specification's
§76.1 mandates ("must not implement a parallel parser, type checker, linter,
or workflow validator"). Version 1 performs one serialized, full Stage-3
compile when an opened document exactly matches disk text and after each save.
It delivers diagnostics, go-to-definition, ten-kind direct-authored document
symbols, and namespace-preserving procedure/workflow/form completion with
compiler-rendered callable signatures from that compile's structured
diagnostics and closed symbol surfaces. It never imports Stage 1, falls back to
Stage 1, performs a
two-phase compile, or analyzes a dirty buffer. Imported workflow bundles
remain supported through one shared read-only in-memory extraction of the
production build pipeline. Successful snapshots are current only while exact
compiler-read SHA-256 source and immutable initialization-context vectors
remain current; dependency changes invalidate and recompile affected open
entries. V1 owns exactly one canonical workspace root; multi-root ownership is
deferred. Trace-read `.orc` dependencies may additionally live under the exact
canonical compiler-owned `_builtin_stdlib_source_root()` injected by
`_effective_source_roots`; that fixed dependency allowance is not another
workspace or caller source root. Direct-call navigation uses optional
compiler-owned authored-callee provenance, not LSP parsing. L5 extends the
same read-only index to exact authored prompt-application heads and only final
unexpanded direct-retained `proc-ref` name tokens in authored non-generated,
non-specialized owners.
Capabilities P1-P5 (hover types, multi-diagnostic error recovery,
as-you-type checking, and incrementality) remain wholly deferred.

## Context And Authority

Verified implementation behavior this design builds on (amendment evidence
refreshed 2026-07-25):

- **The integration contract already exists.** Frontend specification §76.1
  requires machine-readable diagnostics, stable codes, source spans, symbol
  locations, and hover metadata from compiler artifacts, lists
  "diagnostics-on-save through LSP", go-to-definition, completion, and
  document symbols as the anticipated deferred tooling, and mandates: "These
  tools must consume the same compiler diagnostics, source maps, catalogs, and
  validation results used by normal compilation. They must not implement a
  parallel parser, type checker, linter, or workflow validator." This design
  is the implementation architecture for that contract; it invents no new
  policy.
- **Spans survive end-to-end.** `SourcePosition` carries path/line/column/
  offset and `SourceSpan` is a start→end pair (`spans.py:9-23`); every parse
  node (`sexpr.py`), every expression node (`expressions.py` — `span` is a
  mandatory field on every `ExprNode` variant), every definition
  (`definitions.py`, `procedures.py`, `workflows.py`), and every typed root
  (`TypedExpr`, `typecheck_context.py:30`) records its span. Positions are
  1-based lines/columns; LSP requires 0-based UTF-16 positions, so the server
  owns a coordinate translation layer.
- **Direct call heads carry one metadata refinement.** `CallExpr` and
  `ProcedureCallExpr` retain both their whole-form `span` and the optional
  exact authored callee syntax-datum span. V1 uses the metadata-only
  `authored_callee_span: SourceSpan | None` on those nodes. The direct authored
  expression constructors set it only when the exact callee datum has
  unambiguous authored provenance; specialization/traversal/copy preserve that
  value. WCC reconstruction and generated, expanded, or ambiguous calls set
  `None`. This changes no parse judgment, typecheck, lowering, or runtime
  behavior.
- **Diagnostics are structured and already serializable.**
  `LispFrontendDiagnostic` (`diagnostics.py:239`) carries code, message, span,
  severity, phase, notes, and `expansion_stack`; `LispFrontendCompileError`
  (`diagnostics.py:255`) transports a tuple of them; `serialize_diagnostic` /
  `serialize_diagnostics` (`diagnostics.py:290,318`) already emit a JSON
  envelope with path/line/column. Expansion frames (`ExpansionFrame` /
  `HelperExpansionFrame`, `syntax.py:25,36`) carry both `call_span` and
  `definition_span`, so errors inside macro expansions map to the authored
  call site.
- **A no-execute full-compile entry point exists.**
  `compile_stage3_entrypoint` runs the full
  parse→expand→typecheck→effect→lower pipeline with the production
  configuration and bundle inputs and executes nothing. The CLI run path
  reaches that same Stage-3 pipeline. Stage 1 has materially different
  validation scope and therefore is not a parity-preserving editor fallback.
- **The production build pipeline owns imported-bundle semantics.**
  `build_frontend_bundle_in_memory` loads provider/prompt/command/imported
  manifests, recursively compiles `.orc` imported bundles, selects the
  exported workflow, reattaches provenance/semantic IR, and computes
  fingerprints without persistence. The persistent wrapper alone calls
  `_emit` to write `.orchestrate/build`; the LSP consumes the same read-only
  prefix and threaded source-map payload rather than recreating loader
  semantics.
- **Callable registries record definition locations.** `ProcedureCatalog` /
  `WorkflowCatalog` map names to definition nodes whose spans include the
  defining path, and import scopes are built per module
  (`modules.py`, `build_import_scope`). That is sufficient for the deliberately
  closed procedure/workflow navigation matrix; v1 does not expose a nominal
  type-navigation surface.
- **The pipeline is fail-fast.** The reader raises on the first lexical error
  with no partial tree (`reader.py`, `_raise_error` call sites); expression
  typecheck raises on the first error through the shared `raise_error` /
  `raise_required_lint` helpers (`typecheck_context.py:169,190`); the
  validation pipeline stops after the first blocking failure
  (`validation.py`, `run_validation_pipeline`). In the common case one compile
  yields one diagnostic.
- **Compiles use module-global state.** `compile_stage3_entrypoint` calls
  `reset_loop_state_metadata()` (`compiler.py:607`; `loop_state.py:82`) to
  clear module-global carrier metadata per run. Concurrent compiles in one
  process are unsafe; a server must serialize them.
- **Sub-expression types are not retained.** Typecheck persists `typed_body`
  roots on definitions but discards intermediate `TypedExpr` results during
  dispatch; there is no span→type table to power hover.
- **A source-map subsystem exists** (`source_map.py`, schema
  `workflow_lisp_source_map.v1`) mapping generated IR back to authored spans —
  v1 preserves that payload's existing build/IR provenance semantics
  in memory, although surfacing runtime diagnostics through LSP remains
  future work.
- **The v1 language server exists; no grammar or editor extension is
  bundled.** Whole-program compilation has no caching or incrementality;
  every compile resolves the entry file's full import closure plus the
  injected stdlib source root (`compiler.py`, `_effective_source_roots`).
- **Full-compile latency is known.** The Stage-8 feasibility probe measured
  one representative clean, full Stage-3 compile at **1.87 seconds**. That
  save-driven latency is accepted for v1. It does not justify a Stage-1 fast
  path, a two-phase protocol, caching, or incrementality.
- **Timestamps are not source identity.** Freshness must use SHA-256 over
  exact raw file bytes, with explicit distinct missing/unreadable sentinels.
  File-watch notifications can reduce detection latency but cannot prove
  snapshot currentness.
- **The compiler exposes the bytes it parsed as content-addressed trace
  metadata.** `read_sexpr_file` performs one raw-byte read while module
  resolution and Stage-3 helpers may visit a source more than once. V1's
  explicit metadata-only `SourceReadTrace` plumbing runs from
  `compile_stage3_entrypoint` through module loading to `read_sexpr_file`, with
  three views derived from the same single raw-byte read: unchanged
  `raw_bytes` for hashing, its strict UTF-8 `raw_decoded_text` for exact
  disk/editor equality, and `parser_text` with the universal-newline behavior
  of current `Path.read_text(encoding="utf-8")`, which uses text I/O's
  implicit `newline=None` translation. No second file read is permitted.

Ambiguities resolved by this design are both sequencing and authority. Editor
tooling shipped first as a save-driven consumer of the fail-fast Stage-3
pipeline, and parity is established on the complete normalized compile
request before entry selection and input binding rather than inferred from
similar output. Stage 1 and all P1-P5 frontend work remain outside v1.

## Problem Addressed

- Before v1, authoring feedback was terminal-only and manual. An author
  editing a workflow that imported stdlib modules had to leave the editor, run
  a CLI compile, read one diagnostic, fix, and repeat.
- Before v1, there was no navigation across the growing cross-module
  procedure and stdlib import surface.
- The compiler already produces everything an editor needs — structured
  diagnostics with spans and stable codes, definition locations, expansion
  provenance — and v1 now delivers the closed supported subset to an editor.
- Doing this wrong is cheap and tempting: a regex/tree-sitter side-analyzer
  would ship fast and then drift from the real language forever. §76.1
  prohibits exactly that, which makes the architecture a design-level
  decision rather than a tooling detail.

## Goals And Non-Goals

Goals:

1. Diagnostics on open and save for `.orc` files, published with correct
   ranges, stable diagnostic codes, severities, and expansion-stack
   provenance — sourced exclusively from the production compiler, with
   CLI parity: the same broken file and exact normalized compile request yield
   the same stable diagnostic metadata tuple from the server and from
   `run --dry-run`.
2. Go-to-definition for direct procedure/workflow call heads (including
   imported and stdlib targets), document symbols for modules/procedures/
   workflows, and visible callable/form-head completion, sourced from
   compiler expression nodes with non-null exact
   `authored_callee_span` provenance, catalogs, registries, and import scopes.
3. Editor-agnostic delivery: a stdio LSP server usable from any LSP client;
   no editor-specific coupling in the server, within one canonical workspace
   root per v1 server process.
4. Zero language-semantics, typecheck, lowering, or runtime behavior changes
   in v1. The only shared changes are one read-only in-memory extraction of
   the production build prefix, metadata-only exact-byte source read tracing,
   and metadata-only authored callee spans; the runtime dependency footprint
   of non-LSP installs is unchanged.
5. Honest capability boundaries: the symbol surface is a closed matrix,
   dirty/pending/dependency-invalidated/failed documents return null
   navigation, and frontend work P1-P5 is deferred rather than approximated
   in the server.

Non-Goals (intentionally excluded from v1):

- **As-you-type checking (`didChange`) and unsaved-buffer overlay.** The
  compile pipeline reads modules from disk. `didChange` only marks a document
  dirty; it never compiles. A path→text overlay through module resolution is
  deferred P4 work.
- **Hover type information.** Requires a span→type sidecar collected during
  typecheck dispatch (prerequisite P3).
- **Multi-diagnostic error recovery.** Requires diagnostic accumulation in
  the typecheck helpers and reader recovery (prerequisites P1/P2). v1
  publishes what the pipeline produces — usually one blocking diagnostic —
  and states so in its documentation.
- **Rename, formatting, code actions, semantic tokens.**
- **Non-default editor lint/lowering configuration.** V1 fixes both values to
  unchanged `run --dry-run` production defaults; a shared CLI/workspace
  configuration surface is a separate design.
- **Standalone Stage-1 checking for library modules and any Stage-3→Stage-1
  fallback.** Library-only modules compile directly through full Stage 3 with
  a null `entry_workflow`.
- **A syntax-highlighting grammar** (TextMate/tree-sitter). Independent
  deliverable; usually wanted alongside an LSP but architecturally separate.
- **Editor extension packaging** (VS Code marketplace etc.). v1 documents
  generic client configuration; packaging is an open question.
- **Multi-root workspaces and per-root caches.** V1 accepts exactly one
  canonical workspace root. Root-set changes require restart; multi-root
  ownership, arbitration, and caches need a separate design.
- **A persistent compile daemon beyond the LSP process itself**, compile
  caching, or incrementality. Whole-closure compile per save is the v1 cost
  model; the measured 1.87-second result has been accepted.

## Decision

The implemented stdio LSP server in `orchestrator/lsp/` drives the
existing compile entry points and translates their structured results into
LSP messages.

- **Chosen approach:** pure-consumer server (per §76.1); clean-open/save-driven
  full Stage-3 compile model reading from disk; single serialized compile
  worker (global pipeline state forbids concurrency); pygls as the LSP
  transport library, isolated under a new `lsp` optional-dependency extra
  (the project already uses the extras pattern for `dev`); v1 capability set
  = diagnostics plus the closed navigation matrix below; reverse-dependency
  invalidation plus a compiler-populated exact-byte `SourceReadTrace` and
  authoritative digest rechecks keep snapshots current across imported-file
  revisions; one canonical workspace root owns every non-builtin analyzed
  `.orc` path, while the exact compiler-owned builtin stdlib root is the only
  external dependency allowance; imported manifests use the shared read-only
  production build core;
  direct-call navigation uses compiler-owned non-null
  `authored_callee_span`; frontend-dependent capabilities P1-P5 fully
  deferred.
- **Alternatives rejected:**
  - *Parallel lightweight analyzer* (tree-sitter grammar or hand-rolled
    parser inside the server). Rejected: violates §76.1 verbatim, and every
    language change would have to land twice or drift.
  - *Artifact-watching design* (shell out to the CLI compile, parse
    `diagnostics.json` from `.orchestrate/build/`). Rejected: process-spawn
    latency per save, build-directory churn inside the user's workspace for
    every keystroke of feedback, and no in-memory access to catalogs for
    navigation. The entry points are the sanctioned in-process seam.
  - *A second LSP/imported-bundle loader or compiler wrapper.* Rejected: it
    would duplicate production selection, reattachment, recursive import, and
    fingerprint semantics. Both persistent builds and read-only consumers must
    call the same extracted in-memory core.
  - *Embedding the server in the run CLI* (`orchestrator run --lsp`-style).
    Rejected: conflates run lifecycle with editor lifecycle; a separate
    module keeps the runtime path untouched and the dependency optional.
  - *Tolerance-first sequencing* (land reader recovery and diagnostic
    accumulation before any server). Rejected: inverts value delivery —
    diagnostics-on-save with one diagnostic per compile is immediately
    useful and already strictly better than the terminal loop, while
    recovery is the expensive tail. Shipping the consumer first also gives
    the tolerance work a concrete, measurable client.
  - *Stage-3→Stage-1 fallback or two-phase publishing.* Rejected: Stage 1
    answers a narrower language question and cannot preserve full CLI
    diagnostic parity. The measured 1.87-second full compile is accepted, so
    a second compile tier would add identity, ordering, and stale-result
    states without a demonstrated v1 need.
- **Tradeoffs accepted:** one blocking diagnostic per compile in the common
  case (documented v1 limitation); dirty, pending, and failed documents have
  no navigation answer; every clean open and save recompiles the full import
  closure plus stdlib; dependency changes can enqueue multiple serialized
  entry recompiles; v1 requires one workspace root and restart on root-set
  changes; the compiler-owned builtin stdlib root is a fixed non-workspace
  dependency allowance; every compiler read hashes the exact bytes it parses
  and every compile acceptance/navigation request rechecks relevant raw
  source/config bytes; and the accepted save-driven compile latency is 1.87
  seconds.
- **Left open:** only editor client packaging remains a future choice.
  Compile configuration (including fixed lint/lowering defaults),
  single-root scope, compiler-read trace authority, compile tiering,
  diagnostic parity, dependency invalidation, navigation scope, and P1-P5
  ownership are closed by this amendment.

## Design Details

### Server lifecycle and workspace model

- The server uses stdio transport with one process per client and exactly one
  immutable canonical `workspace_root`. At `initialize`, it canonicalizes the
  non-null `rootUri` and every declared workspace-folder URI, then deduplicates
  identical canonical paths. The resulting set must contain exactly one path.
  Zero roots or multiple distinct roots reject initialization; supplying
  `rootUri` and one workspace folder for the same canonical path is one root,
  not two.
- That single root must contain every client-opened `.orc` entry and every
  non-builtin dependency admitted to analysis. An uncontained
  `didOpen`/`didSave` URI is rejected without entry state, compilation,
  diagnostics, or navigation. A trace-read `.orc` path is allowed only when
  its canonical path is under either (a) the one canonical `workspace_root` or
  (b) the exact canonical compiler-owned `_builtin_stdlib_source_root()`
  injected by production `_effective_source_roots`. Any other external path is
  discarded fail-closed and cannot publish. Cross-root import ownership, root
  arbitration, and per-root caching are deferred.
- `workspace/didChangeWorkspaceFolders` cannot hot-add, remove, or replace the
  root. Any such notification latches the existing restart-required
  `configuration_stale` state, invalidates all entries, and blocks further
  compile/navigation until the server is restarted with a valid single root.
- `initializationOptions.source_roots` is the only editor source for caller
  `source_roots`. Its canonical ordered entries correspond one-for-one to the
  parity CLI's ordered explicit `--source-root` values. With no explicit
  values, both caller tuples contain empty `source_roots`. Every explicit
  source root must be contained by the one `workspace_root`; an uncontained
  value rejects initialization. Workspace/root declarations are **never**
  implicitly inserted into caller `source_roots`.
- Both paths call the same production `_effective_source_roots` function, so
  their effective roots remain identical. That function uses the first
  containing explicit caller root as the production-selected entry root;
  otherwise it uses `_infer_entry_source_root`, which may infer an ancestor
  from `defmodule`. It then adds the builtin stdlib and explicit caller roots
  according to the production ordering/deduplication rule. The workspace root
  itself does not participate unless the author also supplies it explicitly
  as a source root.
- During `initialize`, the server obtains and canonicalizes
  `_builtin_stdlib_source_root()` directly from the production compiler and
  freezes that exact identity for its lifetime. It is an immutable allowed
  dependency root, not a workspace root, not a caller `source_root`, never
  client-configurable, and grants no allowance for a sibling, parent, or any
  other external path. Its presence only in production effective roots
  preserves exact CLI parity and never changes the caller `source_roots`
  tuple.
- `initializationOptions` may additionally supply a selected entry workflow
  (optional/null for a library-only source) and paths for provider externs,
  prompt externs, command boundaries, and imported workflow bundles. The
  server passes them to the shared in-memory core, which resolves paths and
  invokes the production loaders before compilation.
- V1 `initializationOptions` **must not expose** `lint_profile` or
  `lowering_route`. The server fixes both to the exact production defaults
  used by unchanged `run --dry-run`, then records their normalized values in
  the F2 parity tuple. `validation_profile` is likewise fixed to
  `SHARED_CALLABLE`. Non-default editor lint/lowering configuration is
  deferred; adding it requires one shared CLI/workspace-configuration design,
  not LSP-only options.
- Every source uses the one initialized `workspace_root`. F2 compares it with
  the unchanged CLI launched with that root as its working directory; a CLI
  invocation from a different working workspace is not a parity peer.
- The server is stateless across restarts: all snapshots are in-memory;
  nothing is written to the workspace.
- Stdout is exclusively the LSP transport: only correctly framed JSON-RPC/LSP
  messages may be written there. Logs go through `window/logMessage` or
  stderr; compiler rendering, tracebacks, and ordinary prints must never
  contaminate stdout.

### Compile driver

- On `didOpen` for an `.orc` document, the server reads the disk file and
  strictly decodes that read's `raw_bytes` as UTF-8 into
  `raw_decoded_text`. It compares the opened text to `raw_decoded_text`
  exactly, without universal-newline or Unicode normalization; `parser_text`
  is never used for clean/dirty equality. Exact equality marks the document
  clean and schedules a full Stage-3 compile. Inequality, a missing or
  unreadable file, or a strict UTF-8 decode failure marks it
  dirty/unavailable and schedules no compile.
- `didChange` only marks the document dirty and invalidates navigation. It
  neither parses nor compiles the buffer. `didSave` re-reads the authoritative
  disk file and recomputes that URI's exact raw-byte SHA-256/sentinel revision;
  notification text is not a source overlay. The reverse-dependency rules
  below schedule the saved entry and every affected importer. A
  missing/unreadable file cannot start its own compile, but its sentinel
  transition still invalidates affected importers.
- `didClose` removes the document's compile-entry state, contribution map,
  snapshot, dependency closure/vector, reverse-index membership, diagnostic
  target ownership, and pending generations, then republishes every formerly
  targeted URI from the remaining entries' aggregate. It removes only edges
  owned by the closed compile entry; another entry's dependency edge targeting
  that URI remains. A late result for the closed entry is discarded.
- Requests are debounced and coalesced per compile-entry URI (latest
  generation wins). Here "entry" means the `source_path` submitted to
  `compile_stage3_entrypoint`, not necessarily a workflow definition; a
  library-only source is an entry with `entry_workflow=null`. A **single
  worker** executes every compile strictly serially because the pipeline
  resets module-global state per run.
- The driver calls the shared read-only in-memory build core defined below.
  Each generation allocates one fresh `SourceReadTrace` collector and passes
  it through the core. That core invokes `compile_stage3_entrypoint` exactly
  once with the collector. The source path must be a valid Stage-3 source;
  `entry_workflow` is either the selected workflow or null for a library-only
  module. There is no import or call of `compile_stage1_entrypoint`, no
  fallback, and no first/second-phase diagnostic publication.
- `LispFrontendCompileError` is caught and its structured diagnostics
  translated as the failed result of the current generation. Any other
  exception is a server-side failure: logged via `window/logMessage`,
  previously published diagnostic contributions left untouched, navigation
  invalidated, and never converted into a synthetic language diagnostic.

### Shared read-only build core and imported bundles

- V1 adds
  `orchestrator.workflow_lisp.build.build_frontend_bundle_in_memory(request,
  *, source_read_trace: SourceReadTrace | None = None) ->
  FrontendInMemoryBuildResult` as the one public read-only core extracted from
  `build_frontend_bundle`. It owns the existing `_resolve_request` and context
  loaders, recursive `load_imported_workflow_bundle_manifest`, `_compile_entry`,
  and a refactored `_select_and_reattach`. A caller-supplied collector is
  threaded through every recursive imported `.orc` compile and the entry
  compile; a caller that omits it gets one fresh collector for that build.
  For a selected entry the result carries the compile result, selection,
  reattached `LoadedWorkflowBundle`, imported bindings, fingerprint,
  prospective build/provenance paths, `source_map_payload`,
  workflow-boundary and persisted-surface payloads, canonical
  semantic/Core-AST/executable payloads, the immutable compiler
  `SourceReadTrace`, the separate configuration trace, and diagnostics. These
  are values, not emitted artifacts.
- `_select_and_reattach` becomes strictly in-memory. It serializes the source
  map, computes the fingerprint and prospective
  `<workspace>/.orchestrate/build/<fingerprint>` plus provenance paths,
  reattaches that prospective provenance to the surface/Core AST/executable
  IR, enriches the runtime plan from the in-memory source-map payload, derives
  semantic IR from that same payload, and serializes every returned payload.
  It must perform no `mkdir`, file read, file write, temporary emission, or
  write-then-delete workaround.
- The existing payload consumers gain one explicit optional parameter:
  `orchestrator.workflow.core_ast.build_core_workflow_ast(...,
  source_map_payload: Mapping[str, object] | None = None)`,
  `orchestrator.workflow.lowering.build_loaded_workflow_bundle(...,
  source_map_payload: Mapping[str, object] | None = None)`, and
  `orchestrator.workflow.semantic_ir.derive_workflow_semantic_ir(...,
  source_map_payload: Mapping[str, object] | None = None)`. The
  `orchestrator.workflow_lisp.build._reattach_bundle_provenance` /
  `_reattach_bundle_semantic_ir` path accepts and threads the same payload when
  rebuilding/reattaching the selected Core AST, executable IR, runtime plan,
  and semantic IR. A supplied payload, including an empty mapping, is
  authoritative: none of these seams may inspect
  `provenance.frontend_source_trace_path`.
- `source_map_payload=None` retains the existing provenance-path read solely as
  a compatibility fallback for a caller loading an already-persisted bundle
  without an in-memory payload. The persistent build, LSP, and recursive
  imported-manifest compilation paths always supply the payload and therefore
  never take that fallback. This is not a second source-map interpretation:
  both payload and legacy-path routes feed the same payload decoder and
  Core-AST/semantic-IR constructors.
- The existing persistent CLI/dashboard `build_frontend_bundle` becomes
  `build_frontend_bundle_in_memory` followed by `_emit`. Only `_emit` creates
  `build_root`, writes the authoritative `source_map_payload` as
  `source_map.json`, and writes/validates the remaining artifacts and manifest.
  The LSP calls only the in-memory core. The production imported-workflow
  manifest loader recursively calls only that core for every compiled `.orc`
  binding; it must not recurse through the persistent wrapper.
- A library-only source with `entry_workflow=null` returns its full Stage-3
  compile result/catalogs and no selection/bundle. Persistent builds continue
  to require an exported selection exactly as today. An imported-manifest row
  continues to require a selected bundle.
- Given the same normalized request and byte-identical configuration, the
  persistent path, LSP path, and recursive imported-manifest path must produce
  canonical-identical entry selection, `LoadedWorkflowBundle`, semantic IR,
  Core AST, executable IR and their serialized payloads, imported bindings,
  build/import fingerprints, and prospective provenance paths before
  persistence. The persistent result must remain identical after `_emit`
  except that those prospective paths now exist. Only `_emit` may create or
  mutate `.orchestrate/build`.
- This is one extraction, not a second frontend: no LSP-specific parser,
  compiler, manifest decoder, imported-bundle loader, selector, reattachment,
  fingerprint, provenance calculator, source-map decoder, or defaulting
  semantics are permitted.

### Dependency revisions and reverse invalidation

- A source or configuration revision is exactly one of:
  - `sha256:<hex>` over the file's exact raw bytes (no text decoding,
    newline normalization, or metadata inputs);
  - the explicit `missing` sentinel; or
  - the explicit `unreadable` sentinel.
  Modification times, sizes, inode identities, watcher versions, and editor
  document versions are never revision authority.
- `orchestrator/workflow_lisp/reader.py` defines the metadata-only
  `SourceReadTrace` collector and immutable `SourceReadRecord` values. Each
  record contains the canonical path, its exact revision, and a monotonically
  increasing read ordinal. The collector retains every read attempt in order
  and also derives the unique canonical-path→revision vector. The exact
  universal-newline projection below is the fixed parser-view contract; an
  implementation may bind that fixed semantics/version alongside the
  raw-byte revision, but must not introduce an extensible source-view schema
  or persist source contents.
- `read_sexpr_file(path, *, source_read_trace: SourceReadTrace | None = None)`
  canonicalizes the path, assigns the next ordinal, and calls `read_bytes`
  exactly once for that invocation. That one read produces:
  - `raw_bytes`, retained unchanged and hashed for the exact source revision;
  - `raw_decoded_text = raw_bytes.decode("utf-8", errors="strict")`, retained
    in memory when exact disk/editor comparison is required; and
  - `parser_text`, computed exactly as
    `raw_decoded_text.replace("\r\n", "\n").replace("\r", "\n")`.
  `read_sexpr_text` receives only `parser_text`, exactly preserving the
  universal-newline semantics of current
  `Path.read_text(encoding="utf-8")`, whose text I/O uses implicit
  `newline=None`, including CRLF and bare-CR handling. The reader must not
  reopen the file or call `read_text`; the digest remains over unchanged
  `raw_bytes`, and exact editor comparison remains against
  `raw_decoded_text`, never `parser_text`. A missing or unreadable attempt
  records its distinct sentinel before preserving existing failure behavior.
  Successfully read bytes that are not valid UTF-8 retain their raw-byte
  revision and propagate the same strict decode failure as the current
  reader. ASTs, spans, and diagnostics therefore retain current parser
  behavior while every view derives from one physical read.
- `compile_stage3_entrypoint(..., source_read_trace: SourceReadTrace | None =
  None)`, its Stage-3 validation/compiler helpers, and
  `resolve_module_graph(..., source_read_trace: SourceReadTrace | None = None)`
  explicitly thread one collector through every reachable `read_sexpr_file`
  call, including lowering helpers that reread `.orc` source. There is no
  module-global/current collector and no Stage-1 trace path.
- Repeated reads of one canonical path in a compile are allowed only when
  every recorded SHA-256 revision is identical. The collector rejects a
  mismatch immediately; the core returns no acceptable generation, and the
  LSP discards/reschedules rather than selecting first-read, last-read, or
  union semantics. Repeated identical reads retain their distinct ordinals but
  contribute one digest to the accepted source vector.
- The server recomputes revisions eagerly on `didOpen`, `didSave`, and
  observed disk create/change/delete events. It registers/watches workspace
  `.orc` changes when the client supports that capability, but watcher
  delivery is only an optimization; correctness never depends on receiving a
  notification.
- Every accepted successful compile result records:
  1. the immutable ordered compiler `SourceReadTrace`;
  2. its unique canonical-path dependency closure, including the compile entry
     and every `.orc` source actually read; and
  3. the exact SHA-256 source vector derived only from that trace; and
  4. the frozen canonical `_builtin_stdlib_source_root()` identity used for
     containment.
  Neither a pre-compile filesystem probe nor LSP text parsing contributes a
  successful generation's accepted source vector.
- A current language-error completion may replace diagnostic contributions.
  It records a trace-derived closure/vector only when the compiler marks the
  trace complete and internally consistent; otherwise the entry is explicitly
  closure-unknown and triggers the conservative rule below.
- Pre-compile entry/last-known-closure probes remain scheduling and clean-buffer
  checks only. They do not become the accepted source vector and cannot
  override the compiler trace. The immutable configuration vector remains a
  separate precondition.
- After the core returns and before accepting any result, the server
  re-reads every canonical path in the trace-derived source closure, computes
  SHA-256 from those current raw bytes, and recomputes the complete
  configuration vector. Acceptance requires the entry generation to remain
  current; the trace to be complete/consistent; every trace path to remain
  under the canonical workspace root or exact frozen canonical builtin stdlib
  root; the production `_builtin_stdlib_source_root()` identity to remain
  equal to that frozen identity; every compiler-read digest, including every
  traced builtin stdlib file, to equal the current digest; and configuration
  to remain live. A missing/unreadable sentinel, unexpected external path, or
  any other mismatch discards the result in full and invokes
  invalidation/rescheduling.
- Before **every** go-to-definition, document-symbol, or completion response,
  the server re-reads and recomputes every raw-byte digest in the candidate
  snapshot's trace-derived source closure and rechecks the frozen builtin
  stdlib root identity. Any digest/identity mismatch, unexpected external
  path, or missing/unreadable sentinel atomically invalidates affected entries
  through the reverse rules, schedules eligible recompiles, and returns
  null/no items for the current request. Previously published diagnostics,
  even when `accepted_generation`-stamped, are not freshness authority.
- When URI B's SHA-256/sentinel revision changes, the server atomically
  advances the affected entries'
  generations, invalidates them, and schedules every open compile entry whose
  last trustworthy closure **or current diagnostic target set** contains B.
  It also schedules B itself when B is open, clean/readable, and otherwise
  eligible for Stage 3. All affected navigation becomes null before any
  recompile begins.
- A failed or unavailable entry may lack a trustworthy complete closure. If
  any affected/open ownership state is unknown, the server conservatively
  advances every open entry's generation, invalidates **every open entry**,
  and schedules every open entry whose own source is readable/eligible;
  entries that cannot currently read their own source remain invalidated.
  Diagnostic target sets may identify additional affected entries, but they
  never prove that an unknown closure is complete.
- An unrelated URI C does not invalidate entry A when all open entries have
  trustworthy closures/target ownership and C is absent from A's closure and
  diagnostic target set. This is the bounded negative control; conservative
  all-open invalidation is reserved for unknown ownership, not the default.
- A result superseded by an entry request, source digest, sentinel transition,
  or configuration-stale transition is discarded in full. The server
  schedules the current generation again when permitted; it never publishes a
  result compiled across a moving source/config vector.
- Missing/unreadable B is therefore not a local no-op: B cannot start its own
  compile, but importers whose closure/targets include B are invalidated and
  recompiled. Their expected import diagnostic contributions may replace the
  old contributions only through a current accepted generation.

### Immutable initialization configuration

- After production loading during `initialize`, the server freezes one
  server-lifetime configuration vector. It contains the exact raw-byte
  SHA-256 revisions and canonical paths for every configured provider-extern,
  prompt-extern, command-boundary, and imported-workflow manifest, plus the
  complete recursively imported source/config closure read by the shared
  in-memory core and the canonical identity of
  `_builtin_stdlib_source_root()`. Traced stdlib file content revisions remain
  in the compiler source trace; the immutable configuration vector binds which
  compiler-owned root may supply them. An unconfigured optional input is
  represented as an absent option; a configured missing/unreadable input fails
  initialization.
- Before compile acceptance and before every navigation/symbol/completion
  response, the server recomputes that entire vector. A changed digest,
  changed builtin-root identity, `missing` sentinel, or `unreadable` sentinel
  latches the server into `configuration_stale`.
- `configuration_stale` atomically invalidates every entry, discards/cancels
  pending results, blocks all further compiles and navigation, and emits one
  restart-required configuration-stale notice through
  `window/showMessage` plus `window/logMessage` (never stdout text). Reverting
  the bytes does not unlatch the state. The user must reinitialize/restart the
  server; v1 performs no context hot reload.
- `didOpen`, `didSave`, and watched-file events eagerly check configured paths
  and recursively imported source/config paths, but these checks only detect
  staleness early. The mandatory pre-accept and pre-navigation recomputation
  remains authoritative.

### Compile-request and diagnostic parity

F2 is an equality contract, not a comparison of whichever diagnostics happen
to be rendered. The server and the parity dry-run CLI must expose the following
normalized compile-request tuple at the shared seam **before** CLI entry
selection and input binding:

1. canonical `source_path`;
2. canonical `workspace_root`, equal to the workspace from which the parity
   CLI is launched;
3. canonical, ordered caller `source_roots`, containing exactly
   `initializationOptions.source_roots` on the LSP side and the one-for-one
   ordered explicit `--source-root` values on the CLI side;
4. `entry_workflow`, including null for a library-only source;
5. `validation_profile=SHARED_CALLABLE`;
6. normalized `lint_profile`, fixed to unchanged `run --dry-run`'s production
   default;
7. normalized `lowering_route`, fixed to unchanged `run --dry-run`'s
   production default;
8. the provider-extern bundle loaded through the production loader;
9. the prompt-extern bundle loaded through the production loader;
10. the command-boundary bundle loaded through the production loader; and
11. the imported-workflow bundle loaded through the production loader.

Parity first requires exact equality of that tuple, including source-root
order, the two fixed normalized defaults, and normalized loaded bundle values.
File-path spelling or the absence of an option is not accepted as a proxy for
bundle/default equality. The parity CLI must be launched from the same
workspace root as the LSP source and receive the same ordered explicit
`--source-root` flags and other explicit context flags. It is called a
**bare** dry-run only when all explicit options are absent; in that case both
caller `source_roots` tuples are empty and `_effective_source_roots`
identically uses the production-inferred entry root (which may be a
`defmodule` ancestor) and builtin stdlib. Changing the CLI working workspace,
implicitly adding the initialized workspace root to caller `source_roots`, or
adding/removing/reordering an explicit source root is a configuration
mismatch, not an editor discrepancy. A
mismatch fails the parity check before either side selects an entry or binds
workflow inputs.

After the compiler applies `with_diagnostic_metadata`, parity compares the
ordered diagnostic sequence, with each diagnostic represented by this ordered
structured tuple:

1. `code`;
2. `diagnostic_kind`;
3. `severity`;
4. `phase`;
5. `validation_pass`;
6. `authority_layer`;
7. canonical raw span path plus start and end, each position including line,
   column, and offset;
8. `form_path`; and
9. ordered structured expansion frames, each containing frame kind,
   macro/function name, `expansion_id` or null, canonical call span or null,
   and canonical definition span or null.

Rendered `message` and `notes` are intentionally excluded from parity. They
remain user-facing information, but wording is not compiler identity and
tests must not freeze it.

### Diagnostics translation and publication

- The translation consumes the raw `LispFrontendDiagnostic`, not the existing
  serialized diagnostic envelope: the serializer omits the span end required
  for an LSP range. The raw canonical start/end span maps to a range
  (1-based line/column → 0-based line/UTF-16 code unit, converted against the
  exact disk text for the accepted generation); `code` maps to the stable
  diagnostic code; severity maps onto LSP severities; and `source` is
  `"orc"`.
- `Diagnostic.data` preserves the structured compiler metadata needed for
  inspection: diagnostic kind, phase, validation pass, authority layer,
  canonical raw path and start/end coordinates (line, column, offset), form
  path, ordered notes, ordered structured expansion frames, and the entry's
  canonical `compile_entry_uri` plus `accepted_generation`. Notes are data,
  not fake locations.
- Only real, structured expansion-frame spans become
  `relatedInformation`: the call span and definition span are emitted in
  frame order when their paths are readable. The server does not derive
  related locations from note or message text.
- A diagnostic with a synthetic or unreadable span path is published on the
  triggering entry URI at the zero-width range `(0,0)→(0,0)`. Its original
  path and raw start/end coordinates remain in `Diagnostic.data`; the server
  neither invents a file URI nor drops the location evidence.
- Each compile entry owns a contribution map
  `target URI -> ordered diagnostics` and a monotonically increasing compile
  generation. A current language-error result atomically replaces that
  entry's whole contribution map from the exception diagnostics; a current
  successful result replaces it from the result's structured diagnostics
  (including fixed-production-profile warnings), which may be empty. The server
  republishes the union of old and new target URIs so removed contributions
  clear.
- Publication for a target URI aggregates contributions from all entries,
  deduplicates diagnostics by the structured parity tuple above, and uses a
  deterministic order. If parity-identical contributions differ only in
  excluded message/note wording, the entry with the lexicographically first
  canonical URI supplies the displayed representative. Recompiling or closing
  one entry cannot clear an equivalent contribution still owned by another
  entry.
- Only a result whose generation, complete trace-derived raw-byte source
  vector, and immutable configuration vector all satisfy the currentness
  contract above may replace contributions or a navigation snapshot. Results
  superseded by a newer entry generation, source digest/sentinel, or
  configuration-stale transition are discarded in full and never published.
  While a
  newer saved/dependency generation is pending, or after `didChange` marks the
  buffer dirty, the prior accepted contribution may remain published to avoid
  flicker; its `Diagnostic.data.accepted_generation` makes clear that it
  describes the earlier accepted disk generation, never the pending or dirty
  buffer. A current completion replaces the entry contribution atomically.

### Navigation index

From each current successful Stage-3 result, the server builds only the span
lookup and catalog/scope views needed by the following closed matrix. It does
not reinterpret tokens, parse text, or broaden the compiler's symbol
categories:

| Request | Supported compiler shape | Result |
| --- | --- | --- |
| go-to-definition | non-null exact `authored_callee_span` of a direct local or imported `ProcedureCallExpr` | defining `defproc` span |
| go-to-definition | non-null exact `authored_callee_span` of a direct local or imported workflow `CallExpr` | defining `defworkflow` span |
| go-to-definition | exact authored head token of one final unexpanded `PromptApplicationExpr` uniquely joined by whole span and canonical identity to original syntax and the prompt catalog | defining `defprompt` span |
| go-to-definition | exact authored name token of one final unexpanded direct-retained `ProcRefLiteralExpr` in an authored non-generated, non-specialized procedure/workflow owner, uniquely joined by whole span and canonical identity to original syntax and the procedure catalog | defining `defproc` span |
| document symbols | `defmodule`, `defproc`, `defworkflow` definitions in the requested document | exactly those symbols and authored spans |
| completion | visible local/imported procedure names, visible local/imported workflow names, and form heads from the compiler registry | exactly that set, deterministically ordered |
| any other node, identifier, definition kind, field, variant, type, macro head, erased/expanded/generated-owner/specialized-owner `proc-ref`, extern, or position | unsupported | null / no item |

Every definition edge is one immutable five-field row:

```text
(reference_kind, reference_span, canonical_target, target_kind, definition_span)
```

`reference_kind` keeps procedure calls, workflow calls, prompt applications,
and proc-refs distinct. The reference span is the exact authored token; the
canonical target and definition span come only from the compiler result.
Prompt and proc-ref projection require exactly one matching original-syntax
list of the expected kind at the same whole span and exactly one matching
compiler-catalog definition. Missing, duplicate, kind-mismatched,
identity-mismatched, span-mismatched, generated, or conflicting facts fail the
whole navigation index. No best-effort row, whole-form fallback, source-text
parse, or server-side name resolution is allowed.

Every new L5 row enters through the same current-success definition preflight
as direct calls. It therefore remains null for unavailable, unreadable, dirty,
compile-pending, dependency-invalidated, language-failed, server-failed,
superseded, closed, unassociated, configuration-stale, source-stale,
source/configuration-stale, clean-idle, malformed, internally inconsistent,
or navigation-index-failed state. Macro heads remain null shape-wide because
the retained expansion facts do not prove a canonical/module-qualified
own-definition identity. Macro-consumed, erased, expanded, generated-owner,
and specialized-owner proc-refs likewise remain null. Existing direct
procedure/workflow behavior is unchanged, and WCC-reconstructed/generated
calls remain excluded.

The metadata seam is exact:

- add optional provenance metadata
  `authored_callee_span: SourceSpan | None = None` to `CallExpr` and
  `ProcedureCallExpr`;
- the existing direct authored constructors in
  `orchestrator/workflow_lisp/expressions.py` set it from the exact authored
  callee `SyntaxDatum`: the list-head datum for a procedure call and the
  explicit callee datum of a `(call ...)` workflow call. They set it only when
  that datum's provenance is unambiguously authored;
- specialization, expression traversal, and every copy/replace path preserve
  the value unchanged, including `None`; they never synthesize provenance;
- WCC-to-frontend reconstruction in
  `orchestrator/workflow_lisp/wcc/defunctionalize.py`, and every
  generated/expanded/ambiguous call construction, sets `None` rather than
  copying a whole-form or generated span; and
- the LSP indexes only a non-null `authored_callee_span`. A null value, a
  cursor elsewhere in the whole-form span, or any unsupported call shape
  returns null.

Imported stdlib procedures/workflows obey the same two direct-call rules
because stdlib modules are ordinary members of the compiled module graph.
"Direct" means the authored call-head expression, not a same-spelled string
in an argument, binding, field, comment, or another part of the call form.
The LSP neither parses the head nor approximates it with the whole-form span.
- Completion does no nominal-type filtering and requires no nominal taxonomy.
  Visibility and compiler-registry membership are the only filters, consistent
  with Principle 29 ("Types Are Opt-In Constraints, Not Mandatory
  Taxonomies"). V1 also does no inferred structural filtering; adding such
  filtering requires its own evidence and design.
- **Freshness contract:** navigation is available only while the requested
  document is clean, the relevant entry's latest requested generation has
  completed successfully, the retained snapshot belongs to that exact
  generation, every recomputed SHA-256/sentinel source revision equals its
  accepted vector, and the immutable configuration remains live. Dirty,
  compile-pending,
  dependency-invalidated, language-failed, server-failed, superseded, closed,
  configuration-stale, or unassociated documents return null/no items. A last
  good snapshot is never served as stale navigation.

### Deferred capabilities and their frontend prerequisites

Each item below is a frontend change with its own blast radius; none is part
of this design's implementation scope, and each needs its own design
treatment (amendment to this document or a follow-on) plus a roadmap slot.
Stage 8 must not add interfaces, partial implementations, preparatory
refactors, configuration placeholders, or ordering decisions for any of them:

- **P1 — diagnostic accumulation.** Teach the shared typecheck raise helpers
  and the validation-pipeline continuation policy to collect multiple
  diagnostics per pass before failing.
- **P2 — reader error recovery.** Partial-AST production from malformed
  buffers (synchronize on list boundaries). Required before any
  mid-keystroke analysis is meaningful.
- **P3 — span→type sidecar.** Optional collection of per-subexpression
  `TypeRef`s during typecheck dispatch, keyed by span/form path, to power
  hover.
- **P4 — source overlay.** An optional path→text provider threaded through
  module resolution and the reader so unsaved editor buffers can shadow disk
  content; unlocks `didChange` checking.
- **P5 — compile caching/incrementality.** Module-level reuse across
  compiles.

The list records ownership boundaries only. It is not a priority order and
does not authorize successor work.

The `authored_callee_span` addition is optional metadata-only v1 work, not
P1-P5: a non-null value records an already-authored syntax location while
`None` records that the compiler cannot prove that provenance. It changes no
language judgment, type, effect, lowering, persistence, or runtime semantics.
Likewise, extracting the read-only production build core and adding
exact-byte source/config trace metadata does not authorize any P1-P5 behavior.

## Contracts And Interfaces

- **New:** `orchestrator/lsp/` package with a `python -m orchestrator.lsp`
  stdio entry point; `lsp` extras group in `pyproject.toml` (pygls); the
  exact compile-request normalization/parity seam; the raw-diagnostic
  translation contract; per-entry contribution/generation bookkeeping;
  exactly one immutable canonical workspace root plus the exact immutable
  compiler-owned builtin-stdlib dependency root; compiler-populated
  `SourceReadTrace`/`SourceReadRecord` metadata, trace-derived canonical
  dependency closures/revision vectors, and reverse invalidation; the
  separate immutable configuration trace/configuration-stale state; the closed
  navigation matrix; and a documented `initializationOptions` schema that
  excludes lint/lowering overrides and cannot configure the builtin root.
- **Reader/module/compiler metadata change:** thread an optional
  `SourceReadTrace` explicitly through `compile_stage3_entrypoint`, every
  Stage-3 source-loading helper, `resolve_module_graph`, and
  `read_sexpr_file`. The reader performs one raw-byte read per invocation,
  hashes the unchanged bytes, strictly decodes them for exact editor
  comparison, applies the fixed legacy universal-newline projection, and
  parses only that derived parser view. This is observation metadata only; it
  changes no AST, span, diagnostic, or other parser judgment and adds no
  Stage-1 or module-global path.
- **Shared build change:** extract one read-only in-memory compile/select/
  reattach core from the existing production build pipeline; make the
  in-memory source-map payload authoritative across Core AST, executable,
  runtime-plan, and semantic-IR attachment. The persistent CLI/dashboard
  wrapper and the LSP/imported-manifest loader call that same core; only the
  persistent wrapper calls `_emit`.
- **Frontend metadata change:** add
  `authored_callee_span: SourceSpan | None = None` to `CallExpr` and
  `ProcedureCallExpr`, populate it only from an unambiguous direct-authored
  callee syntax datum, preserve it through all specialization/traversal/copy
  paths, and leave WCC/generated/expanded/ambiguous reconstruction as `None`.
- **Unchanged behavior:** no language semantics, parser judgments, typecheck,
  effect, lowering, runtime, provider, CLI request, bundle-selection,
  fingerprint, or imported-loader behavior changes. Imported bundles remain
  v1-supported. The default runtime dependency set remains unchanged.
- **Spec deltas required at implementation time:** an implementation note
  under frontend specification §76.1 (the tooling now exists and consumes the
  named surfaces); capability matrix row; no `specs/` contract changes — the
  server executes nothing and owns no run state.

## Dependencies And Sequencing

- **Feasibility: resolved for the v1 capability set.** Structured diagnostics
  retain raw full spans and expansion frames; the no-execute full Stage-3
  entry point, callable catalogs, compiler form registry, and import scopes
  are existing seams. V1 requires only the reviewed shared-build extraction,
  explicit exact-byte reader/module/compiler trace metadata, single-root
  enforcement, and optional authored-callee provenance; it changes no
  language or runtime semantics.
- **F1 — compile tier: positively proven.** Direct
  `compile_stage3_entrypoint` compilation succeeds for all four probed
  zero-workflow stdlib modules (`std/context.orc`, `std/drain.orc`,
  `std/phase.orc`, and `std/resource.orc`). V1 therefore performs the same
  full Stage-3 compile for a library-only clean open/save with
  `entry_workflow=null`; it never imports Stage 1 or triggers a fallback.
- **F2 — CLI parity: contract fixed.** The exact pre-entry normalized
  compile-request tuple and post-`with_diagnostic_metadata` diagnostic tuple
  are specified above. Implementation must prove both-direction equality
  against the production dry-run CLI seam; comparing codes alone is
  insufficient. Initialization has exactly one canonical workspace root; the
  parity CLI runs from it, and the LSP passes the same ordered explicit
  `--source-root` and context flags. The workspace/root declaration never
  enters caller `source_roots` implicitly, and the LSP has no v1
  lint/lowering override with which to diverge from the two production
  defaults.
- **F3 — latency: accepted.** The representative serialized clean full
  Stage-3 compile measured **1.87 seconds**. V1 accepts that save-driven cost
  and does not introduce Stage 1, two-phase publishing, P5 caching, or a
  provisional fast path.
- **Roadmap sequencing:** completed as Stage 8, the final stage of the
  procedure-first roadmap execution sequence (2026-07-13 amendments;
  renumbered from Stage 7 when provider live binding was inserted ahead of
  it). V1 touches the production build boundary and expression
  metadata narrowly; it does not change executor, typecheck, effect, lowering,
  or runtime behavior. The prerequisites P1–P5 are explicitly outside
  Stage 8's scope: they touch reader/typecheck/module-resolution surfaces,
  and each requires its own design treatment and a further roadmap
  amendment.
- Future syntax-highlighting grammar and editor client packaging decisions
  remain independent of the implemented server.

## Invariants And Failure Modes

Invariants that must hold after implementation:

1. **No parallel frontend.** The server contains no parser, typechecker,
   linter, or validator logic; every language judgment originates from a
   compiler entry-point result (§76.1). Outside the compiler's metadata-only
   exact-byte read trace, the server owns only coordinate conversion,
   preflight raw-byte hashing, and equality checks.
2. **Compiles are strictly serialized** within the server process (pipeline
   global state), and each goes through the shared read-only build core and its
   single full Stage-3 entry point, which performs the per-run state reset.
   Stage 1 is never imported or invoked.
3. **Published diagnostics derive only from structured
   `LispFrontendDiagnostic` objects** — never from parsing rendered log
   strings. Raw start/end spans, not the lossy serialized envelope, drive LSP
   ranges.
4. **Contribution and generation ownership is exact.** Each entry replaces
   only its own contribution map, target publication aggregates all entries,
   and no result superseded by an entry generation, raw-byte source revision,
   or configuration-stale transition may publish diagnostics or navigation.
5. **Source currentness is compiler-read, content-addressed, and
   fail-closed.** Every successful snapshot's canonical closure and exact
   SHA-256 vector derive only from its internally consistent
   `SourceReadTrace`. Each reader invocation hashes unchanged `raw_bytes` and
   parses the fixed universal-newline `parser_text` derived from the same one
   read; exact disk/editor equality uses the intervening
   `raw_decoded_text`. A repeated-path digest mismatch rejects the generation.
   Pre-accept and pre-navigation recomputation of workspace and builtin-stdlib
   trace members is mandatory; the frozen canonical builtin-root identity is
   also rechecked. Reverse invalidation schedules known importers, and unknown
   ownership invalidates every open entry. Pre-hoc probes, timestamps, and
   watchers are never snapshot authority.
6. **Initialization configuration is immutable.** The production-loaded
   context, recursive imported source/config closure, and canonical
   `_builtin_stdlib_source_root()` identity have one server-lifetime vector.
   Any mismatch latches `configuration_stale`, invalidates all entries, blocks
   compile/navigation, and requires restart.
7. **Navigation derives only from the current successful entry generation,
   current trace-derived source revision vector, live configuration, exact
   compiler-owned non-null `authored_callee_span`, and closed symbol matrix.**
   Dirty,
   pending, dependency-invalidated, failed, stale, or unsupported requests
   return null/no items; there is no heuristic position patching or
   nominal-type filtering.
8. **Editor compile policy is fixed.** V1 uses
   `validation_profile=SHARED_CALLABLE` and the unchanged dry-run CLI's
   production-default normalized lint profile and lowering route;
   `initializationOptions` cannot override them. Initialization yields exactly
   one immutable canonical `workspace_root`; every client entry and explicit
   source root is contained by it; and every trace-read `.orc` path is under
   either it or the exact immutable compiler-owned builtin stdlib root.
   Neither workspace/root declarations nor that builtin root enter caller
   `source_roots`; that tuple contains exactly the ordered explicit
   `initializationOptions.source_roots`.
9. **Build semantics have one owner.** Persistent build, LSP, and recursive
   imported-manifest paths call the same compile/select/reattach core and
   produce canonical-identical in-memory selection, bundle,
   semantic/Core-AST/executable payloads, fingerprint, and prospective
   provenance paths from the authoritative `source_map_payload`.
10. **The LSP never writes to the workspace.** It and recursive imported
    compilation use the read-only core; `_select_and_reattach` performs no
    filesystem mutation or provenance-path read, and only the persistent build
    wrapper may call `_emit` to create/write `.orchestrate/build`.
11. **Stdout contains protocol frames only.** Logs, rendered compiler output,
   prints, and tracebacks cannot share the stdio transport stream.
12. **Absence of the `lsp` extra changes nothing** for any other orchestrator
   surface; the runtime dependency set of a default install is unchanged.

Failure behavior:

- Zero or multiple distinct initialization roots, an uncontained explicit
  source root, or an uncontained entry URI → reject before compilation/state
  creation. A later workspace-folder change latches restart-required
  `configuration_stale`.
- A path discovered by the compiler trace outside both the workspace root and
  exact compiler-owned builtin stdlib root, or two different digests for
  repeated reads of one canonical path → reject the generation in full,
  publish no result from it, and reschedule only when current
  source/config/root eligibility permits.
- Malformed/broken clean source → the pipeline's (typically single)
  diagnostic atomically replaces that entry's contribution and navigation
  returns null.
- Dirty buffer → no compile; existing clean-generation diagnostics may remain
  visible with their earlier `accepted_generation`, but they are not
  current-buffer analysis and navigation returns null until a new clean
  generation succeeds.
- Compile pending → the prior accepted diagnostic contribution may remain
  visible with its earlier generation; navigation returns null and only the
  current entry generation/source/config vector may replace the contribution.
- Source SHA-256/sentinel revision → every known affected importer is
  invalidated before scheduling; old contributions may remain visibly
  generation-stamped, but no affected navigation remains current.
- Unknown closure ownership → every open entry is invalidated and every
  readable/eligible open entry is recompiled rather than leaving a possibly
  dependent snapshot fresh.
- Missing/unreadable dependency → its importers are still invalidated and
  scheduled even though the dependency cannot start its own compile.
- Initialization-context or recursive imported-closure change → all entries
  are invalidated, compile/navigation remain blocked, and the latched
  restart-required notice is emitted; byte reversion does not hot-reload.
- Server-internal exception during compile → `window/logMessage` error;
  existing diagnostic contributions untouched; navigation returns null; no
  synthetic language diagnostic.
- Synthetic/unreadable diagnostic path → triggering entry URI at zero-width
  `(0,0)` with the original path/raw coordinates preserved in
  `Diagnostic.data`.
- Workspace-contained entry outside all explicit source roots → compiled with
  the production-inferred entry root from `_infer_entry_source_root` plus the
  exact compiler-owned builtin stdlib root (same behavior as the CLI on a
  standalone file).
- Editor kill / crash → no residue: no workspace writes, no external state.

## Security, Operations, And Performance

- The server reads workspace files and executes nothing: no provider
  invocations, no network, no run-state creation. It grants no authority the
  editor user does not already have.
- Cost model: one whole-closure compile per affected open entry, serialized
  and debounced. A dependency save may therefore enqueue multiple entry
  compiles. Every acceptance and navigation request also hashes the complete
  relevant raw-byte source/config closure. The representative 1.87-second
  clean full-Stage-3 measurement is accepted for v1. No Stage-1 fast path,
  two-phase publishing, or P5 work is authorized.
- pygls is confined to the `lsp` extra; CI for the package runs only where
  the extra is installed.

## Evidence And Implementation Boundaries

- The translation layer (raw-span coordinates, severity/code/data mapping,
  structured-frame related information, synthetic/unreadable-path fallback,
  and multi-entry contribution aggregation) is pure and unit-testable against
  synthesized diagnostics.
- Integration evidence drives the real server over stdio against fixture
  `.orc` workspaces, including at least one fixture that imports real stdlib
  modules — no fixture-only shortcut around module-graph resolution.
- Tests assert the complete parity tuple, LSP ranges/data, counts, URIs,
  contribution ownership, and generations — never rendered message or note
  phrasing (repo rule: behavioral/contract assertions that survive wording
  revisions).
- The CLI-parity check proves equality of the normalized pre-entry compile
  request first, then equality of the post-`with_diagnostic_metadata`
  structured diagnostic tuple. Codes-only parity is not sufficient evidence.
- Shared-core evidence compares the persistent, LSP, and recursive imported
  paths before `_emit`: selection, `LoadedWorkflowBundle`,
  semantic/Core-AST/executable values and canonical payloads, imported
  bindings, ordered `SourceReadTrace`, separate configuration trace,
  fingerprints, and prospective provenance paths must be identical.
  Payload-authority tests prove no source-map path is read when
  `source_map_payload` is supplied; a distinct legacy test covers the
  `None`/already-persisted fallback. A filesystem before/after proof
  establishes zero writes for both read-only consumers.
- Freshness evidence mutates raw bytes without LSP notifications and proves
  that the accepted vector hashes the exact `raw_bytes` whose strictly decoded
  text produced the parsed universal-newline view under `SourceReadTrace`,
  and that mandatory post-compile and pre-navigation digest checks, not
  pre-hoc hashes, timestamps, or watchers, drive invalidation.

## Compatibility And Migration

- Additive at the language/runtime boundary. Existing workflow meaning,
  frontend judgments, CLI results, typecheck/effect/lowering behavior, and
  runtime behavior do not change. The production build prefix is extracted
  read-only, compiler file reads gain metadata-only exact-byte tracing, and
  call nodes gain optional provenance metadata. Reader compatibility tests
  require ASTs, spans, and diagnostics to remain identical to the current
  universal-newline reader for both CRLF and bare-CR inputs; no YAML surface
  is involved.
- The server's capability documentation states the v1 limitations explicitly
  (clean-open/save-driven full compile, typically one diagnostic per compile,
  1.87-second representative latency, one canonical workspace root, fixed
  production-default lint/lowering, compiler-read raw-byte freshness checks,
  immutable initialization context/root requiring restart on drift,
  reverse-dependency recompiles, null navigation while
  dirty/pending/dependency-invalidated/configuration-stale/failed, and the
  closed symbol matrix) so editor users' expectations match the pipeline's
  semantics.

## L0 Reliability And Diagnostic Actionability Amendment

**Amendment status:** implemented 2026-07-26. The design was accepted after
ordered independent review: `L0_DESIGN_SPEC_APPROVED`, then
`L0_DESIGN_QUALITY_APPROVED`. The implementation and watcher-disabled
real-stdio gate are recorded in the L0 implementation plan.

This bounded post-v1 amendment corrects four reliability/presentation defects.
It does not add a language feature, source overlay, incremental compiler,
parallel analyzer, runtime debugger, or new diagnostic authority.

### One-Probe Save Observation

`didSave` obtains exactly one authoritative `DiskSourceSnapshot` through
`probe_disk_source`. One pure state transition consumes that same snapshot:

- when its revision differs from the saved entry's retained disk revision, it
  delegates to
  `observe_file_revision` only; that existing observer owns the saved entry,
  trustworthy importers, unknown-closure conservative invalidation,
  diagnostic-target ownership, pending-generation cancellation, and scheduling;
- when the revision is unchanged, it delegates to `save_entry` only so the
  existing one local save generation still occurs.

Revision equality is tested first and includes equal missing or unreadable
sentinels. Thus an unchanged sentinel takes the local-save branch; a transition
to, from, or between different sentinels takes the observer branch. The two
branches are mutually exclusive.

The server must not call `observe_disk_path` from `didSave`, because that owner
performs a second probe. A changed save must not then call `save_entry`; doing
both would advance the saved entry twice. A dirty or unavailable saved source
may be unable to schedule itself, but its changed revision/sentinel still
invalidates every affected importer through the existing observer rules.
Watcher delivery remains an eager optimization, not correctness authority.

### Intentional Initialization Failures

Production initialization loading remains owned by the existing compile-driver
initializer. The LSP boundary catches only `LispFrontendCompileError` from that
loading and translates it to JSON-RPC invalid params (`-32602`) with:

- the fixed-shape human message
  `Workflow Lisp initialization failed (<N> compiler diagnostics); see data`;
  and
- closed structured `data={"diagnostics":[...]}` preserving the compiler
  exception's diagnostic tuple order, with exactly one `{"code":..., "path":...}`
  row per diagnostic. `path` is the canonical path when canonicalization is
  available, otherwise the retained raw path.

No text-document diagnostic is synthesized because initialization has no
accepted document generation. `OSError`, `RuntimeError`, `UnicodeDecodeError`,
permission failures, and other unstructured exceptions are not reclassified as
client mistakes and continue through the existing internal/server-failure path.

### Visible Notes And Expansion Roles

`DiagnosticContribution.message`, parity identity, aggregation key,
representative selection, and structured `data` remain byte-for-byte semantic
authority. LSP presentation derives a visible message by appending the
compiler's ordered `data["notes"]` to the unchanged raw contribution message.
Tests bind order and sentinel containment rather than the complete human prose.

Every expansion-related-information row retains closed structured fields for:

- frame role: `macro` or `helper`;
- location role: `call` or `definition`;
- authored frame name; and
- nullable compiler-owned expansion ID.

The LSP label is a deterministic view of those fields. It does not parse prose,
change the diagnostic span, or mint a new identity.

### Content-Keyed Pure-Projection Source Cache

The untraced pure-projection module-export cache must not key by source path
alone. Its cache key is the canonical source path plus a digest of the exact
raw bytes to be parsed, and the cached parser consumes those same bytes. A
same-path content change therefore cannot reuse the earlier export result;
unchanged bytes may. The compiler-traced path continues to bypass this cache so
`SourceReadTrace` remains the authoritative single-read owner.

This is a local reentrancy correction, not compile caching/incrementality P5 and
not the substrate track's broader MR-4 session-state refactor.

### L0 Acceptance Boundary

Acceptance requires both-direction tests for changed/unchanged saves,
dirty/unavailable dependencies, unknown closures, diagnostic-target ownership,
active-ticket cancellation, exactly one `didSave` probe, structured and
unstructured initialization failures (including missing-manifest and
malformed-manifest positive cases plus an unstructured negative control),
diagnostic aggregation and visible notes/roles, changed/unchanged cached
source content, traced-read bypass, and one watcher-disabled real-stdio
importer save.
Eager `didOpen` reverse
observation, unsaved-buffer analysis, multi-diagnostic recovery, full
`form_path` rendering, and runtime debugging remain excluded.

The accepted boundary is implemented. L1 authored symbols and callable
signatures and L2 recovery-safe static completion are also implemented and
retain this L0 reliability boundary.

## Accepted L1 Authored Symbols And Callable Signatures Amendment

**Amendment status:** implemented after independent specification review
`L1_DESIGN_SPEC_APPROVED`, independent quality review
`L1_DESIGN_QUALITY_APPROVED`, the reviewed five-task implementation plan, and
its repository-real stdio/status closure. The implementation does not change
the v1/L0 freshness or compiler-authority bounds above.

L1 extends only the successful-snapshot navigation index. It does not add a
parser, source-text classifier, partial AST, hover surface, reference graph,
rename operation, type-directed completion, or new freshness authority.

### Compiler-Owned Authored Symbol Projection

The compiler owns one closed original-syntax projection over each
`ResolvedModuleSource.syntax_module`. The projection emits immutable rows with
exactly:

```text
(kind, name, definition_span, selection_span, source_ordinal)
```

The admitted `kind` values are `module`, `procedure`, `workflow`, `enum`,
`path`, `record`, `union`, `schema`, `resource`, and `transition`. The
projection uses only compiler-retained original syntax and compiler-owned
syntax/definition helpers. It does not read source text, ask the LSP to parse
or classify a form, or inspect expanded syntax as authored provenance.

For every directly authored original-syntax row, the compiler must find exactly
one matching definition in the successful compiled module:

- `module` matches the compiled module identity;
- `procedure` and `workflow` match their separate compiler catalogs; and
- `enum`, `path`, `record`, `union`, `schema`, `resource`, and `transition`
  match their corresponding compiled semantic definition collections.

A missing, multiply matching, kind-mismatched, name-mismatched, or
span-ambiguous direct row fails index construction. There is no whole-form,
same-spelled-name, or expanded-node fallback. Conversely, a compiled definition
introduced only by expansion or generation has no direct original-syntax row
and is deliberately excluded; its absence is not an index error. Specialized
procedures/workflows and compiler-generated local procedures remain excluded
by their existing compiler markers. The compiler projection may add the
minimal metadata needed to retain an exact authored definition-name token, but
the LSP may not reconstruct that token from text.

Each document symbol uses:

- `range = definition_span`, the complete authored definition form; and
- `selectionRange = selection_span`, the exact authored name token.

This applies uniformly to all ten admitted kinds. A missing or invalid
selection span omits no individual best-effort answer: it fails the index
closed. Symbols are returned in `(definition_span.start.offset,
source_ordinal)` order. Their protocol presentation is fixed:

| Internal kind | LSP `SymbolKind` |
| --- | --- |
| `module` | `Module` |
| `procedure` | `Function` |
| `workflow` | `Function` |
| `enum` | `Enum` |
| `path` | `Class` |
| `record` | `Struct` |
| `union` | `Enum` |
| `schema` | `Interface` |
| `resource` | `Object` |
| `transition` | `Event` |

This table is presentation, not a nominal subtype hierarchy. The implemented
L5 amendment still does not add go-to-definition for type tokens, schemas,
resources, transitions, fields, variants, arbitrary identifiers, or macro
heads. Existing exact direct procedure/workflow call-head definition behavior
is unchanged.

### Namespace-Preserving Completion Rows

Completion rows have three distinct internal kinds: `procedure`, `workflow`,
and `form`. A procedure and workflow with the same visible label are two
completion items, not one merged callable. A form with the same label is also a
separate form item.

Callable labels come only from:

- directly authored local procedure/workflow definitions; and
- the exact keys in the current module's corresponding
  `ModuleImportScope.procedure_bindings` or
  `ModuleImportScope.workflow_bindings`.

Thus compiler-admitted `alias.member`, `module/member`, and `:only`
unqualified spellings are preserved exactly. The LSP must not derive a visible
label by stripping a canonical catalog key, invent an alias, or union the two
callable namespaces. Each callable row retains its compiler canonical target
solely for signature lookup and deterministic ordering. Form labels remain the
exact registered form heads, with the form head itself as their canonical
target. The complete list is sorted by:

```text
(label, kind_rank, canonical_target)
```

where `kind_rank` is `procedure`, then `workflow`, then `form`.

Completion detail is a deterministic view of existing compiler signatures:

```text
procedure (<name>: <render_type_ref>, ...) -> <render_type_ref> effects <render_effect_set>
workflow (<name>: <render_type_ref>, ...) -> <render_type_ref>
form
```

Zero parameters render as `()`. Procedure details use
`ProcedureSignature.params`, `ProcedureSignature.return_type_ref`, and
`ProcedureSignature.declared_effects`, rendered only through
`render_type_ref` and `render_effect_set`. They do not use direct or transitive
inferred effect summaries. Workflow details use only
`WorkflowSignature.params` and `WorkflowSignature.return_type_ref`; L1 does not
infer or display workflow effects. Form rows have no invented signature.
Procedure and workflow protocol kinds remain `CompletionItemKind.Function`;
form remains `CompletionItemKind.Keyword`. The distinct internal kind and
detail preserve same-label namespace identity without assigning a misleading
protocol category.

### Freshness, Failure, And Deferred Work

The existing successful-snapshot preflight remains the sole availability
authority. A current successful snapshot returns the complete L1 list with
`isIncomplete=false`. Dirty, pending, dependency-invalidated,
language-failed, server-failed, superseded, closed, configuration-stale,
source/configuration-stale, or unassociated documents retain the implemented
v1 null/empty behavior; no last-good symbol or callable row is served as
current. Index-construction failure also returns null/empty through the
existing internal-failure boundary.

L2 alone owns recovery-safe incomplete completion. L1 does not expose form-head
completion for failed or dirty documents and does not change definition or
document-symbol freshness. P1-P5, nominal filtering, arbitrary-expression
hover, type-token definition, references, rename, signature inference,
snippets, and callable insertion rewriting remain deferred.

### L1 Design Verification And Implementation Surface

Acceptance requires both-direction evidence for:

- all ten directly authored document-symbol kinds, exact full/selection spans,
  protocol mappings, and cross-kind source order;
- exclusion of expansion-only/generated definitions, specialized callables,
  generated local procedures, and ambiguous or mismatched projection rows;
- a failing cross-check for every missing, duplicate, kind, name, and exact-span
  mismatch, with no LSP text-parsing fallback;
- distinct same-label procedure/workflow/form rows;
- local labels and every compiler-admitted qualified, canonical-module, and
  `:only` import-scope key, with exact deterministic ordering;
- zero-, one-, and multiple-parameter procedure/workflow details, nested
  resolved types, empty/nonempty declared procedure effects, and proof that
  inferred/transitive effects do not enter detail;
- unchanged current-success, dirty, pending, invalidated, failed, stale,
  closed, and unassociated response behavior; and
- one repository-real stdio LSP check in addition to compiler-projection,
  navigation, server, and integration tests.

The likely carrier and implementation owners are the compiler definition or a
small compiler-owned authored-symbol projection module,
`orchestrator/lsp/navigation.py`, and `orchestrator/lsp/server.py`. Owning
evidence belongs in compiler definition/projection tests,
`tests/test_workflow_lisp_lsp_navigation.py`,
`tests/test_workflow_lisp_lsp_integration.py`,
`tests/test_workflow_lisp_lsp_stdio.py`, and
`tests/test_workflow_lisp_lsp_e2e.py`. That evidence is implemented under the
reviewed L1 plan.

## Implemented L2 Recovery-Safe Static Completion Amendment

**Amendment status:** implemented after independent specification review
`L2_DESIGN_SPEC_APPROVED` and independent quality review
`L2_DESIGN_QUALITY_APPROVED`, the ordered
`L2_PLAN_SPEC_APPROVED` / `L2_PLAN_QUALITY_APPROVED` plan gate, four reviewed
implementation commits through `10e3ccc3`, and ordered final reviews
`L2_FINAL_SPEC_APPROVED` then `L2_FINAL_QUALITY_APPROVED`.

L2 adds one recovery-only completion source without weakening compiler,
snapshot, or freshness authority. The server captures a **process-frozen form
registry** exactly once after production initialization has succeeded:

```text
static_form_heads = tuple(registered_form_heads(target_dsl_version=None))
```

The capture must already be unique and lexicographically ordered. Each head is
projected once to the existing immutable form completion shape
`(label=head, kind=form, canonical_target=head, detail=form)`. The frozen tuple
is retained for the server lifetime and is shared by both full completion
construction and recovery completion. A request must not call the registry
again, parse source text, derive a target version, or augment the tuple from a
last-good navigation index. Capturing with no target is deliberate: an
eligible recovery state has no accepted source-derived target authority, and
the existing full L1 form list is likewise target-neutral. A future
target-aware recovery surface requires a new immutable initialization
contract; L2 does not guess.

### Closed Three-Way Selector

Every completion request first performs the existing immutable-configuration
preflight. Configuration drift latches `configuration_stale` and selects the
empty branch. With live configuration, the request classifies exactly one
associated open entry into `full`, `static-incomplete`, or `empty`:

| Entry state after preflight | Selection | Rationale |
| --- | --- | --- |
| clean, current successful snapshot, and successful navigation-index construction | `full` | Return the complete L1 callable-plus-form union with `isIncomplete=false`. |
| dirty with the normal idle/no-pending shape | `static-incomplete` | The editor has no current compiled callable authority. |
| clean with exactly the current generation pending, including dependency invalidation or supersession | `static-incomplete` | A current compile may later replace this provisional list. |
| clean current `language_error` or `server_error`, with no accepted success snapshot or pending generation | `static-incomplete` | Recovery forms remain useful, but failed output supplies no callable authority. |
| configuration-stale, unavailable/unreadable, closed, unassociated, clean-idle, malformed/internally inconsistent, or current-success index failure | `empty` | Fail closed; do not reinterpret an impossible state or conceal an index defect with fallback data. |

The classifier validates the complete admitted state shape, not only one
status field. In particular, an absent or non-current pending generation,
an accepted snapshot in a recovery row, an unknown status value, or any
contradictory buffer/compile combination selects `empty`. A late result cannot
change the classification unless the existing single-writer coordinator first
accepts it into current state.

The `static-incomplete` response contains exactly the process-frozen form
rows, in lexicographic label order, with `CompletionItemKind.Keyword`,
`detail="form"`, `sortText=head`, and `isIncomplete=true`. It contains **no
stale callable**, signature, import binding, generated symbol, source-derived
target filter, snippet, or prior navigation-index row. The `empty` response
retains the current closed shape `items=()` and `isIncomplete=false`.

### Authority And Non-Goals

Full completion continues through the existing source/configuration
currentness checks and successful compiler-derived navigation index. Recovery
completion is only a frozen compiler-registry view; it does not claim that a
head is valid at the cursor, in the current target version, or in the
unfinished buffer. Definition and document-symbol requests keep their existing
null behavior outside a current successful snapshot.

L2 does not add a parser, partial AST, overlay compile, saved-source compile
trigger, cursor/prefix/type filtering, callable cache, last-good fallback,
target inference, general compile cache, diagnostic recovery, hover, rename,
formatting, or any P1–P5 prerequisite. It does not change compile scheduling,
generation acceptance, diagnostic ownership, configuration restart rules, or
the one-root model.

### L2 Acceptance Boundary

Implementation evidence proves both directions:

- the frozen tuple is captured only after successful initialization, is used
  by both full and recovery rows, and is unaffected by later registry mutation;
- dirty-idle, current-pending (including invalidated/superseded),
  language-error, and server-error open entries return the exact frozen form
  rows with `isIncomplete=true`;
- a current successful entry still returns the complete namespace-preserving
  L1 union with `isIncomplete=false`;
- configuration-stale, unavailable, closed, unassociated, clean-idle,
  malformed, missing/non-current pending, and navigation-index-failed states
  return the exact empty response;
- recovery rows contain no procedure/workflow labels or signature details,
  even when an earlier accepted snapshot existed; and
- one repository-real stdio check demonstrates static recovery followed by a
  successful full completion replacement without changing definition or
  document-symbol freshness.

The direct implementation owners are `orchestrator/lsp/state.py`,
`orchestrator/lsp/compile_driver.py`, `orchestrator/lsp/navigation.py`, and
`orchestrator/lsp/server.py`, with focused evidence in the corresponding LSP
state, driver, navigation, integration, stdio, and end-to-end test modules.

## Verification Strategy

- **Unit (translation layer):** 1-based→0-based and UTF-16 conversion
  including non-BMP characters and spans at line boundaries; severity and
  code/data mapping from raw full spans; notes retained only in data;
  structured expansion-frame spans → relatedInformation locations;
  synthetic/unreadable paths → triggering-entry zero-width fallback with raw
  metadata retained.
- **Unit (contributions/generations):** two entries contributing an identical
  imported-file diagnostic deduplicate without losing ownership; replacing
  one entry preserves the other's contribution; removed target URIs clear;
  results superseded by an entry generation or source/config revision cannot
  publish; a retained pending/dirty/dependency-invalidated contribution
  exposes its earlier `accepted_generation`; `didClose` removes only the
  closed entry's ownership/index state; current generation ordering is
  deterministic.
- **Unit (reverse dependencies):**
  - trusted closure `A -> B`: advancing B advances/invalidates A and schedules
    A;
  - trusted unrelated C: advancing C does not invalidate or schedule A;
  - unknown closure on any failed/unavailable open entry: advancing a disk URI
    invalidates every open entry and schedules every readable/eligible one;
  - missing/unreadable B still invalidates/schedules A even though B cannot
    compile itself;
  - a result whose compiler trace is inconsistent or whose trace-derived
    source vector changes before acceptance is discarded and rescheduled.
- **Unit (workspace-root contract):**
  - one `rootUri`, one workspace-folder URI, and both spellings of the same
    canonical root each initialize the same single-root state;
  - zero roots, two distinct canonical roots, an uncontained explicit source
    root, and an uncontained opened entry each reject fail-closed;
  - a trace-discovered `.orc` path beneath the exact canonical
    `_builtin_stdlib_source_root()` is accepted and its digest/root identity
    enter freshness state, while the same-shaped path under any other external
    directory rejects fail-closed;
  - `workspace/didChangeWorkspaceFolders` latches restart-required
    `configuration_stale`, and no workspace/root declaration appears in caller
    `source_roots` unless it is separately explicit; the builtin root never
    appears there.
- **Unit (compiler-read revision identity and preflight):**
  - SHA-256 is over exact raw bytes; byte/line-ending changes alter identity,
    while timestamp-only changes do not;
  - a counting reader proves each `read_sexpr_file` invocation calls
    `read_bytes` exactly once and derives `raw_decoded_text`, `parser_text`,
    the raw-byte digest, AST, spans, and diagnostics from that one returned
    byte value;
  - for successful and diagnostic fixture cases, the LF source and its CRLF
    encoding produce identical `parser_text`, AST, every source span, and
    structured diagnostics under the proposed reader and the current
    `Path.read_text(encoding="utf-8")` behavior with text I/O's implicit
    `newline=None` translation;
  - the same old/current compatibility comparison covers the LF source and
    its bare-CR encoding. The reverse identity control proves the LF, CRLF,
    and bare-CR `raw_bytes` have pairwise-distinct SHA-256 revisions despite
    their parser-view equality;
  - `raw_decoded_text` retains CRLF or bare CR exactly. Matching disk/editor
    code points compare clean, and both mismatch directions compare dirty
    (CRLF-or-bare-CR disk against LF editor text, and LF disk against
    CRLF-or-bare-CR editor text), even though the corresponding parser views
    are identical;
  - simulated reads `A(v1) -> B(v1) -> A(v1)` retain three ordered read records
    and accept one digest per canonical path, while
    `A(v1) -> B(v1) -> A(v2)` rejects the generation before publication;
  - a pre-compile probe that differs from the later compiler read does not
    poison the accepted vector when the compiler trace and pre-accept
    recomputation agree, proving pre-hoc hashes are not authority;
  - missing and unreadable produce distinct explicit sentinels;
  - mutation between the compiler's exact-byte read and pre-accept
    recomputation discards the result;
  - an external edit delivered by no watcher invalidates on the mandatory
    pre-navigation recomputation;
  - B may be closed in the editor: changing closed imported B still
    invalidates open importer A before A's next navigation response.
- **Unit (immutable configuration):**
  - unchanged production-loaded provider/prompt/command/imported configuration
    and recursively imported source/config bytes pass compile-acceptance and
    navigation preflight;
  - changing, deleting, or making unreadable each configured manifest or any
    recursively imported source/config file invalidates all entries, blocks
    compile/navigation, and emits one restart-required notice;
  - restoring original bytes does not unlatch `configuration_stale`; only a
    fresh initialize/restart does.
- **Unit (compiler-owned call-head provenance):**
  - direct authored workflow/procedure constructors set
    `authored_callee_span` to exactly the authored callee datum and
    specialization, traversal, and copy/replace preserve it byte-for-byte;
  - the reverse direction proves WCC reconstruction plus
    generated/expanded/ambiguous construction yields `None`, remains `None`
    through those same paths, and is never indexed;
  - cursor positions elsewhere in the whole-form span, including arguments,
    return null. No test permits a whole-form fallback.
- **Shared-core parity and zero writes:**
  - for requests with no imports and with recursive imported manifests, the
    persistent wrapper, LSP, and imported-manifest consumer return identical
    selection, `LoadedWorkflowBundle`, semantic/Core-AST/executable values and
    canonical payloads, imported bindings, ordered `SourceReadTrace`, separate
    configuration trace, fingerprints, and prospective provenance paths before
    `_emit`;
  - a supplied `source_map_payload` remains authoritative when its prospective
    provenance path is absent or contains different bytes; neither Core AST nor
    semantic IR reads that path. A separate compatibility test proves
    `source_map_payload=None` can still load one already-persisted bundle
    through the legacy path fallback;
  - tampering either consumer's normalized request or imported source/config
    bytes breaks parity in both directions;
  - LSP and recursive imported compilation leave the complete workspace tree,
    including `.orchestrate/build`, byte-for-byte absent/unchanged; only the
    persistent `_emit` creates the root and writes the source map and remaining
    artifacts.
- **Integration (stdio, fixture workspace):**
  - exactly one initialized canonical root accepts contained entries; zero or
    multiple roots reject, an uncontained entry produces no state, and a
    workspace-folder change latches restart-required stale state;
  - with the fixture workspace outside the compiler installation, an import
    resolved under the production `_builtin_stdlib_source_root()` compiles,
    its external stdlib file remains in the trace/freshness vector, and
    go-to-definition reaches that file; redirecting the same import to an
    arbitrary external `.orc` path rejects the generation;
  - clean `didOpen` on a file with a type error → one full Stage-3 compile and
    one diagnostic with the expected structured tuple and authored range;
  - `didOpen` text unequal to disk → dirty state, no compile, null navigation;
  - `didChange` → dirty state, no compile, null navigation;
  - fix and `didSave` → diagnostics cleared, snapshot refreshed;
  - an error in an imported module → diagnostic published on the imported
    file's URI and cleared when resolved;
  - A imports B; saving B changes and then clears the A-owned diagnostic,
    keeps A navigation null while pending, and refreshes A navigation only
    from the new trace-derived raw-byte source revision vector;
  - saving unrelated C leaves A's accepted generation/navigation untouched
    when all closures are trustworthy;
  - an unknown-closure failure triggers conservative all-open invalidation;
  - deleting or making B unreadable still invalidates A even though B cannot
    start its own compile;
  - an external edit to open or closed imported B, with no watcher event,
    invalidates A on its next navigation request;
  - watcher delivery causes the same invalidation eagerly but is not required;
  - changing any initialization context or recursively imported source/config
    latches restart-required `configuration_stale`, blocks compile/navigation,
    and does not hot reload after byte reversion;
  - imported workflow bundles compile through the read-only shared core and
    remain available to the entry with no workspace writes;
  - direct local/imported procedure and workflow calls with non-null
    `authored_callee_span` resolve to their defining spans, including an
    imported stdlib procedure;
  - every unsupported go-to-definition shape in the closed matrix returns
    null;
  - documentSymbol returns only `defmodule`, `defproc`, and `defworkflow`;
  - completion returns only visible local/imported procedure/workflow names
    plus compiler-registry form heads, with no nominal filtering;
  - null `authored_callee_span` and cursor positions outside a non-null exact
    authored span, including arguments and unsupported generated/WCC calls,
    return null;
  - dirty, compile-pending, dependency-invalidated, configuration-stale,
    language-failed, and server-failed documents return null/no navigation
    items;
  - each of the four library-only stdlib probes compiles directly through one
    full Stage-3 call with `entry_workflow=null` and triggers no Stage-1
    import, call, or fallback.
- **Concurrency:** a rapid save storm produces serialized compiles with
  latest-entry-generation/latest-trace-derived-source-and-config-vector-only
  diagnostics/navigation and no interleaved-state corruption.
- **CLI parity (F2):** positive parity first asserts the exact normalized
  compile-request tuple at the pre-entry-selection/input-binding seam and then
  the complete structured diagnostic tuple:
  - default positive: no explicit LSP source roots and no CLI `--source-root`
    flags produce empty caller `source_roots`; both effective root lists then
    gain the same production-inferred entry root (including a possible
    `defmodule` ancestor) and builtin stdlib through the same production
    `_effective_source_roots`;
  - explicit positive: ordered `initializationOptions.source_roots` and the
    same one-for-one ordered CLI `--source-root` flags produce equal caller
    roots, and both effective lists select the first containing explicit root
    as the production-selected entry root;
  - negative controls in both directions: an extra, missing, replaced, or
    reordered explicit source root fails parity; the one workspace root is
    absent from caller `source_roots` unless it was separately supplied;
  - `rootUri` and a workspace-folder URI that canonicalize to the same path
    produce the same single `workspace_root`; zero or more than one distinct
    canonical root rejects before parity compilation.
  Tampering any other request field, a loaded bundle, raw span end, metadata
  field, form path, or expansion-frame order must fail; message/note wording
  changes must not. The positive CLI launches from the same workspace with the
  same explicit context flags. Supplying `lint_profile` or `lowering_route` in
  `initializationOptions` is rejected, and the captured tuple still contains
  the exact normalized production defaults.
- **Compile tier:** a spy/import guard proves the server invokes exactly one
  full Stage-3 compile through the shared core for each accepted
  clean-open/save generation and never imports/calls Stage 1 or starts a
  second phase.
- **Latency evidence (F3):** preserve the measured 1.87-second result and the
  explicit v1 acceptance in the implementation report; remeasurement is
  informational, not authority to absorb P5.
- **Transport:** capture server stdout and prove it contains only valid
  framed protocol messages; logging/error paths use stderr or
  `window/logMessage`.
- **End-to-end (repo rule):** the real server, launched as an editor would
  launch it, against a real workflow entry in this repository, producing
  correct diagnostics and navigation — recorded as the required
  frontend-adjacent integration check.

## Declarative Acceptance Scenario

An author opens this repository in an editor with a generic LSP client
configured to run `python -m orchestrator.lsp` with this repository as its one
canonical workspace root. They open a contained saved workflow whose editor
text exactly equals disk and that imports stdlib modules, then introduce a type
error in a provider form and save:

- the server performs one serialized full Stage-3 compile using a normalized
  request tuple exactly equal to the tuple from an unchanged dry-run CLI
  launched from the same workspace, including fixed production-default lint
  and lowering values;
- on save, the editor shows one diagnostic whose complete structured parity
  tuple equals the tuple from
  `python -m orchestrator run <file> --dry-run`, with the squiggle exactly on
  the raw authored start/end span;
- the diagnostic's related information points at the macro call site when
  the error originates inside an expansion, while notes and raw metadata
  remain in `Diagnostic.data`;
- go-to-definition inside the non-null exact compiler-owned
  `authored_callee_span` of an imported procedure call jumps to its definition
  in the stdlib module file, while a cursor in its arguments or a call whose
  provenance is `None` returns null;
- changing the unsaved buffer makes navigation return null without compiling;
- fixing the error and saving clears the diagnostic and refreshes document
  symbols;
- when the imported stdlib source B changes on disk, the server invalidates
  this entry A through the recorded reverse dependency, serves null navigation
  while A recompiles, and accepts A's new snapshot only when the digest of the
  exact B `raw_bytes` whose derived `parser_text` was parsed under
  `SourceReadTrace` equals B's current raw-byte SHA-256 revision;
- if a configured context or recursive imported-bundle source changes, the
  server invalidates all entries, refuses further compile/navigation, and
  requires restart rather than hot-reloading it.

This proves the intended integration because every assertion is on stable
configuration identity, structured diagnostic metadata, authored spans,
entry/source/config generation ownership, and CLI parity — not on message
phrasing or on any analysis the server could have produced without the
production compiler.

## Success Criteria

- All Verification Strategy checks implemented and green, including the
  stdio integration tests, the CLI-parity test, and the end-to-end check on a
  real repository workflow.
- F1's positive four-module library-only Stage-3 result enforced; F2's exact
  request and diagnostic tuples proven in both directions; F3's accepted
  1.87-second result recorded.
- F2 fixes validation to `SHARED_CALLABLE`, lint/lowering to the unchanged
  production defaults, and workspace-root parity to a CLI launched from that
  one canonical workspace; every client entry/explicit source root is
  contained by it, every trace-read `.orc` path is under it or the exact
  compiler-owned builtin stdlib root, caller source roots are exactly the
  ordered explicit LSP/CLI roots, neither allowed root is implicit there, and
  v1 exposes no lint/lowering editor overrides.
- The closed symbol matrix and entry/source/config-current freshness rules are
  exact: unsupported, dirty, pending, dependency-invalidated,
  configuration-stale, failed, and stale requests return null/no items.
- Direct navigation uses only non-null exact compiler-owned
  `authored_callee_span`; `None`, arguments, whole-form-only approximations,
  WCC reconstructions, and ambiguous generated/expanded calls return null.
- Reverse invalidation passes both directions: B changes invalidate importer
  A, unrelated C does not when ownership is trustworthy, and unknown
  ownership invalidates all open entries. Missing/unreadable dependencies,
  notification-free external edits, closed imports, `didClose` cleanup, and
  superseded source vectors are covered.
- Each accepted source vector comes only from an internally consistent
  compiler `SourceReadTrace`: each read hashes unchanged `raw_bytes`, compares
  editors against strict UTF-8 `raw_decoded_text`, and parses only the fixed
  universal-newline `parser_text` derived from that same read. CRLF and
  bare-CR compatibility preserves current ASTs, spans, and diagnostics while
  raw revisions remain distinct. Repeated identical reads collapse only in
  the vector, repeated-read digest mismatch rejects, and
  pre-accept/navigation rechecks bind current workspace and builtin-stdlib
  bytes plus the frozen builtin-root identity. An arbitrary external
  dependency rejects.
- Persistent, LSP, and recursive imported-manifest paths have exact in-memory
  selection/bundle/semantic/Core-AST/executable/fingerprint/prospective-path
  parity; read-only consumers write zero files and only `_emit` persists.
- Initialization configuration and its recursively imported source/config
  closure, single workspace root, and compiler-owned builtin-root identity are
  immutable: every change/missing/unreadable/root-set/identity case latches
  restart-required stale state and blocks compile/navigation.
- Stdout contains protocol frames only.
- Default-install dependency set unchanged; `lsp` extra installs cleanly.
- Capability matrix row and doc-index routing are present.
- Independent design and quality review approved the design before
  implementation; the completed implementation plan owns the ordered task and
  final implementation reviews.

## Stop / Revise Criteria

- The LSP and CLI cannot construct exactly equal normalized pre-entry
  compile-request tuples through production loaders → stop; do not weaken F2
  to output similarity or add LSP-only defaults.
- Initialization cannot establish exactly one immutable canonical workspace
  root plus the exact compiler-owned builtin stdlib dependency root, with
  trace paths confined to those two roots → reject/stop; do not add any other
  external allowance, root arbitration, cross-root ownership, or per-root
  caches to v1.
- The persistent, LSP, and recursive imported-manifest paths cannot share one
  compile/select/reattach core with canonical-identical selection,
  `LoadedWorkflowBundle`, semantic/Core-AST/executable payloads, fingerprint,
  prospective provenance paths, and zero read-only writes → stop. In
  particular, if `_select_and_reattach` or a payload-based Core AST /
  semantic-IR seam still needs to create/read `source_map.json`, stop and
  refactor that seam first; do not temporarily emit/delete files, remove
  imported-bundle support, or duplicate loader semantics.
- A requested v1 lint/lowering override would require divergence from
  unchanged dry-run CLI configuration → reject the option and return it to a
  shared CLI/workspace-configuration design; do not add it to
  `initializationOptions`.
- `read_sexpr_file` cannot derive unchanged `raw_bytes`, strict
  `raw_decoded_text`, and the exact legacy universal-newline `parser_text`
  from one read; CRLF or bare-CR AST/span/diagnostic compatibility changes;
  raw digests cease to distinguish byte encodings; exact editor comparison
  uses the normalized parser view; the collector cannot reach every Stage-3
  source read; repeated-path mismatches cannot reject; or mandatory
  post-return/pre-navigation recomputation cannot be enforced → stop/revise
  the explicit `SourceReadTrace` seam. Do not read the file twice, hash
  `parser_text`, or use pre-hoc hashes, timestamps, watcher delivery,
  diagnostics, or entry generation as source-vector authority.
- Initialization context and recursive imported source/config closure cannot
  be frozen/rechecked as one immutable digest vector → stop; do not hot-reload
  partial context or continue after configuration drift.
- The server cannot obtain raw full diagnostic spans or the complete
  post-`with_diagnostic_metadata` tuple → stop; do not parse rendered or
  lossy serialized diagnostics.
- A future latency observation challenges the accepted 1.87-second v1 tradeoff
  → return to design review. Stage-1 fallback, two-phase publishing, and P5
  remain forbidden until separately designed and scheduled.
- The server cannot answer navigation without doing its own parsing → stop;
  the closed compiler-shape lookup is wrong, and §76.1 forbids the workaround.
- `authored_callee_span` cannot be captured only for unambiguous direct-authored
  syntax, preserved through specialization/traversal/copy, and kept `None`
  across WCC/generated/expanded/ambiguous reconstruction → stop direct-call
  navigation; do not parse in the LSP or substitute a whole-form span.
- pygls proves unsuitable → substitute the transport library; the
  translation and driver contracts are library-independent by construction.

## Documentation Impact

Implementation supplies the capability-matrix and routing updates, frontend
specification §76.1 implementation note, Workflow Lisp drafting-guide pointer,
and `docs/workflow_lisp_language_server_setup.md`. The setup guide owns client
configuration, optional installation, exact single-root initialization,
clean-open/save behavior, fixed compile-policy defaults, compiler-read
raw-byte invalidation, restart-required configuration/root drift,
imported-bundle support, zero writes, and null-navigation behavior.

## Implementation Record And Handoff

The implementation completed the following independently tested phases:

1. **Diagnostics core** — translation layer (pure, unit-tested), compile
   shared read-only build-core extraction, exact-byte `SourceReadTrace`
   plumbing with one-read raw/decoded/parser views and legacy-newline
   compatibility, separate immutable configuration trace, single-root
   initialization/containment, request normalizer/parity capture, per-entry
   contribution generations, reverse index, serialized full-Stage-3 driver,
   stdio server skeleton, integration/zero-write tests, and exact CLI/import
   parity tests. F1-F3 choices are enforced and recorded. No language/runtime
   semantics change and no Stage-1 import.
2. **Navigation** — optional `authored_callee_span` metadata
   capture/preservation/absence,
   entry/source/config-current snapshot views, closed-matrix
   go-to-definition, document symbols, completion, mandatory pre-response
   digest checks, and dirty/pending/dependency-invalidated/
   configuration-stale/failed/stale null-result tests.
3. **Packaging and docs** — `lsp` extra, editor-setup documentation,
   capability matrix and routing updates, end-to-end check.
4. **L5 authored reference navigation** — collision-safe five-field definition
   rows; exact original-syntax/compiler-catalog joins for authored prompt heads
   and final direct-retained proc-ref names; common-preflight, visibility,
   collision-refusal, and null-matrix coverage; and a repository-real stdio
   check that resolves the review workflow prompt head while keeping its
   macro-consumed proc-refs and macro head null and its direct workflow call
   exact. No compiler/frontend or non-navigation production file changed.

Likely-touched modules: new files under `orchestrator/lsp/`;
`orchestrator/workflow_lisp/build.py`
(`build_frontend_bundle_in_memory`, `FrontendInMemoryBuildResult`,
`_select_and_reattach`, `_reattach_bundle_provenance`,
`_reattach_bundle_semantic_ir`, `_emit`, and recursive
`load_imported_workflow_bundle_manifest`);
`orchestrator/workflow/core_ast.py::build_core_workflow_ast`,
`orchestrator/workflow/lowering.py::build_loaded_workflow_bundle`, and
`orchestrator/workflow/semantic_ir.py::derive_workflow_semantic_ir` for the
authoritative optional `source_map_payload` parameter and legacy persisted-path
fallback; `orchestrator/workflow_lisp/reader.py` (`SourceReadTrace`,
`SourceReadRecord`, and `read_sexpr_file`),
`orchestrator/workflow_lisp/modules.py::resolve_module_graph`, and
`orchestrator/workflow_lisp/compiler.py::compile_stage3_entrypoint` plus its
Stage-3 source-loading helpers for explicit collector threading; any reachable
Stage-3 reread call sites in `orchestrator/workflow_lisp/lowering/core.py` and
`orchestrator/workflow_lisp/lowering/pure_projection.py`;
`orchestrator/workflow_lisp/expressions.py` plus the existing expression
construction, specialization, traversal, and copy paths, and
`orchestrator/workflow_lisp/wcc/defunctionalize.py` for
`authored_callee_span`; `pyproject.toml` (extras); and focused tests under
`tests/`. Compiler/typecheck/lowering/runtime language behavior is unchanged;
the reader/module/compiler delta is trace metadata and exact-byte plumbing
only.

Known tricky areas: UTF-16 coordinate conversion; clearing multi-file
diagnostics when one entry's target set shrinks while another still
contributes; generation-safe atomic replacement; canonical equality of
production-loaded bundles; recursive imported compilation without `_emit`;
zero-write proof; single-root containment without implicit source roots;
reverse-index cleanup; threading one collector through every Stage-3 reread;
rejecting an `A -> B -> A` digest mismatch; external/closed dependency changes
during a serialized compile; immutable configuration latching; mandatory
digest checks without watcher assistance; preserving exact authored
`authored_callee_span` while preserving `None` through WCC/generated/expanded
forms; conservative invalidation when closure ownership is unknown; raw-span
handling when paths are synthetic or unreadable; keeping stdout frame-only;
and keeping compile-worker serialization airtight under request storms.

The implementation followed that dependency order: shared in-memory build
extraction and exact value/zero-write parity; one-read hash/parse identity and
both `A -> B -> A` controls; single-root state; optional
`authored_callee_span`; then transport, navigation, packaging, and docs.

Still out of scope after implementation: all of P1–P5, grammar/extension
packaging, `didChange` compilation, hover, rename, formatting, semantic
tokens, Stage-1 fallback, two-phase publishing, and nominal completion
filtering. Non-default lint/lowering editor configuration, more than one
workspace root, root arbitration, and per-root caches are also out of scope
pending their own designs.

## Open Questions

1. **Editor client packaging** — whether a thin VS Code extension (bundling
   a grammar and server discovery) lives in this repo, a sibling repo, or
   nowhere (generic client config only). Owner: user decision at
   implementation time. Blocking: no.

The following are **not** open questions: compile configuration is the exact
production-normalized tuple; lint/lowering use the fixed unchanged dry-run
defaults and cannot be overridden by v1 `initializationOptions`; workspace
root parity uses a CLI launched from the one immutable canonical root; more
than one distinct root and root-set changes are rejected/restart-required;
caller `source_roots` are only the ordered explicit LSP/CLI roots and never
implicit workspace declarations; successful-source freshness is
entry-generation plus an internally consistent compiler `SourceReadTrace`
whose exact-byte SHA-256 vector passes mandatory
pre-accept/pre-navigation checks; missing/unreadable sentinels and
initialization configuration/recursive imported closure remain immutable
until restart;
imported bundles use the shared read-only production build core; direct-call
navigation uses only non-null compiler-owned `authored_callee_span`; v1
performs one full Stage-3 compile per affected entry; there is no Stage-1
fallback or two-phase publication; and P1-P5 are fully deferred with no
ordering decision in this design.
