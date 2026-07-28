# Workflow Lisp Language Server L3 Per-Source Entry Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every behavior change. Every task
> receives an independent specification-compliance review followed by a
> distinct implementation-quality review before commit. Use the existing
> clean implementation clone; do not create a worktree.

**Goal:** Ship the accepted L3 initialization contract so one immutable LSP
process can request a workflow for each named application source while
submitting `entry_workflow=None` for unlisted sources, with exact production
CLI request parity and no cross-entry compiler-state bleed.

**Architecture:** Replace the process-wide `entry_workflow` option atomically
with a canonical-path-sorted immutable `entry_workflows` tuple. Normalize and
refuse that JSON object in `state.py`, carry closed initialization-error data
through `server.py`, and perform one exact canonical-path lookup at the
existing `compile_driver._build_request` seam. The production
`FrontendBuildRequest`, Stage-3 compiler, zero/one/many-export selection
semantics, context loaders, serialized worker, and F2 capture remain
unchanged.

**Tech stack:** Python 3.11+, frozen dataclasses/tuples, `pathlib`, existing
Workflow Lisp Stage-3/build/CLI seams, pygls/lsprotocol, pytest/pytest-xdist,
and real framed JSON-RPC over stdio.

**Accepted design:** commit
`c0706f7719035c4e6c1d30f02ed1eb3a7fb663fa`, tree
`4ac67e04cd24c8df49dffbe88ee8a18abb56fb4b`, after ordered
`L3_DESIGN_SPEC_APPROVED`, `L3_DESIGN_QUALITY_APPROVED`,
`L3_DESIGN_FINAL_SPEC_APPROVED`, then
`L3_DESIGN_FINAL_QUALITY_APPROVED`.

**Execution status:** accepted for execution after independent
`L3_PLAN_SPEC_APPROVED` then distinct `L3_PLAN_QUALITY_APPROVED`. The exact
plan/routing snapshot is in final ordered reaffirmation; no production change
is authorized until that reviewed snapshot commits. Task 1 starts only after
the committed plan gate and fresh controls below.

---

## Scope And Deliberate Cost

This plan implements only:

- `initializationOptions.entry_workflows` as a JSON object whose non-empty
  string keys identify contained `.orc` sources and whose non-empty string
  values are exact requested export names;
- deterministic canonicalization, lexical validation precedence, canonical
  duplicate detection, immutable sorted storage, and the accepted closed
  `workflow_lisp_lsp_initialization_error.v1` refusal data;
- removal of the old process-wide `entry_workflow` initialization option;
- exact source-path lookup while constructing each existing
  `FrontendBuildRequest`;
- one multi-export application and one procedure-only library fixture compiled
  in both orders in one process;
- exact listed/unlisted production CLI pre-selection capture parity;
- real-stdio mixed-entry and initialization-refusal evidence; and
- promotion of accepted-target documentation to shipped L3 behavior after all
  code/evidence gates pass.

Do not add a compatibility alias, default selection, basename/ancestor match,
directory inheritance, content/module inference, editor-focus inference,
mutable configuration, configuration watcher, per-entry extern/source-root
context, compiler mode, parallel worker, multi-root ownership, compiler cache,
prompt guidance, or nominal application/library type.

The deliberate cost is an initialization break for clients using the old
scalar. Moving a mapped source or changing its export requires restart with a
new map; the running process does not hot-edit intent. An unlisted request
passes `None` and therefore still follows the unchanged compiler rule: zero
workflow exports yield no selection, one auto-selects, and many refuse with
`entry_workflow_required`. These constraints make hot reconfiguration and
legacy-client compatibility harder, but keep each request deterministic.

## Governing Authorities

Read before implementation:

- `AGENTS.md`;
- `docs/index.md`;
- `docs/capability_status_matrix.md`;
- `docs/design/README.md`;
- `docs/design/workflow_lisp_language_server.md`, especially
  "L3 Target Amendment: Immutable Per-Source Entry Selection";
- `docs/design/workflow_lisp_frontend_specification.md` §76.1;
- `docs/design/workflow_language_design_principles.md`, especially principles
  28, 29, and 30;
- `docs/workflow_lisp_language_server_setup.md`;
- `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`;
- completed MR-4 plan
  `docs/plans/2026-07-27-workflow-lisp-compiler-session-state-implementation-plan.md`;
- completed L0/L1/L2/L5 component plans; and
- this plan's accepted-design commit and tree above.

If this plan conflicts with the accepted design, correct the plan and repeat
ordered plan reviews. Do not reinterpret the design in code.

Principle 28 is the reason the error envelope, exact rejected JSON value,
conditional fields, and precedence are public tests. Principle 29 is the
reason the surface is a structural path-to-string object rather than nominal
application/library records. Principle 30 is the reason selection stays in
deterministic initialization/request construction and adds no prompt prose.

## Ownership, Shared Files, And Exclusions

L3 production ownership is exactly:

- `orchestrator/lsp/state.py`;
- `orchestrator/lsp/compile_driver.py`; and
- `orchestrator/lsp/server.py`.

L3 behavioral test ownership is exactly:

- `tests/test_workflow_lisp_lsp_state.py`;
- `tests/test_workflow_lisp_lsp_compile_driver.py`;
- `tests/test_workflow_lisp_lsp_cli_parity.py`;
- `tests/test_workflow_lisp_lsp_stdio.py`;
- `tests/test_workflow_lisp_lsp_integration.py`;
- `tests/test_workflow_lisp_lsp_e2e.py`;
- a new
  `tests/fixtures/workflow_lisp/modules/valid/lsp_l3_entry_selection/`
  fixture root; and
- exact L3 routing expectations in
  `tests/test_workflow_lisp_drain_roadmap_routing.py`.

The final shared documentation paths are:

- `docs/design/workflow_lisp_language_server.md`;
- exact §76.1 L3 status in
  `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/workflow_lisp_language_server_setup.md`;
- `docs/capability_status_matrix.md`;
- `docs/design/README.md`;
- `docs/index.md`;
- exact L3/L4 routing in the active language-quality roadmap; and
- this plan.

Do not modify compiler/build/CLI production code: L3 consumes their existing
request and selection semantics. Do not touch M0-owned loader, refusal,
typecheck-divergence, or protected test paths. Do not modify or run any
security, safety, secrets, provider-isolation, or provider-launch-shim path.
Do not widen L3 to Q4/Q5, L4, P1-P5, prompt calculus, runtime, provider
coordination, or workflow execution.

## Protected Workspace And Execution Contract

Execute from the existing clean clone:

```bash
cd /home/ollie/.tmp/mr4-plan-pCBIen/repo
```

Do not create a worktree or another clone. Before every task, refresh
`git status --short`; preserve unrelated changes and never use `git add .`,
`git add -A`, destructive checkout/reset, or broad cleanup. Stage only exact
reviewed paths.

Use one fresh implementation subagent per task. For every implementation task:

1. inventory exact owned paths and current `HEAD`;
2. write the smallest behavioral test first;
3. run it and capture the intended RED;
4. implement only that task;
5. rerun the narrow selector and adjacent LSP regressions;
6. inspect the full exact diff and `git diff --check`;
7. obtain independent specification review;
8. correct findings through a fresh RED/GREEN cycle and repeat spec review;
9. obtain distinct quality review;
10. after any correction, repeat ordered spec then quality review;
11. stage only the exact reviewed bytes, inspect the cached diff, and commit;
12. rerun the task's post-commit selector.

Task 2 is an evidence/integration gate over Task 1 and should begin GREEN. If
it exposes missing behavior, return the defect to Task 1, add the smallest RED
test there, and repeat Task-1 ordered reviews before resuming. Do not patch
production opportunistically from an evidence task.

Use the `tmux` skill for commands expected to exceed one minute and for broad
verification. Wait for the assigned review agents; do not substitute a faster
model.

---

## Preimplementation Plan And Routing Gate

Before Task 1:

- [x] Obtain independent `L3_PLAN_SPEC_APPROVED` against this exact plan and
      the accepted design.
- [x] Resolve every specification finding and repeat specification review.
- [x] Obtain distinct `L3_PLAN_QUALITY_APPROVED`.
- [x] Record accepted-for-execution status and both ordered tokens without
      changing scope.
- [x] Route this plan from the design implementation record, active roadmap,
      design router, capability matrix, docs index, and routing tests while
      keeping L3 `Designed`, not implemented.
- [x] Run:

  ```bash
  pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [x] Obtain final ordered specification then quality reaffirmation against
      the exact plan/status/routing snapshot.
- [ ] Commit those exact reviewed bytes before production changes.
- [ ] Capture the fresh pre-L3 focused control:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_cli_parity.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_compiler_session_state.py \
    tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [ ] Retain a byte-for-byte read-only raw transcript outside the repository
      in a directory named by control `HEAD`. The transcript contains the
      control `HEAD`, tree, collected/pass/failure/error/skip totals, elapsed
      time, and exact failures. Store the SHA-256 of those final raw bytes in
      a separate read-only `.sha256` sidecar; the transcript does not hash
      itself. Do not edit this reviewed plan or any other repository path
      between the plan-gate commit and Task 1.
- [ ] Capture a fresh pre-L3 broad non-security collection and suite in tmux
      with the exact Task-3 command. Retain the collected node IDs, failing
      node IDs, totals, and elapsed time as read-only raw transcripts in the
      same external control directory. Store each final transcript's SHA-256
      in its own read-only `.sha256` sidecar so the final run has a
      same-command comparison. Record both controls and their sidecar digest
      values factually only in Task 3's already-authorized plan update.

## Task 1: Atomically Normalize The Map And Build Per-Source Requests

**Outcome:** Initialization accepts only the immutable map, every refusal has
the accepted structured data and deterministic first-failure behavior, the old
scalar is unsupported, and each prepared request receives only its exact
source-path selection.

**Files:**

- Modify: `orchestrator/lsp/state.py`
- Modify: `orchestrator/lsp/compile_driver.py`
- Modify: `orchestrator/lsp/server.py`
- Modify: `tests/test_workflow_lisp_lsp_state.py`
- Modify: `tests/test_workflow_lisp_lsp_compile_driver.py`
- Modify exact initialization fixtures only:
  `tests/test_workflow_lisp_lsp_cli_parity.py`
- Modify exact initialization fixtures only:
  `tests/test_workflow_lisp_lsp_stdio.py`
- Modify exact initialization fixtures only:
  `tests/test_workflow_lisp_lsp_integration.py`
- Modify exact initialization fixtures only:
  `tests/test_workflow_lisp_lsp_e2e.py`

- [ ] Write RED state tests proving absent map becomes `()`, distinct relative
      and absolute contained keys canonicalize into lexical canonical-path
      order, values remain codepoint-for-codepoint unchanged, and the frozen
      tuple cannot be mutated.
- [ ] Prove normalization is boundary-deferred: a missing-but-contained `.orc`
      path and an unknown export name both initialize successfully. Literal
      non-empty key/value spellings are not trimmed, case-folded, or Unicode-
      normalized; no source read, parse, or export lookup occurs during
      initialization. The unknown export may fail only when the ordinary
      compile boundary consumes the prepared request.
- [ ] Write one RED parameterized state matrix for all accepted refusal rows:
      old scalar, non-object, empty key, invalid/empty value, wrong suffix,
      uncontained path, and canonical alias duplicate. Assert the exact
      `schema`, `code`, `field`, `rule`, `rejected_value`, and precisely
      present/absent `entry_key`, `canonical_path`, and
      `conflicting_entry_key`.
- [ ] Write RED precedence tests: unsupported fields before map validation,
      with lexical selection among multiple unsupported field names; the old
      scalar's structured `unsupported_field` row when it is lexically
      selected; map shape/entry validation before `source_roots` or
      configuration-path validation; lexical raw-key order; key then value
      then suffix then containment; and canonical-path/lexical-spelling
      duplicate selection. Assert first failure only.
- [ ] Write RED JSON-domain tests: JSON-native wrong values receive structured
      refusals, while non-JSON programmatic keys/values raise `TypeError`
      before L3 normalization and never use `repr`.
- [ ] Write a RED server test proving `LspInitializationError.data` is
      forwarded unchanged as `JsonRpcInvalidParams.data`; retain existing
      compiler-initialization diagnostic data unchanged.
- [ ] Write RED real-stdio initialization cases for every JSON-deliverable
      refusal row. Assert JSON-RPC `-32602`, exact `error.data`, and
      conditional-field presence/absence; assert no message phrasing.
- [ ] Write RED driver tests with two canonical source paths proving the mapped
      path receives its exact name, the unlisted path receives `None`, request
      order does not matter, and no basename/ancestor/default lookup occurs.
- [ ] Replace `LspInitializationOptions.entry_workflow` with immutable
      `entry_workflows: tuple[tuple[Path, str], ...]`. Add the smallest pure
      JSON-domain/normalization helpers implementing the design's exact table
      and precedence.
- [ ] Extend `LspInitializationError` only enough to carry optional structured
      data. Forward it from `server.py` without changing other initialization
      error schemas.
- [ ] Replace the allowed scalar with `entry_workflows`. At
      `_build_request(source_path)`, perform one exact lookup over the frozen
      tuple and pass the result into the unchanged `FrontendBuildRequest`.
- [ ] Mechanically migrate existing LSP test initialization objects from the
      scalar to a one-row map keyed by their actual entry path. Do not alter
      expected compiler/build selection semantics, and do not change the
      unrelated imported-workflow manifest `entry_workflow` field.
- [ ] Run:

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_cli_parity.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py

  pytest -q \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_cli_parity.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py
  ```

- [ ] Obtain ordered `L3_TASK1_SPEC_APPROVED` then
      `L3_TASK1_QUALITY_APPROVED`, commit only the exact reviewed files, and
      rerun the selector post-commit.

## Task 2: Prove Mixed-Entry Reentrancy, CLI Parity, And Real Stdio

**Outcome:** One initialized driver and one real stdio process compile a mapped
multi-export application and an unlisted procedure-only library in either
order, while exact production CLI captures and isolated peers prove no
selection, diagnostic, catalog, protocol, or artifact bleed.

**Files:**

- Add:
  `tests/fixtures/workflow_lisp/modules/valid/lsp_l3_entry_selection/application.orc`
- Add:
  `tests/fixtures/workflow_lisp/modules/valid/lsp_l3_entry_selection/library.orc`
- Modify: `tests/test_workflow_lisp_lsp_compile_driver.py`
- Modify: `tests/test_workflow_lisp_lsp_cli_parity.py`
- Modify: `tests/test_workflow_lisp_lsp_integration.py`
- Modify: `tests/test_workflow_lisp_lsp_e2e.py`
- Modify only if a genuine Task-1 defect is found: the Task-1 owner paths,
  followed by a fresh Task-1 TDD/review cycle.

- [ ] Add a multi-export application with a non-first selected workflow and a
      zero-workflow exported-procedure library. Keep both fixtures minimal and
      target-compatible with the current compiler.
- [ ] Add a parameterized application→library/library→application driver test
      under one initialization map and one serialized worker.
- [ ] Capture each prepared `FrontendBuildRequest` and assert the application
      alone carries the exact configured name; the library carries `None`; all
      process-wide context fields remain identical.
- [ ] Compare each accepted result with an isolated fresh-process peer:
      request capture, ordered diagnostic identity, entry selection,
      selected-workflow name, typed frontend AST, callable catalogs, and the
      presence/absence of source-map/semantic/executable/runtime artifacts.
- [ ] Assert the application selects the requested non-first export and the
      library remains a non-runnable no-selection build whose existing
      workflow catalog has empty `signatures_by_name` and
      `definitions_by_name`, while its procedure catalog is intact.
- [ ] At the in-process driver boundary, assert both entries finish with
      `compile_status == "success"` and retain current accepted snapshots;
      compare those internal states only with in-process isolated controls.
- [ ] Add a listed-application parity row that invokes the unchanged real CLI
      parser/run path with `--entry-workflow`, initializes the LSP map with the
      same exact name, and compares the full existing F2 capture tuple.
- [ ] Add an unlisted-library parity row that invokes the same CLI without the
      entry flag. Bind the capture attached to the expected persistent
      non-runnable-build error and compare it with the successful read-only LSP
      in-memory result's capture.
- [ ] Assert the application has a selected workflow and matching diagnostic
      identity; the library's request carries `None`, its LSP entry selection
      is `None`, and no successful CLI artifact parity is claimed.
- [ ] Keep workspace root, caller source-root order, fixed compile policy,
      loaded context bundles, and builtin-root treatment inside the equality
      assertion.
- [ ] Open the mapped application and unlisted library in one real server in
      both orders. Wait for each current generation before observing it.
- [ ] Assert the application produces no `entry_workflow_required` diagnostic
      and reaches the same current-success protocol surface as its isolated
      peer; assert the library reaches its corresponding procedure-only
      current-success surface. Exact requested/selected values remain
      authoritative in the in-process and F2 assertions above rather than
      being inferred from protocol output that does not expose them.
- [ ] Compare each combined-process source's diagnostics, document symbols,
      definition/completion observations, and completed protocol responses
      with a fresh one-source server peer. Assert no cross-source contribution
      or callable bleed. Do not claim that stdio exposes internal
      `CompileEntryState` or selection state.
- [ ] Assert protocol stdout remains frame-clean and the read-only server
      creates no build artifacts or run state.
- [ ] Run:

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_cli_parity.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py

  pytest -q \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_cli_parity.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_compiler_session_state.py
  ```

- [ ] Obtain ordered `L3_TASK2_SPEC_APPROVED` then
      `L3_TASK2_QUALITY_APPROVED`, commit only the two fixtures and exact
      reviewed tests, and rerun post-commit.

## Task 3: Promote Shipped L3, Run Broad Gates, And Close

**Outcome:** Current docs expose only the shipped map, L3 is complete, L4 is
the next L-series design gate, and focused/broad non-security evidence plus
ordered final reviews close the exact implementation.

**Files:**

- Modify: `docs/design/workflow_lisp_language_server.md`
- Modify exact §76.1 status:
  `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/workflow_lisp_language_server_setup.md`
- Modify exact L3 row: `docs/capability_status_matrix.md`
- Modify exact language-server row: `docs/design/README.md`
- Modify exact routes: `docs/index.md`
- Modify exact L3/L4 status:
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
- Modify exact assertions:
  `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify factually after all gates: this plan, including the retained
  pre-L3 focused and broad control results

- [ ] First make routing assertions RED for L3 implemented/complete status,
      exact shipped `entry_workflows` behavior, removal of target/pending
      wording and the old scalar from accepted setup, task commit/review
      records, and L4 as the next L-stage design gate.
- [ ] Promote design/setup/router/capability/roadmap wording from accepted
      target to shipped behavior. Preserve MR-4 substrate truth,
      zero/one/many compiler semantics, immutable restart cost, all exclusions,
      and Q4/Q5's independent status.
- [ ] Run the complete focused surface:

  ```bash
  pytest -q \
    tests/test_workflow_lisp_lsp_state.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_cli_parity.py \
    tests/test_workflow_lisp_lsp_navigation.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py \
    tests/test_workflow_lisp_lsp_e2e.py \
    tests/test_workflow_lisp_compiler_session_state.py \
    tests/test_workflow_lisp_drain_roadmap_routing.py
  ```

- [ ] Run this exact broad non-security collection and suite in tmux:

  ```bash
  L3_EXCLUDES=(
    --ignore=tests/test_at61_at62_wait_for_path_safety.py
    --ignore=tests/test_cli_safety.py
    --ignore=tests/test_execution_safety.py
    --ignore=tests/test_provider_isolation_attestation.py
    --ignore=tests/test_provider_isolation_backend.py
    --ignore=tests/test_provider_isolation_backend_identity_negatives.py
    --ignore=tests/test_provider_isolation_bundle_broker.py
    --ignore=tests/test_provider_isolation_candidate.py
    --ignore=tests/test_provider_isolation_controller_lifecycle.py
    --ignore=tests/test_provider_isolation_environment.py
    --ignore=tests/test_provider_isolation_environment_cli.py
    --ignore=tests/test_provider_isolation_execution.py
    --ignore=tests/test_provider_isolation_network_preflight.py
    --ignore=tests/test_provider_isolation_policy.py
    --ignore=tests/test_provider_isolation_runtime_authority.py
    --ignore=tests/test_provider_isolation_schema_resources.py
    --ignore=tests/test_provider_isolation_workflow_continuation.py
    --ignore=tests/test_provider_isolation_workflow_lifecycle.py
    --ignore=tests/test_provider_launch_shim.py
    --ignore=tests/test_secrets.py
    --ignore=tests/test_workflow_provider_isolation_integration.py
  )
  pytest --collect-only -q "${L3_EXCLUDES[@]}" \
    -k 'not security and not secret and not isolation and not safety'
  pytest -q -n 16 --dist=worksteal "${L3_EXCLUDES[@]}" \
    -k 'not security and not secret and not isolation and not safety'
  ```

  Record collection/pass/failure/error/skip totals and exact failed-node delta
  against the pre-L3 same-command control and MR-4 broad baseline. Do not
  repair excluded or unrelated failures under L3.
- [ ] Inspect the exact closure diff and run `git diff --check`.
- [ ] Obtain holistic `L3_FINAL_SPEC_APPROVED`, then distinct
      `L3_FINAL_QUALITY_APPROVED`. Any byte change restarts both reviews in
      order.
- [ ] Commit the exact reviewed closure without post-review edits.
- [ ] Rerun the focused selector and routing test from the committed tree.

## Completion Contract

L3 is complete only when:

1. the process-wide scalar is rejected and the immutable per-source map is the
   only selection configuration;
2. every accepted initialization refusal returns the exact closed structural
   data under deterministic precedence;
3. listed/unlisted driver requests carry exact name/`None` values with no
   inferred fallback;
4. the mixed application/library workload passes both orders and matches
   isolated peers;
5. listed and unlisted requests exactly match production CLI F2 captures;
6. real stdio proves the mixed-entry and refusal matrices without protocol or
   artifact leakage;
7. all focused and broad non-security deltas are classified without weakening
   tests or repairing excluded work;
8. shipped documentation and routing agree; and
9. ordered per-task and final independent reviews approve the exact committed
   bytes.
