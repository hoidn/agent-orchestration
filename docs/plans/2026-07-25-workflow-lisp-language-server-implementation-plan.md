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

**Status:** Accepted for execution after the selected list-traversal
interstage closes. Preliminary review returned `STAGE8_PLAN_SPEC_APPROVED`
then `STAGE8_PLAN_QUALITY_APPROVED`; the final exact plan/routing diff is the
commit candidate for ordered reaffirmation. Stage 8 implementation may begin
only after that interstage closes and this accepted plan plus its
routing/roadmap incorporation are committed.

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
- [ ] Patch-stage the exact plan/routing hunks, inspect the staged diff, and
      commit the accepted execution gate before implementation begins.

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
- Modify: exact reachable Stage-3 reread owners under
  `orchestrator/workflow_lisp/lowering/`
- Create: `tests/test_workflow_lisp_source_read_trace.py`
- Modify: existing reader/module/compiler tests only where they own adjacent
  compatibility assertions

**RED:**

- [ ] Prove `read_sexpr_file` currently cannot return ordered immutable read
      records or a canonical revision vector.
- [ ] Prove one invocation performs one `read_bytes` and derives unchanged
      raw bytes, strict UTF-8 text, and parser text from that one value.
- [ ] Cover LF/CRLF/bare-CR: parser text, AST, spans, and diagnostics match the
      legacy universal-newline reader while raw digests remain distinct.
- [ ] Cover exact editor equality in both directions; parser normalization
      must never make mismatched editor/disk text clean.
- [ ] Cover ordered `A(v1), B(v1), A(v1)` acceptance and
      `A(v1), B(v1), A(v2)` refusal.
- [ ] Cover distinct missing/unreadable sentinels and strict-decode failure.
- [ ] Prove every reachable Stage-3/import/lowering reread joins one explicit
      collector and Stage 1 has no trace path.

**GREEN:**

- [ ] Add immutable `SourceReadRecord` and `SourceReadTrace` in the reader.
- [ ] Canonicalize each path, assign a monotonic ordinal, call `read_bytes`
      once, hash exact bytes, strict-decode, then apply only
      `.replace("\r\n", "\n").replace("\r", "\n")` for parser text.
- [ ] Preserve existing read/parse failures after recording their sentinel or
      exact raw revision.
- [ ] Reject repeated-path digest disagreement immediately.
- [ ] Thread the optional collector explicitly through Stage 3, module graph
      resolution, and every reachable source reread. Use no module global.
- [ ] Rerun reader, parser, module graph, compiler, lowering, and source-map
      regressions.
- [ ] Obtain `STAGE8_TASK1_SPEC_APPROVED`, then
      `STAGE8_TASK1_QUALITY_APPROVED`, and commit.

## Task 2: Extract The Shared Read-Only In-Memory Build Core

**Outcome:** Persistent build, LSP, and recursive imported-manifest consumers
share one compile/select/reattach core; only `_emit` writes.

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Create: `tests/test_workflow_lisp_build_in_memory.py`
- Modify: existing build/import/source-map tests where they own parity

**RED:**

- [ ] Prove there is no public `build_frontend_bundle_in_memory` returning an
      immutable `FrontendInMemoryBuildResult`.
- [ ] Capture exact no-import and recursive imported-manifest parity for
      selection, loaded bundle, imported bindings, semantic/Core/executable
      values and canonical payloads, fingerprints, prospective paths, source
      map, configuration trace, and ordered `SourceReadTrace`.
- [ ] Prove current read-only selection creates/writes build paths.
- [ ] Cover authoritative supplied source-map payload when the prospective
      path is absent or contains conflicting bytes.
- [ ] Cover `source_map_payload=None` as the sole persisted-path compatibility
      fallback.
- [ ] Cover library-only `entry_workflow=null` and selected imported rows.

**GREEN:**

- [ ] Add the public read-only core around existing resolution, loaders,
      recursive compilation, entry compile, selection, and reattachment.
- [ ] Make `_select_and_reattach` a value-only operation: no mkdir, reads,
      writes, temporary emission, or write/delete workaround.
- [ ] Thread an optional authoritative `source_map_payload` through Core AST,
      loaded-bundle/runtime-plan, semantic IR, and reattachment seams.
- [ ] Keep `None` as the existing persisted-provenance fallback; a supplied
      mapping, including `{}`, may not inspect the provenance path.
- [ ] Make persistent `build_frontend_bundle` equal the read-only core followed
      by `_emit`; recursive imported `.orc` compilation calls only the core.
- [ ] Prove complete workspace trees are byte-identical before/after both
      read-only consumers and only `_emit` creates `.orchestrate/build`.
- [ ] Rerun build, import, source-map, Core AST, semantic IR, executable, and
      runtime-plan regressions.
- [ ] Obtain `STAGE8_TASK2_SPEC_APPROVED`, then
      `STAGE8_TASK2_QUALITY_APPROVED`, and commit.

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

- [ ] Cover one `rootUri`, one folder, and equivalent spellings of the same
      canonical root; reject zero/two roots and uncontained entries/explicit
      source roots before state or compilation.
- [ ] Accept traced `.orc` only under the workspace or exact frozen builtin
      stdlib root; reject every other external path.
- [ ] Prove workspace and builtin roots never enter caller `source_roots`
      unless the workspace was separately explicit.
- [ ] Cover immutable production-loaded provider/prompt/command/imported
      configuration and recursive imported closure.
- [ ] At initialization, preserve each unconfigured optional input as absent
      and reject every configured missing/unreadable input. Reject
      `lint_profile` or `lowering_route` in `initializationOptions`.
- [ ] After initialization, cover changed/missing/unreadable configuration
      and root-folder changes latching restart-required
      `configuration_stale`; byte reversion does not unlatch it.
- [ ] Cover clean `didOpen` against exact `raw_decoded_text`; mismatched editor
      text, missing/unreadable disk state, and strict-decode failure create
      dirty/unavailable state, schedule zero compiles, and expose no
      navigation snapshot.
- [ ] Cover serialized compiles, per-entry generations, debounce/coalescing,
      latest-generation acceptance, and late-result discard.
- [ ] Cover trusted `A -> B`, unrelated C negative control, closed B,
      missing/unreadable B, unknown-closure all-open invalidation, and
      `didClose` ownership cleanup.
- [ ] Cover a current language-error completion with a complete, consistent
      trace retaining its precise closure/vector; only incomplete or
      inconsistent error traces become closure-unknown.
- [ ] Cover the state transition for a delivered `.orc`
      create/change/delete observation and its eager invalidation result, with
      a reverse control proving such delivery is never required for
      correctness. Server capability registration belongs to Task 6.
- [ ] Cover mandatory post-compile and pre-request digest/config/root rechecks
      without watcher delivery.
- [ ] Prove library-only entries use exactly one Stage-3 compile and Stage 1
      is neither imported nor called.

**GREEN:**

- [ ] Canonicalize and freeze exactly one workspace root, the exact production
      builtin stdlib root, ordered explicit caller roots, fixed production
      lint/lowering defaults, and `SHARED_CALLABLE`.
- [ ] Freeze the complete configuration vector and implement the latched stale
      transition plus one restart-required notice.
- [ ] Keep initialization failure separate from post-initialization staleness,
      and expose no lint/lowering override in the initialization schema.
- [ ] Represent entry/open/dirty/pending/success/failure/closure-unknown state
      immutably enough that generation acceptance is atomic.
- [ ] Use one worker and one fresh `SourceReadTrace` per generation; call the
      read-only core exactly once.
- [ ] Derive successful closures only from internally consistent compiler
      traces; probes/watchers schedule but never become authority.
- [ ] Maintain trace/diagnostic-target reverse ownership and implement both
      precise and conservative invalidation rules, including precise
      trustworthy language-error closures.
- [ ] Expose one state/driver transition that Task 6 can call for delivered
      file-watch observations; it must use the same revision/invalidation
      authority as notification-free checks. Server capability registration
      belongs to Task 6.
- [ ] Rehash the complete source/configuration vector and builtin-root identity
      before acceptance and every later snapshot response.
- [ ] Rerun the new state/driver tests plus build/compiler/import regressions.
- [ ] Obtain `STAGE8_TASK3_SPEC_APPROVED`, then
      `STAGE8_TASK3_QUALITY_APPROVED`, and commit.

## Task 4: Capture The Production Request And Prove F1-F3

**Outcome:** Before diagnostics transport or navigation begins, the shared
production build seam exposes one exact normalized compile-request value and
the implementation proves the accepted compile tier, CLI parity, and latency
decision.

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/build_manifest_io.py`
- Modify: `orchestrator/cli/commands/run.py` only if the unchanged dry-run
  command needs a test-visible pass-through for the shared captured value
- Modify: `orchestrator/lsp/compile_driver.py`
- Modify: `tests/test_workflow_lisp_build_in_memory.py`
- Create: `tests/test_workflow_lisp_lsp_cli_parity.py`

`FrontendBuildRequest` and the value returned by
`build_manifest_io._resolve_request` are the production normalization owners.
The captured tuple belongs in `workflow_lisp/build.py` at the common seam
after request/configuration loading and before entry selection/input binding;
the LSP may consume it but must not define another normalizer.

**RED:**

- [ ] Prove F1's four library-only modules invoke exactly one full Stage-3
      compile with `entry_workflow=null`; Stage 1 is neither imported nor
      called and no second phase starts.
- [ ] For F2, first compare the exact 11-field normalized request tuple at the
      shared pre-entry-selection/input-binding seam, then compare the complete
      ordered post-`with_diagnostic_metadata` diagnostic tuple.
- [ ] Cover F2 in both directions for extra/missing/replaced/reordered explicit
      source roots, every other request field, normalized loaded bundle value,
      raw span end, metadata, form path, and expansion order. Wording-only
      message/note changes remain non-identity.
- [ ] Prove both the unchanged dry-run CLI and LSP receive the captured value
      from the same production owner and that the LSP cannot substitute
      workspace-root, lint, or lowering defaults.
- [ ] Preserve F3's accepted 1.87-second evidence and add a guard proving it
      does not select Stage 1, a second publication phase, or caching.

**GREEN:**

- [ ] Add one immutable production request-capture value at the exact shared
      seam after `_resolve_request` plus production manifest loading and before
      entry selection/input binding.
- [ ] Expose that same value through the read-only build result so unchanged
      dry-run CLI and LSP observations compare without a test-only or LSP-only
      normalizer.
- [ ] Fix LSP compile policy to `SHARED_CALLABLE` plus unchanged production
      lint/lowering defaults and reject editor overrides.
- [ ] Enforce and record F1-F3 as a completed gate before any diagnostic
      transport or navigation handler exists.
- [ ] Rerun build-core, compile-driver, production dry-run, diagnostic
      metadata, and CLI-parity regressions.
- [ ] Obtain `STAGE8_TASK4_SPEC_APPROVED`, then
      `STAGE8_TASK4_QUALITY_APPROVED`, and commit.

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

**RED:**

- [ ] Cover 1-based raw spans to 0-based UTF-16 ranges, including non-BMP
      characters and line boundaries.
- [ ] Cover code/severity/source/data translation from raw full diagnostics;
      notes remain data and tests never freeze their phrasing.
- [ ] Cover structured expansion call/definition spans as related information;
      no message/note parsing. Explicitly omit an expansion-frame related
      location when that frame's path is unreadable.
- [ ] Cover synthetic/unreadable paths on the triggering entry at `(0,0)` with
      raw coordinates retained.
- [ ] Cover deterministic multi-entry aggregation/deduplication, ownership
      replacement, target clearing, and accepted-generation stamping.
- [ ] Cover dirty/pending/stale/late-result contribution rules.
- [ ] Cover an internal compile-driver exception as a state failure that
      invalidates navigation but preserves every previously published
      contribution byte-for-byte; it is not a synthetic language diagnostic.

**GREEN:**

- [ ] Implement pure coordinate and diagnostic translators over raw compiler
      objects and exact accepted-generation source text.
- [ ] Preserve the full structured parity metadata in `Diagnostic.data`.
- [ ] Aggregate per-entry contribution maps by the complete parity tuple;
      choose the lexicographically first entry only as the display
      representative for wording-only duplicates.
- [ ] Implement contribution ownership/replacement/clearing as explicit
      Task-3 state transitions with no protocol dependency.
- [ ] Rerun coordinate, diagnostics, state/driver, compiler-diagnostic, and
      Task-4 parity regressions.
- [ ] Obtain `STAGE8_TASK5_SPEC_APPROVED`, then
      `STAGE8_TASK5_QUALITY_APPROVED`, and commit.

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

- [ ] Drive real framed initialize/open/change/save/close traffic and prove
      stdout contains only valid protocol frames.
- [ ] Drive client-supported watched-file registration plus framed
      create/change/delete notifications and prove they trigger the same eager
      revision/invalidation transitions defined by Task 3.
- [ ] Cover open/save compilation, dirty change invalidation, close cleanup,
      current contribution publication/clearing, and the one latched stale
      notice.
- [ ] Cover internal error logging through stderr or `window/logMessage`, not
      a synthetic language diagnostic; previously published contributions
      remain byte-for-byte owned while navigation is invalidated.
- [ ] Prove unsupported initialization options and root shapes fail before
      state creation or compile.

**GREEN:**

- [ ] Wire protocol events only to the reviewed Task-3 through Task-5
      transitions; do not duplicate compile, freshness, request, coordinate,
      diagnostic, or contribution logic in the server.
- [ ] Register watched-file capability only when supported and treat delivered
      events as an eager optimization, never currentness authority.
- [ ] Keep all server and compiler logging off stdout.
- [ ] Keep pygls isolated under the `lsp` extra; default dependencies remain
      unchanged.
- [ ] Rerun stdio, state/driver, diagnostics, request-parity, and packaging
      regressions.
- [ ] Obtain `STAGE8_TASK6_SPEC_APPROVED`, then
      `STAGE8_TASK6_QUALITY_APPROVED`, and commit.

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

- [ ] Prove current call nodes expose only whole-form spans.
- [ ] Cover exact list-head procedure datum and explicit `(call ...)` callee
      datum spans.
- [ ] Cover specialization, traversal, cloning, and replace preservation.
- [ ] Cover `None` through WCC reconstruction and every
      generated/expanded/ambiguous construction.
- [ ] Prove no whole-form or same-spelled argument fallback is accepted.

**GREEN:**

- [ ] Add optional `authored_callee_span` metadata to `CallExpr` and
      `ProcedureCallExpr`.
- [ ] Populate it only from an unambiguous direct-authored syntax datum.
- [ ] Preserve the value byte-for-byte through every ordinary copy path.
- [ ] Set/retain `None` on WCC, generated, expanded, and ambiguous paths.
- [ ] Make no type, effect, lowering, runtime, or identity judgment change.
- [ ] Rerun expression, macro, specialization, WCC, source-map, build, and
      procedure/workflow call regressions.
- [ ] Obtain `STAGE8_TASK7_SPEC_APPROVED`, then
      `STAGE8_TASK7_QUALITY_APPROVED`, and commit.

## Task 8: Add The Closed Current-Snapshot Navigation Surface

**Outcome:** Go-to-definition, document symbols, and completion answer only
the accepted matrix and only from a current successful compiler snapshot.

**Files:**

- Create: `orchestrator/lsp/navigation.py`
- Modify: `orchestrator/lsp/server.py`
- Modify: `orchestrator/lsp/state.py`
- Create: `tests/test_workflow_lisp_lsp_navigation.py`

**RED:**

- [ ] Cover direct local/imported/stdlib procedure and workflow call heads with
      non-null exact provenance.
- [ ] Cover cursor outside the exact callee span, `None` provenance,
      generated/WCC calls, fields, types, prompts, externs, and all other
      unsupported shapes returning null.
- [ ] Cover symbols containing exactly `defmodule`, `defproc`, and
      `defworkflow` in authored source order.
- [ ] Cover deterministic completion of visible local/imported callable names
      plus compiler-registry form heads.
- [ ] Add Principle-29 negative controls: no nominal taxonomy requirement,
      nominal filter, or server-inferred structural filter.
- [ ] Cover clean-current success and null/no items for dirty, pending,
      invalidated, configuration-stale, language-failed, server-failed,
      superseded, closed, and unassociated documents.
- [ ] Cover a notification-free source/configuration change detected by the
      mandatory pre-response recheck.

**GREEN:**

- [ ] Build navigation indices exclusively from compiler call provenance,
      definitions, catalogs/import scopes, and form registries.
- [ ] Index only non-null exact `authored_callee_span`.
- [ ] Implement the closed result matrix without parsing source in the LSP.
- [ ] Recheck complete source/config/root currentness before every response;
      atomically invalidate and schedule before returning null on drift.
- [ ] Apply visibility/registry membership only to completion.
- [ ] Rerun navigation, state/driver, stdio, provenance, compiler catalog,
      import, and registry regressions.
- [ ] Obtain `STAGE8_TASK8_SPEC_APPROVED`, then
      `STAGE8_TASK8_QUALITY_APPROVED`, and commit.

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

**Verification:**

- [ ] Run `pytest --collect-only -q tests/test_workflow_lisp_lsp_*.py`.
- [ ] Rerun the already-gated Task-4 F1/F2/F3 selectors unchanged as part of
      the closing evidence; navigation must never precede their first passing
      gate.
- [ ] Run a real stdio client against a fixture workspace with real stdlib and
      recursive imported-bundle paths, diagnostics, navigation, save/
      invalidation, close cleanup, concurrency, and zero workspace writes.
- [ ] Run the real server as an editor would against a real repository
      Workflow Lisp entry and record the required frontend-adjacent E2E check.
- [ ] Prove default dependencies are unchanged and the `lsp` extra installs
      and launches cleanly.
- [ ] Run documentation routing/link/status tests, including
      `tests/test_workflow_lisp_drain_roadmap_routing.py`.
- [ ] Launch the exact broad non-security suite from the Execution Contract in
      tmux and wait for completion.
- [ ] Record fresh counts and distinguish any established external failures
      without weakening selectors or repairing out-of-scope code.
- [ ] Update docs from observed behavior only: accepted design implemented,
      setup limitations exact, Stage 8 complete, P1-P5 and all unrelated
      successor proposals still deferred/parked unless separately activated.
- [ ] Verify the drafting guide is coherent and current for the implemented
      tooling; make only routing/usage corrections supported by observed v1.
- [ ] Obtain `STAGE8_FINAL_SPEC_APPROVED`, then
      `STAGE8_FINAL_QUALITY_APPROVED`.
- [ ] Patch-stage only exact Task-9-owned hunks, verify every protected
      concurrent hunk is absent, and commit the reviewed closing tree.

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
