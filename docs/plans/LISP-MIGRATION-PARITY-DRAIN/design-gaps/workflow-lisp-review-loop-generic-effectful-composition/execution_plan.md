# Workflow Lisp Review Loop Generic Effectful Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the compiler-special `ReviewReviseLoopExpr` path with an imported `std/phase` review-loop surface that preserves the existing keyword API and caller-supplied `:returns`, then compiles through ordinary Workflow Lisp macro expansion, generic specialization, ordinary `ProcRef` hooks, ordinary `loop/recur`, and ordinary lowering.

**Architecture:** This slice stays entirely inside `orchestrator/workflow_lisp/`. The public `review-revise-loop` call remains keyword-oriented in `std/phase.orc`, but the imported stdlib surface becomes thin: it validates the authored keywords and emits a generic specialization request. Typecheck and compiler-owned specialization then resolve the caller's concrete `completed`, `inputs`, and `:returns` types, synthesize monomorphic review/fix wrapper procedures plus a generated loop helper, and rewrite the call site to ordinary generated forms before shared lowering runs. Generic `loop/recur` gains typed exhaustion projection, generic phase-scoped structured results stop depending on the old `ImplementationAttempt` carveout, and source-map plus managed write-root lineage stay intact across the generated helper boundary.

**Tech Stack:** Workflow Lisp `.orc` stdlib modules and macros, Python frontend compiler modules in `orchestrator/workflow_lisp/`, shared workflow lowering/validation reuse, `pytest`

---

## Scope

- Primary authorities:
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`

- Additional required context:
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`

- Progress-ledger status:
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is empty in this checkout, so no recorded later event supersedes the selected gap scope or sequencing.

- In scope for this plan:
- keep the current public `review-revise-loop` keyword surface, including `:ctx`, `:completed`, `:inputs`, `:review-provider`, `:fix-provider`, `:review-prompt`, `:fix-prompt`, `:max`, and caller-supplied `:returns`;
- move that surface into imported `std/phase` source as a thin macro plus generic specialization request;
- add frontend-owned generic specialization support that turns one typed request into monomorphic generated helpers and an ordinary rewritten call;
- route generated review/fix behavior through compile-time `ProcRef` hooks by synthesizing wrapper procedures that close over the captured provider/prompt externs at compile time;
- extend generic `loop/recur` with typed exhaustion projection suitable for the imported stdlib route;
- preserve carried evidence identities and findings handoff semantics for the retained review-loop contract, including rejecting review-provider attempts to replace carried evidence such as `checks_report`;
- relax the current generic phase-scoped `provider-result` restriction so generated review/fix helpers can use caller-declared structured record/union contracts under `with-phase`;
- preserve managed hidden write-root ownership, resume-safe loop lowering, and source-map lineage across the generated helper boundary;
- prove the migration-facing path with targeted tests, including at least one key-migration-oriented fixture path.

- Explicitly out of scope:
- `command-result` runtime/spec authority work, including `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`;
- shared runtime execution or validation changes under `orchestrator/workflow/`;
- `resume-or-start`, reusable-state validation, workflow input defaults, parity report generation, or promotion policy;
- runtime closures, runtime `ProcRef` transport, runtime provider/prompt refs, or runtime workflow refs;
- repo-wide review-findings schema standardization, report parsing, pointer-as-state compatibility, or uncertified shell/Python semantic glue;
- docs-only refactors or unrelated Workflow Lisp cleanup not required to land the selected slice.

## Implementation Architecture

### Unit 1: Imported `std/phase` Public Surface And Specialization Request

- Owns the authored review-loop surface and its imported-stdlib entrypoint:
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/expressions.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_phase_stdlib.py`

- Stable contract:
- authors still call `review-revise-loop` with the existing keyword operands and a caller-owned `:returns` union symbol;
- the imported stdlib surface performs only keyword/shape validation plus emission of generic specialization metadata;
- after macro expansion, the compiler no longer depends on a dedicated review-loop expression node keyed to the literal surface form;
- imported `std/phase` remains the only public review-loop authoring surface.

### Unit 2: Generic Monomorphic Helper Specialization And Compile-Time Hooking

- Owns the frontend-local machinery that turns one typed specialization request into ordinary generated helpers:
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/procedure_refs.py`
- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_workflow_refs.py`

- Stable contract:
- typecheck resolves the concrete `completed`, `inputs`, and `:returns` types for each review-loop call site;
- specialization synthesizes monomorphic wrapper procedures for review and fix behavior plus a generated loop helper or private workflow boundary as needed;
- provider and prompt externs remain compile-time captured implementation details of those wrappers, not runtime-carried values;
- compile-time workflow-extern collection works from the specialized ordinary provider/phase forms rather than a dedicated `ReviewReviseLoopExpr` branch;
- imported-module workflow-ref resolution and extern-rebinding diagnostics continue to operate on the specialized ordinary forms rather than a retired primitive path;
- lowering sees only ordinary generated procedures, ordinary calls, and ordinary loop/procedure/provider/command forms.

### Unit 3: Generic Loop Exhaustion And Phase-Scoped Structured Results

- Owns the generic frontend-local behavior that the specialized route depends on:
- `orchestrator/workflow_lisp/loops.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `tests/test_workflow_lisp_loop_recur.py`
- `tests/test_workflow_lisp_phase_stdlib.py`

- Stable contract:
- `loop/recur` exposes a typed exhaustion projection path or equivalent compiler-private metadata path reachable from the specialized helper;
- exhaustion lowers through `repeat_until.on_exhausted.outputs` scalar overrides plus final projection from the last successful loop-frame state;
- phase-scoped generated helpers may emit caller-declared structured record/union results through ordinary `provider-result` rules rather than the old `ImplementationAttempt` carveout;
- review provider output cannot replace carried evidence identities such as `checks_report`; terminal projection copies those identities from loop state or consumed inputs, and fix/revise receives findings from the previous review result;
- imported stdlib review loops remain resume-safe through persisted `repeat_until` checkpoints rather than only in single-pass lowering;
- exhaustion still fails normally if the final completed iteration did not materialize required projected outputs.

### Unit 4: Primitive Retirement, Hidden Write Roots, And Provenance

- Owns removal of the old primitive route and proof that ordinary lowering still preserves ownership boundaries:
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/stdlib_contracts.py`
- `orchestrator/workflow_lisp/functions.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_source_map.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_key_migrations.py`

- Stable contract:
- `ReviewReviseLoopExpr` no longer exists as a dedicated parse/typecheck/lowering/contract surface;
- hidden `__write_root__...` inputs remain compiler-owned on the generated helper boundary and do not become public caller inputs;
- source maps cover the authored call site, imported stdlib macro frame, specialization request origin, generated wrappers, generated loop helper boundary, and generated hidden input/path nodes;
- migration-facing tests prove the new route does not rely on literal-name special casing or public hidden inputs.

### Dependency Direction

- Unit 1 must land first because the fixture and imported-stdlib surface define the preserved public contract.
- Unit 2 depends on Unit 1 because the specialization request shape comes from the imported stdlib surface.
- Unit 3 depends on Unit 2 because the specialized helper needs typed exhaustion and generic structured-result support.
- Unit 4 depends on Units 1-3 because primitive retirement is safe only once imported stdlib compilation, specialization, loop lowering, provenance, and write-root ownership all work through the generic route.

### Sequencing Constraints

- Do not preserve any literal-name `review-revise-loop` branch after macro expansion.
- Do not change shared runtime behavior under `orchestrator/workflow/`.
- Do not replace caller-supplied `:returns` with a stdlib-owned universal result contract in this slice.
- Do not expose provider refs, prompt refs, or `ProcRef` values in executable runtime state.
- Do not reintroduce report parsing, pointer authority, or uncertified adapter behavior while wiring the generated helper path.

## Task Checklist

### Task 1: Rebuild The Public Review-Loop Surface As Imported `std/phase`

**Files:**

- Modify: `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Update `std/phase.orc` so the review-loop surface lives in imported stdlib source rather than in a Python primitive path.
- [ ] Preserve the current keyword contract exactly: `:ctx`, `:completed`, `:inputs`, `:review-provider`, `:fix-provider`, `:review-prompt`, `:fix-prompt`, `:max`, and `:returns`.
- [ ] Keep the stdlib macro thin: validate required/duplicate keywords, capture the authored operands, and emit only generic specialization metadata plus ordinary expressions.
- [ ] Remove any direct elaboration in `expressions.py` that constructs a review-loop-specific expression node from the surface form.
- [ ] Update the valid fixture and module tests so imported `std/phase` is the only public route exercised by review-loop coverage.
- [ ] Add or adjust contract tests that fail if the public keyword surface drifts, if `:returns` is not preserved, or if imported stdlib usage still depends on primitive-only parsing.

**Blocking verification after Task 1:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_phase_stdlib.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py -k "std_phase or import_macro or review_loop" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or stdlib_module" -q`

### Task 2: Add Generic Specialization And Compile-Time Review/Fix Wrappers

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `orchestrator/workflow_lisp/procedure_refs.py`
- Modify: `orchestrator/workflow_lisp/workflow_refs.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_workflow_refs.py`

- [ ] Introduce one generic specialization path that accepts the macro-origin request, resolves the concrete `completed`, `inputs`, and `:returns` types, and rewrites the call site to ordinary generated definitions plus an ordinary generated call.
- [ ] Synthesize monomorphic review and fix wrapper procedures per call site so provider/prompt extern usage is captured at compile time and routed through compile-time `ProcRef` hooks.
- [ ] Keep runtime `ProcRef` rejection unchanged: no procedure, provider, or prompt ref may survive into executable state or loop-carried values.
- [ ] Update `workflow_refs.py` so compile-time extern collection and workflow-ref analysis observe only the specialized ordinary provider/phase forms and no longer import or branch on `ReviewReviseLoopExpr`.
- [ ] Queue generated helpers into the normal compiler/procedure pipeline rather than adding a review-loop-only lowering side channel.
- [ ] Prove imported stdlib review-loop compilation still works when the compiler can only succeed through the generic specialization route.
- [ ] Add or update tests that cover caller-specific `completed`/`inputs` record types, caller-supplied `:returns` unions, and absence of runtime-carried refs.
- [ ] Add or update dedicated `workflow_refs` coverage so imported-module resolution plus extern-rebinding diagnostics still pass after specialization removes the primitive branch.

**Blocking verification after Task 2:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_modules.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_workflow_refs.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_procedures.py -k "review_loop or review_phase or proc_ref or private_workflow" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or write_root or review_phase" -q`

### Task 3: Extend Generic `loop/recur` Exhaustion And Phase-Scoped Structured Results

**Files:**

- Modify: `orchestrator/workflow_lisp/loops.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Add the generic typed exhaustion projection capability required by the specialized helper, using `repeat_until.on_exhausted.outputs` only for scalar overrides and final projection from last loop-frame state for structured fields.
- [ ] Preserve ordinary failure behavior when exhaustion projection requires outputs that the last completed iteration never materialized.
- [ ] Relax the current generic phase-scoped `provider-result` restriction so generated review/fix wrappers can return any declared structured record or union contract already allowed by the generic provider-result rules.
- [ ] Add focused fixtures for `APPROVE`, `REVISE -> APPROVE`, `BLOCKED`, `EXHAUSTED`, malformed findings, and rejection of review-provider attempts to replace carried evidence identities such as `checks_report`.
- [ ] Prove final review-loop projection copies carried evidence from loop state or consumed inputs and that revise/fix consumes findings from the previous review result.
- [ ] Keep this work generic: the new loop and phase behavior must not mention `review-revise-loop` by name.
- [ ] Add focused loop tests for exhaustion, union-result normalization, and failure-on-missing-projection-output, then prove the imported stdlib review loop uses that generic route.
- [ ] Add a runtime-backed stdlib review-loop fixture that persists a `REVISE` checkpoint, resumes, and reaches `APPROVE` through the imported stdlib route.

**Blocking verification after Task 3:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_phase_stdlib.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_loop_recur.py -k "exhaust or union_result or review" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or exhaustion or write_root" -q`

### Task 4: Retire The Primitive Route And Preserve Write-Root And Source-Map Lineage

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/stdlib_contracts.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Delete `ReviewReviseLoopExpr`, its parse/typecheck/lowering entry points, and any helper dispatch that still classifies it as a special expression family.
- [ ] Ensure lowering sees only ordinary generated helpers, ordinary calls, ordinary `loop/recur`, ordinary `match`, and ordinary `provider-result`/`command-result` forms after specialization.
- [ ] Preserve hidden write-root transport on the generated helper boundary so no public caller input or public executable-state value exposes compiler-owned managed paths.
- [ ] Extend source-map assertions so diagnostics can still blame the user call site, the imported stdlib form, and the generated helper lineage without losing hidden-input/path provenance.
- [ ] Update `stdlib_contracts.py` so review-loop support is described as imported stdlib specialization plus ordinary lowering obligations, not as a primitive-expression backend contract.
- [ ] Rewrite `tests/test_workflow_lisp_lowering.py` to stop importing `ReviewReviseLoopExpr` and to assert the post-retirement contract instead: review-loop support remains in the lowering inventory through imported stdlib specialization plus ordinary statement-family obligations, not through a dedicated expression class.

**Blocking verification after Task 4:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_modules.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_lowering.py -k "stdlib_contract or review_loop or supported_frontend_forms" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_source_map.py -k "review_loop or stdlib or generated" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or write_root or stdlib_module" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py -k "std_phase or import_macro or review_loop" -q`

### Task 5: Prove Migration-Facing Behavior With The Recorded Narrow Checks

**Files:**

- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_workflow_refs.py`
- Create or modify if needed: `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`

- [ ] Add or update at least one migration-facing test path that exercises the design/plan/implementation stack family through the imported stdlib route and proves no public hidden inputs or primitive-only dependency remains.
- [ ] Keep the proof focused on the selected gap: compile/type/lowering/source-map/write-root/migration-path evidence only, not broader promotion-report or runtime-authority work.
- [ ] Add or update migration-facing assertions that the imported stdlib route preserves carried evidence ownership, findings handoff, and primitive retirement without claiming the out-of-scope promotion-report/defaults/runtime-authority work is done.
- [ ] Run one targeted stdlib review-loop resume integration check in addition to the narrow unit/module suite. The test must execute an imported stdlib review loop through `REVISE`, persist the loop checkpoint, resume, and reach `APPROVE` so the changed `repeat_until` lowering is proven resume-safe.
- [ ] Run one explicit frontend integration smoke check against the migration family using `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "review_loop or parity or design_plan_impl" -q` so the recorded design-plan-implementation selectors exercise the imported stdlib route without expanding scope into the out-of-scope parity-report or promotion-policy work.
- [ ] Treat the design/plan/implementation stack family as compile/lowering parity evidence only in this slice. Do not claim full runtime end-to-end coverage for that stack until the out-of-scope parity/report/defaults/runtime authority work lands.

**Blocking verification after Task 5:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_loop_recur.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py -k "std_phase or import_macro or review_loop" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_procedures.py -k "review_loop or review_phase or proc_ref or private_workflow" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_loop_recur.py -k "exhaust or union_result or review" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or write_root or stdlib_module or exhaustion" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_source_map.py -k "review_loop or stdlib or generated" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "review_loop or parity or design_plan_impl" -q`
- [ ] If any targeted tests are added or renamed in the listed modules, run `pytest --collect-only` on those modules before the full narrow suite.

## Acceptance Checklist

- [ ] `review-revise-loop` no longer exists as a dedicated primitive in `expressions.py`, `typecheck.py`, `lowering.py`, or `stdlib_contracts.py`.
- [ ] `orchestrator/workflow_lisp/workflow_refs.py` no longer imports or special-cases `ReviewReviseLoopExpr`; compile-time extern collection works from ordinary specialized forms.
- [ ] Dedicated workflow-ref coverage proves imported-module resolution and extern-rebinding diagnostics still hold after specialization and primitive retirement.
- [ ] Imported `std/phase` is the only public review-loop authoring surface.
- [ ] The public surface still accepts the current keyword operands and caller-supplied `:returns`.
- [ ] After specialization, lowering proceeds only through ordinary generated helpers, ordinary calls, ordinary `loop/recur`, ordinary `match`, and ordinary structured-result forms.
- [ ] Generic typed exhaustion projection exists and is exercised by the imported stdlib route.
- [ ] Managed hidden write roots stay compiler-owned on the generated helper boundary and never become public caller inputs.
- [ ] No runtime `ProcRef`, provider ref, or prompt ref value appears in executable state.
- [ ] Source maps cover the authored call site, stdlib macro frame, specialization origin, generated helper, and generated hidden path/input origins.
- [ ] Migration-facing tests prove the new route no longer depends on the retired primitive path.

## Explicit Non-Goals

- Do not touch `orchestrator/workflow/` runtime execution or shared validation behavior for this item.
- Do not add command bundle-path authority work, reusable-state validation, workflow input defaults, or parity-report machinery here.
- Do not replace the caller-owned `:returns` contract with a standardized stdlib-owned result union in this slice.
- Do not introduce runtime callable transport, runtime closures, report parsing, pointer authority changes, or uncertified shell/Python adapters.
