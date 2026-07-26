# Workflow Lisp Pure List Traversal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to execute this plan task by
> task. Every behavior change uses `superpowers:test-driven-development`.
> Every task receives an independent specification-compliance review followed
> by a distinct implementation-quality review before its commit. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the accepted target-2.18 list construction/traversal
surface, pure and bounded-effectful mapping binders, collection-valued loop
state, and containment-safe rooted path construction without adding function
values or a new executable control node.

**Architecture:** Add schema-2 expression forms to the shared pure evaluator
while preserving byte-identical schema-1 payload emission for older forms.
Represent authored list/path forms in the frontend, admit only whole-list
types accepted by the existing transport contract, and erase
`list/map-effect` after specialization into pure projections plus the
existing `repeat_until` loop. Carry only an optional generic exhaustion
diagnostic code through existing loop metadata; all scheduling, settlement,
and resume boundaries remain the established ones.

**Tech stack:** Python 3.11+, immutable dataclasses, canonical JSON,
Workflow Lisp target DSL 2.18, pure-expression schemas 1 and 2, WCC schema 2,
Core/Executable/runtime-plan v1, state schema 2.1, pytest/pytest-xdist.

**Accepted design:** `docs/design/workflow_lisp_pure_list_traversal.md` at
commit `80df061659c035ef3e067fe75b770b4786246f43`, tree
`d69457f34ce263ef970eb2a0df1aab6f9f14f297`, content digest
`sha256:e161d45eeaa0a6b9924831467e6eced21c40014aa72d8f7e62bb1d2720e0a5d5`.
That commit records ordered `LIST_DESIGN_SPEC_APPROVED` then
`LIST_DESIGN_QUALITY_APPROVED`. Implementation may begin only after this
plan receives ordered plan reviews and is committed.

**Status:** Accepted for execution. Ordered plan review:
`LIST_PLAN_SPEC_APPROVED` then `LIST_PLAN_QUALITY_APPROVED` (2026-07-25).
No implementation code began before this gate.

---

## Scope And Deliberate Cost

This plan implements only:

- target-2.18 `(list ...)`, `list/empty?`, `list/head`, `list/rest`,
  `list/append`, and `list/length`;
- target-2.18 pure `list/map`;
- target-2.18 `path/join-under` with an explicit rooted path family;
- whole-list-contract-expressible `List[T]` loop state;
- target-2.18 bounded `list/map-effect` with a single existing effectful call
  body;
- pure-expression schema 2 only for payloads using the new forms;
- optional generic repeat-loop exhaustion diagnostic metadata; and
- deterministic compile/run/resume evidence for ordered runtime-cardinality
  fan-out.

Do not add record/union elements to collection contracts, public partial list
operations, Optional flow refinement, a public `list/case`, higher-order
functions, `ProcRef` mapping, nested effectful maps, new Core/Executable
nodes, a routable exhaustion union, or filesystem checks in pure evaluation.

The direct binder-and-erasure approach makes future first-class mapping and
general effectful comprehension composition harder: either would need a
separate callable/lifecycle design rather than reusing this syntax
accidentally. Deferring record/union collection elements also means an author
must accumulate existing scalar, enum, path, or nested collection shapes in
this tranche. Those costs are accepted to keep the named runtime-cardinality
consumer small and structurally typed.

Principle 29 is binding. Generic `List[T]` and the prelude path families are
valid loose contracts; no task may require authors to mint nominal element
types. The explicit path family remains nominal because its root and
existence policy are load-bearing.

## Governing Authorities

Read before implementation:

- `AGENTS.md`
- `docs/index.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/design/workflow_lisp_pure_list_traversal.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_native_transportable_returns.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_lexical_execution_checkpoints.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- `specs/dsl.md`
- `specs/state.md`
- `specs/versioning.md`

If this plan conflicts with the accepted design, correct the plan and repeat
its ordered reviews; do not reinterpret the design in code.

## Execution Contract

Run every command from:

```bash
cd /home/ollie/Documents/agent-orchestration
```

Do not create a worktree. Preserve every pre-existing user or external
change. Stage exact task-owned paths only; never use `git add .`,
`git add -A`, destructive checkout/reset, or broad cleanup.

For every task:

1. add the smallest contract or behavioral test;
2. run it and confirm RED for the intended missing behavior;
3. implement only the selected behavior;
4. rerun the narrow selector;
5. run the task's adjacent regression selectors;
6. run `pytest --collect-only -q` for every new or renamed test module;
7. update this plan with fresh verification evidence and a truthful
   `reviews pending` task status so the bookkeeping is part of the exact diff
   under review;
8. dispatch a fresh specification reviewer against the accepted design and
   that exact task diff;
9. resolve findings, refresh verification bookkeeping if needed, and repeat
   until specification approval;
10. dispatch a distinct quality reviewer against the spec-approved exact
    diff;
11. resolve findings and repeat the ordered reviews until preliminary quality
    approval, then record both factual verdicts and `commit pending` status in
    this plan;
12. ask the same specification reviewer to reaffirm the final exact diff,
    then ask the quality reviewer to reaffirm that spec-reaffirmed final
    exact diff; and
13. stage exact paths, run `git diff --cached --check`, inspect the staged
    names/diff, and commit those re-affirmed bytes without any post-review
    bookkeeping edit;
14. obtain the implementation commit hash, update only this plan to replace
    `commit pending` with the factual hash and mark the task complete, verify
    the follow-up diff contains no behavior or other documentation change,
    and create a separate plan-only bookkeeping commit.

The plan-only bookkeeping commit records an event that already occurred; it
does not alter the reviewed implementation tree or claim a verdict that did
not exist. It does not substitute for either ordered review and must never
carry source, test, fixture, normative-doc, or routing changes.

Use the `tmux` skill for the closing broad suite and any integration selector
that exceeds one minute. Keep the installed/default provider and model;
wait instead of substituting a faster model.

Security is excluded by standing owner direction. Do not implement, test, or
review security behavior. The closing broad command must exclude the
security/isolation modules and use:

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

The following current changes are outside this plan. Do not edit, restore,
stage, or commit them:

```text
docs/index.md                         # except exact list/Stage-8 routing hunks
docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md
docs/plans/2026-07-01-workflow-audit-tier-fixes.md
docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md
docs/superpowers/plans/2026-07-23-provider-phase-information-isolation.md
docs/superpowers/specs/2026-07-22-workflow-lisp-evolution-substrate-and-feature-design.md
state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt
workflows/library/prompts/workflow_step_back/diagnose_non_progress.md
docs/reports/2026-07-22-compelling-example-search-and-effectiveness-doubts.md
docs/reports/provider-isolation-environment-feasibility/
orchestrator/cli/commands/__init__.py
orchestrator/cli/commands/provider_isolation_environment_manifest.py
orchestrator/cli/main.py
orchestrator/providers/isolation.py
orchestrator/providers/isolation_environment.py
orchestrator/providers/provider_launch_shim.py
orchestrator/providers/schemas/provider-environment-manifest-v1.schema.json
specs/cli.md
specs/providers.md
specs/security.md
tests/test_provider_isolation_policy.py
tests/test_provider_isolation_schema_resources.py
tests/test_provider_isolation_environment.py
tests/test_provider_isolation_environment_cli.py
tests/test_provider_launch_shim.py
```

`docs/index.md` contains an unstaged owner-authored parked-roadmap hunk. The
closing routing task may edit only list/Stage-8 status lines and must stage
those hunks with a generated patch, leaving the owner hunk unstaged.

## File And Responsibility Map

Shared pure kernel:

- `orchestrator/workflow/pure_expr.py`
- `tests/test_workflow_pure_expr.py`
- `tests/fixtures/workflow_lisp/pure_expr/golden_vectors.json`

Frontend and lowering:

- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/form_registry.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/expression_traversal.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/procedure_specialization.py`
- `orchestrator/workflow_lisp/typecheck_dispatch.py`
- `orchestrator/workflow_lisp/typecheck_pure_ops.py`
- `orchestrator/workflow_lisp/lowering/pure_projection.py`
- `orchestrator/workflow_lisp/wcc/route.py`
- `orchestrator/workflow_lisp/wcc/elaborate.py`
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`

Loop carriage and generic diagnostic metadata:

- `orchestrator/workflow_lisp/loops.py`
- `orchestrator/workflow_lisp/loop_state.py`
- `orchestrator/workflow_lisp/lowering/control_loops.py`
- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/runtime_step.py`
- `orchestrator/workflow/loops.py`
- `orchestrator/workflow/state_projection.py`
- `orchestrator/workflow/validation.py`

Focused integration:

- new `tests/test_workflow_lisp_list_traversal.py`
- `tests/test_workflow_lisp_loop_recur.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_wcc_m4.py`
- `tests/test_resume_command.py` or the narrow owning lexical-resume module,
  selected from the actual seam before writing the test

Keep new helpers in existing owning modules unless one module would otherwise
mix frontend syntax with runtime evaluation. Do not create a general
collection framework.

---

## Task 1: Freeze Target 2.18 And Dual Pure-Payload Versions

**Outcome:** Target/version gates exist before any new source behavior.
Existing target-2.14 through 2.17 inputs and schema-1 pure payloads remain
byte-identical.

**Files:**

- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow/validation.py`
- Modify: `orchestrator/workflow/pure_expr.py`
- Modify: `orchestrator/workflow_lisp/lowering/pure_projection.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_workflow_pure_expr.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Create: `tests/test_workflow_lisp_list_traversal.py`

**RED:**

- [x] Add collectable tests proving target 2.18 is currently rejected.
- [x] Add schema tests proving version 2 is currently rejected and version 1
      remains canonical.
- [x] Freeze one representative target-2.17 schema-1 payload/build digest.
- [x] Run:

```bash
pytest --collect-only -q tests/test_workflow_lisp_list_traversal.py
pytest -q \
  tests/test_loader_validation.py \
  tests/test_workflow_pure_expr.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_list_traversal.py
```

**GREEN:**

- [x] Add `2.18` and a single list-traversal minimum-target constant.
- [x] Extend shared mapping validation's supported-version set/order so a
      compiled target-2.18 mapping is accepted while unknown versions still
      fail closed.
- [x] Make pure payload validation explicitly dispatch schemas 1 and 2.
- [x] Keep old-only lowering on schema 1 even in a target-2.18 module.
- [x] Reject unsupported schema versions and schema/node mismatches with
      `pure_expr_schema_mismatch` or the accepted target diagnostic.
- [x] Rerun the RED selector and existing pure-expression/build regressions.
- [x] Obtain `TASK1_SPEC_APPROVED`, then `TASK1_QUALITY_APPROVED`, and commit.

**Implementation record (2026-07-25; complete):**

- RED collection produced 8 tests; the focused selector failed only at the
  intended missing gates/dispatch seams (`5 failed, 386 passed`). A follow-up
  strict-version RED added two intended failures for boolean and float schema
  values.
- GREEN collection is 13 tests. The exact focused selector above passes
  (`396 passed in 12.60s`), and `git diff --check` is clean.
- The frozen target-2.17 schema-1 payload digest is
  `sha256:a40fe0237ee12f03aff127afcc613dfa89daad5a0e586c0a49072289a50f0323`.
- The three pre-existing test modules required no edits: all new assertions
  live in the focused list-traversal module, while the pre-existing modules
  remain part of the passing regression selector.
- Ordered preliminary review verdicts are `TASK1_SPEC_APPROVED` then
  `TASK1_QUALITY_APPROVED`; final exact-diff verdicts are
  `TASK1_SPEC_REAFFIRMED` then `TASK1_QUALITY_REAFFIRMED`.
- Implementation commit:
  `3f6453b456e9ca2b496c9238b1be0d14a0e149f0`.

## Task 2: Implement The Schema-2 Pure Kernel

**Outcome:** The shared evaluator and compile-time folder implement the five
total list operators, constructor, pure map, rooted path join, and
compiler-owned nonempty extraction from one golden-vector contract.

**Files:**

- Modify: `orchestrator/workflow/pure_expr.py`
- Modify: `tests/fixtures/workflow_lisp/pure_expr/golden_vectors.json`
- Modify: `tests/test_workflow_pure_expr.py`
- Modify: `tests/test_workflow_lisp_list_traversal.py`

**RED:**

- [x] Add shared vectors for empty/single/multiple/nested collection values,
      order-preserving map, Optional head, rest-on-empty, append immutability,
      length, both general path families, and one narrower path descriptor.
- [x] Add both-direction failures for list element/descriptor mismatch,
      binder scope/collision, malformed selected root, empty/malformed child,
      absolute/escaping child, and compiler marker/nonempty invariant.
- [x] Assert schema 1 rejects every schema-2 node/operator and schema 2 counts
      all nested item/body nodes against the existing node cap.
- [x] Run the focused pure-kernel selector and confirm failures are missing
      behavior rather than malformed fixtures.

**GREEN:**

- [x] Version catalog entries so new list operators are schema-2-only.
- [x] Add validated `list`, `list_map`, `path_join_under`, and compiler-owned
      `list_nonempty_head` payload nodes.
- [x] Add evaluator-local binder scope; never merge it into top-level resolved
      bindings.
- [x] Evaluate list sources once, preserve order, return fresh arrays, and
      propagate existing body diagnostics.
- [x] Validate selected roots locally without changing `defpath` elaboration
      globally.
- [x] Use the same evaluator for folding; do not duplicate operator semantics.
- [x] Rerun golden vectors twice—runtime evaluation and compile-time folding.
- [x] Obtain `TASK2_SPEC_APPROVED`, then `TASK2_QUALITY_APPROVED`, and commit.

**Implementation record (2026-07-25; complete):**

- Initial RED collected 133 tests and produced only intended missing-behavior
  failures (`62 failed, 71 passed`). A follow-up unresolved-path diagnostic
  edge was separately RED (`1 failed, 4 passed`) before its correction.
- Specification review found that descriptor mismatches were still rejected
  only at evaluation. The direct validation-boundary RED produced 16 intended
  failures; a closed static type-derivation pass now rejects those payloads
  without evaluating values or placeholders.
- GREEN collection is 158 tests. The loader/pure/build/list selector passes
  (`510 passed in 13.41s`); the pure-projection/WCC folding regressions pass
  (`85 passed in 5.56s`); both JSON files parse; and the scoped diff check is
  clean.
- Every golden vector runs through both the runtime export and the compiler
  fold module's exact imported shared-evaluator seam.
- Descriptor comparison preserves the established path-type alias contract
  through Optional/List/Map containers while rejecting different path names,
  roots, or existence policies; record/union descriptors remain exact.
- The operator-justification registry required five list-operator rows to
  preserve its exact catalog invariant; no registry assertion was weakened.
- Ordered preliminary review verdicts are `TASK2_SPEC_APPROVED` then
  `TASK2_QUALITY_APPROVED`; final exact-diff verdicts are
  `TASK2_SPEC_REAFFIRMED` then `TASK2_QUALITY_REAFFIRMED`.
- Implementation commit:
  `2debaac4a2c4ba0615a6766bde4ebe4342542a06`.

## Task 3: Add Frontend List, Map, Path, And Expected-Type Forms

**Outcome:** Target-2.18 source parses, specializes, typechecks, traverses,
and lowers the pure surface with exact contextual empty-list typing and no
function values.

**Files:**

- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/loop_state.py`
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify: `orchestrator/workflow_lisp/typecheck_calls.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/typecheck_proofs.py`
- Modify: `orchestrator/workflow_lisp/typecheck_pure_ops.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/lowering/pure_projection.py`
- Modify: `orchestrator/workflow_lisp/wcc/route.py`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `tests/test_workflow_lisp_list_traversal.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

**RED:**

- [x] Cover constructor/operator type synthesis and each exact diagnostic.
- [x] Cover `(list)` in loop-state, record/union field, direct callable
      argument, declared return, and propagated `if`/`match` branch contexts.
- [x] Cover standalone and unannotated-`let*` empty-list rejection.
- [x] Cover valid/invalid pure-map binder shapes, lexical capture, input
      evaluated once, body purity, ordering, and whole-list transport
      admissibility including supported nested Optional/Map and rejected
      record/union elements.
- [x] Cover explicit prelude/local/imported path families, exact result type,
      deferred existence, and all three path refusal families.
- [x] Assert no new Core/Executable node kind and schema-1 projections remain
      byte-identical.

**GREEN:**

- [x] Add dedicated immutable frontend nodes for constructor, pure binder, and
      rooted path form; keep binder syntax non-value-producing.
- [x] Prove every new source form/operator is rejected below target 2.18
      through the accepted target/surface diagnostic.
- [x] Add a narrowly scoped expected-type argument only at the accepted
      checked positions; do not add global inference or annotated `let*`.
- [x] Gate every form/operator at target 2.18.
- [x] Apply `is_transportable_result_type(List[T])` to complete source/result
      list types and report `list_collection_contract_unsupported`.
- [x] Emit schema-2 pure payloads with resolved descriptors and source maps.
- [x] Route the new pure forms through WCC as values, not effects or nodes.
- [x] Rerun focused frontend, build-artifact, WCC M1/M2/M4, and pure
      expression selectors.
- [x] Obtain `TASK3_SPEC_APPROVED`, then `TASK3_QUALITY_APPROVED`, and commit.

**Implementation record (2026-07-25; complete):**

- The initial frontend RED collected 111 tests and failed only at the intended
  missing seams (`36 failed, 75 passed`). The first complete GREEN boundary
  passed all 112 then-current focused tests.
- Preliminary review found that globally registered 2.18 heads incorrectly
  reserved the same spellings in target 2.17. A 33-case callable/local-macro
  RED and a later 8-case imported-macro RED drove one canonical authored-head
  inventory plus target-aware callable and local/imported macro ownership.
  All eight spellings remain available to resolved 2.17 callables/macros,
  remain compiler-owned at 2.18, and still fail through the target diagnostic
  below 2.18 when no legacy binding resolves.
- Quality review then exposed missing macro hygiene for the `list/map`
  binder. Local and imported macro cases were both RED with
  `list_map_binder_invalid`; the target-aware hygiene owner now rewrites the
  source in the outer environment and the introduced binder/body in one
  extended environment. The opposite 2.17 user-macro case remains generic.
- Final collection is 176 focused tests. The exact frontend/pure/macro/
  procedure/all-WCC/build selector passes (`709 passed in 4.61s`); the
  build/workflow/procedure owner regression passes (`365 passed in 8.24s`);
  bytecode compilation and the scoped diff check are clean.
- `procedure_specialization.py` required no edit because its discovery paths
  already delegate to the updated shared `iter_child_exprs`. The added
  caller-owner files are the exact owners of loop-state, direct-call,
  declared-return, branch propagation, target-aware name ownership, and
  macro-hygiene contexts; no general inference or new Core/Executable node
  was added.
- Ordered preliminary verdicts are `TASK3_SPEC_APPROVED` then
  `TASK3_QUALITY_APPROVED`; final exact-diff verdicts are
  `TASK3_SPEC_REAFFIRMED` then `TASK3_QUALITY_REAFFIRMED`.
- Implementation commit:
  `dde5dd2cf72f2d0d937a0d397ff72f674f28285a`.

## Task 4: Carry Collection-Contract Lists Through Loops And Resume

**Outcome:** Eligible lists are one canonical JSON-array loop field with
exact descriptor/digest validation across seed, iteration, checkpoint, and
resume.

**Files:**

- Modify: `orchestrator/workflow_lisp/loops.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_loops.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow/executor.py`
- Inspect only: `orchestrator/workflow_lisp/loop_state.py` (its existing
  owner already delegates projectability to the shared loop gate)
- Modify: `tests/test_workflow_lisp_loop_state.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`
- Modify: `tests/test_workflow_lisp_list_traversal.py`
- Modify: `tests/test_resume_command.py` as the selected real resume owner

**RED:**

- [x] Prove eligible `List[String]`, `List[Path.artifact-root]`, and one
      supported nested Optional/Map list are currently rejected as loop state.
- [x] Prove top-level Optional/Map and list-of-record/union remain rejected.
- [x] Cover empty placeholder `[]`, one-field collection projection, canonical
      JSON array persistence, and descriptor identity.
- [x] Add clean resume plus tampered descriptor, non-array, invalid element,
      payload digest, and checkpoint digest failures.

**GREEN:**

- [x] Replace the unconditional list rejection in
      `ensure_loop_projectable_type` with the shared whole-list predicate.
- [x] Derive one collection contract field; do not flatten indices.
- [x] Add collection-aware empty placeholders without changing scalar,
      record, union, relpath, Optional, or Map top-level rules.
- [x] Reuse existing contract coercion and checkpoint validation on write and
      restore; do not create report/pointer artifacts.
- [x] Rerun loop, contract, state projection, lexical checkpoint, and resume
      selectors.
- [x] Obtain `TASK4_SPEC_APPROVED`, then `TASK4_QUALITY_APPROVED`, and commit.

**Implementation record — complete (2026-07-25):**

- Corrected RED was 6 failed / 4 passed at the list loop-carriage boundary.
  The next WCC RED was `typed list expression is missing its element type`;
  runtime then failed before generic named collection-root extraction.
- Eligible whole-list contracts now use `is_transportable_result_type`.
  Authored generic-procedure coverage proves unresolved `List[T]` defers and
  is revalidated when specialized: `List[String]` passes, while
  `List[Item]` fails with `list_collection_contract_unsupported`. Generic
  top-level `Optional[T]` and `Map[String,T]` fail before specialization, so
  their pre-existing refusal remains unconditional.
- Direct whole-list seeds use the existing pure projection. A record seed
  mixing a pure list expression with `GeneratedRelpathSeedExpr` now emits one
  deterministic list-only pure-projection component, then keeps the canonical
  seed step on `materialize_artifacts`: the list field is sourced from that
  component and the generated relpath remains on its established literal,
  contract, and origin-map path. The whole carrier and
  `GeneratedRelpathSeedExpr` were not broadened into a pure seed. Named
  collection roots are extracted generically at runtime; nested record
  collection fields retain flattened field lookup.
- Resume coverage now interrupts at the exact post-persist,
  post-lexical-checkpoint committed `CONTINUE` boundary. Persisted state
  carries `["first", "second"]`; resume reports a restored loop frame and
  executes only iteration 1, proving iteration 0 is not replayed.
- The target-2.15 scalar loop oracle was captured independently from exact
  pre-edit commit `f6dda982` via `git archive`: 6,649 canonical authored-
  mapping bytes, digest
  `sha256:57905acdc66527abdd6e021ebc97c27cfac20675bd335ae6de4ce1d16b75c479`.
  The Task-4 tree produces the identical bytes and digest.
- Fresh final owner-file verification:
  `pytest -q tests/test_workflow_lisp_list_traversal.py
  tests/test_workflow_lisp_loop_recur.py
  tests/test_workflow_lisp_loop_state.py tests/test_resume_command.py`
  produced 327 passes in 5.04 seconds, and the same four files collect all
  327 tests. The focused correction runs produced 221 loop/list passes and
  27 loop-state/list-resume passes (79 deselected). Earlier adjacent
  checkpoint/contract/pure-projection/state verification produced 284 passes
  plus the independently reproduced committed-HEAD failure
  `test_provider_valid_output_bundle_overrides_raw_nonzero_exit`; the Task-4
  diff does not touch that behavior. Scoped diff checking is clean.
- The first correction evidence review rejected direct-only generic tests and
  a whole-record pure route for the mixed seed. Those findings were resolved
  by the authored specialization tests and hybrid component/materializer
  lowering above. Ordered correction review then returned
  `TASK4_CORRECTIONS_SPEC_APPROVED` followed by
  `TASK4_CORRECTIONS_QUALITY_APPROVED`.
- `loop_state.py` required no production edit because it already delegates to
  the shared projectability owner. Ordered preliminary full-diff review
  returned `TASK4_SPEC_APPROVED` followed by `TASK4_QUALITY_APPROVED`; the
  same reviewers returned `TASK4_SPEC_REAFFIRMED` followed by
  `TASK4_QUALITY_REAFFIRMED` on the final exact diff.
- Implementation commit:
  `e2e2d5c275da7600c806a8689795c45372bd40c4`.

## Task 5: Add Generic Repeat Exhaustion Diagnostic Metadata

**Outcome:** Existing repeat loops may carry an optional compiler-owned code
that changes only exhaustion diagnostics and identity; ordinary loops remain
byte-for-byte and behaviorally unchanged.

**Files:**

- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/runtime_step.py`
- Modify: `orchestrator/workflow/statements.py`
- Modify: `orchestrator/workflow/loops.py`
- Modify: `orchestrator/workflow/state_projection.py`
- Modify: `orchestrator/workflow/validation.py`
- Modify: `orchestrator/workflow_lisp/loops.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_loops.py`
- Modify: `tests/test_workflow_loops_exhaustion_state.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

**RED:**

- [x] Freeze an ordinary repeat-loop Core/Executable/runtime-plan digest and
      generic `repeat_until_iterations_exhausted` failure.
- [x] Add an internal emitter test requiring a supplied diagnostic code to
      survive each projection, participate in executable identity, and appear
      only as `error.code` on exhaustion.
- [x] Add invalid/undeclared metadata tests that fail closed.

**GREEN:**

- [x] Add optional `exhaustion_diagnostic_code` through existing repeat-loop
      dataclasses/configuration and canonical serialization.
- [x] Validate it as inert compiler-owned metadata.
- [x] Preserve `error.type = repeat_until_iterations_exhausted` and existing
      state projection recognition; populate `error.code` only when supplied.
- [x] Prove `on_exhausted`, scheduling, settlement, and ordinary authored
      `loop/recur` output/digests are unchanged.
- [x] Rerun executable IR, runtime plan, loop executor, state projection,
      build artifact, and loop/recur selectors.
- [x] Obtain `TASK5_SPEC_APPROVED`, then `TASK5_QUALITY_APPROVED`, and commit.

**Implementation record — complete (2026-07-25):**

- Optional compiler-owned `exhaustion_diagnostic_code` now crosses authored
  mapping, Surface, Core, Executable configuration/frame identity,
  `RuntimeStep`, and runtime-plan projections. Omission is preserved at every
  serializer, so ordinary repeat loops retain their exact bytes.
- Shared validation accepts the metadata only from an exact Workflow Lisp
  compiler declaration, recursively associates nested generated loops by
  explicit step id, and rejects missing, extra, mismatched, invalid, or
  non-Workflow-Lisp declarations. The mechanism and schema contain no
  consumer or workflow-family names.
- Failed exhaustion retains
  `error.type = repeat_until_iterations_exhausted` and adds the optional code
  only at `error.code`. Successful settlement and `on_exhausted` settlement
  retain no error, and state projection continues to recognize the generic
  type rather than the optional code.
- The ordinary target-2.18 loop oracle is frozen at Core
  `47,271 / sha256:9f16ae97966378522dd64dc0c334bf294c271e806008e43e0615d8fa80c649f3`,
  Executable
  `65,326 / sha256:f244c285363bf59cce8da285276a33e3791fe7c0e1d95a224ceaef71842ad580`,
  and runtime plan
  `50,784 / sha256:f5e9bbb6042fb78af825f7595b08eb775d24a8dd586eed1e54bae964ceac2379`;
  all three omit the new key when no code is supplied.
- Fresh focused verification produced 46 loop/exhaustion passes and 326
  executable/runtime-plan/build/shared-validation/state-projection passes.
  Bytecode compilation and scoped diff checking were clean.
- Ordered independent verdicts were `TASK5_SPEC_APPROVED`, then
  `TASK5_QUALITY_APPROVED`.
- Implementation commit:
  `d7ccf046`.

## Task 6: Erase `list/map-effect` Into Existing Loop Semantics

**Outcome:** A target-2.18 bounded effectful binder executes one existing call
per element in order and resumes without replay or duplication.

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/expression_traversal.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py`
- Modify: `orchestrator/workflow_lisp/wcc/route.py`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_loops.py`
- Modify: `orchestrator/workflow_lisp/source_map.py`
- Modify: `tests/test_workflow_lisp_list_traversal.py`
- Modify: `tests/test_workflow_lisp_wcc_m4.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: the selected narrow resume module

**RED:**

- [ ] Cover malformed binder, absent/computed/zero/negative `:max`, impure
      source, unsupported body composition, and unsupported complete source
      or result list contract.
- [ ] Cover empty, one, `N < max`, `N == max`, and `N > max`, asserting exact
      call counts and order.
- [ ] On `N > max`, require generic `error.type`, exact
      `list_map_effect_cap_exceeded` code, and no `(max + 1)`th call.
- [ ] Cover body failure with no append and interruption after committed body
      effect but before accumulator commit with no replay, duplicate, skip, or
      reorder.
- [ ] Freeze stable loop/iteration/checkpoint/source-map identity and assert no
      new executable node kind.

**GREEN:**

- [ ] Add the source binder node and validate the first-tranche body as one
      specialized existing provider/command/workflow/procedure call with pure
      arguments.
- [ ] Evaluate/seed the source once, carry `remaining` and `results`, and use
      compiler-owned schema-2 nonempty extraction only in the generated
      nonempty branch.
- [ ] Append only after the committed body boundary.
- [ ] Return `done` in the iteration that consumes the last element so
      `N == max` succeeds.
- [ ] Attach the generic exhaustion code metadata and map all generated roles
      to the authored form span.
- [ ] Reuse existing prior-boundary resume validation; do not add a special
      restart or recovery path.
- [ ] Rerun focused list, WCC M4, loop, build, checkpoint, and resume selectors.
- [ ] Obtain `TASK6_SPEC_APPROVED`, then `TASK6_QUALITY_APPROVED`, and commit.

## Task 7: Prove The Runtime-Cardinality Consumer And Close The Interstage

**Outcome:** One deterministic-provider workflow consumes a runtime list,
produces ordered path results, synthesizes them, and proves clean/resumed
equivalence. Normative/routing docs truthfully mark the bounded surface
implemented.

**Files:**

- Create: one focused target-2.18 `.orc` fixture under
  `tests/fixtures/workflow_lisp/valid/`
- Modify: `tests/test_workflow_lisp_list_traversal.py`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_pure_list_traversal.md`
- Modify: `docs/design/README.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md` only at exact list/Stage-8 routing hunks
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: this plan
- Modify: relevant non-security normative specs if and only if the owning
  doc router requires them

**Verification:**

- [ ] Run `pytest --collect-only -q` on every new/renamed module.
- [ ] Run the focused pure/list/loop/WCC/build/resume selectors.
- [ ] Run a clean deterministic-provider end-to-end execution.
- [ ] Interrupt after a committed per-element effect and resume the same run;
      compare ordered outputs, attempt identities, and call counts to clean.
- [ ] Run target-2.17 compatibility and schema-1 frozen-artifact checks.
- [ ] Run documentation routing/link/status tests, including:

```bash
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
```

- [ ] Launch the closing broad non-security suite in tmux with the exact
      command in the Execution Contract and wait for completion.
- [ ] Record fresh counts and distinguish any established external failures
      without weakening selectors or repairing out-of-scope code.
- [ ] Update docs from observed behavior only. Mark the accepted design
      implemented and the selected interstage complete; leave Stage 8 as the
      next numbered stage.
- [ ] Obtain `TASK7_FINAL_SPEC_APPROVED`, then
      `TASK7_FINAL_QUALITY_APPROVED`.
- [ ] Stage only exact task-owned hunks. For every dirty protected file with
      an explicit overlap exception above (currently only `docs/index.md`),
      use patch-based staging and inspect the staged patch to verify every
      protected pre-existing hunk is absent even though the file name may
      appear. Verify every protected path without an explicit exception is
      absent from the staged name list, then commit.

## Interstage Completion Gate

The selected list-traversal interstage is complete only when:

- Tasks 1-7 are committed after their ordered reviews;
- the target-2.17/schema-1 frozen oracle is unchanged;
- all accepted diagnostics have both-direction coverage;
- clean and interrupted/resumed deterministic-provider evidence proves exact
  ordered results and no replay;
- the focused and broad non-security gates pass or contain only truthfully
  recorded pre-existing external failures;
- docs and capability routing match the implemented bounded surface; and
- ordered final specification and quality reviews approve the closing tree.

After this gate, proceed directly to Stage 8 under the execution-sequence
roadmap. Do not begin any post-Stage-8 successor item before Stage 8 closes.
