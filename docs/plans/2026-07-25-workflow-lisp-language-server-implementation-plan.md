# Workflow Lisp Language Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute this plan task by task.
> Every behavior change uses `superpowers:test-driven-development`. Every task
> receives an independent specification-compliance review followed by a
> distinct implementation-quality review before its commit.

**Goal:** Implement the accepted Stage 8 Workflow Lisp language-server v1 as
a read-only, save-driven consumer of the production Stage-3 compiler, with
exact CLI diagnostic parity, content-addressed freshness, and the accepted
closed navigation surface.

**Architecture:** Add metadata-only exact-byte source tracing and exact
authored-callee provenance to the compiler, extract one read-only in-memory
prefix from the production build pipeline, and place a serialized single-root
LSP state machine around those shared seams. The server performs one full
Stage-3 compile for a clean open/save, publishes raw structured diagnostics,
and answers navigation only from a current successful compiler snapshot.
Only the persistent build `_emit` path writes workspace artifacts.

**Tech stack:** Python 3.11+, immutable dataclasses, SHA-256/canonical JSON,
Workflow Lisp Stage 3, pygls under the optional `lsp` extra, LSP over stdio,
pytest/pytest-xdist.

**Accepted design:** `docs/design/workflow_lisp_language_server.md` at commit
`cfcac27f`, with ordered `STAGE8_DESIGN_SPEC_APPROVED` then
`STAGE8_DESIGN_QUALITY_APPROVED`, followed by exact-diff reaffirmations.

**Status:** Closing verification for one post-completion correctness
correction. Tasks 1–9 remain committed, but Gate S8 is not reclosed until the
correction below has passed final exact-diff review and committed.
Preliminary closing review returned `STAGE8_FINAL_SPEC_APPROVED`, then
`STAGE8_FINAL_QUALITY_APPROVED`; the same reviewers reaffirmed the exact
closing diff as `STAGE8_FINAL_SPEC_REAFFIRMED`, then
`STAGE8_FINAL_QUALITY_REAFFIRMED`, and Task 9 committed at `c69c33a1`.
Preliminary plan review returned
`STAGE8_PLAN_SPEC_APPROVED` then `STAGE8_PLAN_QUALITY_APPROVED`; the final
exact plan/routing diff received ordered reaffirmation from the same reviewers
as `STAGE8_PLAN_SPEC_REAFFIRMED` then `STAGE8_PLAN_QUALITY_REAFFIRMED`, and
the accepted plan/routing gate committed at `e565fc84`.

---

## Preimplementation Plan And Routing Gate

Before Task 1:

- [x] Obtain independent `STAGE8_PLAN_SPEC_APPROVED`, then a distinct
      `STAGE8_PLAN_QUALITY_APPROVED` against this exact plan.
- [x] Correct `docs/design/README.md` so its canonical design entry records
      the already accepted design and routes to this implementation plan.
- [x] Correct the Stage-8 entry in `docs/index.md` so it identifies the design
      as accepted and routes to this reviewed queued implementation plan; do
      not disturb concurrent owner-authored hunks in that file.
- [x] Incorporate the reviewed task sequence and dependency order into
      `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`.
- [x] Set this plan's status to `Accepted for execution` and present the
      final exact plan/design-router/index/roadmap diff for
      `STAGE8_PLAN_SPEC_REAFFIRMED`, then
      `STAGE8_PLAN_QUALITY_REAFFIRMED`. These tokens are the external
      commit gate; the reviewed bytes are not edited to predict their receipt.
- [x] Patch-stage the exact plan/routing hunks, inspect the staged diff, and
      commit the accepted execution gate before implementation begins.

**Gate record:** commit `e565fc84`; ordered preliminary verdicts
`STAGE8_PLAN_SPEC_APPROVED` / `STAGE8_PLAN_QUALITY_APPROVED`; ordered final
exact-diff verdicts `STAGE8_PLAN_SPEC_REAFFIRMED` /
`STAGE8_PLAN_QUALITY_REAFFIRMED`; routing selector test `50 passed`.

## Scope And Deliberate Cost

This plan implements only:

- one immutable canonical workspace root per server process;
- the exact compiler-owned builtin stdlib root as the sole external source
  dependency allowance;
- clean-open/save-driven, serialized, full Stage-3 compilation;
- exact-byte compiler `SourceReadTrace` metadata and content-addressed
  source/configuration freshness;
- one shared read-only in-memory production build core;
- structured diagnostics over stdio;
- direct-call go-to-definition using exact compiler-owned authored provenance;
- document symbols for `defmodule`, `defproc`, and `defworkflow`;
- completion from visible callable names and compiler registry form heads;
- exact pre-entry request and post-metadata diagnostic parity with the
  production dry-run CLI; and
- optional `lsp` packaging plus truthful setup/capability documentation.

Do not add Stage-1 fallback, two-phase publication, dirty-buffer compilation,
source overlays, hover, diagnostic recovery/accumulation, compilation caches,
incrementality, multiple roots, lint/lowering overrides, rename, formatting,
code actions, semantic tokens, editor extensions, grammar packaging, or
nominal completion filtering. These are P1-P5 or separately deferred work.

The chosen whole-closure model makes low-latency as-you-type behavior harder:
each affected entry recompiles serially and every accepted/navigation
snapshot rehashes its complete relevant source/configuration closure. That
cost is accepted for v1; the measured 1.87-second compile does not authorize
P4/P5 shortcuts.

Principle 29 is binding. Completion is constrained only by compiler visibility
and registry membership. Stage 8 must not require nominal type taxonomies or
invent nominal filtering where structural compiler state is sufficient.

## Governing Authorities

Read before implementation:

- `AGENTS.md`
- `docs/index.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/design/workflow_lisp_language_server.md`
- `docs/design/workflow_lisp_frontend_specification.md` §76.1
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- `specs/dsl.md`
- `specs/versioning.md`

If this plan conflicts with the accepted design, correct the plan and repeat
its ordered reviews. Do not reinterpret the design in code.

## Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve every pre-existing user or external
change. Stage exact task-owned paths only; never use `git add .`, `git add -A`,
destructive checkout/reset, or broad cleanup.

For every task:

1. add the smallest behavioral or contract test;
2. run it and confirm RED for the intended missing behavior;
3. implement only the selected behavior;
4. rerun the narrow selector;
5. run adjacent regression selectors;
6. run `pytest --collect-only -q` for every new or renamed module;
7. update this plan with fresh evidence and `reviews pending`;
8. obtain an independent specification-compliance review;
9. resolve findings with TDD and repeat until specification approval;
10. obtain a distinct implementation-quality review;
11. resolve findings and repeat the ordered reviews until quality approval;
12. record both preliminary verdicts and `commit pending`;
13. ask the same reviewers to reaffirm the final exact diff in spec-then-
    quality order;
14. stage exact reviewed paths, run `git diff --cached --check`, inspect names
    and diff, and commit without post-review edits; and
15. record the factual implementation hash in a separate plan-only
    bookkeeping commit.

The plan-only commit may not carry source, tests, fixtures, normative docs, or
routing changes.

Use the `tmux` skill for the closing broad suite and any integration selector
exceeding one minute. Keep the installed/default provider and model; wait
instead of substituting a faster model.

Security work remains excluded by standing owner direction. Do not modify or
exercise the unrelated provider-isolation/security surfaces. The closing broad
command is:

```bash
pytest -q -n 16 --dist=worksteal \
  --ignore=tests/test_at61_at62_wait_for_path_safety.py \
  --ignore=tests/test_cli_safety.py \
  --ignore=tests/test_provider_isolation_policy.py \
  --ignore=tests/test_provider_isolation_schema_resources.py \
  --ignore=tests/test_provider_isolation_environment.py \
  --ignore=tests/test_provider_isolation_environment_cli.py \
  --ignore=tests/test_provider_launch_shim.py \
  --ignore=tests/test_secrets.py \
  -k 'not security and not secret and not isolation'
```

## Protected Working Tree

Before every commit, refresh `git status --short` and preserve every unrelated
dirty path. In particular, do not stage the standing protected planning,
security/provider-isolation, experiment-report, state-log, or prompt edits
listed by the active roadmap execution handoff. `docs/index.md` may contain
owner-authored concurrent hunks; routing updates must be patch-staged so only
Stage-8-owned hunks enter the commit.

## File And Responsibility Map

Exact-byte compiler reads:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/compiler.py`
- reachable Stage-3 reread owners under
  `orchestrator/workflow_lisp/lowering/`

Read-only production build core:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/semantic_ir.py`

Authored call provenance:

- `orchestrator/workflow_lisp/expressions.py`
- existing expression traversal/specialization/copy owners
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`

Language server:

- new package `orchestrator/lsp/`
- `pyproject.toml`

Documentation:

- `docs/capability_status_matrix.md`
- `docs/index.md`
- `docs/design/README.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/lisp_workflow_drafting_guide.md`
- new `docs/workflow_lisp_language_server_setup.md`
- `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- this plan

Proposed focused test owners:

- new `tests/test_workflow_lisp_source_read_trace.py`
- new `tests/test_workflow_lisp_build_in_memory.py`
- new `tests/test_workflow_lisp_authored_callee_span.py`
- new `tests/test_workflow_lisp_lsp_state.py`
- new `tests/test_workflow_lisp_lsp_compile_driver.py`
- new `tests/test_workflow_lisp_lsp_coordinates.py`
- new `tests/test_workflow_lisp_lsp_diagnostics.py`
- new `tests/test_workflow_lisp_lsp_stdio.py`
- new `tests/test_workflow_lisp_lsp_navigation.py`
- new `tests/test_workflow_lisp_lsp_cli_parity.py`
- new `tests/test_workflow_lisp_lsp_integration.py`
- new `tests/test_workflow_lisp_lsp_e2e.py`

If an existing module is the actual owner, extend it instead of duplicating
helpers. Do not create a second compiler wrapper, manifest loader, parser,
typechecker, or source-map decoder.

---

## Task 1: Trace The Exact Bytes Parsed By Every Stage-3 Read

**Outcome:** One explicit compiler-owned collector proves the exact bytes,
strict decoded editor text, and legacy universal-newline parser text used by
every Stage-3 source read.

**Files:**

- Modify: `orchestrator/workflow_lisp/reader.py`
- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/result_guidance.py`
- Modify: exact reachable Stage-3 reread owners under
  `orchestrator/workflow_lisp/lowering/`
- Modify: exact reachable Stage-3 reread owners under
  `orchestrator/workflow_lisp/wcc/`
- Create: `tests/test_workflow_lisp_source_read_trace.py`
- Modify: existing reader/module/compiler tests only where they own adjacent
  compatibility assertions

**RED:**

- [x] Prove `read_sexpr_file` currently cannot return ordered immutable read
      records or a canonical revision vector.
- [x] Prove one invocation performs one `read_bytes` and derives unchanged
      raw bytes, strict UTF-8 text, and parser text from that one value.
- [x] Cover LF/CRLF/bare-CR: parser text, AST, spans, and diagnostics match the
      legacy universal-newline reader while raw digests remain distinct.
- [x] Cover exact editor equality in both directions; parser normalization
      must never make mismatched editor/disk text clean.
- [x] Cover ordered `A(v1), B(v1), A(v1)` acceptance and
      `A(v1), B(v1), A(v2)` refusal.
- [x] Cover distinct missing/unreadable sentinels and strict-decode failure.
- [x] Prove every reachable Stage-3/import/lowering reread joins one explicit
      collector and Stage 1 has no trace path.

**GREEN:**

- [x] Add immutable `SourceReadRecord` and `SourceReadTrace` in the reader.
- [x] Canonicalize each path, assign a monotonic ordinal, call `read_bytes`
      once, hash exact bytes, strict-decode, then apply only
      `.replace("\r\n", "\n").replace("\r", "\n")` for parser text.
- [x] Preserve existing read/parse failures after recording their sentinel or
      exact raw revision.
- [x] Reject repeated-path digest disagreement immediately.
- [x] Thread the optional collector explicitly through Stage 3, module graph
      resolution, and every reachable source reread. Use no module global.
- [x] Rerun reader, parser, module graph, compiler, lowering, and source-map
      regressions.
- [x] Obtain `STAGE8_TASK1_SPEC_APPROVED`, then
      `STAGE8_TASK1_QUALITY_APPROVED`, and commit.

**Implementation record:** commit `21bcc212`.

- RED established the missing immutable collector/Stage-3 plumbing and the
  nominal result-guidance reread that escaped the first collector pass.
- The focused source-read module collects 18 tests and passes 18.
- Fresh adjacent selectors pass: result guidance/pure projection 20; lowering
  and pure projection 183; reader/modules/source maps 139; WCC inventory 82;
  materialize/provider-peer surfaces 88; WCC M1-M5 plus characterization 233;
  collection types/typed prompts/result guidance 38.
- `py_compile`, scoped `git diff --check`, and the direct-read seam scan across
  compiler, modules, lowering, and WCC are clean.
- Ordered preliminary reviews returned `STAGE8_TASK1_SPEC_APPROVED`, then
  `STAGE8_TASK1_QUALITY_APPROVED`. Ordered final exact-diff reviews returned
  `STAGE8_TASK1_SPEC_REAFFIRMED`, then
  `STAGE8_TASK1_QUALITY_REAFFIRMED`.

## Task 2: Extract The Shared Read-Only In-Memory Build Core

**Outcome:** Persistent build, LSP, and recursive imported-manifest consumers
share one compile/select/reattach core; only `_emit` writes.

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/build_artifacts.py`
- Modify: `orchestrator/workflow_lisp/build_manifest_io.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Create: `tests/test_workflow_lisp_build_in_memory.py`
- Modify: existing build/import/source-map tests where they own parity

**RED:**

- [x] Prove there is no public `build_frontend_bundle_in_memory` returning an
      immutable `FrontendInMemoryBuildResult`.
- [x] Capture exact no-import and recursive imported-manifest parity for
      selection, loaded bundle, imported bindings, semantic/Core/executable
      values and canonical payloads, fingerprints, prospective paths, source
      map, configuration trace, and ordered `SourceReadTrace`.
- [x] Prove current read-only selection creates/writes build paths.
- [x] Cover authoritative supplied source-map payload when the prospective
      path is absent or contains conflicting bytes.
- [x] Cover `source_map_payload=None` as the sole persisted-path compatibility
      fallback.
- [x] Cover library-only `entry_workflow=null` and selected imported rows.

**GREEN:**

- [x] Add the public read-only core around existing resolution, loaders,
      recursive compilation, entry compile, selection, and reattachment.
- [x] Make `_select_and_reattach` a value-only operation: no mkdir, reads,
      writes, temporary emission, or write/delete workaround.
- [x] Thread an optional authoritative `source_map_payload` through Core AST,
      loaded-bundle/runtime-plan, semantic IR, and reattachment seams.
- [x] Keep `None` as the existing persisted-provenance fallback; a supplied
      mapping, including `{}`, may not inspect the provenance path.
- [x] Make persistent `build_frontend_bundle` equal the read-only core followed
      by `_emit`; recursive imported `.orc` compilation calls only the core.
- [x] Prove complete workspace trees are byte-identical before/after both
      read-only consumers and only `_emit` creates `.orchestrate/build`.
- [x] Rerun build, import, source-map, Core AST, semantic IR, executable, and
      runtime-plan regressions.
- [x] Obtain `STAGE8_TASK2_SPEC_APPROVED`, then
      `STAGE8_TASK2_QUALITY_APPROVED`, and commit.

**Implementation record:** commit `138aa0df`.

- RED established the absent public core, hidden selection/fingerprint I/O,
  recursive child emission, null-selection rejection, authoritative
  source-map gaps, missing source/configuration trace validation, excess
  public configuration-trace parameter, and lost legacy JSON newline
  diagnostics.
- The new in-memory build module collects 16 tests and passes 16, including
  exact LF/CRLF/bare-CR configuration-loader compatibility over distinct raw
  revisions.
- Fresh adjacent selectors pass: build/source-map/runtime/CLI 211;
  imported-stdlib/CLI/shared validation 129; source trace/Core AST 25; and
  applicable semantic IR 49.
- Two semantic-IR module expectations remain red and were reproduced
  byte-identically at pre-Task-2 `HEAD` `7fe83912`: typed-prompt lineage
  without its retired family-profile input and pre-existing nested
  `form_path` serialization. A separate causal audit confirmed neither is
  owned or changed by Task 2.
- `py_compile` and scoped `git diff --check` are clean.
- Ordered preliminary reviews returned `STAGE8_TASK2_SPEC_APPROVED`, then
  `STAGE8_TASK2_QUALITY_APPROVED`. Ordered final exact-diff reviews returned
  `STAGE8_TASK2_SPEC_REAFFIRMED`, then
  `STAGE8_TASK2_QUALITY_REAFFIRMED`.

## Task 3: Implement Single-Root State, Immutable Configuration, And The Serialized Driver

**Outcome:** A read-only LSP state machine owns one root, serialized full
compiles, exact source/configuration currentness, and deterministic reverse
invalidation.

**Files:**

- Create: `orchestrator/lsp/__init__.py`
- Create: `orchestrator/lsp/state.py`
- Create: `orchestrator/lsp/compile_driver.py`
- Create: `tests/test_workflow_lisp_lsp_state.py`
- Create: `tests/test_workflow_lisp_lsp_compile_driver.py`

**RED:**

- [x] Cover one `rootUri`, one folder, and equivalent spellings of the same
      canonical root; reject zero/two roots and uncontained entries/explicit
      source roots before state or compilation.
- [x] Accept traced `.orc` only under the workspace or exact frozen builtin
      stdlib root; reject every other external path.
- [x] Prove workspace and builtin roots never enter caller `source_roots`
      unless the workspace was separately explicit.
- [x] Cover immutable production-loaded provider/prompt/command/imported
      configuration and recursive imported closure.
- [x] At initialization, preserve each unconfigured optional input as absent
      and reject every configured missing/unreadable input. Reject
      `lint_profile` or `lowering_route` in `initializationOptions`.
- [x] After initialization, cover changed/missing/unreadable configuration
      and root-folder changes latching restart-required
      `configuration_stale`; byte reversion does not unlatch it.
- [x] Cover clean `didOpen` against exact `raw_decoded_text`; mismatched editor
      text, missing/unreadable disk state, and strict-decode failure create
      dirty/unavailable state, schedule zero compiles, and expose no
      navigation snapshot.
- [x] Cover serialized compiles, per-entry generations, debounce/coalescing,
      latest-generation acceptance, and late-result discard.
- [x] Cover trusted `A -> B`, unrelated C negative control, closed B,
      missing/unreadable B, unknown-closure all-open invalidation, and
      `didClose` ownership cleanup.
- [x] Cover a current language-error completion with a complete, consistent
      trace retaining its precise closure/vector; only incomplete or
      inconsistent error traces become closure-unknown.
- [x] Cover the state transition for a delivered `.orc`
      create/change/delete observation and its eager invalidation result, with
      a reverse control proving such delivery is never required for
      correctness. Server capability registration belongs to Task 6.
- [x] Cover mandatory post-compile and pre-request digest/config/root rechecks
      without watcher delivery.
- [x] Prove library-only entries use exactly one Stage-3 compile and Stage 1
      is neither imported nor called.

**GREEN:**

- [x] Canonicalize and freeze exactly one workspace root, the exact production
      builtin stdlib root, ordered explicit caller roots, fixed production
      lint/lowering defaults, and `SHARED_CALLABLE`.
- [x] Freeze the complete configuration vector and implement the latched stale
      transition plus one restart-required notice.
- [x] Keep initialization failure separate from post-initialization staleness,
      and expose no lint/lowering override in the initialization schema.
- [x] Represent entry/open/dirty/pending/success/failure/closure-unknown state
      immutably enough that generation acceptance is atomic.
- [x] Use one worker and one fresh `SourceReadTrace` per generation; call the
      read-only core exactly once.
- [x] Derive successful closures only from internally consistent compiler
      traces; probes/watchers schedule but never become authority.
- [x] Maintain trace/diagnostic-target reverse ownership and implement both
      precise and conservative invalidation rules, including precise
      trustworthy language-error closures.
- [x] Expose one state/driver transition that Task 6 can call for delivered
      file-watch observations; it must use the same revision/invalidation
      authority as notification-free checks. Server capability registration
      belongs to Task 6.
- [x] Rehash the complete source/configuration vector and builtin-root identity
      before acceptance and every later snapshot response.
- [x] Rerun the new state/driver tests plus build/compiler/import regressions.
- [x] Obtain `STAGE8_TASK3_SPEC_APPROVED`, then
      `STAGE8_TASK3_QUALITY_APPROVED`.
- [x] Commit Task 3.

**Implementation record:** commit `87016ecc`.

- RED established the missing one-root state machine, immutable production
  configuration snapshot, serialized compile driver, exact source/currentness
  proofs, and deterministic reverse invalidation.
- The Task-3 state/driver/source/build selectors collect 238 tests and pass
  238. Fresh adjacent compiler/build/import/CLI/diagnostic selectors pass 426.
- The process-local mutex is covered in both directions: natural concurrent
  callers remain serialized, while a deterministic held-mutex control leaves
  state and queued work untouched and fails under the legacy boolean
  check/set mutation.
- Scoped `py_compile` and `git diff --check` are clean.
- Ordered preliminary reviews returned `STAGE8_TASK3_SPEC_APPROVED`, then
  `STAGE8_TASK3_QUALITY_APPROVED`.
- Ordered final exact-diff reviews returned
  `STAGE8_TASK3_SPEC_REAFFIRMED`, then
  `STAGE8_TASK3_QUALITY_REAFFIRMED`.

## Task 4: Capture The Production Request And Prove F1-F3

**Outcome:** Before diagnostics transport or navigation begins, the shared
production build seam exposes one exact normalized compile-request value and
the implementation proves the accepted compile tier, CLI parity, and latency
decision.

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `orchestrator/cli/commands/run.py` only if the unchanged dry-run
  command needs a test-visible pass-through for the shared captured value
- Modify: `tests/test_workflow_lisp_build_in_memory.py`
- Modify: `tests/test_workflow_lisp_lsp_compile_driver.py`
- Create: `tests/test_workflow_lisp_lsp_cli_parity.py`

`FrontendBuildRequest` and the value returned by
`build_manifest_io._resolve_request` are the production normalization owners.
The captured tuple belongs in `workflow_lisp/build.py` at the common seam
after request/configuration loading and before entry selection/input binding;
the LSP may consume it but must not define another normalizer.

**RED:**

- [x] Prove F1's four library-only modules invoke exactly one full Stage-3
      compile with `entry_workflow=null`; Stage 1 is neither imported nor
      called and no second phase starts.
- [x] For F2, first compare the exact 11-field normalized request tuple at the
      shared pre-entry-selection/input-binding seam, then compare the complete
      ordered post-`with_diagnostic_metadata` diagnostic tuple.
- [x] Cover F2 in both directions for extra/missing/replaced/reordered explicit
      source roots, every other request field, normalized loaded bundle value,
      raw span end, metadata, form path, and expansion order. Wording-only
      message/note changes remain non-identity.
- [x] Prove both the unchanged dry-run CLI and LSP receive the captured value
      from the same production owner and that the LSP cannot substitute
      workspace-root, lint, or lowering defaults.
- [x] Preserve F3's accepted 1.87-second evidence and add a guard proving it
      does not select Stage 1, a second publication phase, or caching.

**GREEN:**

- [x] Add one immutable production request-capture value at the exact shared
      seam after `_resolve_request` plus production manifest loading and before
      entry selection/input binding.
- [x] Expose that same value through the read-only build result so unchanged
      dry-run CLI and LSP observations compare without a test-only or LSP-only
      normalizer.
- [x] Fix LSP compile policy to `SHARED_CALLABLE` plus unchanged production
      lint/lowering defaults and reject editor overrides.
- [x] Enforce and record F1-F3 as a completed gate before any diagnostic
      transport or navigation handler exists.
- [x] Rerun build-core, compile-driver, production dry-run, diagnostic
      metadata, and CLI-parity regressions.
- [x] Obtain `STAGE8_TASK4_SPEC_APPROVED`, then
      `STAGE8_TASK4_QUALITY_APPROVED`.
- [x] Commit Task 4.

**Implementation record:** commit `1f24cca8`.

- RED established the missing production-owned 11-field compile-request
  capture and diagnostic-identity owner. The core slice had two intended
  request-capture failures while F1/F3 already proved the existing Stage-3
  route; the 29-case parity slice failed only on the two absent production
  surfaces.
- GREEN adds one frozen structural request value after production loaders and
  makes it the Stage-3 authority for both persistent CLI and read-only LSP
  paths. Post-seam language failures, including recursive imported-child
  selection rejection, retain the exact attempted capture.
- Real bare and ordered-explicit CLI/LSP pairs prove equal caller captures and
  exact production effective-root outcomes. A real malformed source proves
  equal nonempty post-metadata diagnostic identity; structural mutation
  controls cover every request/diagnostic field while excluding only
  message/note wording.
- F1 covers all four library modules with no Stage-1 alias or call. F3 covers
  two eligible generations with one fresh full Stage-3 compile apiece and no
  timing threshold, provisional phase, or cache reuse.
- Fresh Task-4/build/driver/CLI/diagnostic selectors collect 530 tests and pass
  530. Source/module/source-map adjacency passes 156.
- `py_compile` and scoped `git diff --check` are clean.
- Ordered preliminary reviews returned `STAGE8_TASK4_SPEC_APPROVED`, then
  `STAGE8_TASK4_QUALITY_APPROVED`.
- Ordered final exact-diff reviews returned
  `STAGE8_TASK4_SPEC_REAFFIRMED`, then
  `STAGE8_TASK4_QUALITY_REAFFIRMED`.

## Task 5: Translate Coordinates And Own Diagnostic Contributions

**Outcome:** Pure protocol-independent translators and state transitions
produce exact current-generation diagnostic contributions without introducing
stdio, watcher, or navigation behavior.

**Files:**

- Create: `orchestrator/lsp/coordinates.py`
- Create: `orchestrator/lsp/diagnostics.py`
- Modify: `orchestrator/lsp/state.py`
- Modify: `orchestrator/lsp/compile_driver.py`
- Create: `tests/test_workflow_lisp_lsp_coordinates.py`
- Create: `tests/test_workflow_lisp_lsp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_lsp_state.py`
- Modify: `tests/test_workflow_lisp_lsp_compile_driver.py`

**RED:**

- [x] Cover 1-based raw spans to 0-based UTF-16 ranges, including non-BMP
      characters and line boundaries.
- [x] Cover code/severity/source/data translation from raw full diagnostics;
      notes remain data and tests never freeze their phrasing.
- [x] Cover structured expansion call/definition spans as related information;
      no message/note parsing. Explicitly omit an expansion-frame related
      location when that frame's path is unreadable.
- [x] Cover synthetic/unreadable paths on the triggering entry at `(0,0)` with
      raw coordinates retained.
- [x] Cover deterministic multi-entry aggregation/deduplication, ownership
      replacement, target clearing, and accepted-generation stamping.
- [x] Cover dirty/pending/stale/late-result contribution rules.
- [x] Cover an internal compile-driver exception as a state failure that
      invalidates navigation but preserves every previously published
      contribution byte-for-byte; it is not a synthetic language diagnostic.

**GREEN:**

- [x] Implement pure coordinate and diagnostic translators over raw compiler
      objects and exact accepted-generation source text.
- [x] Preserve the full structured parity metadata in `Diagnostic.data`.
- [x] Aggregate per-entry contribution maps by the complete parity tuple;
      choose the lexicographically first entry only as the display
      representative for wording-only duplicates.
- [x] Implement contribution ownership/replacement/clearing as explicit
      Task-3 state transitions with no protocol dependency.
- [x] Rerun coordinate, diagnostics, state/driver, compiler-diagnostic, and
      Task-4 parity regressions.
- [x] Obtain `STAGE8_TASK5_SPEC_APPROVED`, then
      `STAGE8_TASK5_QUALITY_APPROVED`.
- [x] Commit Task 5.

**Implementation record:** commit `d50ac678`.

- RED established missing coordinate/diagnostic translators and the missing
  single contribution-ownership contract in state/driver. A real production
  warning also exposed the compiler's `warn` severity spelling.
- GREEN converts validated compiler spans to UTF-16 ranges, preserves the
  complete structured diagnostic identity/data, and owns exactly one
  immutable contribution tuple per compile entry. Current success and language
  errors atomically republish the sorted old/new target union; dirty, pending,
  observation, and server-error transitions preserve prior ownership; close
  and configuration staleness retract it.
- The driver reuses the exact disk snapshots from its post-build currentness
  proof for translation. Injected success/error tests prove one compiler trace
  read plus one acceptance probe and no third translation read.
- Specification review found that compiler offsets follow the reader's
  universal-newline parser view. A real-reader CRLF RED then established the
  defect; the translator now validates offsets against normalized parser text
  while deriving editor UTF-16 positions from the exact accepted disk line.
- Quality RED hardened direct contribution construction against nested alias
  mutation, rejects duplicate canonical owner spellings, and makes local file
  URI parsing absolute, component-preserving, and strict-UTF-8. State remains
  structurally admissible under principle 29; no author-facing type taxonomy
  or Task-6 transport behavior was added.
- Fresh Task-5/build/driver/CLI/diagnostic/source-map selectors pass 451 tests.
  `py_compile`, focused collection, and scoped whitespace checks are clean.
- Corrected-diff specification review returned
  `STAGE8_TASK5_SPEC_APPROVED`; final exact-diff review returned
  `STAGE8_TASK5_SPEC_REAFFIRMED`.
- The bounded translation and state/driver quality reviews returned
  `TASK5_TRANSLATION_QUALITY_REAFFIRMED` and
  `TASK5_STATE_DRIVER_QUALITY_REAFFIRMED`, jointly satisfying the ordered
  `STAGE8_TASK5_QUALITY_APPROVED` gate.

## Task 6: Expose A Frame-Clean Stdio And Watcher Transport

**Outcome:** A real stdio process maps protocol events onto the already
reviewed state/compile/diagnostic transitions, publishes only current
contributions, and keeps stdout frame-clean.

**Files:**

- Create: `orchestrator/lsp/server.py`
- Create: `orchestrator/lsp/__main__.py`
- Modify: `orchestrator/lsp/state.py`
- Modify: `orchestrator/lsp/compile_driver.py`
- Modify: `pyproject.toml` only for the minimal optional transport dependency
- Create: `tests/test_workflow_lisp_lsp_stdio.py`

**RED:**

- [x] Drive real framed initialize/open/change/save/close traffic and prove
      stdout contains only valid protocol frames.
- [x] Drive client-supported watched-file registration plus framed
      create/change/delete notifications and prove they trigger the same eager
      revision/invalidation transitions defined by Task 3.
- [x] Cover open/save compilation, dirty change invalidation, close cleanup,
      current contribution publication/clearing, and the one latched stale
      notice.
- [x] Cover internal error logging through stderr or `window/logMessage`, not
      a synthetic language diagnostic; previously published contributions
      remain byte-for-byte owned while navigation is invalidated.
- [x] Prove unsupported initialization options and root shapes fail before
      state creation or compile.

**GREEN:**

- [x] Wire protocol events only to the reviewed Task-3 through Task-5
      transitions; do not duplicate compile, freshness, request, coordinate,
      diagnostic, or contribution logic in the server.
- [x] Register watched-file capability only when supported and treat delivered
      events as an eager optimization, never currentness authority.
- [x] Keep all server and compiler logging off stdout.
- [x] Keep pygls isolated under the `lsp` extra; default dependencies remain
      unchanged.
- [x] Rerun stdio, state/driver, diagnostics, request-parity, and packaging
      regressions.
- [x] Obtain `STAGE8_TASK6_SPEC_APPROVED`, then
      `STAGE8_TASK6_QUALITY_APPROVED`, and commit.

**Implementation record:** commit `1825a13e`.

- RED first established the absent optional transport dependency and stdio
  entrypoint, then the missing framed lifecycle, dynamic watcher,
  publication, root/configuration-staleness, and internal-error behavior.
- GREEN adds one synchronous pygls 2.x controller that consumes only the
  reviewed immutable state, compile-driver, and diagnostic-contribution
  transitions. Full-sync `didChange` remains invalidation-only; `didSave`
  ignores notification text and reprobes disk authority.
- Dynamic registration is conditional on client support and deterministically
  covers workspace `.orc` files plus the exact frozen non-source
  configuration paths. Delivered watcher kinds never become authority: every
  admitted event routes through the same raw-byte disk probe, while unrelated
  paths are ignored.
- Workspace-root or frozen-configuration drift latches through the existing
  state transition, clears owned publications, and emits exactly one paired
  `window/showMessage` / `window/logMessage` restart notice. Internal compiler
  exceptions log without synthesizing language diagnostics and preserve the
  prior contribution tuple.
- `sys.stdout` is redirected away from ordinary writes after the binary
  transport stream is captured, leaving stdout exclusively for framed LSP
  traffic. pygls remains confined to `project.optional-dependencies.lsp`;
  default imports load neither pygls nor lsprotocol.
- Fresh stdio collection found 14 cases and all 14 passed. The combined
  state/driver/coordinates/diagnostics/CLI-parity/stdio gate passed 263 tests
  under xdist. `py_compile` and scoped whitespace checks were clean.
- Ordered independent review returned `STAGE8_TASK6_SPEC_APPROVED`, followed
  by `STAGE8_TASK6_QUALITY_APPROVED`. The adapter adds no language taxonomy or
  nominal authoring obligation under principle 29, and Task-8 navigation
  remains absent.

## Task 7: Preserve Exact Direct-Authored Callee Provenance

**Outcome:** After the diagnostics/F1-F3 gate passes, direct
workflow/procedure calls may carry the exact authored callee datum span; every
generated, WCC, expanded, or ambiguous call remains unindexed with `None`.

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: exact expression traversal/specialization/copy owners discovered by
  the RED inventory
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Create: `tests/test_workflow_lisp_authored_callee_span.py`

**RED:**

- [x] Prove current call nodes expose only whole-form spans.
- [x] Cover exact list-head procedure datum and explicit `(call ...)` callee
      datum spans.
- [x] Cover specialization, traversal, cloning, and replace preservation.
- [x] Cover `None` through WCC reconstruction and every
      generated/expanded/ambiguous construction.
- [x] Prove no whole-form or same-spelled argument fallback is accepted.

**GREEN:**

- [x] Add optional `authored_callee_span` metadata to `CallExpr` and
      `ProcedureCallExpr`.
- [x] Populate it only from an unambiguous direct-authored syntax datum.
- [x] Preserve the value byte-for-byte through every ordinary copy path.
- [x] Set/retain `None` on WCC, generated, expanded, and ambiguous paths.
- [x] Make no type, effect, lowering, runtime, or identity judgment change.
- [x] Rerun expression, macro, specialization, WCC, source-map, build, and
      procedure/workflow call regressions.
- [x] Obtain `STAGE8_TASK7_SPEC_APPROVED`, then
      `STAGE8_TASK7_QUALITY_APPROVED`, and commit.

**Implementation record:** commit `87c115e0`.

- RED proved both call-node variants retained only their whole-form span;
  five direct/provenance cases failed while the three generated/WCC absence
  controls already held.
- GREEN adds optional, equality-neutral metadata
  (`field(default=None, compare=False)`) so provenance cannot alter call
  identity, hashing, type, effect, lowering, or runtime judgments.
- The two direct elaborators capture only the exact procedure list-head or
  explicit workflow-call callee datum. Any expansion stack on the call or
  callee, or any compiler-introduced callee identity, produces `None`; no
  token/name search or whole-form fallback exists.
- Ordinary dataclass replacement, caller-syntax cloning, expression traversal,
  shallow/deep copy, and parametric specialization preserve the exact value.
  Both WCC reconstruction sites explicitly write `None`, while all other
  generated construction inherits the fail-closed default.
- Focused collection found 8 cases and all 8 passed. The combined
  expression/macro/procedure/source-map/build/workflow/WCC gate passed 802
  tests under xdist; `py_compile` and scoped whitespace checks were clean.
- Ordered independent review returned `STAGE8_TASK7_SPEC_APPROVED`, followed
  by `STAGE8_TASK7_QUALITY_APPROVED`. This is opt-in compiler provenance under
  principle 29, not a nominal authoring requirement.

## Task 8: Add The Closed Current-Snapshot Navigation Surface

**Outcome:** Go-to-definition, document symbols, and completion answer only
the accepted matrix and only from a current successful compiler snapshot.

**Files:**

- Create: `orchestrator/lsp/navigation.py`
- Modify: `orchestrator/lsp/server.py`
- Modify: `orchestrator/lsp/state.py`
- Modify: `orchestrator/lsp/compile_driver.py`
- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Create: `tests/test_workflow_lisp_lsp_navigation.py`
- Modify: `tests/test_workflow_lisp_lsp_compile_driver.py`

**RED:**

- [x] Cover direct local/imported/stdlib procedure and workflow call heads with
      non-null exact provenance.
- [x] Cover cursor outside the exact callee span, `None` provenance,
      generated/WCC calls, fields, types, prompts, externs, and all other
      unsupported shapes returning null.
- [x] Cover symbols containing exactly `defmodule`, `defproc`, and
      `defworkflow` in authored source order.
- [x] Cover deterministic completion of visible local/imported callable names
      plus compiler-registry form heads.
- [x] Add Principle-29 negative controls: no nominal taxonomy requirement,
      nominal filter, or server-inferred structural filter.
- [x] Cover clean-current success and null/no items for dirty, pending,
      invalidated, configuration-stale, language-failed, server-failed,
      superseded, closed, and unassociated documents.
- [x] Cover a notification-free source/configuration change detected by the
      mandatory pre-response recheck.

**GREEN:**

- [x] Build navigation indices exclusively from compiler call provenance,
      definitions, catalogs/import scopes, and form registries.
- [x] Index only non-null exact `authored_callee_span`.
- [x] Implement the closed result matrix without parsing source in the LSP.
- [x] Recheck complete source/config/root currentness before every response;
      atomically invalidate and schedule before returning null on drift.
- [x] Apply visibility/registry membership only to completion.
- [x] Rerun navigation, state/driver, stdio, provenance, compiler catalog,
      import, and registry regressions.
- [x] Obtain `STAGE8_TASK8_SPEC_APPROVED`, then
      `STAGE8_TASK8_QUALITY_APPROVED`, and commit.

**Implementation record:** commit `5cc389e2`.

- RED first left 13 currentness/transport cases failing after the pure index
  slice passed, then an independent specification review exposed a legal
  same-canonical-name collision between the procedure and workflow
  namespaces. The added two-direction regression reproduced the wrong target
  before the namespace fix.
- GREEN freezes the exact successful postflight source text alongside the
  accepted revision vector, builds pure indices only from Stage-3 artifacts,
  and keys definition targets by callable kind plus canonical compiler
  identity. UTF-16 coordinates and target locations use the frozen text; the
  server never rereads or parses source to answer navigation.
- Every handler passes through the compile driver's mandatory configuration,
  builtin-root, and complete source-vector recheck. Drift transitions retain
  their scheduling/publication effects, the current request returns null, and
  any queued clean generation runs through the existing serialized driver.
- Completion is the deterministic union of compiler-visible local/imported
  procedure/workflow spellings and the complete public form registry. It has
  no cursor-type input, nominal taxonomy, nominal filter, or inferred
  structural filter, preserving principle 29.
- Fresh collection found 39 navigation cases. The final combined
  navigation/state/driver/stdio/provenance/module/procedure/workflow gate
  passed 525 tests under xdist; `py_compile` and scoped whitespace checks were
  clean.
- Ordered independent review returned `STAGE8_TASK8_SPEC_APPROVED`, followed
  by `STAGE8_TASK8_QUALITY_APPROVED`.

## Task 9: Package V1, Run End-To-End Evidence, Update Docs, And Close Stage 8

**Outcome:** Real CLI/server/integration evidence proves the accepted v1 and
the roadmap truthfully records Stage 8 complete without starting deferred
successors.

**Files:**

- Modify: `pyproject.toml`
- Create: `docs/workflow_lisp_language_server_setup.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md` at exact Stage-8 routing hunks only
- Modify: `docs/design/README.md`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/design/workflow_lisp_language_server.md`
- Modify: this plan
- Modify: `tests/test_workflow_lisp_lsp_cli_parity.py`
- Create: `tests/test_workflow_lisp_lsp_integration.py`
- Create: `tests/test_workflow_lisp_lsp_e2e.py`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Modify:
  `tests/fixtures/workflow_lisp/procedure_identity_retirement/old/typed_frontend_ast.json`
- Modify:
  `tests/fixtures/workflow_lisp/procedure_identity_retirement/new/typed_frontend_ast.json`
- Modify:
  `tests/fixtures/workflow_lisp/procedure_identity_retirement/old/build_manifest.json`
- Modify:
  `tests/fixtures/workflow_lisp/procedure_identity_retirement/new/build_manifest.json`
- Modify:
  `tests/fixtures/workflow_lisp/procedure_identity_retirement/valid_internal_retirement.json`

**Verification:**

- [x] Run `pytest --collect-only -q tests/test_workflow_lisp_lsp_*.py`.
- [x] Rerun the already-gated Task-4 F1/F2/F3 selectors unchanged as part of
      the closing evidence; navigation must never precede their first passing
      gate.
- [x] Run a real stdio client against a fixture workspace with real stdlib and
      recursive imported-bundle paths, diagnostics, navigation, save/
      invalidation, close cleanup, concurrency, and zero workspace writes.
- [x] Run the real server as an editor would against a real repository
      Workflow Lisp entry and record the required frontend-adjacent E2E check.
- [x] Prove default dependencies are unchanged and the `lsp` extra installs
      and launches cleanly.
- [x] Run documentation routing/link/status tests, including
      `tests/test_workflow_lisp_drain_roadmap_routing.py`.
- [x] Launch the exact broad non-security suite from the Execution Contract in
      tmux and wait for completion.
- [x] Record fresh counts and distinguish any established external failures
      without weakening selectors or repairing out-of-scope code.
- [x] Update docs from observed behavior only: accepted design implemented,
      setup limitations exact, Stage 8 complete, P1-P5 and all unrelated
      successor proposals still deferred/parked unless separately activated.
- [x] Verify the drafting guide is coherent and current for the implemented
      tooling; make only routing/usage corrections supported by observed v1.
- [x] Obtain `STAGE8_FINAL_SPEC_APPROVED`, then
      `STAGE8_FINAL_QUALITY_APPROVED`.
- [x] Patch-stage only exact Task-9-owned hunks, verify every protected
      concurrent hunk is absent, and commit the reviewed closing tree.

**Closing verification record:**

- Fresh LSP collection found 307 cases. The unchanged Task-4 F1/F2/F3
  selectors passed 36 cases, and the CLI-parity plus new real stdio/repository
  integration set separately passed 36 cases.
- The real fixture covers recursive imported-bundle compilation through
  builtin `std/context`, local/imported procedure and workflow navigation,
  diagnostics, dirty/save/close transitions, dependency break/repair, rapid
  latest-save serialization, direct builtin-stdlib navigation, and an exact
  before/after workspace tree with no `.orchestrate` creation.
- The repository E2E launches `python -m orchestrator.lsp` against
  `workflows/examples/cycle_guard_demo.orc`, proves clean symbols/completion,
  unsupported/null definition and dirty/null navigation, and preserves source,
  command-manifest, and build-tree digests.
- Wheel RED proved the compiler-owned `.orc` stdlib was absent from the
  distribution. The package-data fix ships exactly `context.orc`, `drain.orc`,
  `phase.orc`, and `resource.orc`; a clean temporary wheel install resolved
  the `[lsp]` metadata, imported from site-packages, found that installed
  stdlib, and launched frame-clean outside the source checkout. Default
  dependencies remain unchanged.
- The setup guide, frontend/drafting contracts, capability/design routers,
  completed roadmap status, and non-selected successor handoff are updated
  from observed v1 behavior. Local link audit is clean, and the complete
  roadmap-routing module passes all 52 cases.
- The first broad comparison exposed three new Stage-8-owned stale-oracle
  failures in addition to two retained external failures. Task 1's accepted
  exact-byte reader makes the same-path compiler evidence byte-only, so its
  existing migration oracle now requires positive `read_bytes` and exactly
  zero `read_text`/`open` calls. Task 7's accepted authored-callee provenance
  added one exact `authored_callee_span` to each retirement typed-AST fixture;
  the two fixtures, their build manifests, and the valid retirement record's
  content-addressed bindings are refreshed without excluding that semantic
  field. The repaired retirement/migration/source-read adjacency passes 506
  cases with 5 skips.
- A second broad attempt began between the fixture-byte refresh and its
  content-addressed binding refresh, so its retirement-validation cascade is
  discarded as a non-comparable in-flight snapshot. The final stable exact
  broad command completed with 8,214 passed, 21 skipped, and only the two exact
  retained external failures:
  `test_provider_valid_output_bundle_overrides_raw_nonzero_exit` and
  `test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys`.
  Both are present in the frozen pre-Stage-8 baseline; Stage 8 introduces zero
  remaining failure identities.
- Ordered preliminary closing reviews found no issues and returned
  `STAGE8_FINAL_SPEC_APPROVED`, followed by
  `STAGE8_FINAL_QUALITY_APPROVED`. The same reviewers then reaffirmed the
  exact 19-path staged tree as `STAGE8_FINAL_SPEC_REAFFIRMED`, followed by
  `STAGE8_FINAL_QUALITY_REAFFIRMED`. The reviewed closing tree committed at
  `c69c33a1`; its cached `docs/index.md` diff excluded the owner-authored
  Evolution-roadmap hunk, which remained unstaged.

**Task 9 implementation record:** commit `c69c33a1`.

### Post-completion LSP controller correction

A delayed independent quality review found that the real pygls handlers called
the synchronous compile drain inline. A blocked production Stage-3 build
therefore blocked the event-loop thread, so later save/change/close
notifications could not reach the accepted coalescing and stale-result
machinery. The same review found that `orchestrator.lsp.server` was imported
before the stdio entry point redirected ordinary stdout, leaving import-time
output able to contaminate the protocol stream. Stage 8 reopened fail-closed
for these two correctness defects.

The correction uses a controller/worker split without changing compiler or
navigation semantics:

- the controller thread prepares an opaque-ticketed compile and later
  adjudicates its completion;
- the worker executes only the prepared blocking build;
- the real server owns one event-loop compile pump and delegates that blocking
  execution through `asyncio.to_thread`;
- canceled or superseded tickets are discarded, wrong or duplicate
  completions fail closed, and the pump's final queue recheck closes the
  schedule/exit lost-wakeup window; and
- the stdio entry point imports the server only after redirecting ordinary
  stdout to stderr.

TDD established all three missing behaviors first: a save storm and a close
were not observed while a controlled build was blocked, and import-time
stdout preceded the first protocol frame. The corrected transport observes
save/close before releasing that build, coalesces the save storm to one latest
follow-up compile, discards the closed generation, and remains frame-clean.
Split-phase unit controls additionally cover close/reopen generation aliasing,
wrong and duplicate tickets, and a stale completion with newer queued work.
The first final quality pass then found that the fixture's worker-finished
marker could precede controller adjudication by one event-loop turn; the
affected navigation assertion now polls for the authoritative snapshot while
retaining single-shot null assertions for genuinely pending and closed state.
Its exact selector and the complete LSP selector pass after that test-only
correction.

Fresh correction verification:

- the focused driver/stdio/navigation/integration set passed 163 cases;
- the complete LSP selector passed 314 cases;
- the unchanged F1/F2/F3 selectors passed 36 cases;
- roadmap routing passed 52 cases;
- retirement/migration/source-read adjacency passed 506 cases with 5 skips;
- `py_compile` and the scoped diff check are clean; and
- the exact closing non-security broad command passed 8,225 cases with 21
  skips and only the two retained external failures already named above.

Ordered preliminary correction reviews returned
`STAGE8_CORRECTION_SPEC_APPROVED`, then
`STAGE8_CORRECTION_QUALITY_APPROVED`. Final exact-diff reaffirmations are
pending. The correction implementation commit is pending.

## Stage 8 Completion Gate

Stage 8 is complete only when:

- Tasks 1-9 are committed after ordered reviews;
- compiler reading preserves legacy parser judgments while exact raw bytes
  become the only source revision identity;
- persistent, LSP, and recursive import consumers share one read-only core and
  have canonical in-memory parity;
- the server owns exactly one root plus the exact builtin-stdlib exception,
  and source/config/root drift fails closed;
- diagnostics and navigation obey current generation/source/config ownership;
- the closed navigation matrix contains no server parsing or nominal filter;
- F1, F2, and F3 are satisfied exactly;
- real stdio and repository E2E checks pass with zero read-only workspace
  writes and frame-clean stdout;
- the focused and broad non-security gates pass or contain only truthfully
  recorded pre-existing external failures; and
- ordered final specification and quality reviews approve the closing tree.

After this gate, consult only the active execution-sequence roadmap. The
parked evolution roadmap and related experiments are not selectors. Prompt
calculus, E0, parsimony candidates, or any other successor may begin only
where the authoritative roadmap explicitly schedules it and after its own
required design/review gate.
