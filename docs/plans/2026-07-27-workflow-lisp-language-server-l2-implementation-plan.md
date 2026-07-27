# Workflow Lisp Language Server L2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every behavior change. Each task
> receives an independent specification-compliance review followed by a
> distinct implementation-quality review before commit.

**Goal:** Implement the accepted L2 recovery-safe static completion surface:
current successful entries retain the full L1 callable-plus-form list, valid
open recovery states receive only one process-frozen form-registry list marked
incomplete, and every stale, unavailable, unassociated, malformed, or
index-failed state remains empty.

**Architecture:** Freeze target-neutral form completion rows once in
`initialize_compile_driver` after normal production initialization succeeds.
Require the successful navigation index to consume that same immutable tuple
instead of consulting the registry per build. Add one pure state classifier
for the exact recovery-eligible entry shapes, then give only the completion
handler a closed full/static/empty request path. Definition, symbols,
compilation, diagnostics, generations, and all other LSP behavior remain
unchanged.

**Tech stack:** Python 3.11+, immutable dataclasses and tuples, existing
Workflow Lisp form registry, existing LSP state/compile-driver/navigation
layers, pygls/lsprotocol, pytest/pytest-xdist, real JSON-RPC over stdio.

**Accepted design:** commit `7b5a15d2`, tree
`417526b6a1481539bd941341a60f463030f9a830`, after ordered independent
`L2_DESIGN_SPEC_APPROVED` then `L2_DESIGN_QUALITY_APPROVED`.

**Execution status:** complete. The plan was accepted after independent
`L2_PLAN_SPEC_APPROVED` followed by independent
`L2_PLAN_QUALITY_APPROVED`. Tasks 1–4 landed in order through `10e3ccc3`;
Task 5 completed the normative, authoring, routing, focused, and broad
non-security gates. Ordered `L2_FINAL_SPEC_APPROVED` then
`L2_FINAL_QUALITY_APPROVED` close this exact reviewed record. L3's separate
design-review gate is next, subject to its compile-path reentrancy entry
condition; Q3 remains independently at design review.

**Landed task record:**

| Task | Commit | Ordered task reviews |
| --- | --- | --- |
| 1 — frozen shared form catalog | `70b83f32` | `L2_TASK1_SPEC_APPROVED`, then `L2_TASK1_QUALITY_APPROVED` |
| 2 — closed recovery-state classifier | `b399c041` | `L2_TASK2_SPEC_APPROVED`, then `L2_TASK2_QUALITY_APPROVED` |
| 3 — full/static/empty protocol path | `ee213a43` | `L2_TASK3_SPEC_APPROVED`, then `L2_TASK3_QUALITY_APPROVED` |
| 4 — real stdio recovery-to-full gate | `10e3ccc3` | `L2_TASK4_SPEC_APPROVED`, then `L2_TASK4_QUALITY_APPROVED` |
| 5 — docs, routing, and closure | exact reviewed closure containing this record | `L2_FINAL_SPEC_APPROVED`, then `L2_FINAL_QUALITY_APPROVED` |

---

## Scope And Deliberate Cost

This plan implements only:

- one process-lifetime, target-neutral snapshot of
  `registered_form_heads(target_dsl_version=None)`, taken after successful
  production initialization;
- one immutable form-row projection shared by full and recovery completion;
- one exact recovery-state classifier for valid dirty-idle, current-pending,
  current-language-error, and current-server-error open entries;
- the existing complete L1 union with `isIncomplete=false` for a current,
  source/configuration-validated success whose navigation index builds;
- the exact frozen form rows with `isIncomplete=true` for recovery;
- exact empty `items=()` with `isIncomplete=false` for every closed branch;
  and
- focused state, driver, navigation, protocol, integration, and repository-real
  stdio evidence.

Do not add source parsing, partial ASTs, target inference, prefix/cursor/type
filtering, overlays, compile triggers, last-good callable reuse, navigation
caching, general compile caching, diagnostic recovery, hover, references,
rename, formatting, snippets, multi-root support, or any P1–P5 prerequisite.
Do not change definition or document-symbol availability.

The deliberate cost is target-neutral recovery help. A failed or dirty entry
has no accepted source-derived target authority, so L2 offers the same frozen
registry heads used by full completion rather than guessing a target-specific
subset. Making recovery completion target-aware later requires a new immutable
initialization contract. The strict malformed-state and index-failure empty
branches also make best-effort recovery harder, but preserve fail-closed
behavior and expose defects instead of hiding them.

## Governing Authorities

Read before implementation:

- `AGENTS.md`
- `docs/index.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/design/workflow_lisp_language_server.md`, especially
  "Accepted L2 Recovery-Safe Static Completion Amendment"
- `docs/design/workflow_lisp_frontend_specification.md` §76.1, especially
  "Accepted L2 Recovery-Safe Static Completion Compatibility"
- `docs/design/workflow_language_design_principles.md`, especially principle
  29
- `docs/workflow_lisp_language_server_setup.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- the completed L0 and L1 component plans

If this plan conflicts with the accepted design, correct the plan and repeat
ordered plan reviews. Do not reinterpret the accepted contract in code.

## Disjoint Concurrent Ownership

L2 production ownership is limited to:

- `orchestrator/lsp/state.py`;
- `orchestrator/lsp/compile_driver.py`;
- `orchestrator/lsp/navigation.py`; and
- `orchestrator/lsp/server.py`.

L2 test ownership is limited to:

- `tests/test_workflow_lisp_lsp_state.py`;
- `tests/test_workflow_lisp_lsp_compile_driver.py`;
- `tests/test_workflow_lisp_lsp_navigation.py`;
- `tests/test_workflow_lisp_lsp_stdio.py`;
- `tests/test_workflow_lisp_lsp_integration.py`; and
- `tests/test_workflow_lisp_lsp_e2e.py`.

Q3 owns prompt identity, prompt evidence schemas, provider-call identity,
observability/report comparison, Q3 design/spec files, and its own tests. L2
must not edit any Q3 production or test path. Q3 and L2 shared routing files
are serialized: this L2 plan gate and implementation closure commit before Q3
may write those routing paths.

Shared L2 closure paths are:

- `docs/design/workflow_lisp_language_server.md`;
- `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/workflow_lisp_language_server_setup.md`;
- `docs/lisp_workflow_drafting_guide.md`;
- `docs/capability_status_matrix.md`;
- `docs/design/README.md`;
- `docs/index.md`;
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`;
- `tests/test_workflow_lisp_drain_roadmap_routing.py`; and
- this plan.

Preserve all unrelated owner and concurrent changes in those files. Construct
review and commit snapshots from exact L2 hunks; never stage a whole shared
dirty path merely because L2 touches it.

## Protected Working Tree And Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve every pre-existing user, owner, experiment,
provider, runtime, report, and unrelated staged/unstaged change. Never use
`git add .`, `git add -A`, destructive checkout/reset, or broad cleanup.

Execute with a fresh implementation subagent per task. For every task:

1. refresh `git status --short` and identify exact task-owned paths;
2. write the smallest behavioral test first;
3. run it and confirm RED for the intended missing behavior;
4. implement only the selected task;
5. rerun the narrow selector and adjacent LSP regressions;
6. run `pytest --collect-only -q` for every new or renamed test module;
7. inspect the complete exact task diff;
8. obtain an independent specification-compliance review;
9. correct findings through a fresh RED/GREEN cycle and repeat spec review;
10. obtain a distinct implementation-quality review;
11. correct findings through TDD and repeat ordered spec then quality review;
12. construct an isolated exact-path commit snapshot;
13. run diff checks and inspect every reviewed byte; and
14. commit without post-review edits.

Task 4 is an integration/stdio gate over Tasks 1–3. Its assertions should begin
GREEN. If it exposes missing behavior, return the defect to its owning task and
complete a fresh TDD and review cycle there.

Run narrow selectors per task. Use the `tmux` skill for commands expected to
exceed one minute and for the closing broad suite. Wait for the installed
review agents; do not substitute a faster model.

All security, safety, secrets, and provider-isolation modules remain excluded
from this roadmap and its verification. Do not modify, run, review, or repair
those paths under L2.

## File And Responsibility Map

Frozen catalog:

- `orchestrator/lsp/navigation.py` owns validation/projection of exact form
  heads into immutable `NavigationCompletion` rows and requires those rows
  when building a successful navigation index.
- `orchestrator/lsp/compile_driver.py` captures the registry exactly once
  after successful initialization and retains the tuple for the driver
  lifetime.

State classification:

- `orchestrator/lsp/state.py` owns a pure, filesystem-free closed classifier
  over one associated open entry. It validates the whole admitted state shape
  and returns only `static-incomplete` or `empty` when no externally validated
  current success is supplied.

Protocol request:

- `orchestrator/lsp/server.py` performs the existing configuration/source
  preflight, distinguishes source-current success from recovery, refuses
  static fallback after index-construction failure, and maps the selected rows
  to the existing LSP protocol shapes.

Evidence:

- state tests prove exact positive and negative classifier rows;
- driver/navigation tests prove capture timing, immutability, and shared rows;
- stdio/integration tests prove exact protocol shape and no stale callable;
- one repository-real E2E proves recovery-static to full replacement without
  changing definition or document-symbol freshness.

---

## Preimplementation Plan And Routing Gate

Before Task 1:

- [x] Obtain independent `L2_PLAN_SPEC_APPROVED` against this exact plan and
      the accepted design.
- [x] Resolve every specification finding in this plan and repeat spec review.
- [x] Obtain distinct `L2_PLAN_QUALITY_APPROVED`.
- [x] Record accepted-for-execution status and both ordered tokens without
      changing scope.
- [x] Add the exact plan route to the active roadmap, docs index, design router,
      capability matrix, and routing test while preserving current L1 runtime
      status.
- [x] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [x] Obtain final ordered specification then quality reaffirmation against
      the exact plan/status/routing snapshot.
- [x] Commit those exact reviewed bytes before production changes.
- [x] Capture a fresh pre-L2 focused control:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py
  ```

  Record the plan-gate `HEAD`, tree, totals, and any exact failures in this
  plan before Task 1.

### Pre-L2 Focused Control

Captured before Task 1:

- `HEAD`: `60edd53744d2aad48cbc467ec326e072a67f0738`
- tree: `2d694804a6cf66605aea707c9509841e7094e796`
- selector result: **283 passed in 79.09s**, with zero failures, errors, or
  skips
- dirty-tree inventory: 301 `git status --short` rows already present in the
  shared workspace (`250 ??`, `1 D`, `35 M`, `15 MM`), normalized SHA-256
  `3d92f2b2f8bee9ee06d7ca59f3e12df8ced2e70e231e4bdc60fd4012c8c2f0cd`
- L2 production paths had no unstaged worktree diff against this `HEAD`;
  unrelated index/worktree state remains protected and is not part of the
  control.

## Task 1: Freeze One Shared Form Completion Catalog

**Outcome:** Successful initialization captures one immutable target-neutral
form-row tuple, and every full navigation index consumes that tuple instead of
calling the registry.

**Files:**

- Modify: `orchestrator/lsp/navigation.py`
- Modify: `orchestrator/lsp/compile_driver.py`
- Modify only to pass the frozen tuple into the existing full-index path:
  `orchestrator/lsp/server.py`
- Modify: `tests/test_workflow_lisp_lsp_navigation.py`
- Modify: `tests/test_workflow_lisp_lsp_compile_driver.py`

- [x] Write RED navigation tests for a pure helper that accepts only a tuple of
      unique lexicographically sorted non-empty heads and returns exact
      immutable rows:

  ```text
  label=head
  kind=form
  canonical_target=head
  detail=form
  ```

  Duplicate, unsorted, empty, non-string, or non-tuple input fails closed.
- [x] Write RED tests that `build_navigation_index` requires the frozen tuple,
      uses it for every module, and never calls `registered_form_heads`.
- [x] Write RED driver tests proving the registry is read exactly once after
      normal production initialization succeeds, is not read when
      initialization fails, and later registry mutation cannot change the
      retained tuple.
- [x] Add an immutable driver field for the tuple. In
      `initialize_compile_driver`, load and validate production configuration
      first, then call `registered_form_heads(target_dsl_version=None)` once
      and project it through the pure navigation helper.
- [x] Remove the registry import/call from `build_navigation_index`; require
      the exact frozen rows as an explicit keyword-only input.
- [x] Update all direct navigation-index callers and fixtures to pass one
      explicit frozen tuple. In the production server's existing full
      navigation path, pass the tuple retained by its initialized driver.
      Do not otherwise change request selection in Task 1 and do not add a
      compatibility default that rereads the registry.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_stdio.py
  ```

- [x] Obtain ordered Task-1 specification then quality approval and commit only
      the five exact changed paths. Task-1 `HEAD` must keep the existing full
      completion request green before Task 2 begins.

## Task 2: Closed Recovery-State Classifier

**Outcome:** One pure classifier admits only the exact recovery shapes and
fails every contradictory or unavailable state to empty.

**Files:**

- Modify: `orchestrator/lsp/state.py`
- Modify: `tests/test_workflow_lisp_lsp_state.py`

- [x] Write a RED parameterized positive matrix for:

  - dirty + idle + no pending + no accepted snapshot;
  - clean + pending + `pending_generation == generation` + no accepted
    snapshot;
  - clean + language error + no pending + no accepted snapshot; and
  - clean + server error + no pending + no accepted snapshot.

  Each entry must be associated, open, have a coherent readable disk/editor
  shape, and live under non-stale configuration.
- [x] Include dependency-invalidated and superseded fixtures through their
      normal dirty-idle or current-pending shapes rather than inventing new
      status values.
- [x] Write RED negative tests for configuration stale, unavailable,
      unassociated, closed, clean-idle, success, unknown status, missing or
      non-current pending generation, pending with an accepted snapshot,
      recovery status with an accepted snapshot, contradictory disk/editor
      state, and malformed field values.
- [x] Implement one filesystem-free helper returning only
      `static-incomplete` or `empty`. It must not inspect a compile result,
      navigation index, registry, source text, or last-good snapshot.
- [x] Preserve every existing state transition and
      `current_navigation_snapshot`; no compile scheduling, generation,
      contribution, or diagnostic behavior changes in Task 2.
- [x] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_lsp_state.py
  ```

- [x] Obtain ordered Task-2 specification then quality approval and commit only
      the two exact paths.

## Task 3: Wire The Full / Static-Incomplete / Empty Protocol Path

**Outcome:** Completion selects the exact protocol branch after existing
currentness checks, while definition and document symbols remain unchanged.

**Files:**

- Modify: `orchestrator/lsp/server.py`
- Modify as required by explicit frozen-row carriage:
  `orchestrator/lsp/navigation.py`
- Modify: `tests/test_workflow_lisp_lsp_navigation.py`
- Modify: `tests/test_workflow_lisp_lsp_stdio.py`

- [x] Write RED server tests that:

  - current validated success returns the full L1 procedure/workflow/form union
    with `isIncomplete=false`;
  - every valid recovery state returns exactly the frozen form rows with
    `CompletionItemKind.Keyword`, `detail="form"`, `sortText=head`, and
    `isIncomplete=true`;
  - recovery contains no procedure/workflow label, canonical target, signature,
    import binding, or prior-index row;
  - configuration-stale, unavailable, unassociated, closed, clean-idle, and
    malformed states return `items=()` with `isIncomplete=false`; and
  - a current successful snapshot whose navigation index raises returns empty
    and never falls back to static rows.

- [x] Add a RED frozen-snapshot test: mutate the live form registry after
      initialization and prove both full and recovery responses retain the
      original rows.
- [x] Refactor completion only. Reuse the driver's existing configuration and
      source-currentness preflight and transition-effect handling. Capture the
      recovery classification at the single-writer request boundary before a
      synchronous test drain may accept a later generation.
- [x] If the preflight yields a current snapshot, build the index with the
      driver's frozen rows. Catch the existing index-construction errors, log
      once, and return the exact empty response.
- [x] If no current snapshot exists, use only Task 2's classifier. Return the
      driver's frozen rows for `static-incomplete`; otherwise return empty.
- [x] Keep `_current_navigation`, definition, and document-symbol handlers on
      their existing successful-snapshot-only path. Do not share recovery
      behavior with them.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py
  ```

- [x] Obtain ordered Task-3 specification then quality approval and commit the
      exact reviewed paths.

## Task 4: Real Stdio Recovery-To-Full Transition Gate

**Outcome:** Real JSON-RPC proves static recovery help is provisional and is
replaced by the full compiler-owned list after a current successful compile.

**Files:**

- Modify: `tests/test_workflow_lisp_lsp_integration.py`
- Modify: `tests/test_workflow_lisp_lsp_e2e.py`
- Modify only if a genuine Task-3 defect is found: the owning Task-3 production
  file and focused test, followed by a fresh Task-3 TDD/review cycle.

- [x] Add a real stdio integration case that opens a checked-in `.orc` source,
      makes it dirty, requests completion, and observes only the exact frozen
      form rows with `isIncomplete=true`.
- [x] In the same session, save coherent source, wait for the current compile,
      request completion again, and observe the full L1 callable-plus-form
      union with `isIncomplete=false`.
- [x] Assert definition and document symbols remain null during recovery and
      become available only after current success.
- [x] Add a language-error or server-error stdio direction proving static
      recovery contains no callable retained from the earlier success.
- [x] Assert the workspace byte snapshot is unchanged except for the
      deliberately authored test save and the server creates no artifacts or
      run state.
- [x] Run:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_lsp_stdio.py
  ```

- [x] Obtain ordered Task-4 specification then quality approval and commit only
      the exact reviewed test paths unless a defect was routed back through
      Task 3.

## Task 5: Documentation, Broad Verification, And Serialized Closure

**Outcome:** All routing and authoring surfaces describe shipped L2 behavior,
the focused and broad non-security gates pass or are classified against the
fresh control, and ordered final reviews close L2 before Q3 routing proceeds.

**Files:**

- Modify: `docs/design/workflow_lisp_language_server.md`
- Modify exact L2 status:
  `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/workflow_lisp_language_server_setup.md`
- Modify exact L2 editor paragraph:
  `docs/lisp_workflow_drafting_guide.md`
- Modify exact L2 row: `docs/capability_status_matrix.md`
- Modify exact L2 row: `docs/design/README.md`
- Modify exact L2 routing: `docs/index.md`
- Modify exact L2 stage/sequence:
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- Modify exact L2 routing expectations:
  `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify factually after all gates: this plan

- [x] First make routing tests RED for L2 implemented/complete status, exact
      shipped three-way behavior, accepted final review tokens, and L3 as the
      next L-series design gate.
- [x] Update every owning design/status/setup/drafting surface from
      accepted-but-unimplemented to shipped behavior. Preserve the statement
      that definition/document symbols remain success-only and P1–P5 remain
      deferred.
- [x] Run the complete focused LSP surface:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [x] Run the active roadmap's exact broad non-security command in tmux with
      `pytest -q -n 16 --dist=worksteal`, all listed ignore paths, and
      `-k 'not security and not secret and not isolation and not safety'`.
- [x] Record collection/pass/failure/error/skip totals and classify every
      retained failure against the fresh pre-L2 control. Do not repair an
      excluded or unrelated failure under L2.

  Closing evidence on the exact candidate:

  - routing RED was observed on the two intended stale L2-selection tests;
    after the routing projection, the complete routing module passed
    **57 tests in 2.92 seconds**, and the final integrity rerun passed the
    same 57 tests in 2.61 seconds;
  - the complete seven-module LSP selector passed **404 tests in 81.81
    seconds**, with zero failures, errors, or skips;
  - the roadmap's exact broad non-security command collected and executed
    **9,461 selected tests**: **9,416 passed, 24 failed, 0 errors, and 21
    skipped**, with 35 warnings, in 303.43 seconds;
  - against Q2's immediately preceding like-for-like broad control (9,329
    passed, 24 failed, 21 skipped), **23 failure node identities are exact
    stable matches**: two output-contract/Semantic-IR controls, one
    content-addressed identity-retirement FIFO control, two provider
    supervision controls, fourteen peer-group protocol controls, three
    retirement-evidence fixture controls, and one lean-pilot special-file
    control;
  - the sole failure-identity delta is unrelated provider-execution-control
    work: the earlier
    `test_large_unread_controlled_stdin_cannot_block_cancellation[prebind]`
    row is absent and
    `test_persistent_group_signal_failure_uses_bounded_leader_fallback` is
    newly non-passing. No L2-owned production, test, documentation, or routing
    path owns either node; and
  - no retained failure touches `orchestrator/lsp/`, an LSP test module, or
    this stage's shipped completion contract. L2 did not repair, waive, or
    rebaseline any retained failure.

- [x] Obtain `L2_FINAL_SPEC_APPROVED` against the exact candidate snapshot.
- [x] Obtain distinct `L2_FINAL_QUALITY_APPROVED`.
- [x] Commit the exact reviewed production, evidence, docs, routing, and plan
      bytes without post-review edits. This checkbox becomes true atomically
      when this exact reviewed tree enters history; no post-review plan edit
      is required.
- [x] Verify the commit tree and rerun the focused routing plus exact L2
      behavioral nodes from committed `HEAD`; the parent records that
      post-commit confirmation outside the immutable reviewed tree.

## Completion Gate

L2 is complete only when:

- the frozen registry tuple is captured once after successful initialization;
- full and recovery completion use the identical immutable form rows;
- every positive and negative state branch is proven;
- recovery exposes no stale callable or source-derived target claim;
- index failure and malformed state remain exact empty responses;
- definition and document-symbol freshness are unchanged;
- the repository-real recovery-to-full stdio gate passes;
- the focused and broad non-security gates are recorded and classified;
- ordered final specification then quality approval is recorded;
- exact reviewed bytes are committed; and
- active routing names L3, not L2, as the next L-series design gate while Q3
  remains independently sequenced.

Completion does not select L3 implementation, Q4, P1–P5, E0, any parked
roadmap, or any runtime debugging surface.
