# Workflow Lisp Language Server

- **Status:** proposed
- **Kind:** feature / developer tooling architecture decision
- **Owner:** Workflow Lisp frontend (tooling consumer)
- **Reviewers:** pending independent design review; direction requested by the
  user on 2026-07-13
- **Created:** 2026-07-13
- **Last material update:** 2026-07-13
- **Related docs / plans:**
  - `docs/design/workflow_lisp_frontend_specification.md` §76.1 "Editor And
    Lint Tooling Compatibility" (parent authority for this design)
  - `docs/design/workflow_lisp_frontend_mvp_specification.md` §9.1 "Linter And
    LSP Compatibility" (records LSP capabilities as deferred, not rejected)
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/`
    (predecessor: built the machine-readable diagnostics surface "suitable for
    future lint/LSP tooling" while explicitly excluding "editor/LSP
    implementation, background daemons, or persistent compile servers")
  - `docs/design/workflow_lisp_source_map.md` (source-map component contract)
  - `docs/design/workflow_language_design_principles.md`
  - `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
    (governing roadmap; see Dependencies And Sequencing)
- **Implementation target:** not scheduled; requires an explicit amendment to
  the procedure-first roadmap (see Dependencies And Sequencing)

## Summary

`.orc` authors get compiler feedback today only by running
`python -m orchestrator run <file> --dry-run` or `compile` in a terminal, one
blocking diagnostic at a time, with no editor navigation across the growing
stdlib/import surface.

This design adds an **LSP (Language Server Protocol) server for `.orc`**: a
stdio server in a new `orchestrator/lsp/` package that is a **pure consumer**
of the existing compile entry points, exactly as the frontend specification's
§76.1 mandates ("must not implement a parallel parser, type checker, linter,
or workflow validator"). Version 1 delivers diagnostics on open/save,
go-to-definition, document symbols, and name completion — all powered by
compiler data structures that already carry full source spans, stable
diagnostic codes, and definition locations. Capabilities that require frontend
changes (hover types, multi-diagnostic error recovery, as-you-type checking)
are named as explicit prerequisites and deferred, not approximated.

## Context And Authority

Verified implementation behavior this design builds on (2026-07-13 checkout):

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
- **Diagnostics are structured and already serializable.**
  `LispFrontendDiagnostic` (`diagnostics.py:239`) carries code, message, span,
  severity, phase, notes, and `expansion_stack`; `LispFrontendCompileError`
  (`diagnostics.py:255`) transports a tuple of them; `serialize_diagnostic` /
  `serialize_diagnostics` (`diagnostics.py:290,318`) already emit a JSON
  envelope with path/line/column. Expansion frames (`ExpansionFrame` /
  `HelperExpansionFrame`, `syntax.py:25,36`) carry both `call_span` and
  `definition_span`, so errors inside macro expansions map to the authored
  call site.
- **No-execute compile entry points exist.** `compile_stage1_entrypoint`
  (`compiler.py:516`) validates module headers, imports/exports, and type
  definitions "without requiring provider externs, prompt externs, command
  adapters, or imported workflows". `compile_stage3_entrypoint`
  (`compiler.py:575`) runs the full parse→expand→typecheck→effect→lower
  pipeline with optional externs/boundaries/bundles parameters and executes
  nothing. The CLI run path feeds `.orc` files through the same pipeline via
  `build_frontend_bundle`, with externs files as **optional** CLI arguments
  (`orchestrator/cli/commands/run.py:331-351`) — so a compile with no externs
  supplied is exactly what a bare `run --dry-run` performs.
- **Symbol registries record definition locations.** `ProcedureCatalog` /
  `WorkflowCatalog` map names to definition nodes whose spans include the
  defining path; `FrontendTypeEnvironment` (`type_env.py`) resolves type names
  to definitions; import scopes are built per module
  (`modules.py`, `build_import_scope`). Go-to-definition needs no new
  frontend capability.
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
  relevant to future runtime-diagnostic surfacing, not required by v1.
- **No editor tooling exists today**: no grammar, no extension, no server.
  Whole-program compilation has no caching or incrementality; every compile
  resolves the entry file's full import closure plus the injected stdlib
  source root (`compiler.py`, `_effective_source_roots`).

Ambiguity resolved by this design: whether editor tooling waits for
error-tolerant frontend infrastructure or ships first as a save-driven
consumer of the fail-fast pipeline. This design fixes it as consumer-first:
v1 ships on today's pipeline; tolerance work is a named, separately gated
follow-on.

## Problem

- Authoring feedback is terminal-only and manual. An author editing a
  workflow that imports stdlib modules must leave the editor, run a CLI
  compile, read one diagnostic, fix, and repeat — per error.
- There is no navigation. The procedure-first migration is deliberately
  growing the cross-module reuse surface (procedures and stdlib modules
  consumed via imports), which multiplies "where is this defined?" lookups
  that currently require grep.
- The compiler already produces everything an editor needs — structured
  diagnostics with spans and stable codes, definition locations, expansion
  provenance — but no surface delivers it to an editor.
- Doing this wrong is cheap and tempting: a regex/tree-sitter side-analyzer
  would ship fast and then drift from the real language forever. §76.1
  prohibits exactly that, which makes the architecture a design-level
  decision rather than a tooling detail.

## Goals And Non-Goals

Goals:

1. Diagnostics on open and save for `.orc` files, published with correct
   ranges, stable diagnostic codes, severities, and expansion-stack
   provenance — sourced exclusively from the production compiler, with
   CLI parity: the same broken file yields the same diagnostic codes from the
   server and from `run --dry-run`.
2. Go-to-definition (including cross-module and stdlib targets), document
   symbols, and module-scope name completion, sourced from compiler catalogs
   and import scopes.
3. Editor-agnostic delivery: a stdio LSP server usable from any LSP client;
   no editor-specific coupling in the server.
4. Zero frontend behavior changes in v1; the server is an additive package,
   and the runtime dependency footprint of non-LSP installs is unchanged.
5. Honest capability boundaries: features blocked on frontend work are
   deferred with named prerequisites, never approximated in the server.

Non-Goals (intentionally excluded from v1):

- **As-you-type checking (`didChange`) and unsaved-buffer overlay.** The
  compile pipeline reads modules from disk; v1 compiles on save. A path→text
  overlay through module resolution is prerequisite P4 (below).
- **Hover type information.** Requires a span→type sidecar collected during
  typecheck dispatch (prerequisite P3).
- **Multi-diagnostic error recovery.** Requires diagnostic accumulation in
  the typecheck helpers and reader recovery (prerequisites P1/P2). v1
  publishes what the pipeline produces — usually one blocking diagnostic —
  and states so in its documentation.
- **Rename, formatting, code actions, semantic tokens.**
- **A syntax-highlighting grammar** (TextMate/tree-sitter). Independent
  deliverable; usually wanted alongside an LSP but architecturally separate.
- **Editor extension packaging** (VS Code marketplace etc.). v1 documents
  generic client configuration; packaging is an open question.
- **A persistent compile daemon beyond the LSP process itself**, compile
  caching, or incrementality. Whole-closure compile per save is the v1 cost
  model, with measured latency as a feasibility gate (F3).

## Decision

Build a stdio LSP server as a new `orchestrator/lsp/` package that drives the
existing compile entry points and translates their structured results into
LSP messages.

- **Chosen approach:** pure-consumer server (per §76.1); save-driven compile
  model reading from disk; single serialized compile worker (global pipeline
  state forbids concurrency); pygls as the LSP transport library, isolated
  under a new `lsp` optional-dependency extra (the project already uses the
  extras pattern for `dev`); v1 capability set = diagnostics + navigation
  (Tier 0/1); frontend-dependent capabilities deferred behind the named
  prerequisites P1–P5.
- **Alternatives rejected:**
  - *Parallel lightweight analyzer* (tree-sitter grammar or hand-rolled
    parser inside the server). Rejected: violates §76.1 verbatim, and every
    language change would have to land twice or drift.
  - *Artifact-watching design* (shell out to the CLI compile, parse
    `diagnostics.json` from `.orchestrate/build/`). Rejected: process-spawn
    latency per save, build-directory churn inside the user's workspace for
    every keystroke of feedback, and no in-memory access to catalogs for
    navigation. The entry points are the sanctioned in-process seam.
  - *Embedding the server in the run CLI* (`orchestrator run --lsp`-style).
    Rejected: conflates run lifecycle with editor lifecycle; a separate
    module keeps the runtime path untouched and the dependency optional.
  - *Tolerance-first sequencing* (land reader recovery and diagnostic
    accumulation before any server). Rejected: inverts value delivery —
    diagnostics-on-save with one diagnostic per compile is immediately
    useful and already strictly better than the terminal loop, while
    recovery is the expensive tail. Shipping the consumer first also gives
    the tolerance work a concrete, measurable client.
- **Tradeoffs accepted:** one blocking diagnostic per compile in the common
  case (documented v1 limitation); navigation and ranges are as-of-last-save,
  so positions drift while the buffer is dirty; every save recompiles the
  full import closure plus stdlib.
- **Left open:** see Open Questions (externs/config surface, two-phase
  stage1/stage3 publishing, client packaging, lint publication, Tier-2
  ordering).

## Design Details

### Server lifecycle and workspace model

- The server starts per editor workspace (stdio transport, one process per
  client). LSP `initialize` workspace folders become the compile
  `source_roots`; the compiler injects the builtin stdlib root itself
  (`_effective_source_roots`), so stdlib imports resolve with no
  configuration.
- `initializationOptions` may supply additional source roots and the same
  optional context files the run CLI accepts (provider externs, prompt
  externs, command boundaries, imported workflow bundles) so editor
  diagnostics can match a specific run configuration. The default —
  no options — matches a bare `run --dry-run`.
- The server is stateless across restarts: all snapshots are in-memory;
  nothing is written to the workspace.

### Compile driver

- On `didOpen` and `didSave` of an `.orc` file, the server schedules a
  compile of that file as the entry point. Requests are debounced and
  coalesced per URI (latest wins); a **single worker** executes compiles
  strictly serially because the pipeline resets module-global state per run.
- The driver calls `compile_stage3_entrypoint` first. If the file is not a
  valid stage-3 entry on its own (feasibility item F1 determines the exact
  failure classes), it degrades to `compile_stage1_entrypoint`, which still
  validates module wiring and type surfaces. The tier actually achieved is
  reported to the client via a log message, never silently faked.
- `LispFrontendCompileError` is caught and its structured diagnostics
  translated. Any other exception is a server-side error: logged via
  `window/logMessage`, previously published diagnostics left untouched, and
  never converted into a synthetic language diagnostic.

### Diagnostics translation and publication

- `LispFrontendDiagnostic` → LSP `Diagnostic`: span start/end map to a range
  (1-based line/column → 0-based line/UTF-16 code unit, converted against
  the file's text); `code` maps to the stable diagnostic code; severity maps
  onto LSP severities; `source` is `"orc"`; `notes` and each
  `expansion_stack` frame (call site and definition site) become
  `relatedInformation` locations.
- Diagnostics whose span path is not the compiled entry file are published to
  the owning file's URI (an entry compile can surface an error in an imported
  module). The server tracks which URIs each entry's last compile touched and
  clears stale diagnostics on the next compile of that entry.
- A successful compile publishes empty diagnostics for all touched URIs and
  retains the compile result as that entry's **last good snapshot**.

### Navigation index

- From each entry's last good snapshot the server builds, per file, an
  interval index over node spans (every parse/expression/definition node
  carries one), giving position→innermost-node lookup with no parsing in the
  server.
- **Go-to-definition:** resolve the identifier at the cursor through the
  module's import scope and the snapshot's catalogs
  (`ProcedureCatalog`, `WorkflowCatalog`, `FrontendTypeEnvironment`); the
  resolved definition's span (which carries its defining path) becomes the
  `Location`. Cross-module and stdlib targets work identically because
  stdlib modules are ordinary members of the compiled module graph.
- **Document symbols:** the module's definitions (types, procedures,
  workflows, prompts/externs) with their spans.
- **Completion (v1):** names visible in the module's scope — local and
  imported definitions plus known form heads. No type-directed or
  position-aware filtering in v1.
- **Staleness contract:** navigation answers are as-of the last successful
  compile. If the buffer changed since, or the last compile failed, the
  server answers from the stale snapshot (standard LSP behavior) — it never
  guesses, re-parses, or heuristically patches positions.

### Deferred capabilities and their frontend prerequisites

Each item below is a frontend change with its own blast radius; none is part
of this design's implementation scope, and each needs its own design
treatment (amendment to this document or a follow-on) plus a roadmap slot:

- **P1 — diagnostic accumulation.** Teach the shared typecheck raise helpers
  and the validation-pipeline continuation policy to collect multiple
  diagnostics per pass before failing. Highest UX value per unit of work;
  recommended first.
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
  compiles. Only worth designing against measured latency evidence from F3.

## Contracts And Interfaces

- **New:** `orchestrator/lsp/` package with a `python -m orchestrator.lsp`
  stdio entry point; `lsp` extras group in `pyproject.toml` (pygls); the
  diagnostic-translation contract (structured `LispFrontendDiagnostic`
  fields → LSP `Diagnostic` fields, including expansion-stack
  `relatedInformation`); a documented `initializationOptions` schema.
- **Changed:** nothing in the frontend, runtime, providers, or CLI for v1.
  The server imports existing public entry points read-only.
- **Spec deltas required at implementation time:** an implementation note
  under frontend specification §76.1 (the tooling now exists and consumes the
  named surfaces); capability matrix row; no `specs/` contract changes — the
  server executes nothing and owns no run state.

## Dependencies And Sequencing

- **Feasibility: proven for the v1 capability set.** Every v1 feature is
  backed by a verified existing seam (Context And Authority): structured
  diagnostics with spans and serialization, no-execute entry points,
  catalogs with definition locations, expansion provenance. No frontend
  change is required to ship v1.
- **Feasibility items to verify in phase 1 (recorded, not assumed):**
  - **F1** — `compile_stage3_entrypoint` accepts a library-only module (no
    workflow definitions) as an entry, or fails with an identifiable class
    the driver can catch to trigger the stage-1 fallback.
  - **F2** — compiling with no externs/boundaries files supplied yields the
    same diagnostics as a bare `run --dry-run` on the same file (CLI
    parity of the default configuration).
  - **F3** — measured on-save compile latency for the largest in-repo `.orc`
    entry points is acceptable (target: comfortably sub-second on
    representative workflows). If it is not, the two-phase publishing open
    question is resolved before proceeding; caching (P5) is not designed
    speculatively.
- **Roadmap sequencing:** v1 touches no compiler, executor, build, typecheck,
  or lowering surfaces, so it does not contend with procedure-first Stage 5
  wave work at shared surfaces. It is nonetheless discretionary work:
  scheduling requires an explicit amendment to the procedure-first roadmap
  execution sequence; this document does not make it selectable. The Tier-2
  prerequisites P1–P5 **do** touch reader/typecheck/module-resolution
  surfaces and must respect the roadmap's concurrency rules (serial with
  Stage 5/6 changes at shared surfaces) when they are eventually scheduled.
- Work that can proceed independently: independent design review of this
  document; a syntax-highlighting grammar; editor client packaging
  decisions.

## Invariants And Failure Modes

Invariants that must hold after implementation:

1. **No parallel frontend.** The server contains no parser, typechecker,
   linter, or validator logic; every language judgment originates from a
   compiler entry-point result (§76.1). The only text processing the server
   owns is coordinate conversion.
2. **Compiles are strictly serialized** within the server process (pipeline
   global state), and each goes through the entry points that perform the
   per-run state reset.
3. **Published diagnostics derive only from structured
   `LispFrontendDiagnostic` objects** — never from parsing rendered log
   strings.
4. **Navigation derives only from real compile snapshots.** Staleness is
   explicit; no heuristic position patching.
5. **The server never writes to the workspace.** It uses the in-memory entry
   points, not `build_frontend_bundle` (which persists build artifacts).
6. **Absence of the `lsp` extra changes nothing** for any other orchestrator
   surface; the runtime dependency set of a default install is unchanged.

Failure behavior:

- Malformed/broken source → the pipeline's (typically single) diagnostic is
  published with its authored span; the previous good snapshot keeps serving
  navigation.
- Server-internal exception during compile → `window/logMessage` error;
  existing diagnostics untouched; no synthetic language diagnostic.
- File outside all source roots → compiled with the entry-derived default
  roots (same behavior as the CLI on a standalone file).
- Editor kill / crash → no residue: no workspace writes, no external state.

## Security, Operations, And Performance

- The server reads workspace files and executes nothing: no provider
  invocations, no network, no run-state creation. It grants no authority the
  editor user does not already have.
- Cost model: one whole-closure compile per save, serialized and debounced.
  F3 gates acceptability with measurements rather than assumptions; the
  documented fallback direction (two-phase stage-1/stage-3 publishing) is an
  open question resolved on evidence.
- pygls is confined to the `lsp` extra; CI for the package runs only where
  the extra is installed.

## Evidence And Implementation Boundaries

- The translation layer (coordinates, severity/code mapping,
  expansion-stack related-information, multi-URI publish/clear bookkeeping)
  is pure and unit-testable against synthesized diagnostics.
- Integration evidence drives the real server over stdio against fixture
  `.orc` workspaces, including at least one fixture that imports real stdlib
  modules — no fixture-only shortcut around module-graph resolution.
- Tests assert diagnostic **codes, spans, counts, and URIs** — never rendered
  message phrasing (repo rule: behavioral/contract assertions that survive
  wording revisions).
- The CLI-parity check (same codes from server and `run --dry-run` on the
  same broken file) is the sanctioned proof that the server consumes the
  production pipeline rather than a lookalike.

## Compatibility And Migration

- Purely additive. No existing workflow, CLI, or frontend behavior changes.
  No YAML surface involvement.
- The server's capability documentation states the v1 limitations explicitly
  (save-driven, typically one diagnostic per compile, snapshot-stale
  navigation) so editor users' expectations match the pipeline's semantics.

## Verification Strategy

- **Unit (translation layer):** 1-based→0-based and UTF-16 conversion
  including non-BMP characters and spans at line boundaries; severity and
  code mapping; expansion-stack frames → relatedInformation locations;
  publish/clear bookkeeping across multi-file diagnostic sets.
- **Integration (stdio, fixture workspace):**
  - `didOpen` on a file with a type error → one diagnostic with the expected
    stable code and the authored range;
  - fix and `didSave` → diagnostics cleared, snapshot refreshed;
  - an error in an imported module → diagnostic published on the imported
    file's URI and cleared when resolved;
  - definition request on an imported procedure → `Location` at the defining
    span in the other module (and in a stdlib module);
  - documentSymbol lists the module's definitions; completion includes
    imported names;
  - a library-only module gets (at minimum) stage-1 diagnostics (F1).
- **Concurrency:** a rapid save storm produces serialized compiles with
  last-request-wins results and no interleaved-state corruption (assert via
  deterministic final diagnostics).
- **CLI parity (F2):** one test compiles a broken fixture through the server
  and through the dry-run CLI path and asserts identical diagnostic codes.
- **Latency evidence (F3):** measured compile times on the largest in-repo
  entry points, recorded in the implementation report.
- **End-to-end (repo rule):** the real server, launched as an editor would
  launch it, against a real workflow entry in this repository, producing
  correct diagnostics and navigation — recorded as the required
  frontend-adjacent integration check.

## Declarative Acceptance Scenario

An author opens this repository in an editor with a generic LSP client
configured to run `python -m orchestrator.lsp`. They open a workflow that
imports stdlib modules and introduce a type error in a provider form:

- on save, the editor shows one diagnostic whose code equals the code
  `python -m orchestrator run <file> --dry-run` prints for the same file,
  with the squiggle exactly on the authored span;
- the diagnostic's related information points at the macro call site when
  the error originates inside an expansion;
- go-to-definition on an imported procedure name jumps to its definition in
  the stdlib module file;
- fixing the error and saving clears the diagnostic and refreshes document
  symbols.

This proves the intended integration because every assertion is on stable
codes, authored spans, and CLI parity — not on message phrasing or on any
analysis the server could have produced without the production compiler.

## Success Criteria

- All Verification Strategy checks implemented and green, including the
  stdio integration tests, the CLI-parity test, and the end-to-end check on a
  real repository workflow.
- F1–F3 verified and their outcomes recorded; F3 latency documented.
- Default-install dependency set unchanged; `lsp` extra installs cleanly.
- Capability matrix row and doc-index routing added at implementation time.
- Independent design review signoff before implementation starts.

## Stop / Revise Criteria

- v1 cannot deliver useful diagnostics without frontend edits (e.g., F2
  reveals the default compile configuration produces spurious diagnostics
  that only extern wiring can silence) → stop and resequence behind the
  configuration open question rather than adding frontend special cases.
- F3 shows on-save latency is unusable on real workflows → revise toward
  two-phase stage-1/stage-3 publishing before designing caching (P5).
- The server cannot answer navigation without doing its own parsing → stop;
  the snapshot/interval-index abstraction is wrong, and §76.1 forbids the
  workaround.
- pygls proves unsuitable → substitute the transport library; the
  translation and driver contracts are library-independent by construction.

## Documentation Impact

At implementation time: capability matrix row; `docs/index.md` and
`docs/design/README.md` routing updates from "proposed" to the implemented
status; an editor-setup how-to (client configuration, extras install);
frontend specification §76.1 implementation note; a Workflow Lisp drafting
guide pointer once the tooling is usable. None are edited by this proposal
beyond the routing entries that announce it.

## Implementation Handoff

Suggested phases (each independently testable):

1. **Diagnostics core** — translation layer (pure, unit-tested), compile
   driver with serialization/debounce, stdio server skeleton, integration
   tests, CLI-parity test. F1–F3 are verified and recorded here. No frontend
   changes.
2. **Navigation** — snapshot retention, per-file interval index,
   go-to-definition, document symbols, completion, staleness contract tests.
3. **Packaging and docs** — `lsp` extra, editor-setup documentation,
   capability matrix and routing updates, end-to-end check.

Likely-touched modules: new files under `orchestrator/lsp/` only, plus
`pyproject.toml` (extras) and new tests under `tests/`. Read-only imports
from `orchestrator/workflow_lisp/` (`compiler`, `diagnostics`, `modules`,
catalogs) — no edits there.

Known tricky areas: UTF-16 coordinate conversion; clearing multi-file
diagnostics when the touched-URI set shrinks between compiles; representing
the stage-3→stage-1 degradation honestly in the client log; keeping the
compile worker's serialization airtight under request storms.

Safe first step: the translation layer plus the CLI-parity test — pure code,
no server process, immediately verifiable.

Out of scope for the implementation: all of P1–P5, grammar/extension
packaging, `didChange` handling, hover, rename, formatting, semantic tokens.

## Open Questions

1. **Externs/configuration surface** — is `initializationOptions` (mirroring
   the run CLI's optional context-file flags) the right long-term surface, or
   should a workspace config file own it so CLI and editor share one
   configuration? Recommendation: `initializationOptions` in v1; revisit if
   F2 shows the default configuration is too noisy. Blocking: no.
2. **Two-phase publishing** — publish fast stage-1 diagnostics immediately,
   then refine with stage-3 results? Adds ordering complexity; only worth it
   if F3 measurements demand it. Recommendation: single-phase v1. Blocking:
   no.
3. **Editor client packaging** — whether a thin VS Code extension (bundling
   a grammar and server discovery) lives in this repo, a sibling repo, or
   nowhere (generic client config only). Owner: user decision at
   implementation time. Blocking: no.
4. **Lint publication** — should lint classifications (the `lint_profile`
   surface the dry-run path already renders) publish as LSP warnings in v1?
   Recommendation: yes if they arrive on the same structured surface;
   verify shape during phase 1. Blocking: no.
5. **Tier-2 ordering** — recommended P1 (diagnostic accumulation) first on
   UX value, then P4 (overlay) before P2 (recovery), P3 (hover) opportunistic
   alongside typecheck work, P5 only on latency evidence. Each needs its own
   design treatment and roadmap slot. Blocking: no.
