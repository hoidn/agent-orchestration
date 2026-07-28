# Workflow Lisp Compiler Session State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every production change. Each task
> receives an independent specification-compliance review followed by a
> distinct implementation-quality review before its exact-path commit. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mutable Workflow Lisp compile-phase module globals with one
explicit per-compile session and prove sequential LEGACY/WCC_M4/LSP compiles
cannot inherit elaboration, typecheck, generated-carrier, specialization, or
lowering-counter state.

**Architecture:** A small `CompilerSession` owns separate elaboration,
typecheck, and lowering state objects. Public compile entry points create a
fresh session by default; the production build seam passes one session through
the complete module graph, while recursive typecheck contexts and
`_LoweringContext` carry the relevant sub-session explicitly. The final task
adds failure-to-success, application-to-library, and real-process LSP
reentrancy proofs without changing language semantics, IR, diagnostics, or
entry-selection policy.

**Tech Stack:** Python 3.11+, dataclasses, explicit context threading, Workflow
Lisp Stage-3 compiler, LEGACY and WCC_M4 lowering, frontend in-memory builds,
LSP JSON-RPC stdio, pytest/pytest-xdist, and tmux for long gates.

---

## Authority And Plan Status

The original component plan passed ordered review and landed at `95c5dced`
(restored byte-identically after a concurrent-index race at `b344350d`).
This execution-readiness amendment reconciles the governing MR-4 paragraph
with L0's earlier content-addressed cache correction, adds two omitted
loop-carrier consumers, relocates the real-process proof to its owning
integration module, and rebases the collision record through completed M0 and
Q5. Production work may begin only after these exact amended bytes pass a new
ordered independent specification review followed by a distinct quality
review.

This component plan implements only MR-4 from:

- `docs/plans/2026-07-26-provider-at-least-once-loosening-amendment.md`
  under “MR-4 — Compiler session state”;
- `docs/plans/2026-07-26-substrate-maintenance-track.md`, including its
  governing bounds and concurrency rules;
- the L3 structural entry gate in
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`;
- `AGENTS.md`; and
- the source census recorded below.

MR-4 is behavior-preserving compiler reliability work. It must complete before
or with L3 because L3 intentionally increases sequential multi-source compiles
inside one process. It does not select L3, alter LSP entry-selection design, or
change any Q-series language surface.

Production work may begin only after this exact plan receives ordered
independent specification then quality review and is committed without
post-review edits. No gate in this document is pre-completed.

## Deliberate Cost

Explicit session parameters and context fields increase local signatures and
may increase net LOC. That is the owner-approved MR-4 exception to the
deletion-over-refactoring bound. The approach makes ad hoc calls into internal
elaboration/typecheck/lowering helpers more cumbersome because callers must
carry a session, but it makes process lifetime irrelevant to compiler
correctness and exposes future mutable phase state at code review.

## Frozen Census And Ownership

The implementation begins from this verified census:

1. `orchestrator/workflow_lisp/expressions.py` owns ten mutable active
   registers, including `_ACTIVE_PROMPT_CATALOG`, through save/mutate/restore
   globals around `elaborate_expression`.
2. `orchestrator/workflow_lisp/typecheck_context.py::_SESSION_STATE` is an
   additional mutable root whose `TypecheckSessionState` has ten fields.
3. `orchestrator/workflow_lisp/loop_state.py` owns two mutable dictionaries:
   carrier metadata by generated name and by expression/signature key.
4. `orchestrator/workflow_lisp/procedure_typecheck.py` owns the mutable
   parametric-specialization request dictionary.
5. `orchestrator/workflow_lisp/lowering/control_dispatch.py` owns mutable
   intrinsic-lowering counts.
6. `compile_stage3_entrypoint` currently resets loop metadata, while direct
   `compile_stage3_module` does not; intrinsic counts are never reset by either
   production entry.
7. `build._compile_entry -> compile_stage3_entrypoint` is the production build
   and LSP compiler seam.
8. `TypecheckContext` and `ProcedureTypecheckContext` are the existing explicit
   recursive typecheck carrier seams.
9. `_LoweringContext` is the existing explicit lowering carrier seam.
10. The LSP compile driver invokes the production prepared-build path; each
    prepared build must therefore receive a fresh compiler session without
    adding LSP-owned compiler state.

The following are deliberately excluded from sessionization:

- macro-expansion `ContextVar` owners, whose scoped token/reset behavior is
  already explicit;
- immutable registries and frozen catalogs;
- source-independent constants and diagnostic tables; and
- the content-addressed process-wide pure-projection export cache.

The cache at
`orchestrator/workflow_lisp/lowering/pure_projection.py::_cached_module_export_info`
remains process-wide. Its cache identity is the
`_ModuleExportCacheInput.canonical_source_path` plus the content-derived
`_ModuleExportCacheInput.source_sha256`; `raw_bytes` is the parsing payload and
is deliberately excluded from dataclass comparison and hashing with
`compare=False, hash=False`. MR-4 must not alter its decorator, identity
fields, payload treatment, input normalization, cache lifetime, or behavior.
If explicit loop-carrier lookup requires a small call-site hunk in that module,
only that lookup may change; the complete cache definition block and
`tests/test_workflow_lisp_pure_projection_cache.py` behavior remain frozen.

## Scope And Invariants

MR-4 implements only:

- one fresh compiler session per public compile/build attempt;
- one shared session across every module in a single module-graph compile;
- explicit elaboration state instead of ten `_ACTIVE_*` globals;
- explicit typecheck state instead of `_SESSION_STATE`;
- session-owned loop-carrier metadata and specialization requests;
- session-owned intrinsic lowering counts carried by `_LoweringContext`;
- compatible standalone helper entry points that create a local session when
  no enclosing compile exists;
- LEGACY and WCC_M4 reentrancy proofs; and
- one real LSP-server-process sequential-recompile proof.

The following invariants are load-bearing:

1. A session is created at a compile boundary, never lazily in a leaf after a
   compile is already active.
2. Every module in one resolved graph shares the same session; separate public
   compile calls never share one implicitly.
3. Session state is not persisted, serialized, included in source/IR/runtime
   identity, exposed as a Workflow Lisp value, or retained by the LSP.
4. Recursive elaboration and typecheck use explicit state from their existing
   context/call chain; no fallback reads a module singleton.
5. Nested helper calls may snapshot/restore fields inside the current session,
   but never swap or restore a module-global session root.
6. Generated loop carrier metadata and parametric specialization requests are
   visible for the duration of one compile only and are unreachable from the
   next compile.
7. Intrinsic counts remain test/compatibility evidence only. They are scoped to
   one lowering session and never affect lowering decisions.
8. Failure at any elaboration, typecheck, specialization, or lowering point
   cannot contaminate the next compile.
9. LEGACY and WCC_M4 retain their existing diagnostics, typed artifacts,
   lowered workflow bytes, source maps, runtime plans, and validation results.
10. Direct `compile_stage3_module`, linked `compile_stage3_entrypoint`, and
    `build_frontend_bundle_in_memory` all receive fresh-session semantics.
11. The LSP creates no second compiler-session abstraction: one prepared build
    enters the unchanged production build/compiler seam and receives a fresh
    compiler session there.
12. Application entry selection followed by a library-only compile with no
    selection returns no entry; a prior selected workflow is never reused.
13. The pure-projection content-addressed cache remains unchanged and
    process-wide.
14. No macro ContextVar, immutable registry, Q-series behavior, L3 surface,
    runtime, provider, checkpoint, persistence, or report code enters scope.

## Explicit Non-Goals

Do not add:

- parallel compiler execution;
- thread- or task-local hidden session lookup;
- compiler-session persistence or cache serialization;
- LSP entry-selection changes, multi-root support, or L3 implementation;
- new compiler diagnostics or changed diagnostic precedence;
- WCC middle-end redesign;
- pure-projection cache relocation or invalidation changes;
- unrelated typecheck cleanup, helper extraction, or API polish;
- runtime/executor/provider changes; or
- any security, safety, secrets, or provider-isolation work or tests.

## Governing Files And Existing Seams

Per-compile session and elaboration/typecheck owners:

- Create: `orchestrator/workflow_lisp/compiler_session.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/result_guidance.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/typecheck_context.py`
- `orchestrator/workflow_lisp/typecheck_dispatch.py`
- `orchestrator/workflow_lisp/typecheck_resume.py`
- `orchestrator/workflow_lisp/procedure_typecheck.py`
- `orchestrator/workflow_lisp/loop_state.py`
- `orchestrator/workflow_lisp/type_env.py` — explicit carrier lookup only
- `orchestrator/workflow_lisp/procedures.py` — explicit carrier lookup only

Lowering carrier owners:

- `orchestrator/workflow_lisp/lowering/context.py`
- `orchestrator/workflow_lisp/lowering/core.py`
- `orchestrator/workflow_lisp/lowering/procedures.py`
- `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- `orchestrator/workflow_lisp/lowering/pure_projection.py` — explicit
  loop-carrier lookup hunk only; cache block frozen
- `orchestrator/workflow_lisp/wcc/elaborate.py` — explicit loop-carrier lookup
  carrier hunk only
- `orchestrator/workflow_lisp/wcc/defunctionalize.py` — top-level
  `_LoweringContext` carrier hunk only; no middle-end algorithm change

Production build/LSP seam:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/lsp/compile_driver.py` is inspect/test-only; production changes
  are not expected because it already calls the prepared-build seam.
- `orchestrator/lsp/server.py` is inspect/test-only.

Primary tests:

- Create: `tests/test_workflow_lisp_compiler_session_state.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify only generated-state API callers:
  `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_stdlib_form_migration.py`
- Modify: `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`
- Modify: `tests/test_workflow_lisp_lsp_integration.py`

Adjacent regression suites are named in each task and need not be edited merely
to be run.

## M0 And Concurrent-Edit Entry Gate

M0's typecheck-family repairs landed through `7dcd177c`; the final overlapping
change is `6182ae48`. MR-4 must treat the following files as
collision-owned history rather than as an active parallel edit:

```text
orchestrator/workflow_lisp/procedure_typecheck.py
orchestrator/workflow_lisp/typecheck_context.py
orchestrator/workflow_lisp/typecheck_dispatch.py
orchestrator/workflow_lisp/typecheck_resume.py
orchestrator/workflow_lisp/typecheck.py
orchestrator/workflow_lisp/typecheck_calls.py
orchestrator/workflow_lisp/typecheck_effects.py
orchestrator/workflow_lisp/typecheck_proofs.py
orchestrator/workflow_lisp/typecheck_structural_values.py
orchestrator/workflow_lisp/specialization_typecheck.py
and any other adjacent typecheck owner changed by M0
```

The collision gate covers the complete landed M0 diff, not merely its
typecheck-family subset. The completed refusal-diagnosability work includes:

```text
orchestrator/workflow_lisp/workflows.py
orchestrator/workflow_lisp/typecheck_context.py
orchestrator/workflow_lisp/typecheck_calls.py
orchestrator/workflow_lisp/lowering/context.py
orchestrator/workflow_lisp/lowering/workflow_calls.py
tests/test_workflow_lisp_lowering.py
```

The first four paths are direct MR-4 owner collisions. The latter two are
adjacent M0 behavior/test owners and must be preserved even though this plan
does not currently authorize MR-4 edits to them. This census is a lower bound,
not a substitute for deriving the final landed inventory.

Q5 later changed direct MR-4 seams at `bceb03e4`: `expressions.py`,
`typecheck_context.py`, `typecheck_effects.py`, `wcc/defunctionalize.py`, and
`wcc/elaborate.py`. Those committed provider-result paths are current baseline
behavior. Before touching any of them, recensus the post-Q5 bytes and prove
session threading preserves every added provider-result field, diagnostic, and
lowering path. The stopped Task-13 working files do not overlap MR-4
production owners.

Before Task 1, bind M0's recorded predecessor and final commits and enumerate
every path in the complete landed M0 range:

```bash
git diff --name-status <m0-predecessor>..<m0-final>
git diff --stat <m0-predecessor>..<m0-final>
git diff --binary <m0-predecessor>..<m0-final>
```

Reconcile that derived inventory against every MR-4 source and test path in
this plan, including newly discovered overlap. Before the first MR-4 touch of
each collided path, capture separate current baselines:

```bash
git rev-parse HEAD
git rev-parse HEAD^{tree}
git rev-parse HEAD:<path>
git hash-object <path>
git diff --binary HEAD -- <path>
git diff --stat HEAD -- <path>
```

Store one patch per collided path outside the repository. Read the complete
landed M0 diff, reconcile both committed and surviving working-tree bytes, and
recalculate function-level ownership before making the first MR-4 edit to that
path. MR-4 stages only exact sessionization hunks; no whole-file staging is
permitted on a collided path. Immediately before each staged candidate, compare
the current blob and working-file hashes with that first-touch baseline and
inspect the exact staged hunk to prove every M0 byte remains. If M0 changes a
planned seam materially, or if Q5 changed the seam beyond the recensus above,
amend and re-review this plan before production edits.

MR-4 may overlap active Q work only after the parent executors confirm exact
behavioral and file ownership is disjoint. Q1 is complete, satisfying the
authority's prohibition on concurrent Q1 elaboration churn. If another actor
changes an MR-4 path during a task, rebuild the candidate on current `HEAD`,
rerun RED/GREEN, and restart both ordered reviews.

## Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve every user/external worktree change. Execute
Tasks 1–3 in order with one active MR-4 implementer at a time. For every task:

1. dispatch a fresh implementer with the complete task and MR-4 authority;
2. add the smallest contract/behavior test first;
3. run it and prove RED for the intended state leak or absent explicit carrier;
4. implement only the selected task;
5. rerun the narrow selector GREEN and named adjacent suites;
6. run `pytest --collect-only -q` for every created/renamed test module;
7. stage exact task paths or exact hunks into an isolated index;
8. run `git diff --cached --check`, inspect staged names, and read the complete
   staged diff;
9. obtain independent specification-compliance review against MR-4 and the
   exact candidate;
10. resolve findings and repeat specification review until approved;
11. obtain a distinct implementation-quality review only after specification
    approval;
12. if any byte changes, restart ordered specification then quality review;
13. commit exactly the reviewed bytes without post-review edits; and
14. rerun the task selector from the committed tree.

Never use `git add .`, `git add -A`, destructive checkout/reset, or whole-file
staging of a shared dirty file. Do not weaken verification to hide a failure.

Use the `tmux` skill for commands expected to exceed one minute, the real LSP
process test when run with adjacent suites, and the closing broad suite. Wait
for the configured review provider/model; do not substitute a faster model.

All security, safety, secrets, and provider-isolation modules/tests/docs are
excluded. Do not inspect them as authorities, edit them, stage them, or include
them in focused selectors.

## Preimplementation Plan And Baseline Gate

Before Task 1:

- [x] Obtain independent specification review of this exact plan; resolve every
  finding and repeat.
- [x] Obtain distinct implementation-quality review of the same plan bytes.
- [x] Patch-stage only this plan, the governing MR-4 paragraph, and its
  `docs/index.md` route; run `git diff --cached --check`, inspect the complete
  staged documentation delta, and commit exact reviewed bytes.
- [x] Bind the completed M0 range through `7dcd177c`, perform the collision
  audit above, and confirm no M0 agent remains active on typecheck owners.
- [x] Confirm exact disjointness from active Q work.
- [x] Record the current blob hash of the pure-projection cache block and run:

  ```bash
  pytest -q tests/test_workflow_lisp_pure_projection_cache.py
  ```

- [x] Run the Task 3 broad non-security command in tmux as the pre-MR-4
  control. Record commit/tree, collected node IDs, totals, failing node IDs,
  and dirty-tree inventory.

## Task 1: Explicit Per-Compile Elaboration And Typecheck Session

**Files:**

- Create: `orchestrator/workflow_lisp/compiler_session.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/definitions.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/result_guidance.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/typecheck_context.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck_resume.py`
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify: `orchestrator/workflow_lisp/loop_state.py`
- Modify only explicit loop-carrier lookup seams:
  `orchestrator/workflow_lisp/type_env.py`
- Modify only explicit loop-carrier lookup seams:
  `orchestrator/workflow_lisp/procedures.py`
- Modify only the explicit loop-carrier compatibility lookup seams:
  `orchestrator/workflow_lisp/lowering/core.py`
- Modify only the explicit loop-carrier compatibility lookup seam, with the
  content-addressed cache block frozen:
  `orchestrator/workflow_lisp/lowering/pure_projection.py`
- Modify only the explicit loop-carrier compatibility lookup seam:
  `orchestrator/workflow_lisp/wcc/elaborate.py`
- Create: `tests/test_workflow_lisp_compiler_session_state.py`
- Modify: `tests/test_workflow_lisp_expressions.py`

- [x] **Step 1: Confirm M0 serialization and recapture collided files.**
  Verify the completed M0 gate and derive/read the complete landed M0 diff,
  then reconcile every overlap, including `workflows.py`,
  `typecheck_context.py`, and `typecheck_calls.py`, against its first-touch
  HEAD/working-file baseline. Define exact MR-4 hunks against those current
  bytes; preserve the adjacent `lowering/workflow_calls.py` and
  `tests/test_workflow_lisp_lowering.py` M0 work without claiming either path
  for Task 1. Recensus the five Q5-touched MR-4 seams against `bceb03e4`.
- [x] **Step 2: Write the smallest behavioral RED and explicit-session
  structural tests.**
  First add
  `test_direct_module_sequential_edit_does_not_reuse_loop_carrier_metadata`.
  In one process, compile one source through direct `compile_stage3_module`
  so it generates a loop carrier, rewrite the same path to a distinct source
  that references the old generated name without defining it, and require
  `type_unknown`. This must fail on the current direct-module path, which does
  not reset the global carrier maps.
  Require one `CompilerSession` with distinct elaboration/typecheck/lowering
  sub-state. Require `compile_stage3_entrypoint` and direct
  `compile_stage3_module` to create fresh sessions by default, while every
  module inside one linked graph sees the same session identity. Require
  standalone `elaborate_expression`/`typecheck_expression` calls to use one
  local session without retaining it globally.
  Add the both-direction compatibility check required by removing the carrier
  globals: a carrier registered in the active typecheck session keeps the
  private nominal descriptor, while a merely prefix-shaped unregistered
  record does not.
- [x] **Step 3: Write census-root RED tests.**
  Parse the named compile-path modules with `ast` and reject module-level
  mutable phase roots. Add exact negative assertions for `_ACTIVE_*`,
  `_SESSION_STATE`, `_CARRIER_METADATA_BY_NAME`,
  `_CARRIER_METADATA_BY_EXPR_KEY`, and
  `_ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS`. Allow only reviewed immutable
  registries and existing macro ContextVars.
- [x] **Step 4: Write elaboration isolation RED tests.**
  In one process and one test, elaborate expressions under different function,
  procedure, workflow, local-proc, loop-depth, let-proc, guidance, target, and
  prompt-catalog inputs. Nest one elaboration call and inject one failure.
  Assert outer state restores inside the same session and a new session sees
  defaults for all ten fields.
- [x] **Step 5: Write typecheck/loop/specialization isolation RED tests.**
  Populate all ten current `TypecheckSessionState` fields, both loop metadata
  maps, generated local procedures, let-proc rewrites, and parametric
  specialization requests. Exercise success and exception paths. Assert
  nested calls share/restore their explicit current session and a new compile
  observes none of those values. Snapshot every session-owned mutable root.
  On nested success, preserve unambiguous new generated procedures, carrier
  metadata, and specialization requests for the enclosing compile; on nested
  failure, restore the complete outer snapshot. Treat a same-key,
  different-value persistent-output collision as an internal fail-closed
  contract error before applying any partial merge. Repeated specialization
  requests with the same materialization payload are idempotent even when
  their diagnostic origins differ; retain the completed request and its
  last-writer origin so existing diagnostics and materialization semantics
  remain unchanged.
- [x] **Step 6: Prove RED is intentional.**

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_compiler_session_state.py
  pytest -q \
    tests/test_workflow_lisp_compiler_session_state.py \
    tests/test_workflow_lisp_expressions.py \
    -k 'elaboration or typecheck or loop_carrier or specialization or globals'
  ```

  Expected: new structural and isolation cases fail on the census globals;
  unrelated expression/typecheck controls remain green.
- [x] **Step 7: Add the smallest session model.**
  Define dataclasses only for mutable compile-lifetime state. Keep diagnostic
  tables, immutable catalogs, macro ContextVars, source read traces, and the
  pure-projection cache outside it. Use direct fields rather than a registry or
  extensible bag. Retain concrete or forward-referenced types for stable
  catalogs, expressions, signatures, carriers, capabilities, and
  specialization requests; use heterogeneous types only where the stored
  values are genuinely private and structurally mixed.
- [x] **Step 8: Thread elaboration state explicitly.**
  Replace the ten `expressions.py` active globals with an
  `ElaborationSessionState` passed through `elaborate_expression`, recursive
  `_elaborate` owners, and callers in definitions/functions/result-guidance/
  procedures/workflows. Nested calls snapshot/restore that object only when
  required by their lexical semantics.
- [x] **Step 9: Thread typecheck state explicitly.**
  Remove `_SESSION_STATE`, `get_session_state`, and module-root
  snapshot/restore. Make `TypecheckContext` and `ProcedureTypecheckContext`
  carry the concrete typecheck sub-session. Pass it through dispatch, resume,
  procedure helpers, effect-summary fixpoints, generated local procedures, and
  reusable-state helpers. Standalone compatibility entry points allocate a
  fresh local `CompilerSession`. Generated-procedure consume/reset operations
  require the active typecheck session and have no detached no-argument
  fallback.
- [x] **Step 10: Move loop and specialization maps into the session.**
  Make all carrier lookup/register functions and specialization
  consume/reset operations require the active typecheck session. Remove
  production reset-at-entry cleanup: freshness now comes from session
  construction, while within-compile consume/reset semantics stay exact.
  Include the existing carrier readers in `type_env.py` and `procedures.py`;
  neither may retain a hidden global fallback. Update only the required
  compatibility readers in `lowering/core.py`,
  `lowering/pure_projection.py`, and `wcc/elaborate.py` to consult that same
  compile-local typecheck session. Those three hunks belong to Task 1 because
  the Task 1 green/artifact contract cannot run after global removal without
  them; change no lowering decision or artifact, and keep the complete
  pure-projection cache block frozen.
- [x] **Step 11: Run GREEN and adjacent typecheck regressions.**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_compiler_session_state.py \
    tests/test_workflow_lisp_expressions.py \
    tests/test_workflow_lisp_loop_state.py \
    tests/test_workflow_lisp_procedures.py \
    tests/test_workflow_lisp_pure_projection_cache.py \
    tests/test_workflow_lisp_wcc_m4.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_build_in_memory.py
  ```

- [x] **Step 12: Run the first exact grep gates.**

  ```bash
  if rg -n \
    '^(_ACTIVE_|_SESSION_STATE|_CARRIER_METADATA_BY_NAME|_CARRIER_METADATA_BY_EXPR_KEY|_ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS)' \
    orchestrator/workflow_lisp/expressions.py \
    orchestrator/workflow_lisp/typecheck_context.py \
    orchestrator/workflow_lisp/loop_state.py \
    orchestrator/workflow_lisp/procedure_typecheck.py; then
    exit 1
  fi

  if rg -n '\bglobal\b.*(_ACTIVE_|_SESSION_STATE|_CARRIER_METADATA_)' \
    orchestrator/workflow_lisp/expressions.py \
    orchestrator/workflow_lisp/typecheck_context.py \
    orchestrator/workflow_lisp/loop_state.py \
    orchestrator/workflow_lisp/procedure_typecheck.py; then
    exit 1
  fi
  ```

- [x] **Step 13: Review and commit.**
  Stage only Task 1 paths/hunks, preserving every M0 hunk. Obtain ordered
  specification then quality approval, commit exact reviewed bytes, and rerun
  the selector.

**Task 1 completion gate:** Both public Stage-3 compile entries create fresh
sessions; one graph shares one session; all elaboration/typecheck/loop/
specialization census roots are explicit; nested semantics and diagnostics are
unchanged; no mutable compile-phase global remains in Task 1 owners.

## Task 2: Lowering Session Carrier And Production Build Seam

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler_session.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/lowering/context.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`, excluding Task 1's
  frozen loop-carrier compatibility lookup hunks
- Modify: `orchestrator/workflow_lisp/lowering/procedures.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- Inspect only: Task 1's loop-carrier compatibility hunk and the frozen cache
  block in `orchestrator/workflow_lisp/lowering/pure_projection.py`
- Inspect only: Task 1's loop-carrier compatibility hunk in
  `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify only the top-level context-construction carrier hunk:
  `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `tests/test_workflow_lisp_compiler_session_state.py`
- Modify: `tests/test_workflow_lisp_stdlib_form_migration.py`
- Modify: `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`

- [x] **Step 1: Reconfirm current path ownership.**
  Recheck active Q/M work and current file hashes. Before the first MR-4 edit
  to `lowering/context.py`, reconcile its M0 refusal-diagnosability hunk
  against the complete landed M0 diff and its first-touch baseline; later stage
  only the exact session-carrier hunk. Freeze the pure-projection cache block
  hash again. Bind and reverify the already-landed Task 1 carrier-reader hunks
  in `lowering/core.py`, `lowering/pure_projection.py`, and `wcc/elaborate.py`;
  Task 2 must not modify or recreate them. The only permitted Task 2 WCC edit
  is the top-level context-construction carrier hunk in
  `wcc/defunctionalize.py`; do not refactor WCC middle-end algorithms.
- [x] **Step 2: Write lowering-session RED tests.**
  Compile two LEGACY workflows and two WCC_M4 workflows in alternating order
  with explicit sessions. Assert `_LoweringContext` always exposes the current
  lowering sub-session, child procedure contexts preserve its object identity,
  and no context from compile A is reachable from compile B.
- [x] **Step 3: Write intrinsic-count RED tests.**
  Exercise each existing compatibility-lane counter. Counts aggregate inside
  one lowering session, begin empty for a second session, and do not affect
  emitted workflow bytes. Replace reset/read test helpers with explicit
  session-taking APIs or direct immutable snapshots; no no-argument global
  fallback is allowed.
- [x] **Step 4: Write build-seam RED tests.**
  Observe `build._compile_entry -> compile_stage3_entrypoint` and prove one
  fresh session per `_compile_entry` call, including a compile that raises.
  Prove direct `compile_stage3_module` gets the same fresh-session behavior and
  no longer depends on the linked-entry loop reset.
- [x] **Step 5: Prove RED is intentional.**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_compiler_session_state.py \
    tests/test_workflow_lisp_stdlib_form_migration.py \
    tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py \
    -k 'lowering_session or intrinsic or compile_entry or direct_module'
  ```

- [x] **Step 6: Carry lowering state through the production seam.**
  Have each public compile/build attempt create or receive one
  `CompilerSession`; pass its lowering sub-session through
  `_lower_workflows_for_route` into the LEGACY and WCC_M4 top-level lowering
  entries and `_LoweringContext`. Child contexts preserve it through
  `dataclasses.replace` and explicit construction.
- [x] **Step 7: Remove global intrinsic counts.**
  Store counts on the lowering sub-session and make record/read/reset helpers
  require that session. Keep counts observational and absent from artifacts,
  identities, diagnostics, and compiler results.
- [x] **Step 8: Reverify Task 1's frozen carrier-reader prerequisites.**
  Prove the bound Task 1 hunks in `lowering/core.py`,
  `lowering/pure_projection.py`, and `wcc/elaborate.py` still read loop
  metadata from the compile-local typecheck session and still pass the
  registered/unregistered both-direction check. Do not edit those hunks.
  Task 2 owns only lowering-session/counter/build-seam carriage; its new
  lowering contexts must preserve the enclosing compiler-session identity
  without changing Task 1's carrier lookup, WCC calculus, or artifacts.
- [x] **Step 9: Prove the pure-projection cache is untouched.**
  Compare the frozen cache-block hash and run:

  ```bash
  pytest -q tests/test_workflow_lisp_pure_projection_cache.py
  ```

  The content-addressed process-wide cache must remain behaviorally and
  textually unchanged.
- [x] **Step 10: Run GREEN and adjacent lowering regressions.**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_compiler_session_state.py \
    tests/test_workflow_lisp_stdlib_form_migration.py \
    tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py \
    tests/test_workflow_lisp_loop_state.py \
    tests/test_workflow_lisp_pure_projection_cache.py \
    tests/test_workflow_lisp_wcc_m4.py \
    tests/test_workflow_lisp_wcc_characterization.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_build_in_memory.py
  ```

- [x] **Step 11: Run exact lowering grep gates.**

  ```bash
  if rg -n \
    '^_INTRINSIC_FORM_LOWERING_COUNTS|\bglobal\b.*INTRINSIC_FORM_LOWERING' \
    orchestrator/workflow_lisp/lowering/control_dispatch.py; then
    exit 1
  fi

  rg -n 'compiler_session|lowering_session' \
    orchestrator/workflow_lisp/compiler.py \
    orchestrator/workflow_lisp/build.py \
    orchestrator/workflow_lisp/lowering/context.py \
    orchestrator/workflow_lisp/lowering/core.py \
    orchestrator/workflow_lisp/wcc/defunctionalize.py
  ```

  Inspect every carrier hit; no hidden module lookup or target-specific
  fallback is permitted.
- [x] **Step 12: Review and commit.**
  Stage only Task 2 exact paths/hunks. Prove the cache block and all unowned
  WCC hunks are absent, and prove Task 1's three frozen carrier-reader hunks
  are byte-unchanged. Obtain ordered specification then quality approval,
  commit exact reviewed bytes, and rerun the selector.

**Task 2 completion gate:** The production build seam, direct module compile,
LEGACY lowering, and WCC_M4 lowering all receive explicit fresh sessions;
intrinsic counters are session-owned; Task 1's session-owned loop-metadata
readers remain byte-unchanged and verified; emitted artifacts are unchanged;
the pure-projection cache is untouched.

## Task 3: Reentrancy Closure, Real LSP Process, And Final Gates

**Files:**

- Modify: `tests/test_workflow_lisp_compiler_session_state.py`
- Modify: `tests/test_workflow_lisp_lsp_integration.py`
- Modify:
  `docs/plans/2026-07-27-workflow-lisp-compiler-session-state-implementation-plan.md`

Task 3 is expected to be test-and-record only. If a test exposes a production
defect, reopen the owning Task 1 or Task 2 files, fix with TDD, and repeat that
task's ordered reviews before rebuilding the Task 3 candidate.

- [x] **Step 1: Write LEGACY failure-to-success reentrancy test.**
  In one Python process, compile a source that populates elaboration,
  typecheck, loop-carrier, specialization, and intrinsic-count state, then
  inject a sentinel failure after those owners have run. Restore only the
  injected seam—not compiler state—and compile a distinct valid source under
  LEGACY. Compare its diagnostics, typed artifacts, lowered JSON, source map,
  executable IR, and runtime plan with a fresh-process/fresh-session control.
- [x] **Step 2: Write WCC_M4 failure-to-success reentrancy test.**
  Repeat the same sequence through WCC_M4. Prove the successful second compile
  equals its isolated control and contains no names, generated carrier types,
  specialization requests, prompt catalog entries, or intrinsic counts from
  the failed first compile.
- [x] **Step 3: Write application-entry to library-no-entry test.**
  Call `build_frontend_bundle_in_memory` twice in one process: first with a
  multi-export application and explicit selected workflow, then with a
  library-only source and no selection. Assert the second result has
  `entry_selection=None`, `selected_workflow_name=None`, no runnable bundle,
  and only its own diagnostics/artifacts. Reverse the order as a negative
  control.
- [x] **Step 4: Write real LSP-process sequential-recompile test.**
  Extend the existing real-process integration owner rather than the transport
  protocol module. Start one `_LspProcess` over stdio. Compile a valid source,
  edit it to a failure that exercises stateful compiler paths, observe the
  current failure, then edit it to a different valid source and observe a
  successful current generation. Compare the last diagnostics/symbol/
  completion surface with a fresh-server control for those exact final bytes.
  Assert no first-generation names, generated carriers, diagnostics, or
  callable entries survive. Do not add or change LSP entry-selection behavior.
- [x] **Step 5: Run collection and focused reentrancy gates.**

  ```bash
  pytest --collect-only -q \
    tests/test_workflow_lisp_compiler_session_state.py
  pytest -q \
    tests/test_workflow_lisp_compiler_session_state.py \
    tests/test_workflow_lisp_lsp_integration.py \
    -k 'compiler_session or reentrancy or sequential_recompile'
  ```

- [x] **Step 6: Run the complete affected compiler/LSP gate in tmux.**

  ```bash
  pytest -q \
    tests/test_workflow_lisp_expressions.py \
    tests/test_workflow_lisp_loop_state.py \
    tests/test_workflow_lisp_procedures.py \
    tests/test_workflow_lisp_stdlib_form_migration.py \
    tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py \
    tests/test_workflow_lisp_pure_projection_cache.py \
    tests/test_workflow_lisp_build_artifacts.py \
    tests/test_workflow_lisp_build_in_memory.py \
    tests/test_workflow_lisp_wcc_m4.py \
    tests/test_workflow_lisp_wcc_characterization.py \
    tests/test_workflow_lisp_lsp_compile_driver.py \
    tests/test_workflow_lisp_lsp_stdio.py \
    tests/test_workflow_lisp_lsp_integration.py
  ```

- [x] **Step 7: Run final mutable-global structural and grep gates.**
  Run the AST structural test over every compile-path module. Then run:

  ```bash
  if rg -n \
    '^(_ACTIVE_|_SESSION_STATE|_CARRIER_METADATA_BY_NAME|_CARRIER_METADATA_BY_EXPR_KEY|_ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS|_INTRINSIC_FORM_LOWERING_COUNTS)' \
    orchestrator/workflow_lisp/expressions.py \
    orchestrator/workflow_lisp/typecheck_context.py \
    orchestrator/workflow_lisp/loop_state.py \
    orchestrator/workflow_lisp/procedure_typecheck.py \
    orchestrator/workflow_lisp/lowering/control_dispatch.py; then
    exit 1
  fi

  if rg -n '\bglobal\b.*(ACTIVE|SESSION|CARRIER|SPECIALIZATION|INTRINSIC)' \
    orchestrator/workflow_lisp/expressions.py \
    orchestrator/workflow_lisp/typecheck_context.py \
    orchestrator/workflow_lisp/typecheck_dispatch.py \
    orchestrator/workflow_lisp/typecheck_resume.py \
    orchestrator/workflow_lisp/procedure_typecheck.py \
    orchestrator/workflow_lisp/loop_state.py \
    orchestrator/workflow_lisp/lowering/control_dispatch.py; then
    exit 1
  fi
  ```

  Review the AST allowlist: only immutable registries and existing macro
  ContextVars may remain. No mutable compile-path phase state is allowlisted.
- [x] **Step 8: Reverify cache and artifact parity.**
  Recheck the pure-projection cache block hash, rerun its focused test, and
  compare representative pre/post LEGACY and WCC_M4 artifacts. Session object
  identity and counters must not appear in serialized output.
- [x] **Step 9: Run broad non-security collection in tmux.**
  Save collected node IDs and compare them with the pre-MR-4 control,
  explaining every added/removed node.

  ```bash
  pytest --collect-only -q \
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

- [x] **Step 10: Run broad non-security suite in tmux.**

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

  Classify every non-pass against the pre-MR-4 control and task ownership.
  Never repair excluded security/safety/secrets/provider-isolation work.
- [x] **Step 11: Build the exact closure candidate.**
  Update this plan only with factual task commits, fresh checks, and review
  outcomes. Stage Task 3 tests plus this factual record; run
  `git diff --cached --check`, inspect names, and read the complete diff.
- [x] **Step 12: Obtain ordered final reviews.**
  First obtain independent holistic specification-compliance review against
  MR-4 and all three commits. Only after approval, obtain a distinct holistic
  implementation-quality review. Any byte change restarts both in order.
- [x] **Step 13: Commit and verify exact reviewed closure.**
  Commit without post-review edits. Rerun the focused session/reentrancy tests,
  grep gates, and pure-projection cache test from the committed tree.

**Task 3 completion gate:** Sequential failed→successful compiles are isolated
under LEGACY and WCC_M4; application selection cannot bleed into a library-only
compile; one real LSP process recovers to the same current result as a fresh
server; no mutable compile-path phase global remains; the pure-projection cache
and serialized compiler artifacts are unchanged; broad non-security evidence
and ordered holistic reviews approve the exact final tree.

## Factual Execution Record

This record describes the completed MR-4 closure on 2026-07-28. The exact
Task 3 candidate was staged, received ordered holistic specification then
quality approval, and was committed without post-review edits.

### Bound commits

- The reviewed execution-readiness amendment is
  `3bfe89adc850d12b4731a9f9081bcfb760e076c7`, tree
  `a19755b08c9034f16717a63fe1bbfbf70869c7a4`.
- Task 1 is
  `bad145cd8e334784c689e13832e1235021812c1e`, tree
  `4a8b7cbb4482fd7dd271341027215e270542a301`.
- Task 2 is
  `33d01003c0711458233667a71e923759d471d8f5`, tree
  `101459456baf88fb145f11fbf7e4411832ff4543`.
- Task 3's first broad run exposed six new standalone-helper compatibility
  failures, so Task 1 reopened rather than weakening or editing those tests.
  The reviewed corrective commit is
  `155ffe19d8c11240e477d5ba274089987eb5f163`, tree
  `66a4db567c40aca851e13092ce8faa9e099f8dc7`. It restores a fresh local
  `CompilerSession` default at both validation-pipeline helper boundaries
  while preserving explicitly supplied sessions.

### Task 3 candidate and focused evidence

- The candidate modifies only
  `tests/test_workflow_lisp_compiler_session_state.py`,
  `tests/test_workflow_lisp_lsp_integration.py`, and this plan. Before this
  factual record, the two test-file SHA-256 digests were respectively
  `8abe53508675ab55ae22c7b57adcb85d6bf18c81807b7fe62793eec7e27a53d9`
  and
  `c776a3210e6cbc502da53a69f1a62bfacf109c3a35d6a7a884e2ab4c3f23aa5b`.
- The compiler-session module collects 30 tests. The required focused selector
  passes 31 tests with 8 deselected, including LEGACY and WCC_M4
  failure-after-state parity against isolated subprocess controls,
  application-to-library selection isolation with the reverse control, and
  the real `_LspProcess` valid→stateful-failure→different-valid comparison
  against a fresh server.
- The affected compiler/LSP gate records 736 passed and the same six failing
  golden/identity nodes present before MR-4. Its log is
  `/tmp/mr4-task3-affected-r2.log`, SHA-256
  `bb89d2955677a49d11dabc8d349544d2c587c5a25dcd373c535a39c54522b23f`.
- Five AST mutable-root cases pass; both exact mutable-global grep gates return
  no hits; the pure-projection cache suite passes 4 tests; and the cache
  definition is byte-unchanged. The only MR-4 difference in that module is the
  reviewed compile-local loop-carrier lookup. The roadmap-routing suite passes
  61 tests.

### Collection and broad comparison

- The pre-MR-4 non-security control at the amendment commit recorded 10,733
  passed, 41 failed, 21 skipped, and 33 warnings in
  `/tmp/mr4-control.log`, SHA-256
  `78d58a0ae7d24ee1bbb1be779d4bc04f24582782c74c13ffdf6b71a049ea0744`.
  A collection-only reconstruction from an archive of that exact commit
  collected 10,795 selected nodes out of 10,814, with 19 deselected.
- The post-correction collection gate collected 10,826 selected nodes out of
  10,845, with 19 deselected. Its log is
  `/tmp/mr4-task3-collect-r2.log`, SHA-256
  `19ed0f7867901aba70102013b45b282ccfc3c92bb38bcf82ca0d098ada13ae69`.
  Exact node comparison has 32 additions and one removal: 30 new
  compiler-session tests, one real-LSP test, and a one-for-one rename of the
  existing failed-compile generated-state test. The added and removed lists are
  `/tmp/mr4-task3-added-nodeids.txt` (SHA-256
  `aac409792c3288a29bb4cdb01b2341347155109d904aee6e943b8ec7d030e2a1`)
  and `/tmp/mr4-task3-removed-nodeids.txt` (SHA-256
  `04358e6d0d9e566776fb43acedaccd9719415288858501d5c9d269a07e9a116a`).
- The final broad non-security gate records 10,764 passed, 41 failed, 21
  skipped, and 33 warnings in 157.20 seconds. Its log is
  `/tmp/mr4-task3-suite-r3.log`, SHA-256
  `a730ea7d03c2c7aa1c8d8c44633e59ab212c8de4bc188617f6b49bf1d08ad565`.
  Both exact set differences against the 41 pre-MR-4 failing node IDs are
  empty. The previously observed six helper-signature failures are absent.
- Every command above used the plan's explicit security, safety, secrets, and
  provider-isolation exclusions. No excluded module, test, or behavior entered
  the candidate.

### Final reviews, commit, and post-commit verification

- The exact staged three-file candidate had SHA-256
  `7e7b0c152b1cd9ecaf8e4479fb72681e3cbc88df4f7d61fe14257379c84f3619`.
- Ordered independent reviews returned `MR4_TASK3_SPEC_APPROVED` and then
  `MR4_TASK3_QUALITY_APPROVED`; no byte changed between those verdicts and the
  commit.
- The reviewed Task 3 closure is
  `632980cd3fa6afc2972a361178a26c966270c7d0`, tree
  `a7f4e77698a5081ea112c4b186170b3da00f14f1`.
- From that committed tree, the focused session/reentrancy selector passed
  31 tests with 8 deselected. The combined pure-projection cache and roadmap
  routing selector passed 65 tests. The working tree was clean.

## Handoff To L3

This component closes MR-4 only. After the exact final commit, the parent
roadmap executor may separately and serially update routing authorities to
record the compile-path reentrancy prerequisite as satisfied and replace the
language-server design's module-global serialization rationale with the
implemented session contract. This plan does not accept an L3 design, change
initialization schema, or start per-source entry-selection implementation.

## Final Completion Checklist

MR-4 is complete only when:

1. one explicit session owns every mutable census item;
2. public compile/build calls create fresh sessions and one graph shares one;
3. elaboration/typecheck/loop/specialization/lowering helpers have no hidden
   mutable session fallback;
4. direct module compile and linked entry compile behave identically with
   respect to freshness;
5. LEGACY and WCC_M4 failure-to-success proofs match isolated controls;
6. application-to-library and real-LSP sequential compile proofs pass;
7. exact AST/grep gates find no mutable compile-path phase global;
8. macro ContextVars and immutable registries remain unchanged;
9. the content-addressed pure-projection cache remains unchanged and green;
10. diagnostics, IR, lowered workflows, source maps, and runtime plans retain
    parity and contain no session artifacts;
11. M0 changes are preserved and every collided hunk was isolated;
12. no security/safety/secrets/provider-isolation or L3 surface entered scope;
13. each task has an exact reviewed commit after specification then quality
    review; and
14. focused, real-process, broad non-security, and ordered final review gates
    have fresh evidence.
