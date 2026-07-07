# Runtime-Native Drain Compiler / Private-Context / Stdlib Composition Report

Status: diagnostic report
Created: 2026-07-02
Scope: active `workflow_lisp_runtime_native_drain_authoring.md` drain run, selected gap `workflow-lisp-design-delta-work-item-private-phasectx-boundary`

## Purpose

This report records the current situation behind the slow progress on the runtime-native drain target. It is not a new target design and does not redefine Workflow Lisp semantics. It documents the concrete compiler/private-context/stdlib composition problem that the active workflow is working through, why it matters, what appears partially addressed, and what tasks remain before the current gap can honestly be considered complete.

The active run is:

- Run id: `20260702T121602Z-fpq40u`
- Workflow: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- Current selected gap: `workflow-lisp-design-delta-work-item-private-phasectx-boundary`
- Current state at time of writing: run alive, iteration 7 implementation in progress, no accepted implementation-review outcome yet.

## Governing Context

The target design asks the Design Delta `.orc` family to move away from YAML-shaped path and carrier choreography toward ordinary typed composition:

- public authoring should not expose `RunCtx`, `PhaseCtx`, generated write roots, checkpoint paths, runtime state roots, or generated bundle targets;
- internal calls may receive private context supplied by lowering/runtime;
- stdlib helpers such as `std/phase` and `std/drain` should compose through ordinary imports and specialization, not compiler branches keyed to one workflow family;
- typed returns, projections, resource transitions, publication, and compatibility bridges should remain separate concepts;
- completion requires retiring transitional private/path carriers from ordinary composition, not merely hiding them better.

The current gap narrows that into one active requirement: make the Design Delta work-item route compile and validate with `run-work-item`'s `PhaseCtx` private, while keeping selected-item stdlib calls on a fixed typed-payload contract and not reintroducing public or hidden `run_state_path` carriers to get past compile failures.

## What Went Wrong

The workflow initially looked like it was blocked on a narrow Design Delta boundary issue, but the implementation exposed a broader shared compiler problem. The compiler can handle many individual pieces, but the combination below is still fragile:

1. an imported stdlib procedure, especially `std/phase::review-revise-loop-proc`;
2. procedure specialization through proc refs and concrete caller payload types;
3. generated loop-state carrier types;
4. WCC lowering / defunctionalization into private workflow or loop machinery;
5. generated managed write roots and output bundles;
6. parent workflows consuming child workflow results while private context stays off the public boundary.

The observed failures are not well explained as a Design Delta family bug. They are signs that the shared Workflow Lisp pipeline is not yet carrying the same ownership/type/private-context facts through every stage.

## Concrete Failure Modes Observed

### 1. Imported stdlib specialization loses the correct owner type environment

The active gap plan already records failures around imported `std/phase` specialization. The symptom is that a specialized stdlib procedure body needs to resolve types from its defining module, from generated loop-state carriers, and from the caller's concrete payload records.

In practice, the compiler has been touching these areas:

- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/procedure_typecheck.py`
- `orchestrator/workflow_lisp/specialization_typecheck.py`
- `orchestrator/workflow_lisp/procedure_specialization.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/compiler.py`

The implementation stream showed new tests for imported `std/phase::review-revise-loop-proc` specializations. That is the right direction: the fix should be generic owner-environment handling for imported stdlib procedures, not a Design Delta-specific exception.

### 2. Generated loop-state carrier types are not stable enough across specialization and validation

A key failure observed in the stream was:

```text
workflow_return_not_exportable
`loop/recur` could not project `state__completed__plan_path` from `NameExpr`
in `std/phase.orc` at `defproc review-revise-loop-proc`
```

The important part is not the literal field name. The problem is that a generated loop-state carrier produced by specialization/lowering must remain:

- resolvable in the correct module/type environment;
- exportable through Stage 3 shared validation;
- source-mapped to the authored stdlib/caller structure;
- distinct when the same imported stdlib procedure is specialized more than once with different caller payload types.

The active implementation added or edited tests around multiple imported `std/phase` review-loop specializations with distinct loop-state carriers. That suggests the current fix is aiming at the right general case.

### 3. Private managed write roots leak or lose wiring when stdlib calls become generated private workflows

The stream showed assertions around generated `__managed_write_roots` steps. The expected shape is that managed write-root bundle paths in lowered private/generated workflows use `${inputs.<name>}` and that the input name exists on the lowered workflow boundary.

That matters because private runtime context is supposed to be hidden from the public authored boundary, but it still must be present as executable context for generated runtime operations. If generated private workflows refer to write roots or bundle paths that are not bound as executable inputs, the compiler can appear to have hidden the value while actually producing an unrunnable lowered graph.

The implementation has touched:

- `orchestrator/workflow_lisp/lowering/generated_paths.py`
- `orchestrator/workflow_lisp/lowering/context.py`
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow_lisp/lowering/procedures.py`
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`

This is relevant target-design work only if it produces a generic private-context transport path. It would not be progress if it merely added another Design Delta bridge or carrier.

### 4. Parent/child workflow call lowering must propagate private inputs without making them authored inputs

The current target design wants call sites like `run-work-item item` or imported stdlib calls to behave like typed composition. The implementation detail is harder: a child workflow may need generated write roots, private context, bundle targets, or resource context, but the caller should not expose those as ordinary public/domain parameters.

The active implementation touched workflow-call lowering, suggesting this path is still being fixed. The expected final behavior is:

- public authored workflow inputs stay domain-shaped;
- generated/private inputs exist only in executable lowered workflow boundaries;
- call-site lowering supplies those generated/private inputs deterministically;
- build artifacts and source maps explain the generated bindings;
- runtime validation sees the executable contract without treating private context as user-provided data.

### 5. Verification has expanded because the failure crosses module boundaries

The current dirty diff shows changes across compiler modules and tests, including:

- procedure and specialization tests;
- Design Delta feasibility tests;
- build artifact tests;
- WCC/lowering modules;
- stdlib resource/drain modules.

This is why the implementation is slow. The selected gap looked narrow, but the failure path crosses imported stdlib, WCC, lowering, executable inputs, generated paths, and build artifacts.

## Why This Matters

This is a direct dependency of the runtime-native drain target. If it is not fixed generically, the project has only bad options:

- reintroduce public `PhaseCtx`, `RunCtx`, `run_state_path`, or generated path inputs;
- add compiler special cases for Design Delta or `std/phase`;
- preserve compatibility bridge/carrier machinery inside ordinary composition;
- keep the `.orc` family compiling only through brittle fixture-specific paths;
- treat rendered files or state paths as semantic authority again.

Any of those would defeat the authoring goal of the target design. The target is not merely to make the current fixture compile. The target is to make ordinary imported stdlib composition work while runtime context and generated paths remain private implementation details.

## Current Evidence

At time of writing:

- The active workflow is still running and has not reached implementation review.
- The current iteration is still iteration 7.
- No accepted commit has landed for the active compiler fix.
- The stream shows active work on:
  - imported `std/phase::review-revise-loop-proc` specialization;
  - distinct loop-state carriers for multiple imported specializations;
  - managed write-root input wiring in lowered workflows;
  - Design Delta feasibility/build-artifact test coverage.
- The dirty diff relative to `HEAD` includes shared Workflow Lisp compiler/lowering modules and tests. That is in-flight work, not completed target progress.

## Work That Appears Partially Addressed

These items appear to be in progress, but should not be considered complete until the implementation review approves them and verification passes:

1. **Owner environment selection for imported procedure specializations**
   - likely direction: carry or recover the defining module's type environment for imported typed procedures and generated specializations.
   - risk: adding aliases or fallback resolution that masks the real owner boundary.

2. **Generated loop-state carrier identity**
   - likely direction: make generated loop-state carrier types stable, owner-qualified, and resolvable after specialization.
   - risk: fixing only `std/phase::review-revise-loop-proc` by name.

3. **Managed write-root executable input propagation**
   - likely direction: ensure private/generated workflow steps bind output bundles through executable inputs rather than dangling path expressions.
   - risk: exposing those inputs as public authored parameters.

4. **Workflow-call lowering for generated private inputs**
   - likely direction: have parent call lowering supply private child inputs through executable contract machinery.
   - risk: threading hidden carriers through domain records or family wrappers.

5. **Build artifact evidence for private/generated inputs**
   - likely direction: build artifacts should show the generated private inputs and source-map lineage.
   - risk: turning build artifact checks into stale manifest bookkeeping rather than executable contract checks.

## Outstanding Tasks

### Task 1: Finish and verify generic owner-env propagation

The compiler should use the correct type environment for imported typed procedures and their generated specializations. The result should support:

- imported `std/phase` procedures;
- local caller payload records;
- generated loop-state carrier types;
- multiple distinct specializations of the same imported procedure in one caller graph.

Acceptance evidence should include focused tests where two call sites specialize the same imported stdlib procedure with different payload shapes and both compile without type or carrier collision.

### Task 2: Make loop-state carriers first-class compiler artifacts

Generated loop-state carriers need stable identity across:

- specialization;
- WCC elaboration;
- defunctionalization;
- shared validation;
- executable lowering;
- source-map/build-artifact output.

The compiler should not infer loop-state validity from generated field names alone. It should preserve enough typed structure to know which loop-state fields are active, exportable, and owned by which generated/specialized procedure.

### Task 3: Keep private context private while making generated workflows runnable

The fix must prove that generated managed write roots and private runtime context:

- are not public authored workflow inputs;
- are present on executable generated/private workflow boundaries when needed;
- are supplied by caller lowering/runtime mechanics;
- are visible in source maps/build artifacts as private generated inputs;
- cannot be used as semantic domain payload fields to satisfy user-facing contracts.

### Task 4: Validate parent-to-child call input propagation

When a parent calls an imported stdlib/private workflow route, lowering must supply both authored semantic arguments and generated/private executable arguments. This should be covered by a fixture that:

- calls an imported stdlib procedure from a parent workflow;
- produces generated private workflow or loop steps;
- has at least one generated managed write-root step;
- verifies the generated step's bundle path references a real executable input.

### Task 5: Re-run actual Design Delta work-item feasibility

The generic tests are necessary but not sufficient. The selected gap only closes when the Design Delta work-item route compiles and validates with:

- no public `PhaseCtx`;
- no public `RunCtx`;
- no public or hidden `run_state_path` carrier introduced for this slice;
- private work-item binding such as `phase-ctx__work-item` still represented as private runtime context;
- no reintroduced compatibility bridge as an internal semantic dependency.

### Task 6: Check stdlib guard suites

Because the fix touches shared stdlib/procedure/lowering paths, the relevant stdlib guard suites must remain green. The minimum useful coverage is:

- focused procedure-specialization tests;
- stdlib phase/review-loop tests;
- stdlib drain tests affected by child-call/loop lowering;
- build-artifact tests for generated private inputs;
- Design Delta feasibility tests for the selected work-item route.

### Task 7: Commit only after reviewable evidence exists

The current working tree contains both workflow-mechanics fixes and active implementation edits. The active compiler/private-context fix should land as a coherent slice only after:

- focused tests pass;
- implementation review approves or issues concrete findings;
- unrelated dirty changes are not silently bundled;
- any workflow-mechanics changes are kept in their own commit if still uncommitted.

## Non-Goals For This Fix

This situation should not be resolved by:

- adding public `PhaseCtx`, `RunCtx`, generated roots, checkpoint paths, or `run_state_path` inputs;
- adding a compiler branch keyed to Design Delta, `review-revise-loop`, or a specific generated step name;
- preserving compatibility bridges as internal composition;
- weakening shared validation so generated private values pass without type/source-map provenance;
- replacing the stdlib call with an inline hand-written parent loop;
- treating reports, state-path files, or rendered summaries as semantic authority.

## What Would Count As Resolution

The problem is resolved when all of the following are true:

1. Imported `std/phase` review-loop specialization compiles through ordinary import/specialization machinery.
2. Multiple imported specializations keep distinct loop-state carriers.
3. Generated loop-state fields pass shared validation because their typed owner/provenance is preserved, not because validation was weakened.
4. Generated managed write-root steps use executable private inputs that exist on the lowered workflow boundary.
5. Parent/child workflow calls propagate private executable inputs without exposing them as public authored parameters.
6. The selected Design Delta work-item private `PhaseCtx` route compiles and validates.
7. Build artifacts/source maps expose the generated private bindings clearly enough for diagnostics and review.
8. No public or hidden `run_state_path` carrier is reintroduced as the solution.
9. The implementation review approves the slice.
10. The workflow advances past the current implementation/review stage without retrying the same stale blocker.

## If It Blocks Again

If the active implementation blocks again, the recovery should depend on the blocker class:

- If the blocker is another concrete shared compiler limitation, classify it as a prerequisite compiler-contract gap or revise the current gap architecture to include it explicitly.
- If the blocker is stale recovered-gap evidence, fix deterministic recovery mechanics rather than asking a provider to infer freshness.
- If the blocker is a contradiction in the gap plan, revise the gap design/plan to remove or split the stale assumption.
- If the blocker is only missing broad evidence, keep it bounded to checks that prove the executable contract, not manifest or fixture bookkeeping.

The correct response is not to add more compatibility carriers. The correct response is to make the compiler carry the same typed/private/owner facts through the full path from imported stdlib source to executable runtime contract.
