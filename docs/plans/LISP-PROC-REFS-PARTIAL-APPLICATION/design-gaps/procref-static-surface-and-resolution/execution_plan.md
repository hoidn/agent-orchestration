# ProcRef Static Surface And Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded compile-time `ProcRef[...]` surface for Workflow Lisp so procedure references parse, resolve through existing module/procedure catalogs, typecheck as compile-time-only values, and are rejected at runtime transport seams without adding `bind-proc`, specialization, or executable proc-ref lowering.

**Architecture:** Reuse the existing `WorkflowRef` shape where it helps, but keep the ProcRef slice narrower. Add one frontend-owned `procedure_refs.py` authority layer, extend the parser/type environment with `ProcRefTypeExpr` and `ProcRefTypeRef`, elaborate `(proc-ref ...)` literals through the existing procedure-name canonicalization path, and reject `ProcRef` values anywhere they would cross workflow boundaries, collections, records/unions, or `loop/recur` state. Do not add runtime procedure values, proc-ref calls, specialization, or lowering support in this tranche.

**Tech Stack:** Python 3 dataclasses, `orchestrator.workflow_lisp` compiler/typecheck/modules/procedures infrastructure, canonical callable keys in `orchestrator.workflow_lisp.modules`, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as authoritative for execution:

- `docs/index.md`
- `docs/steering.md`
  - currently empty in this checkout; do not treat that as permission to widen scope
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
  - `Syntax Delta`
  - `Typechecking Rules`
  - `Module And Catalog Behavior`
  - `Source Maps And Diagnostics`
  - `Relationship To WorkflowRef`
- `docs/design/workflow_lisp_frontend_specification.md`
  - module/import authority and canonical callable identity
  - typed procedural authoring and compile-time-only reference rules
  - runtime-boundary and source-map constraints
- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/work_instructions.md`
- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-static-surface-and-resolution/implementation_architecture.md`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-20260528T215013Z/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-20260528T215013Z/iterations/0/selector/selection.json`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-20260528T215013Z/iterations/0/design-gap-architect/check_commands.json`
- `state/LISP-PROC-REFS-PARTIAL-APPLICATION/progress_ledger.json`
  - currently `{"ledger_version": 1, "events": []}`; there is no prior ProcRef execution history to reconcile

Reference current seams before editing:

- `orchestrator/workflow_lisp/type_expressions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/loops.py`
- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/README.md`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_collection_types.py`
- `tests/test_workflow_lisp_loop_recur.py`

## Current Checkout Baseline

- The checkout already implements the full compile-time `WorkflowRef` path:
  - `WorkflowRefTypeExpr` parsing in `type_expressions.py`
  - `WorkflowRefTypeRef` plus nested-transport rejection in `type_env.py`
  - `(workflow-ref ...)` literals in `expressions.py`
  - catalog-backed signature resolution in `workflow_refs.py`
  - caller-side typechecking in `typecheck.py`
  - top-level workflow-boundary exceptions for `WorkflowRef` in `workflows.py`
- There is no `ProcRef`, `proc-ref`, `procedure_refs.py`, or proc-ref-specific diagnostic coverage in the current implementation.
- Procedure identity already flows through canonical callable keys using `ModuleImportScope.resolve_procedure_name(...)` and compiler-owned `_procedure_name_resolver(...)`; reuse that path rather than adding a second procedure-identity scheme.
- `build_procedure_catalog(...)` already resolves procedure signatures against `TypeRef`; once `ProcRefTypeRef` exists, procedure signatures can carry it without inventing a new catalog type.
- `docs/steering.md` is empty and the progress ledger is empty; there is no local steering or prior implementation event that overrides this work item.

## Hard Scope Limits

Implement only this bounded slice:

- `ProcRef[...]` parsing, including `ProcRef[() -> R]`
- `ProcRefTypeRef` resolution in the frontend type environment
- `(proc-ref name)` literal elaboration with source-mapped authored spans
- compile-time resolution of visible same-module and imported-exported `defproc` signatures
- targeted diagnostics for:
  - `proc_ref_unknown`
  - `proc_ref_literal_required`
  - `proc_ref_signature_invalid`
  - `proc_ref_runtime_transport_forbidden`
  - `proc_ref_private_import_invalid`
- runtime-transport rejection across workflow boundaries, collections, records/unions, and `loop/recur` state

Explicit non-goals:

- no `bind-proc`
- no residual-signature computation
- no calling through proc-ref values
- no specialization, generated hidden procedures, or lowering support for executable proc-ref calls
- no runtime procedure values, serialization, ledgers, provider-selected procedures, or dynamic dispatch
- no workflow YAML, prompt, adapter, or runtime-engine changes

Required deferrals:

- Do not add `proc_ref_binding_unknown`, `proc_ref_binding_duplicate`, `proc_ref_binding_type_invalid`, or `proc_ref_specialization_cycle` in this gap unless a shared helper needs a stub that remains unused. Those belong to later `bind-proc` and specialization work.

## File Map

Create:

- `orchestrator/workflow_lisp/procedure_refs.py`
- `tests/fixtures/workflow_lisp/valid/proc_ref_static_surface.orc`
- `tests/fixtures/workflow_lisp/invalid/proc_ref_literal_required.orc`
- `tests/fixtures/workflow_lisp/invalid/proc_ref_runtime_transport_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/proc_ref_signature_invalid.orc`
- `tests/fixtures/workflow_lisp/modules/valid/proc_refs/imported_entry.orc`
- `tests/fixtures/workflow_lisp/modules/valid/proc_refs/imported_helper.orc`
- `tests/fixtures/workflow_lisp/modules/invalid/proc_refs/private_entry.orc`
- `tests/fixtures/workflow_lisp/modules/invalid/proc_refs/private_helper.orc`

Modify:

- `orchestrator/workflow_lisp/type_expressions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/loops.py`
- `orchestrator/workflow_lisp/README.md`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_collection_types.py`
- `tests/test_workflow_lisp_loop_recur.py`

Modify only if a failing proc-ref test proves it necessary:

- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/lowering.py`

## Locked Decisions

- `ProcRef` is compile-time-only in this tranche.
- Bare procedure names are not proc-ref values; authored values must use `(proc-ref ...)`.
- Imported exported procedures are referenceable; imported private procedures must fail with `proc_ref_private_import_invalid`.
- Workflow boundaries must reject `ProcRef` everywhere, including top-level workflow params. Do not copy the existing `WorkflowRef` top-level exception into ProcRef.
- No unresolved proc-ref value may reach lowered workflow boundaries, loop-carried runtime state, record/union payloads, artifacts, or result bundles.
- If a proc-ref value survives far enough that executable lowering would need specialization, fail early with a targeted compile-time diagnostic rather than inventing a runtime fallback.
- No orchestrator/demo smoke run is required for this item because it does not modify workflow YAML, prompts, artifact contracts, or provisioning surfaces.

### Task 1: Lock The Static ProcRef Test Surface First

**Files:**

- Create: `tests/fixtures/workflow_lisp/valid/proc_ref_static_surface.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/proc_ref_literal_required.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/proc_ref_runtime_transport_invalid.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/proc_ref_signature_invalid.orc`
- Create: `tests/fixtures/workflow_lisp/modules/valid/proc_refs/imported_entry.orc`
- Create: `tests/fixtures/workflow_lisp/modules/valid/proc_refs/imported_helper.orc`
- Create: `tests/fixtures/workflow_lisp/modules/invalid/proc_refs/private_entry.orc`
- Create: `tests/fixtures/workflow_lisp/modules/invalid/proc_refs/private_helper.orc`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_collection_types.py`
- Modify: `tests/test_workflow_lisp_loop_recur.py`

- [ ] **Step 1: Add direct parser and type-environment coverage for `ProcRef[...]`**

In `tests/test_workflow_lisp_collection_types.py`, add tests that:

- parse `ProcRef[WorkflowInput -> WorkflowOutput]`
- parse `ProcRef[(WorkflowInput WorkflowOutput) -> String]`
- parse `ProcRef[() -> String]`
- resolve those parsed types to `ProcRefTypeRef`
- reject `List[ProcRef[...]]`, `Optional[ProcRef[...]]`, and `Map[String, ProcRef[...]]` with `proc_ref_runtime_transport_forbidden`

- [ ] **Step 2: Add same-file and imported-resolution procedure tests**

In `tests/test_workflow_lisp_procedures.py` and `tests/test_workflow_lisp_modules.py`, add focused tests that prove:

- a `defproc` signature may include a `ProcRef[...]` parameter
- `(proc-ref helper)` resolves to the canonical same-module procedure key
- `(proc-ref helper/exported)` resolves to an imported exported canonical key
- a non-literal argument in a `ProcRef[...]` position raises `proc_ref_literal_required`
- a mismatched referenced signature raises `proc_ref_signature_invalid`
- an explicitly imported but non-exported procedure raises `proc_ref_private_import_invalid`

- [ ] **Step 3: Add runtime-transport rejection tests at workflow and loop seams**

In `tests/test_workflow_lisp_workflows.py` and `tests/test_workflow_lisp_loop_recur.py`, add invalid-compile tests that prove:

- top-level workflow params of type `ProcRef[...]` are rejected
- workflow return types, record fields, and union payloads cannot transport `ProcRef`
- `loop/recur` carried state and `done` results cannot carry `ProcRef`

- [ ] **Step 4: Collect the touched tests before implementation**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_collection_types.py tests/test_workflow_lisp_loop_recur.py -q
```

Expected: the new `proc_ref` tests collect cleanly.

- [ ] **Step 5: Run the narrow failing selectors**

Run:

```bash
pytest tests/test_workflow_lisp_collection_types.py -k proc_ref -q
pytest tests/test_workflow_lisp_procedures.py -k proc_ref -q
pytest tests/test_workflow_lisp_modules.py -k proc_ref -q
pytest tests/test_workflow_lisp_workflows.py -k proc_ref -q
pytest tests/test_workflow_lisp_loop_recur.py -k proc_ref -q
```

Expected: failures point to missing ProcRef parser/typecheck/resolution logic, not unrelated shared-runtime issues.

### Task 2: Add `ProcRef[...]` Parsing And Type Resolution

**Files:**

- Modify: `orchestrator/workflow_lisp/type_expressions.py`
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`

- [ ] **Step 1: Extend parsed type expressions with a dedicated ProcRef node**

Add `ProcRefTypeExpr` to `type_expressions.py` and extract the current callable-ref parameter parsing into a shared helper that supports:

- `WorkflowRef`: one or more parameter types required
- `ProcRef`: zero or more parameter types allowed

Keep the existing `WorkflowRef[...]` grammar and diagnostics stable while adding `ProcRef[() -> R]`.

- [ ] **Step 2: Add `ProcRefTypeRef` and keep transport diagnostics kind-specific**

In `type_env.py`:

- add `ProcRefTypeRef` to `TypeRef`
- resolve proc-ref parameter and return types through the existing `FrontendTypeEnvironment`
- allow any resolved `TypeRef` as the proc-ref return type
- reject nested transport of `ProcRef` inside collections, records, unions, and any other runtime surfaces with `proc_ref_runtime_transport_forbidden`
- keep workflow-ref diagnostics on the workflow-ref path; do not collapse both features into one shared error code

- [ ] **Step 3: Update compiler-side parsed-type validation**

Extend `compiler.py` so `_validate_parsed_field_type(...)` and any exhaustive `ParsedTypeExpr` handling understand `ProcRefTypeExpr`. The validator should recurse into proc-ref parameter and return subexpressions without pretending proc refs are ordinary named types.

- [ ] **Step 4: Run the parser/type tests**

Run:

```bash
pytest tests/test_workflow_lisp_collection_types.py -k proc_ref -q
```

Expected: the parser accepts the three ProcRef shapes, and nested transport cases now fail with `proc_ref_runtime_transport_forbidden`.

### Task 3: Elaborate `(proc-ref ...)` Literals And Resolve Them Through Procedure Catalog Authority

**Files:**

- Create: `orchestrator/workflow_lisp/procedure_refs.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/modules.py` only if direct import-scope introspection is required

- [ ] **Step 1: Add an authored proc-ref literal AST node**

In `expressions.py`:

- add `ProcRefLiteralExpr`
- dispatch `proc-ref` in the main elaboration switch
- mirror the span, form-path, and expansion-stack behavior of `WorkflowRefLiteralExpr`
- resolve the authored symbol through `_ACTIVE_PROCEDURE_NAME_RESOLVER` so local and imported names canonicalize before later checks

- [ ] **Step 2: Implement the compile-time proc-ref authority layer**

Create `procedure_refs.py` with the minimal shapes and helpers needed now:

- `ProcRefAuthoritySource`
- `ResolvedProcRef`
- `ProcRefRequirement`
- `proc_ref_type_from_signature(...)`
- `proc_ref_target_name(...)`
- `validate_proc_ref_signature(...)`
- `resolve_proc_ref_name(...)`
- `resolve_proc_ref_expr(...)`

This module must use the existing `ProcedureCatalog` and canonical procedure names as authority. It must not create any runtime registry or lowering plan.

- [ ] **Step 3: Distinguish unknown targets from private imported targets**

If current import-scope data is insufficient, add the smallest helper needed in `modules.py` so proc-ref resolution can tell the difference between:

- a procedure that truly does not exist: `proc_ref_unknown`
- a procedure in an explicitly imported module that is present but not exported: `proc_ref_private_import_invalid`

Do not change ordinary procedure-call resolution semantics while doing this.

- [ ] **Step 4: Run the resolution-focused tests**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py -k proc_ref -q
pytest tests/test_workflow_lisp_modules.py -k proc_ref -q
```

Expected: same-file and imported exported proc refs resolve, and private imported targets fail with the dedicated diagnostic.

### Task 4: Typecheck ProcRef Values And Reject Runtime Transport

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/loops.py`
- Modify: `orchestrator/workflow_lisp/procedures.py` only if a failing test proves catalog or signature plumbing needs a focused change
- Modify: `orchestrator/workflow_lisp/lowering.py` only if a proc-ref literal still leaks past typecheck into lowering

- [ ] **Step 1: Add a proc-ref argument/typecheck helper parallel to workflow refs**

In `typecheck.py`, add `_typecheck_proc_ref_argument(...)` and direct `ProcRefLiteralExpr` handling so:

- a literal proc ref infers its exact `ProcRefTypeRef` from the resolved procedure signature
- a `NameExpr` already bound to `ProcRefTypeRef` is treated as a forwarded compile-time proc ref
- any non-literal/non-forwarded value in a proc-ref position raises `proc_ref_literal_required`
- a mismatched supplied proc ref raises `proc_ref_signature_invalid`

- [ ] **Step 2: Keep ProcRef support bounded to procedure-parameter positions**

Allow `ProcedureCallExpr` parameters typed as `ProcRefTypeRef`, but do not add support for:

- using a proc-ref value as a `ProcedureCallExpr` callee
- using proc refs in workflow `call` bindings
- any specialization or executable call-through behavior

If a proc-ref survives far enough that executable lowering would require those behaviors, fail early rather than widening scope.

- [ ] **Step 3: Reject ProcRef at workflow boundaries and loop state**

In `workflows.py` and `loops.py`:

- treat `ProcRefTypeRef` as non-lowerable everywhere
- reject top-level workflow params, returns, nested record/union payloads, and loop-carried state/results with `proc_ref_runtime_transport_forbidden`
- leave the current `WorkflowRef` top-level exception intact for workflow refs only

- [ ] **Step 4: Run the bounded runtime-seam tests**

Run:

```bash
pytest tests/test_workflow_lisp_workflows.py -k proc_ref -q
pytest tests/test_workflow_lisp_loop_recur.py -k proc_ref -q
```

Expected: all runtime-boundary and loop transport cases fail with `proc_ref_runtime_transport_forbidden`, while the pure procedure/module proc-ref tests continue to pass.

### Task 5: Update The Code Map And Run The Required Verification Set

**Files:**

- Modify: `orchestrator/workflow_lisp/README.md`

- [ ] **Step 1: Document the new frontend-owned authority layer**

Update `orchestrator/workflow_lisp/README.md` so the code map mentions `procedure_refs.py` and makes clear that ProcRef support is currently limited to the static compile-time surface, with specialization and lowering intentionally deferred.

- [ ] **Step 2: Run the full required verification modules from the work item**

Run:

```bash
pytest tests/test_workflow_lisp_procedures.py
pytest tests/test_workflow_lisp_modules.py
pytest tests/test_workflow_lisp_workflows.py
pytest tests/test_workflow_lisp_collection_types.py
pytest tests/test_workflow_lisp_loop_recur.py
```

Expected: all five modules pass, satisfying `check_commands.json`.

- [ ] **Step 3: Record implementation evidence in the handoff**

When execution is complete, record:

- which files were created or modified
- which diagnostics were added or reused
- which pytest commands were run
- whether any fallback change to `modules.py`, `procedures.py`, or `lowering.py` was required

Do not claim ProcRef specialization, `bind-proc`, executable proc-ref lowering, or source-map coverage for generated specializations; those belong to later gaps.
