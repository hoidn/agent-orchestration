# ProcRef Bind-Proc Specialization And Lowering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the remaining compile-time `ProcRef` pipeline so Workflow Lisp supports keyword-only `bind-proc`, residual `ProcRef[...]` signatures, lexical invocation through ProcRef bindings, deterministic specialized `defproc` generation before executable lowering, and lowered workflows with no unresolved ProcRef values.

**Architecture:** Extend the existing static ProcRef surface rather than inventing a second callable model. Add a dedicated `BindProcExpr`, resolve bound ProcRef values through `procedure_refs.py`, materialize compiler-owned specialized `TypedProcedureDef` variants during stage-3 effect inference, and then reuse the existing `defproc` inline/private-workflow lowering path with specialization metadata and compile-time substitutions. ProcRef values remain compile-time-only throughout; no runtime procedure values, adapters, or dynamic dispatch are introduced.

**Tech Stack:** Python 3 dataclasses, `orchestrator.workflow_lisp` expression/typecheck/compiler/lowering modules, canonical callable keys from module/procedure catalogs, Stage 3 effect-summary fixpoint logic, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as authoritative for execution:

- `docs/index.md`
- `docs/steering.md`
  - currently empty in this checkout; do not widen scope because of that
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
  - `Partial Application`
  - `Typechecking Rules`
  - `Specialization Rules`
  - `Lowering Rules`
  - `Effect Rules`
  - `Source Maps And Diagnostics`
  - `Acceptance Tests`
- `docs/design/workflow_lisp_frontend_specification.md`
  - compile-time-only reference rules
  - `defproc` lowering rules
  - source-map ownership on authored forms
  - effect visibility and typed procedural composition
- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md`
- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-static-surface-and-resolution/implementation_architecture.md`
- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-bind-proc-specialization-lowering/implementation_architecture.md`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-20260528T215013Z/iterations/1/selector/selection.json`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-20260528T215013Z/iterations/1/design-gap-architect/work_item_context.md`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-20260528T215013Z/iterations/1/design-gap-architect/check_commands.json`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/progress_ledger.json`
  - currently `{"ledger_version": 1, "events": []}`; there is no prior ProcRef specialization work to reconcile

Reference current seams before editing:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/procedure_refs.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/README.md`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_collection_types.py`
- `tests/test_workflow_lisp_loop_recur.py`

## Current Checkout Baseline

Assume this exact starting state:

- The static ProcRef tranche is already implemented:
  - `ProcRefTypeExpr` parsing in `type_expressions.py`
  - `ProcRefTypeRef` and transport rejection in `type_env.py`
  - `(proc-ref ...)` literal elaboration in `expressions.py`
  - literal resolution and signature validation in `procedure_refs.py`
  - ProcRef argument checking in `typecheck.py`
- `procedure_refs.py` currently resolves only literal or forwarded ProcRef names. It does not model partial application, residual signatures, specialization keys, or nested compile-time ProcRef values.
- `expressions.py` only elaborates list heads as procedure calls when the head is already a known procedure name. A lexical binding in call-head position still fails during elaboration, which blocks ProcRef parameter invocation.
- `typecheck.py` accepts ProcRef literals or forwarded `NameExpr` bindings as arguments to `ProcRef[...]` parameters, but it has no `BindProcExpr` node, no ProcRef-specific residual-signature path, and no branch for call-through via a bound ProcRef callee.
- `_infer_stage3_effect_summaries(...)` in `compiler.py` only iterates over authored procedure names and direct `ProcedureCallExpr.callee_name` dependencies. There is no specialization registry or ProcRef cycle graph.
- `lowering.py` already has workflow-ref specialization support and a workflow-ref-only `_specialize_typed_procedure(...)`, but procedure specialization still happens late, only for workflow refs, and provenance/local-value propagation only knows about `workflow_ref_bindings`.
- `orchestrator/workflow_lisp/README.md` still says ProcRef support is static only and that specialization plus executable proc-ref lowering remain deferred.
- `docs/steering.md` is empty and the progress ledger is empty; there is no local steering override or prior event that narrows this selected gap further.

## Hard Scope Limits

Implement only this bounded slice:

- `bind-proc` as a keyword-only frontend form
- residual `ProcRef[...]` signature computation after keyword binding
- compile-time ProcRef value resolution across:
  - direct `(proc-ref ...)` literals
  - forwarded ProcRef lexical bindings
  - nested `bind-proc` values
- lexical invocation through ProcRef-bound call heads inside `defproc` and `defworkflow` bodies
- compiler-owned deterministic specialized `TypedProcedureDef` materialization before executable lowering
- stage-3 effect inference and cycle detection that account for specialized procedures
- lowering that reuses existing inline/private-workflow `defproc` machinery after ProcRef specialization
- source-map/provenance coverage for `proc-ref`, `bind-proc`, specializing call sites, and generated specialized procedures

Explicit non-goals:

- no runtime first-class procedures, closures, or serialization
- no arbitrary computed callee expressions such as `((bind-proc ...) value)`
- no positional partial application, defaults, or variadic keyword bags
- no ProcRef transport through workflow boundaries, records, unions, artifacts, ledgers, provider results, command results, or loop runtime state
- no workflow YAML, prompt, adapter, or runtime-engine changes
- no command adapters, scripts, or runtime-native effects to fake specialization semantics
- no unrelated refactor of general workflow-ref behavior outside narrow shared-helper reuse

## Non-Negotiable Rules

Do not re-decide any of these while executing:

- ProcRef values are compile-time-only in this tranche.
- `bind-proc` specializes before Core AST / Semantic IR / executable lowering; lowered workflows must not contain unresolved ProcRef values.
- Bare procedure names are still not ProcRef values; authored ProcRef values must come from `(proc-ref ...)`, a forwarded ProcRef binding, or a prior `bind-proc`.
- The only new callable surface is a lexical bound name in procedure-call position. Do not widen to arbitrary callee expressions.
- `defproc :lowering` remains authoritative after specialization:
  - `inline` specializes first, then inlines
  - `private-workflow` specializes first, then emits the existing private workflow shape if boundary checks pass
  - `auto` specializes first, then chooses using the existing heuristics
- Preserve effect visibility. Specialization may reuse existing effect summaries, but it must not hide provider, command, workflow, or state effects.
- Preserve existing WorkflowRef behavior unless a failing ProcRef test proves a small shared-helper extraction is necessary.
- No orchestrator/demo smoke run is required for this item because it does not change workflow YAML, prompts, provisioning, artifact contracts, or demo trial mechanics.

## File Map

Create:

- `tests/fixtures/workflow_lisp/valid/proc_ref_bind_proc_forwarding.orc`
- `tests/fixtures/workflow_lisp/invalid/proc_ref_specialization_cycle.orc`

Modify:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/procedure_refs.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/README.md`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_workflows.py`

Modify only if a failing test proves it necessary:

- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/__init__.py`
- `tests/test_workflow_lisp_collection_types.py`
- `tests/test_workflow_lisp_loop_recur.py`

## Required Diagnostics

Add or activate these codes for this slice:

- `proc_ref_binding_unknown`
- `proc_ref_binding_duplicate`
- `proc_ref_binding_type_invalid`
- `proc_ref_specialization_cycle`

Preserve and continue using these existing ProcRef diagnostics:

- `proc_ref_unknown`
- `proc_ref_literal_required`
- `proc_ref_signature_invalid`
- `proc_ref_runtime_transport_forbidden`
- `proc_ref_private_import_invalid`

If a lexical call head resolves to a non-ProcRef binding, keep the failure anchored at the authored call site. Do not let it degrade into an opaque lowering-time error.

### Task 1: Lock The `bind-proc` And Specialization Regression Surface First

**Files:**

- Create: `tests/fixtures/workflow_lisp/valid/proc_ref_bind_proc_forwarding.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/proc_ref_specialization_cycle.orc`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_workflows.py`

- [ ] **Step 1: Add one valid fixture that exercises the full authored surface**

Create `tests/fixtures/workflow_lisp/valid/proc_ref_bind_proc_forwarding.orc` with a minimal higher-order procedure stack that proves:

- a `defproc` parameter can be typed as `ProcRef[...]`
- `let*` can bind `(bind-proc (proc-ref helper) :fixed value ...)`
- the bound ProcRef can be forwarded through another `defproc`
- a lexical ProcRef binding can appear in procedure-call position
- the residual signature preserves original parameter order after removing bound keywords

- [ ] **Step 2: Add negative coverage for keyword validation and cycle detection**

Use a mix of one dedicated fixture and inline `_write_module(...)` test modules to lock down:

- unknown `bind-proc` keywords -> `proc_ref_binding_unknown`
- duplicate `bind-proc` keywords -> `proc_ref_binding_duplicate`
- mistyped bound arguments -> `proc_ref_binding_type_invalid`
- a specialization chain that depends on a specialized version of itself -> `proc_ref_specialization_cycle`

Keep the negative tests narrow. Each test should fail for exactly one reason.

- [ ] **Step 3: Extend neighboring suites instead of creating a new monolithic ProcRef test file**

Add focused assertions to:

- `tests/test_workflow_lisp_procedures.py`
  - elaboration produces `BindProcExpr`
  - typechecking computes the expected residual `ProcRefTypeRef`
  - call-through via a lexical ProcRef binding compiles and merges the selected procedure effects
- `tests/test_workflow_lisp_modules.py`
  - imported exported ProcRefs can be rebound with `bind-proc`
  - canonical imported procedure keys are preserved after specialization
- `tests/test_workflow_lisp_lowering.py`
  - inline lowering eliminates unresolved ProcRef call targets
  - private-workflow lowering reuses a single specialized procedure/private workflow when the specialization key is identical
  - provenance/origin notes include authored `proc-ref`, `bind-proc`, and call-site lineage
- `tests/test_workflow_lisp_workflows.py`
  - a workflow using a ProcRef-specialized procedure still validates with ordinary runtime-facing inputs/outputs

- [ ] **Step 4: Collect the touched tests before implementation**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_workflows.py -q
```

Expected: the new ProcRef/bind-proc tests collect cleanly.

- [ ] **Step 5: Run the narrow failing selectors**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py -k "proc_ref or bind_proc" -q
pytest tests/test_workflow_lisp_modules.py -k "proc_ref or bind_proc" -q
pytest tests/test_workflow_lisp_lowering.py -k "proc_ref or specialization" -q
pytest tests/test_workflow_lisp_workflows.py -k "proc_ref" -q
```

Expected: failures point to missing `bind-proc`, specialization, or lowering logic rather than unrelated runtime regressions.

### Task 2: Add `BindProcExpr` And Compile-Time ProcRef Value Resolution

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/procedure_refs.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add a dedicated frontend AST node for `bind-proc`**

In `expressions.py`:

- add `BindProcExpr`
- store the base ProcRef expression plus authored keyword/value pairs in authored order
- preserve duplicate keywords in the AST so diagnostics can point at the authored form instead of silently normalizing
- elaborate `(bind-proc <expr> :name value ...)` as a dedicated special form

- [ ] **Step 2: Allow lexical bound names to elaborate as procedure calls**

Still in `expressions.py`, relax procedure-call elaboration only enough that:

- known procedure names still elaborate exactly as they do now
- if the list head is a lexical bound name, elaborate it as `ProcedureCallExpr` and let typechecking decide whether that binding is a callable ProcRef
- arbitrary list heads, nested expressions, and computed callees remain rejected

- [ ] **Step 3: Extend `procedure_refs.py` from literal resolution into specialization authority**

Add owned data shapes and helpers for:

- bound ProcRef arguments with stable source identity
- recursively resolved ProcRef values from literals, forwarded names, and `BindProcExpr`
- residual signature computation after removing bound parameters in declaration order
- deterministic specialization-key and specialized-name generation of the form `%proc-ref.<module>.<procedure>.<stable-hash>`

Prefer extending the existing ProcRef helper module instead of scattering specialization logic across `typecheck.py` and `lowering.py`.

- [ ] **Step 4: Run the authored-surface tests**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py -k "proc_ref or bind_proc" -q
```

Expected: elaboration reaches `BindProcExpr` and lexical call-head forms instead of failing immediately in `expressions.py`.

### Task 3: Typecheck `bind-proc`, Materialize Specializations During Stage 3, And Detect ProcRef Cycles

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Typecheck `BindProcExpr` against ProcRef values**

In `typecheck.py`:

- resolve the base expression as a compile-time ProcRef value
- validate each keyword against the referenced procedure parameters
- reject duplicates and type mismatches with the new diagnostic codes
- compute and return the residual `ProcRefTypeRef`
- preserve `EMPTY_EFFECT_SUMMARY` for the `bind-proc` form itself

- [ ] **Step 2: Teach `ProcedureCallExpr` typechecking to branch on callee authority**

When `expr.callee_name` is a lexical binding:

- if the binding type is `ProcRefTypeRef`, resolve the compile-time ProcRef value and treat the call site as a specialization request
- if the binding exists but is not a ProcRef, raise a call-site diagnostic immediately
- otherwise preserve the existing named-procedure path

The typed call must merge:

- argument expression effects
- the specialized callee's transitive effects
- any ordinary procedure-call graph edges needed for later cycle validation

- [ ] **Step 3: Add compiler-owned ProcRef specialization materialization before final effect validation**

In `compiler.py` and `procedures.py`:

- add specialization metadata on `TypedProcedureDef` rich enough to describe base procedure, bound values, residual params, specialized name, and origin spans
- discover ProcRef specialization requests during `_infer_stage3_effect_summaries(...)`
- materialize or reuse deterministic specialized procedures in a registry keyed by specialization identity
- re-run the existing effect-summary fixpoint across authored plus specialized procedures until convergence

- [ ] **Step 4: Extend cycle detection to the specialization graph**

Update `_validate_procedure_effects_and_cycles(...)` so it can distinguish:

- authored recursion -> existing `proc_lowering_cycle`
- ProcRef-triggered specialization recursion -> `proc_ref_specialization_cycle`

Point the ProcRef cycle diagnostic at the authored `bind-proc` or ProcRef-consuming call site that introduced the recursive specialization edge.

- [ ] **Step 5: Run the focused compile/typecheck selectors**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py -k "proc_ref or bind_proc" -q
pytest tests/test_workflow_lisp_lowering.py -k "specialization_cycle or proc_ref" -q
```

Expected: positive ProcRef specialization tests now pass through stage 3, and negative cycle/keyword/type cases fail with the new targeted diagnostics.

### Task 4: Lower Specialized Procedures Through The Existing `defproc` Backends And Preserve Provenance

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/procedure_refs.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_workflows.py`

- [ ] **Step 1: Reuse or generalize the current specialization helper instead of inventing a second lowering path**

In `lowering.py`, either generalize `_specialize_typed_procedure(...)` or introduce a ProcRef-aware sibling that:

- accepts ordinary bound arguments and bound ProcRef values in addition to workflow-ref bindings
- reuses deterministic specialized names produced earlier in the compiler pass
- respects the requested `defproc` lowering mode after specialization

Do not build a new runtime execution path for specialized procedures.

- [ ] **Step 2: Lower lexical ProcRef call sites to concrete specialized procedures**

For `ProcedureCallExpr` with a ProcRef-bound callee:

- resolve or fetch the already-materialized specialized `TypedProcedureDef`
- substitute compile-time bound values into the inline/private-workflow lowering environment
- continue through the existing inline or private-workflow code path with the specialized concrete procedure identity

After this step, no lowered workflow dictionary, generated private workflow, or validation bundle should contain an unresolved ProcRef call target.

- [ ] **Step 3: Preserve provenance and explainability across specialization**

Extend provenance/origin note helpers so generated outputs can explain:

- the original `defproc` definition
- the authored `proc-ref` literal, if present
- the authored `bind-proc` form, if present
- the call site that consumed the ProcRef

Generated specialized procedures and generated private workflows must retain authored spans from the forms that selected the procedure target.

- [ ] **Step 4: Run the lowering-focused selectors**

Run:

```bash
pytest tests/test_workflow_lisp_lowering.py -k "proc_ref or specialization" -q
pytest tests/test_workflow_lisp_workflows.py -k "proc_ref" -q
```

Expected: the lowered call targets are concrete specialized procedure/workflow names, private-workflow reuse stays deterministic, and provenance assertions pass.

### Task 5: Align The Package Map And Run Final Visible Verification

**Files:**

- Modify: `orchestrator/workflow_lisp/README.md`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_workflows.py`

- [ ] **Step 1: Update the package README status line**

Revise `orchestrator/workflow_lisp/README.md` so it no longer claims ProcRef support is static-only. Replace that statement with the implemented boundary:

- `bind-proc` and compile-time specialization are supported
- ProcRef remains compile-time-only
- runtime ProcRef transport and dynamic dispatch remain unsupported

- [ ] **Step 2: Re-run test collection if any tests were added or renamed during implementation**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_workflows.py -q
```

Expected: collection succeeds with the final test names and locations.

- [ ] **Step 3: Run the full relevant verification set**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_collection_types.py tests/test_workflow_lisp_loop_recur.py -q
```

Expected: PASS. Existing static ProcRef transport checks still pass, and the new `bind-proc` specialization behavior is covered without regressions.

- [ ] **Step 4: Record verification evidence in the completion handoff**

When implementation is done, record:

- the exact files changed
- which selectors were run and their outcome
- whether any optional files from the "modify only if necessary" list were touched
- confirmation that no orchestrator/demo smoke run was required because no workflow/prompt/provisioning surfaces changed
