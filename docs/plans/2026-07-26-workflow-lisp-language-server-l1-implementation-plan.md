# Workflow Lisp Language Server L1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every behavior change. Each task
> receives an independent specification-compliance review and then a distinct
> implementation-quality review before commit.

**Goal:** Implement the accepted L1 authored-symbol and callable-signature
surface: compiler-owned original-syntax projections for ten document-symbol
kinds and namespace-preserving procedure/workflow/form completion rows with
resolved signature details.

**Architecture:** Add one small compiler-owned projection over each
`ResolvedModuleSource.syntax_module` and cross-check every direct authored row
against the successful compiled module. The existing LSP navigation index
consumes that projection plus compiler import scopes and catalogs; the server
only maps closed internal rows to LSP protocol kinds/ranges/details. Existing
snapshot freshness and null/empty response authority remains unchanged.

**Tech stack:** Python 3.11+, immutable dataclasses, Workflow Lisp Stage 3,
existing syntax/catalog/import-scope/type/effect renderers, pygls/lsprotocol,
pytest/pytest-xdist, real JSON-RPC over stdio.

**Accepted design:** commit `c79cee2c`, with:

- `docs/design/workflow_lisp_language_server.md`, SHA-256
  `a71bb39caee04c3f0f40460f345677772864d910ee5bd15208ef43951a9789d1`;
- `docs/design/workflow_lisp_frontend_specification.md`, SHA-256
  `8a6c53a91a8bb25402c3f12c2863a89f5d527a21d1ea675d1964872ad3100b47`;
  and
- ordered design reviews `L1_DESIGN_SPEC_APPROVED` then
  `L1_DESIGN_QUALITY_APPROVED`.

**Status:** accepted for execution after ordered independent
`L1_PLAN_SPEC_APPROVED` then `L1_PLAN_QUALITY_APPROVED`.

---

## Scope And Deliberate Cost

This plan implements only:

- immutable compiler-owned authored rows with exactly
  `(kind, name, definition_span, selection_span, source_ordinal)`;
- the closed kinds `module`, `procedure`, `workflow`, `enum`, `path`, `record`,
  `union`, `schema`, `resource`, and `transition`;
- exact crosschecks against the successful compiled module, with
  expanded/generated/specialized shapes excluded;
- LSP document-symbol ranges and exact name-token selection ranges for those
  ten kinds;
- distinct procedure, workflow, and form completion rows, including same-label
  coexistence;
- local authored labels and exact imported
  `ModuleImportScope.procedure_bindings` /
  `.workflow_bindings` keys;
- details rendered only from existing `ProcedureSignature` /
  `WorkflowSignature`, `render_type_ref`, and `render_effect_set`;
- the existing complete/current `isIncomplete=false` response; and
- existing null/empty behavior for every non-current or unavailable snapshot.

Do not add source-text parsing, a second syntax classifier, type-token
definition, hover, references, rename, signature inference, snippets,
insertion rewriting, type-directed/nominal filtering, partial completion,
last-good callable reuse, dirty-buffer analysis, recovery, overlays, caching,
incrementality, or runtime debugging. L2 alone owns recovery-safe incomplete
form completion.

The deliberate cost is fail-closed index construction: one malformed or
ambiguous authored projection suppresses navigation for that request instead
of returning a best-effort subset. L1 also rebuilds the pure navigation index
from the already accepted compile result on each current request, as v1 does
today. This keeps compiler authority and freshness simple, but makes partial
symbol recovery and cached navigation indexes harder later; those require
their own accepted design rather than an L1 shortcut.

## Governing Authorities

Read before implementation:

- `AGENTS.md`
- `docs/index.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/design/workflow_lisp_language_server.md`, especially
  "Accepted L1 Authored Symbols And Callable Signatures Amendment"
- `docs/design/workflow_lisp_frontend_specification.md` §76.1 and
  "Accepted L1 Authored Symbol And Completion Compatibility"
- `docs/design/workflow_language_design_principles.md`, especially principle 29
- `docs/workflow_lisp_language_server_setup.md`
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- `docs/plans/2026-07-25-workflow-lisp-language-server-implementation-plan.md`
- `docs/plans/2026-07-26-workflow-lisp-language-server-l0-implementation-plan.md`

If this plan conflicts with the accepted design, correct the plan and repeat
ordered plan reviews. Do not reinterpret the accepted contract in code.

## Disjoint Concurrent Ownership

L1 production ownership is limited to:

- new `orchestrator/workflow_lisp/authored_symbols.py`;
- `orchestrator/lsp/navigation.py`; and
- `orchestrator/lsp/server.py`.

`orchestrator/workflow_lisp/syntax.py` is shared with Q2. L1 Task 1 executes
first and owns only the exact `ModuleDirective.name_span` carrier hunk; it
patch-stages and commits that hunk before Q2 Task 1 may begin. Q2 then
reconciles against the landed L1 carrier and owns its separate target/version
and prompt-slot syntax hunks. No L1 and Q2 implementer may edit or stage this
file concurrently.

L1 test/fixture ownership is limited to:

- new `tests/test_workflow_lisp_authored_symbols.py`;
- new
  `tests/fixtures/workflow_lisp/modules/valid/lsp_l1_symbols/lsp_l1_symbols/entry.orc`;
- only the Task-1 `frontend_ast.json` module-name-span contract hunk in shared
  `tests/test_workflow_lisp_build_artifacts.py`, committed before Q2 begins;
- `tests/test_workflow_lisp_lsp_navigation.py`;
- `tests/test_workflow_lisp_lsp_stdio.py`;
- `tests/test_workflow_lisp_lsp_integration.py`; and
- `tests/test_workflow_lisp_lsp_e2e.py`.

Q2 owns prompt declarations/contracts, provider prompting, output-position
validation, executor wiring, Q2 fixtures/tests, and its own consumer migration.
L1 must not edit Q2 production or test paths. L1 does not modify
`orchestrator/lsp/state.py` or `orchestrator/lsp/compile_driver.py`: their
successful-snapshot preflight remains the sole freshness/availability
authority.

The following status/routing files are shared with Q2. Their closure order is
fixed: L1 Task 5 commits its L1-only closure first while preserving Q2's
accepted-plan/execution status; Q2 Task 7 then commits its Q2-only closure
while preserving completed L1 status:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/index.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- `tests/test_workflow_lisp_drain_roadmap_routing.py`

Patch-stage only L1-owned hunks in those files. Do not edit
`docs/design/workflow_lisp_prompt_calculus.md`.

## Protected Working Tree And Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve every pre-existing user, owner, experiment,
provider, runtime, state, report, prompt, and security/provider-isolation
change. In particular, `docs/index.md`, `docs/design/README.md`,
`docs/capability_status_matrix.md`, and the roadmap-routing test already carry
concurrent work; inspect their exact diffs before editing and patch-stage only
the L1 hunk. Never use `git add .`, `git add -A`, destructive checkout/reset,
or broad cleanup.

Execute with a fresh implementation subagent per task. For every task:

1. refresh `git status --short` and record the task-owned paths;
2. for behavior-changing Tasks 1–3, write the smallest behavioral test first;
3. run it and confirm RED for the intended missing behavior, not a setup error;
4. implement only the selected behavior; Tasks 4–5 instead add GREEN
   integration/regression evidence over the reviewed landed implementation;
5. rerun the narrow selector and adjacent non-security regressions;
6. run `pytest --collect-only -q` for every created or renamed test module;
7. inspect the exact task diff;
8. dispatch an independent specification-compliance reviewer;
9. correct findings through a new RED/GREEN cycle and repeat spec review until
   approved;
10. dispatch a distinct implementation-quality reviewer;
11. correct findings through TDD and repeat ordered spec then quality review;
12. stage only the exact reviewed task paths;
13. run `git diff --cached --check`, inspect `git diff --cached --name-status`
    and the complete staged diff; and
14. commit without post-review edits.

Tasks 4 and 5 are integration/regression and closure gates over behavior landed
by Tasks 1–3. Do not manufacture a RED failure after that behavior exists:
their newly added regression/E2E assertions must begin GREEN against the
reviewed landed implementation. If either exposes a genuine missing
requirement, route the defect back to its owning source task and use a fresh
RED/GREEN cycle there before repeating the later gate.

Do not run a broad suite per task. Use narrow selectors first and run the one
closing broad non-security suite only in Task 5. Use the `tmux` skill for the
real-stdio selector if it exceeds one minute and for the closing broad suite.
Keep the installed/default review provider and model; wait rather than
substituting a faster model.

Security, safety, secrets, and provider-isolation work is excluded. Do not
modify those paths, run their tests, review their design, or repair their
failures under L1.

## File And Responsibility Map

Compiler projection:

- Create `orchestrator/workflow_lisp/authored_symbols.py` for the immutable row,
  direct original-syntax candidate extraction, compiled-definition
  crosschecks, generated-shape exclusion, and deterministic source ordering.
- Modify `orchestrator/workflow_lisp/syntax.py` only to retain the exact
  `defmodule` name-token span on `ModuleDirective`; every other admitted form
  already retains its original `SyntaxIdentifier.span` in
  `WorkflowLispSyntaxModule.forms`.
- Modify one exact hunk in `tests/test_workflow_lisp_build_artifacts.py` to
  prove the intentional additive `frontend_ast.json` contract change:
  `module_directive` gains `name_span`, all other pre-L1 fields remain
  byte-identical, and the content-addressed artifact digest changes only as a
  consequence of those bytes. The build artifact is observational and is not
  a runtime/load/resume schema.

LSP index and protocol:

- Modify `orchestrator/lsp/navigation.py` to consume compiler rows, preserve
  definition/selection spans, retain callable namespaces/canonical targets,
  render catalog-owned signature details, and sort deterministically.
- Modify `orchestrator/lsp/server.py` only for the fixed `SymbolKind` /
  `CompletionItemKind` presentation, separate ranges, and completion detail.
  Its `_current_navigation` preflight and internal-error boundary remain the
  only request path.

Evidence:

- Create `tests/test_workflow_lisp_authored_symbols.py` for projection and
  crosscheck behavior.
- Create one compiled L1 fixture at
  `tests/fixtures/workflow_lisp/modules/valid/lsp_l1_symbols/lsp_l1_symbols/entry.orc`
  containing all ten directly authored kinds, zero/one/multi-parameter
  callables, nested resolved types, and empty/nonempty declared procedure
  effects.
- Extend `tests/test_workflow_lisp_lsp_navigation.py` for pure index and direct
  server presentation.
- Extend `tests/test_workflow_lisp_lsp_stdio.py` for JSON protocol shape and
  index-failure containment.
- Extend `tests/test_workflow_lisp_lsp_integration.py` for real stdio imported
  labels/signatures.
- Extend `tests/test_workflow_lisp_lsp_e2e.py` for one repository-real read-only
  L1 session.

Documentation/status:

- Modify `docs/design/workflow_lisp_language_server.md`.
- Modify exact L1 status text in
  `docs/design/workflow_lisp_frontend_specification.md`.
- Modify `docs/workflow_lisp_language_server_setup.md`.
- Modify one exact L1 paragraph in `docs/lisp_workflow_drafting_guide.md`.
- Modify exact L1 rows/hunks in `docs/capability_status_matrix.md`,
  `docs/design/README.md`, `docs/index.md`, and the active roadmap.
- Modify `tests/test_workflow_lisp_drain_roadmap_routing.py` before those
  routing docs.
- Update this plan factually only after implementation/reviews complete.

---

## Preimplementation Plan And Routing Gate

Before Task 1:

- [ ] Obtain independent `L1_PLAN_SPEC_APPROVED` against this exact plan and
      accepted design.
- [ ] Resolve every specification finding in this plan and repeat review.
- [ ] Obtain a distinct `L1_PLAN_QUALITY_APPROVED`.
- [ ] Record accepted-for-execution status and both ordered tokens without
      changing task scope.
- [ ] Patch-stage only this new plan and exact L1 routing hunks selected by the
      parent roadmap executor.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py \
    -k 'language_quality or language_server or post_stage_8'
  ```

- [ ] Obtain final ordered specification then quality reaffirmation against
      the exact staged plan/status/routing bytes. Commit those exact reviewed
      bytes without post-review edits before any production change.
- [ ] At that landed plan-gate commit and before any L1 or Q2 production edit,
      run the active roadmap's exact broad non-security command in tmux.
      Record `HEAD`, `HEAD^{tree}`, the dirty-tree inventory, collection/pass/
      failure/skip totals, the exact collected-node identity set, and exact
      failing node IDs as the fresh pre-L1 control. The same run may serve as
      Q2's pre-stage control only when Q2 binds the identical commit/tree and
      no L1/Q2 production edit preceded it.

## Task 1: Compiler-Owned Original-Syntax Projection

**Outcome:** One compiler-owned pure projection emits and validates exact
authored rows for all ten admitted definition kinds without source reads,
expanded-syntax provenance, or LSP classification.

**Files:**

- Create: `orchestrator/workflow_lisp/authored_symbols.py`
- Modify: `orchestrator/workflow_lisp/syntax.py`
- Create: `tests/test_workflow_lisp_authored_symbols.py`
- Create:
  `tests/fixtures/workflow_lisp/modules/valid/lsp_l1_symbols/lsp_l1_symbols/entry.orc`
- Modify exact L1 artifact-contract hunk:
  `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Write a RED compiled-fixture test named
      `test_projection_emits_all_ten_direct_kinds_with_exact_name_spans` that
      expects, in cross-kind source order:

  ```text
  module, enum, path, schema, record, union, resource, transition,
  procedure, workflow
  ```

  Assert each row has exactly `kind`, `name`, `definition_span`,
  `selection_span`, and `source_ordinal`; slicing accepted text by the two
  offsets must yield the full authored form and exact authored name token
  respectively.

- [ ] Run that test and confirm RED because
      `orchestrator.workflow_lisp.authored_symbols` does not exist.
- [ ] Add `ModuleDirective.name_span: SourceSpan`, populated only from
      `_parse_module_directive`'s already validated `SyntaxIdentifier.span`.
      Do not add name-span copies to semantic definitions or make a second
      source read.
- [ ] Before production edits, freeze the current canonical
      `frontend_ast.json` bytes and artifact digest for the fixture. Write a RED
      test that expects the exact additive nested `SourceSpan` at
      `module_directive.name_span`. After implementation, remove only that
      nested field from the observed projection and require byte equality with
      the frozen pre-L1 projection; require the new content-addressed artifact
      digest to differ from the frozen digest. This artifact evolution is
      intentional; do not add a runtime schema, compatibility decoder, or
      non-persisted side channel.
- [ ] Before editing `syntax.py`, confirm no Q2 implementer owns it. Patch-stage
      only the `ModuleDirective.name_span` carrier hunk, and commit Task 1
      before Q2 Task 1 begins.
- [ ] Add immutable `AuthoredSymbolProjectionRow` and
      `AuthoredSymbolProjectionError(ValueError)` plus:

  ```python
  def project_authored_symbols(
      resolved_source: ResolvedModuleSource,
      compiled_result: Stage3CompileResult,
  ) -> tuple[AuthoredSymbolProjectionRow, ...]:
      ...
  ```

  Inspect only `resolved_source.syntax_module.module_directive` and
  `.forms`. Map exact direct heads `defproc`, `defworkflow`, `defenum`,
  `defpath`, `defrecord`, `defunion`, `defschema`, `defresource`, and
  `deftransition` to their fixed internal kind, and take the selection span
  from the already retained second `SyntaxIdentifier`. Assign ordinals from
  the original module declaration/form sequence.

- [ ] Build same-kind compiled candidates from:

  - `compiled_result.procedure_catalog.definitions_by_name`;
  - `compiled_result.workflow_catalog.definitions_by_name`;
  - `compiled_result.module.definitions`;
  - `compiled_result.module.schemas`;
  - `compiled_result.module.resources`; and
  - `compiled_result.module.transitions`.

  Validate the `module` row separately: the authored directive name,
  `resolved_source.module_name`, and `compiled_result.module.module_name` must
  be the same compiled module identity. The compiler has no separate compiled
  `defmodule` full-span candidate, so no invented module-span comparison is
  allowed. For the other nine kinds, normalize canonical callable names only
  for comparison with the direct authored name and require exactly one
  same-kind/name/full-span match. Never accept a same-spelled row of another
  kind or a whole-form/name-span fallback.

- [ ] Write RED parameterized tests named
      `test_projection_fails_closed_on_compiled_crosscheck_mismatch` for
      missing, duplicate, kind mismatch, name mismatch, and exact full-span
      mismatch, plus a separate module-identity mismatch, using immutable
      replacements or a narrow candidate helper. Assert one projection error
      and no partial rows.
- [ ] Write RED selection-span validation tests for wrong source path,
      zero/negative or reversed range, and a name-token span outside its
      definition span. Require same-path, non-empty ordered containment inside
      the definition span before emitting any row; one invalid selection span
      fails the entire projection.
- [ ] Write RED tests proving expansion-only definitions, specialized
      procedures/workflows, and generated local procedures do not create rows
      or make an otherwise valid direct projection fail. The original syntax
      module is positive authority: compiled-only generated shapes are not
      reverse-projected.
- [ ] Implement only those crosschecks and exclusions. Sort final rows by
      `(definition_span.start.offset, source_ordinal)`.
- [ ] Run:

  ```bash
  pytest --collect-only -q tests/test_workflow_lisp_authored_symbols.py
  pytest -q tests/test_workflow_lisp_authored_symbols.py \
    tests/test_workflow_lisp_modules.py \
    tests/test_workflow_lisp_definitions.py \
    tests/test_workflow_lisp_procedures.py
  pytest -q tests/test_workflow_lisp_build_artifacts.py \
    -k 'frontend_ast_module_name_span'
  ```

- [ ] Obtain ordered independent Task-1 specification then quality approval,
      stage the three wholly owned paths plus only the reviewed
      `ModuleDirective.name_span` hunk in shared `syntax.py` and the reviewed
      artifact-contract hunk in shared `test_workflow_lisp_build_artifacts.py`,
      and commit.

## Task 2: Ten-Kind Document Symbols And Exact Selection Ranges

**Outcome:** The navigation index and protocol expose all ten compiler-proven
authored kinds in source order, with full definition ranges and exact name-token
selection ranges.

**Files:**

- Modify: `orchestrator/lsp/navigation.py`
- Modify: `orchestrator/lsp/server.py`
- Modify: `tests/test_workflow_lisp_lsp_navigation.py`
- Modify: `tests/test_workflow_lisp_lsp_stdio.py`

- [ ] Replace the existing v1 symbol test with RED assertions for the complete
      ten-kind fixture, cross-kind source order, and distinct full/selection
      spans. Keep a negative test proving the LSP performs no file read or
      text parsing while constructing the index.
- [ ] Add RED server/protocol tests for this exact presentation:

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

- [ ] Change `NavigationSymbol` to retain `definition_span`,
      `selection_span`, and `source_ordinal`. In `build_navigation_index`, call
      `project_authored_symbols` once per compiled graph module and delete the
      old typed-procedure/workflow symbol reconstruction.
- [ ] Keep the existing definition-link traversal unchanged. Do not broaden
      go-to-definition beyond exact direct procedure/workflow call heads.
- [ ] Map document-symbol `range` from `definition_span` and
      `selectionRange` from `selection_span`, using only the accepted frozen
      text already supplied by the snapshot. Coordinate translation failure
      for either range returns null for the whole request.
- [ ] Add a RED negative test that a projection crosscheck failure is logged as
      one internal error and yields document-symbol null rather than a partial
      list or a language diagnostic.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_authored_symbols.py \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_stdio.py
  ```

- [ ] Obtain ordered independent Task-2 specification then quality approval,
      stage the four exact paths, and commit.

## Task 3: Namespace-Preserving Callable Signature Completion

**Outcome:** Procedure, workflow, and form rows remain distinct, preserve every
compiler-admitted visible spelling, and render details solely from resolved
compiler signatures.

**Files:**

- Modify: `orchestrator/lsp/navigation.py`
- Modify: `orchestrator/lsp/server.py`
- Modify: `tests/test_workflow_lisp_lsp_navigation.py`
- Modify: `tests/test_workflow_lisp_lsp_stdio.py`
- Modify:
  `tests/fixtures/workflow_lisp/modules/valid/lsp_l1_symbols/lsp_l1_symbols/entry.orc`

- [ ] Write RED tests that one procedure, workflow, and monkeypatched
      registered form with the same label produce three rows in kind order,
      never one `callable` row. Assert the internal kinds are exactly
      `procedure`, `workflow`, and `form`.
- [ ] Write RED imported-callable tests against the existing `callables`
      fixture for every exact key already admitted by
      `ModuleImportScope.procedure_bindings` and `.workflow_bindings`:
      `alias.member`, `module/member`, and `:only` unqualified spellings.
      Assert no label is obtained by stripping a catalog key or inventing an
      alias.
- [ ] Extend `NavigationCompletion` with `kind`, `canonical_target`, and
      `detail`. Produce local callable rows only from direct authored projection
      rows; produce imported rows from the exact import-scope mapping keys; use
      each `ModuleMemberBinding.canonical_name` only for catalog signature
      lookup and sorting. Keep form label/canonical target equal to the exact
      registered head.
- [ ] Sort rows by `(label, kind_rank, canonical_target)`, with ranks
      procedure, workflow, form. Do not deduplicate across namespaces.
- [ ] Add RED detail tests for zero, one, and multiple parameters; nested
      resolved `Optional`/`List`/`Map` or ref types; empty and nonempty declared
      procedure effects; and workflow returns. Render exactly:

  ```text
  procedure (<name>: <render_type_ref>, ...) -> <render_type_ref> effects <render_effect_set>
  workflow (<name>: <render_type_ref>, ...) -> <render_type_ref>
  form
  ```

  Use `ProcedureSignature.params`, `.return_type_ref`, and
  `.declared_effects`, plus `WorkflowSignature.params` and `.return_type_ref`.
  Form detail is exactly `form`.

- [ ] Add a negative control where direct/transitive inferred procedure effects
      differ from declared effects. Assert only
      `ProcedureSignature.declared_effects` appears. Never infer or display
      workflow effects.
- [ ] Map procedure/workflow rows to
      `CompletionItemKind.Function`, form rows to
      `CompletionItemKind.Keyword`, include the compiler-rendered `detail`, and
      retain `isIncomplete=false`.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_modules.py \
    tests/test_workflow_lisp_effects.py
  ```

- [ ] Obtain ordered independent Task-3 specification then quality approval,
      stage the five exact paths, and commit.

## Task 4: Preserve Snapshot Freshness And Fail-Closed Availability

**Outcome:** L1 enriches only a current successful navigation index; every
implemented dirty/pending/invalidated/failed/stale/closed/unassociated response
remains byte-for-byte compatible.

**Files:**

- Modify: `tests/test_workflow_lisp_lsp_navigation.py`
- Modify: `tests/test_workflow_lisp_lsp_stdio.py`
- Modify: `tests/test_workflow_lisp_lsp_integration.py`
- Do not modify production in this gate. If integration exposes a genuine
  missing presentation requirement, return it to Task 2 or 3 and complete a
  fresh RED/GREEN/review cycle there; do not edit state or compile-driver code.

- [ ] Extend the existing parameterized non-current snapshot test to assert all
      three responses together:

  - definition is null;
  - document symbols are null; and
  - completion is a complete empty list (`isIncomplete=false`, no items).

  Cover dirty, pending, dependency-invalidated, language-failed, server-failed,
  superseded, closed, configuration-stale, source/configuration-stale, and
  unassociated documents.

- [ ] Add both-direction currentness tests: a current successful snapshot
      returns the full L1 symbol/completion rows, while the same retained build
      under each stale state returns no last-good L1 row.
- [ ] Add an index-construction-failure test proving one ambiguous/mismatched
      compiler projection crosses the existing internal-error boundary and
      returns null/empty without publishing a language diagnostic, changing
      state, or writing a workspace file.
- [ ] Add a real stdio integration test with imported procedure/workflow labels
      and details. Assert exact namespace coexistence and order, then make the
      open document dirty and assert null/empty behavior through JSON-RPC.
- [ ] Confirm `orchestrator/lsp/state.py` and
      `orchestrator/lsp/compile_driver.py` have no L1 diff.
- [ ] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py
  ```

- [ ] Obtain ordered independent Task-4 specification then quality approval,
      stage only the exact changed paths, and commit.

## Task 5: Repository-Real Stdio Gate And Serialized Closure

**Outcome:** A repository-real editor session proves L1 over stdio without
workspace writes, and status/routing truthfully advances from L1 to L2.

**Files:**

- Modify: `tests/test_workflow_lisp_lsp_e2e.py`
- Modify: `docs/design/workflow_lisp_language_server.md`
- Modify exact L1 status only:
  `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/workflow_lisp_language_server_setup.md`
- Modify exact L1 editor paragraph only:
  `docs/lisp_workflow_drafting_guide.md`
- Modify exact L1 row only: `docs/capability_status_matrix.md`
- Modify exact L1 row only: `docs/design/README.md`
- Modify exact L1 routing only: `docs/index.md`
- Modify exact L1 stage/sequence only:
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- Modify exact L1 routing expectations only:
  `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify factually after all gates:
  `docs/plans/2026-07-26-workflow-lisp-language-server-l1-implementation-plan.md`

- [ ] Add a repository-real stdio regression/E2E test using an existing
      checked-in `.orc` workflow/module that has authored type definitions plus
      procedure/workflow callables. Confirm it begins GREEN against the
      reviewed Tasks 1–3 implementation and assert:

  - exact full and selection ranges for at least one non-callable type and one
    callable;
  - procedure/workflow/form protocol kinds and compiler-rendered details;
  - no diagnostics on the valid source;
  - dirty-buffer null/empty behavior; and
  - unchanged source/configuration bytes and unchanged
    `.orchestrate/build` tree digest.

- [ ] Run the real-stdio E2E in tmux if needed:

  ```bash
  pytest -q tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_lsp_integration.py
  ```

- [ ] Run the complete focused L1 selector:

  ```bash
  pytest -q tests/test_workflow_lisp_authored_symbols.py \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_modules.py \
    tests/test_workflow_lisp_definitions.py \
    tests/test_workflow_lisp_procedures.py \
    tests/test_workflow_lisp_effects.py
  pytest -q tests/test_workflow_lisp_build_artifacts.py \
    -k 'frontend_ast_module_name_span'
  ```

- [ ] Before documentation edits, write RED routing expectations that L1 is
      implemented/complete and L2's design-amendment/review gate is next. No L2
      design is accepted yet. Then update the exact shared status/routing hunks
      and rerun:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py \
    -k 'language_quality or language_server or post_stage_8'
  ```

- [ ] Update the setup guide to describe the shipped ten symbol kinds,
      namespace-preserving completion, signature details, and unchanged
      freshness/null behavior. Do not document L2 partial completion as
      shipped.
- [ ] Update the drafting guide's editor paragraph from its v1-only
      module/procedure/workflow symbol and generic completion description to
      the shipped L1 ten-kind symbols and namespace-preserving callable
      signatures. Keep L2 recovery completion and every later surface
      explicitly deferred.
- [ ] In tmux, run the one closing broad non-security suite:

  ```bash
  pytest -q -n 16 --dist=worksteal \
    --ignore=tests/test_at61_at62_wait_for_path_safety.py \
    --ignore=tests/test_cli_safety.py \
    --ignore=tests/test_execution_safety.py \
    --ignore=tests/test_provider_isolation_attestation.py \
    --ignore=tests/test_provider_isolation_backend.py \
    --ignore=tests/test_provider_isolation_backend_identity_negatives.py \
    --ignore=tests/test_provider_isolation_bundle_broker.py \
    --ignore=tests/test_provider_isolation_candidate.py \
    --ignore=tests/test_provider_isolation_controller_lifecycle.py \
    --ignore=tests/test_provider_isolation_environment.py \
    --ignore=tests/test_provider_isolation_environment_cli.py \
    --ignore=tests/test_provider_isolation_execution.py \
    --ignore=tests/test_provider_isolation_network_preflight.py \
    --ignore=tests/test_provider_isolation_policy.py \
    --ignore=tests/test_provider_isolation_runtime_authority.py \
    --ignore=tests/test_provider_isolation_schema_resources.py \
    --ignore=tests/test_provider_isolation_workflow_continuation.py \
    --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
    --ignore=tests/test_provider_launch_shim.py \
    --ignore=tests/test_secrets.py \
    --ignore=tests/test_workflow_provider_isolation_integration.py \
    -k 'not security and not secret and not isolation and not safety'
  ```

  Compare like-for-like with the recorded pre-L1 control: use the same
  authoritative command and exact outcomes on the stable-node intersection.
  Enumerate every added, removed, or changed node identity; classify L1-owned
  additions/changes against the ordered reviewed task evidence and any
  interleaved Q2-owned additions/changes against Q2's reviewed evidence rather
  than silently folding them into the pre-L1 totals. Classify unrelated deltas
  without repairing excluded or ambient work.

- [ ] Obtain one final ordered specification review of the committed Tasks 1–4
      plus the exact Task-5 E2E/docs/routing diff, then a distinct quality
      review. Resolve findings with TDD and repeat in order.
- [ ] Refresh the dirty-tree inventory. Patch-stage only L1-owned hunks, run
      `git diff --cached --check`, inspect the complete staged diff, and commit
      the reviewed L1-only E2E/docs/routing closure. This post-review commit
      releases the shared routing paths for Q2 Task 7; preserve Q2's accepted
      implementation-plan/execution status exactly, do not mark Q2 complete,
      and do not select Q3.
- [ ] In a separate plan-only factual commit, record exact task hashes,
      the pre-L1 control binding, focused/routing/broad outcomes,
      like-for-like unrelated-failure classification, and final review tokens.
      Do not combine source/tests/normative docs with this bookkeeping commit.

## Completion Contract

L1 is complete only when:

1. the compiler emits exactly the ten admitted direct authored kinds from
   original syntax, with exact full/name spans and deterministic source order;
2. the module row matches the authored directive, resolved source, and compiled
   module identity, while each of the other nine direct rows crosschecks
   exactly one same-kind/name/full-span compiled definition and
   expansion-only/generated/specialized shapes remain excluded;
3. document symbols use the fixed protocol mapping, full definition range, and
   exact name-token selection range without an LSP text parser or fallback;
4. procedure, workflow, and form completion rows remain distinct even at the
   same label, preserve exact local/import-scope spellings, and sort by the
   accepted tuple;
5. details come only from resolved compiler signatures, `render_type_ref`,
   declared procedure effects, and `render_effect_set`;
6. current success returns a complete list and every dirty, pending,
   invalidated, failed, stale, superseded, closed, or unassociated state keeps
   the implemented null/empty behavior;
7. projection/index failure returns no partial answer and does not become a
   language diagnostic;
8. compiler-projection, navigation, server, integration, and repository-real
   stdio evidence passes with no workspace writes;
9. the focused selector, routing selector, and one closing broad non-security
   suite are freshly run and truthfully classified;
10. every task and the final range receive ordered independent specification
    then quality approval before commit;
11. shared Q2/L1 routing files contain only serialized L1 closure hunks; and
12. capability/status docs mark L1 implemented only after all prior conditions
    hold and route next to the L2 design-amendment/review gate without claiming
    an accepted L2 design or shipped L2 behavior.
