# Workflow Lisp Unified Frontend Design

Status: draft unified design / proposed authoritative frontend contract  
Date: 2026-05-29  
Intended path: `docs/design/workflow_lisp_unified_frontend_design.md`  
Primary owner: Workflow Lisp frontend / workflow validation maintainers  
Target substrate: existing validated workflow loader/runtime, with future Core Workflow AST / Semantic IR integration only where explicitly accepted

## 0. Summary

Workflow Lisp is a typed frontend compiler for authoring deterministic workflows. It is not a second runtime, not a YAML-text generator, and not a mechanism for runtime code loading. Its job is to parse `.orc` source, elaborate high-level authoring forms, typecheck them, preserve effect and authority information, lower them into the existing validated workflow pipeline, and produce source-mapped diagnostics and explainable generated workflow artifacts.

This document merges the prior Workflow Lisp design cluster into one self-contained contract. It preserves the key decisions from the umbrella frontend design, the MVP design, the accepted `ProcRef` / `bind-proc` design, the proposed `let-proc` design, and the deferred runtime-closure boundary. It also clarifies which parts are current, historical, proposed, or deferred.

The central invariant is:

```text
Workflow Lisp may add authoring structure, type information, reusable procedures,
and source-mapped compiler generation, but it must not weaken shared workflow
validation or introduce hidden runtime semantics.
```

The current frontend boundary is:

```text
.orc source
  -> reader / syntax objects
  -> macro expansion and definition collection
  -> module/import/export resolution where supported
  -> type environment construction
  -> expression and definition typechecking
  -> procedure/workflow validation
  -> effect-summary inference
  -> lowering to ordinary workflow dictionaries
  -> shared workflow validation
  -> existing workflow loader/runtime
```

The long-term internal architecture may introduce explicit Core Workflow AST, Semantic IR, and Executable IR layers. Those layers are design targets, not assumptions that every layer already exists as a serialized production artifact.

## 1. Design status and merged-document authority

This document should become the single high-level design authority for Workflow Lisp frontend behavior.

The prior documents should be reclassified as follows:

| Prior document | New role |
| --- | --- |
| `workflow_lisp_frontend_specification.md` | Superseded umbrella / background architecture. Keep for historical rationale and detailed component sketches. |
| `workflow_lisp_frontend_mvp_specification.md` | Historical MVP tranche. Use for the original first-slice acceptance story, not as current feature status. |
| `workflow_lisp_proc_refs_partial_application.md` | Accepted design delta. Fold into this document as the current compile-time procedure-reference contract. |
| `workflow_lisp_let_proc_local_proc_refs.md` | Proposed follow-on delta. Fold into this document as the next compile-time procedure ergonomics feature. |
| `workflow_lisp_runtime_closures_boundary.md` | Deferred acceptance gate. Fold into this document as the runtime-callable-value prohibition and future gate. |

This document is self-contained. A reader should not need the prior files to understand the intended language, compiler boundary, procedure model, or deferred runtime-closure boundary.

## 2. Implementation-status tiers

Use these status labels consistently in design, implementation plans, tests, and review notes.

| Status | Meaning |
| --- | --- |
| Current | Implemented or substantially represented in the active frontend path. Tests and source remain the final authority. |
| Accepted / active target | Design accepted and intended for implementation or already partially implemented, but acceptance tests must still determine completeness. |
| Historical | A prior tranche description that may be stale as a status source. Useful for rationale only. |
| Proposed | Directionally accepted enough to review, but not yet current implementation behavior. Must pass its gate before being marked accepted/current. |
| Deferred | Explicitly not an implementation target. Current behavior must reject it or keep it as design-only fixtures. |
| Component target | Internal architecture or validation component that may be partly present but is not itself an author-facing promise. |

### 2.1 Current or substantially implemented

The active frontend is a compiler to existing workflow machinery. It parses `.orc`, typechecks, lowers to ordinary workflow dictionaries, and validates through the existing workflow loader/runtime path.

The following are current or substantially represented in the compiler architecture:

| Subset | Status | Contract |
| --- | --- | --- |
| `.orc` frontend compiler path | Current | Compile authoring source to validated workflow artifacts; do not execute independently. |
| Typed definitions for enums, paths, records, unions, schemas | Current | Define structured workflow-facing types and contracts. |
| `defworkflow` | Current | Define runtime-callable workflows that lower into existing workflow dictionaries. |
| `defproc` | Current / active | Define reusable workflow procedures that may lower inline or as private generated workflow structure. |
| Shared validation after lowering | Current | Frontend validation may reject earlier but may not replace or weaken shared validation. |
| Modules/imports/exports | Current or partially current | Use current tests/source to determine exact supported surface. Design requires deterministic, non-ambiguous resolution. |
| `WorkflowRef` | Current or partially current | Compile-time/module-link workflow reference; not runtime code loading. |
| `ProcRef[...]`, `(proc-ref ...)`, `bind-proc` | Accepted / current compile-time feature | Procedure references are compile-time only and must disappear before executable/runtime artifacts. |
| Source maps and diagnostics | Current / required | Generated nodes must remain attributable to authored syntax. |

### 2.2 Historical or partially superseded

The MVP design remains useful because it captures the first proof obligations: direct lowering, typed records/unions, variant proof via `match`, one real workflow phase migration, source spans, and shared validation. It is not a reliable current feature-status list because several features it deferred may now exist or be partially implemented.

The MVP should be labeled:

```text
Status: Historical MVP design. Some unsupported features listed here have since
been implemented or partially implemented. Use the unified design, current tests,
and current source for feature status.
```

### 2.3 Proposed or deferred

| Subset | Status | Contract |
| --- | --- | --- |
| `let-proc` | Proposed follow-on | Compile-time lexical procedure binding that closure-converts to a private generated `defproc` equivalent. It must not create runtime closures. |
| Runtime closures | Deferred | Runtime callable values are not allowed. Current behavior must reject runtime closure values unless a future acceptance gate is satisfied. |
| Runtime first-class procedures / dynamic dispatch | Deferred | No provider-selected procedures, procedure serialization, runtime proc registries, or dynamic invocation in executable artifacts. |
| Full Semantic IR / Executable IR serialization | Component target | A future internal architecture target. Do not claim current behavior depends on a production serialized layer unless implemented. |
| Full hygienic macro system | Component target / deferred until gated | Macro support must not hide effects or emit unchecked runtime behavior. |
| Debug YAML renderer | Optional tooling target | Debug projection only; never semantic authority. |
| Legacy adapter framework | Component target | Migration-only boundary for quarantined old behavior, especially markdown parsing or command glue. |
| Full effect graph, proof graph, reference catalog, state layout catalog | Component targets | Internal validation contracts required for broader runtime-integrated implementation. |

## 3. Core thesis

Workflow Lisp exists because workflow authoring needs abstractions that YAML cannot express safely or ergonomically:

- typed workflow inputs, outputs, records, unions, and variants;
- reusable workflow procedures;
- module-level reuse;
- structured provider/command results;
- variant proof contexts;
- source-mapped compiler generation;
- derived path/state contexts;
- explicit effect visibility;
- safe compile-time references to workflows and procedures.

It must not merely translate punctuation. This is not valuable:

```lisp
(step MaterializeImplementationInputs ...)
```

if it is only a syntactic rewrite of:

```yaml
steps:
  - name: MaterializeImplementationInputs
```

The valuable surface is higher-level workflow logic that preserves the existing runtime's authority:

```lisp
(defworkflow run-selected-item
  ((ctx ItemCtx)
   (selection SelectionInput)
   (providers ItemProviders))
  -> SelectedItemResult

  (let* ((selected (resolve-selected-item ctx selection))
         (roadmap  (call roadmap/sync
                     :ctx (phase-ctx ctx 'roadmap)
                     :selected selected
                     :providers providers.roadmap))
         (plan     (ensure-approved-plan
                     :ctx (phase-ctx ctx 'plan)
                     :selected selected
                     :roadmap roadmap.current
                     :providers providers.plan))
         (impl     (call implementation/run
                     :ctx (phase-ctx ctx 'implementation)
                     :inputs (make-implementation-inputs ctx selected plan)
                     :providers providers.implementation)))
    (finalize-selected-item ctx selected plan impl)))
```

The authored form should rarely require ordinary users to hand-spell state JSON paths, pointer paths, snapshot names, variant bundle paths, `requires_variant` pairings, line-prefix report extraction, or temporary write roots. Those are compiler/runtime responsibilities.

## 4. Non-goals

Workflow Lisp does not provide:

- a second workflow runtime;
- arbitrary Lisp evaluation;
- runtime code loading;
- untyped dynamic dispatch;
- procedure serialization;
- hidden provider calls;
- hidden command calls;
- hidden filesystem I/O;
- semantic parsing of markdown reports;
- weakening of existing workflow validation;
- replacement of artifact/path authority with pointer-file conventions;
- YAML text as the authoritative compiler target;
- provider-produced callable code or provider-selected procedures;
- runtime procedure values in state, artifacts, ledgers, records, unions, or output bundles.

Generated YAML may exist only as a debug, audit, migration-comparison, or golden-fixture projection. It is never the semantic target.

## 5. Global invariants

### 5.1 Existing runtime authority

The existing workflow loader/runtime remains authoritative for execution semantics, provider invocation, command invocation, state writes, artifact publication, resume behavior, observability, and runtime safety.

The frontend owns authoring-time structure: parsing, syntax objects, modules, type definitions, procedure/workflow elaboration, source maps, and lowering.

The frontend must not own runtime execution.

### 5.2 Shared validation authority

Frontend checks may reject invalid source earlier and with better diagnostics. They may not replace shared validation.

Every lowered workflow artifact must pass shared validation unless the caller explicitly requests a partial compile stage that is documented as non-executable.

### 5.3 Structured data authority

Structured records, unions, output bundles, typed provider results, and typed command results are semantic authority.

Reports are views. Dashboards are views. Debug projections are views. Pointer files are representations. None of those should be parsed as the source of semantic truth in normal workflow code.

### 5.4 Artifact values, not pointer files

An artifact/path value is the semantic value. A pointer file may be materialized for legacy interop, prompt visibility, audit, or runtime convention, but the pointer file is not the authority.

Bad:

```lisp
(read-pointer-file report-pointer-path)
```

Good:

```lisp
completed.execution-report
```

where `completed` is a typed union branch value proven by `match`.

### 5.5 Variant proof before variant-specific access

Variant-only fields require proof. Proof comes from `match`, explicit `requires_variant`-equivalent constructs, or a compiler-generated proof context with the same semantic strength.

Bad:

```lisp
(if (= implementation.status 'COMPLETED)
  implementation.execution-report
  nil)
```

Good:

```lisp
(match implementation
  ((COMPLETED completed) completed.execution-report)
  ((BLOCKED blocked) nil))
```

### 5.6 Effects remain visible

No abstraction may hide:

- provider calls;
- command calls;
- workflow calls;
- state updates;
- artifact reads or writes;
- snapshot reads or writes;
- resource moves;
- queue/backlog mutations;
- ledger updates;
- pointer materialization;
- write-root allocation.

Macros, procedures, `ProcRef`, `bind-proc`, and future `let-proc` must preserve effect summaries and source-map provenance.

### 5.7 Generated nodes are source-mapped

Every generated node that can affect validation, diagnostics, runtime explain output, or observability must be traceable to authored source. This includes macro expansions, generated procedure names, `ProcRef` specializations, generated private workflows, lowered match branches, generated path contracts, and future `let-proc` closure-conversion products.

### 5.8 Contracts may only narrow

Frontend type refinements, path refinements, schema refinements, and procedure/workflow signatures must not weaken existing runtime contracts. A lowering may add stricter checks, but it must not bypass or broaden shared validation.

## 6. Pipeline and authority boundary

### 6.1 Current executable pipeline

The current executable pipeline is conceptually:

```text
source file
  -> S-expression reader
  -> source-mapped syntax tree
  -> macro expansion where supported
  -> definition elaboration
  -> module/import/export resolution where supported
  -> type environment construction
  -> workflow/procedure/function catalog construction
  -> expression typechecking
  -> effect inference and validation
  -> lowering to ordinary workflow dictionaries
  -> source-map document construction
  -> shared workflow validation
  -> existing loader/runtime
```

`compile_stage1`-style operations may validate module and type-definition surfaces without requiring executable provider, prompt, command, or imported workflow bindings.

`compile_stage3`-style operations must produce executable lowered workflow artifacts and, when requested, validate them through the existing workflow loader.

### 6.2 Long-term internal architecture

The long-term target architecture may become:

```text
.orc source
  -> Frontend AST
  -> Macro/procedure elaboration
  -> Core Workflow AST
  -> Shared validation
  -> Semantic Workflow IR
  -> Executable IR
  -> Existing runtime
```

This document treats Core Workflow AST, Semantic IR, and Executable IR as useful names for design contracts. The current implementation may instead lower directly to ordinary workflow dictionaries while preserving the same invariants.

A design may claim runtime-integrated implementation readiness only when it specifies:

1. what shape crosses the frontend/shared boundary;
2. which existing validation pass owns each check;
3. which frontend checks are new;
4. which lowering choices are allowed;
5. which runtime behavior already exists;
6. which runtime behavior would be newly required;
7. how diagnostics and source maps are reported;
8. how generated artifacts are explained and tested.

## 7. Language surface

### 7.1 File form

Workflow Lisp source files use `.orc`.

Two module-header styles may coexist during migration:

MVP-style single compilation unit:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  ...)
```

Module-style source:

```lisp
(defmodule neurips.implementation
  (:language workflow-lisp "0.1")
  (:target-dsl "2.14")
  (import core)
  (import std/paths :as path)
  (import neurips/types :as nt)
  (export ImplementationInputs ImplementationResult run-implementation-phase))
```

The module-style form is the design target for reusable code. The MVP-style form may remain supported as a compatibility surface if current tests require it.

### 7.2 Lexical syntax

Workflow Lisp syntax consists of atoms, keywords, strings, numbers, booleans, `nil`, quoted symbols, comments, lists, and optional vector literal shorthand.

Examples:

```text
symbols         implementation/run, ctx, selected.plan
keywords        :ctx, :inputs, :providers
strings         "artifacts/work/report.md"
integers        86400
floats          0.25
booleans        true, false
nil             nil
quoted symbols  'implementation
comments        ; this is a comment
lists           (form arg1 arg2 :keyword value)
vectors         [APPROVE REVISE]
```

Vector shorthand is optional. A frontend version may omit it if tests and reader compatibility favor a smaller parser.

### 7.3 Name resolution

Names resolve deterministically. The compiler must reject ambiguous unqualified names.

Resolution order:

1. lexical bindings;
2. local definitions;
3. imported aliases;
4. module-qualified names;
5. standard prelude names.

Examples:

```text
ctx
selected.plan-path
providers.implementation.execute
implementation/run
path.execution-report
```

Collisions between functions, workflows, procedures, records, unions, schemas, macros, and generated names must be rejected unless the relevant namespaces are explicitly distinct and diagnostics can explain the ambiguity.

### 7.4 Primitive types

Supported primitive type names:

```text
String
Int
Float
Bool
Json
TimestampNs
RunId
Symbol
```

A frontend version may support fewer primitives if a compile-stage gate explicitly documents that restriction. Unsupported primitives must fail with stable diagnostics rather than silently degrade to `Json`.

### 7.5 Enum types

Enums define scalar values with a fixed allowed set.

```lisp
(defenum ReviewDecision APPROVE REVISE)
(defenum DrainStatus CONTINUE BLOCKED EMPTY)
```

Enums lower to scalar contracts with allowed values and may be used as union discriminants or ordinary record fields.

### 7.6 Path types

Path types define refined path contracts.

Use one spelling for existence semantics:

```lisp
(defpath Path.state-file
  :kind relpath
  :under "state"
  :must-exist false)

(defpath Path.execution-report
  :kind relpath
  :under "artifacts/work"
  :must-exist true)

(defpath Path.execution-report-target
  :kind relpath
  :under "artifacts/work"
  :must-exist false)
```

The preferred option is `:must-exist`. Target paths are represented by a target path type whose `:must-exist` is `false`, not by a separate `:must-exist-target` option. If an implementation retains `:must-exist-target` for compatibility, it should be treated as an alias with a deprecation warning or explicitly documented as a distinct target-path option.

Path values are not pointer-file paths. Pointer files are optional materialized representations.

### 7.7 Schemas

Schemas define reusable field groups independent of concrete record types.

```lisp
(defschema ReportTargets
  (execution-report-target Path.execution-report-target)
  (checks-report-target Path.checks-report-target)
  (review-report-target Path.review-report-target))
```

Schema expansion must preserve source-map frames so diagnostics can identify both the schema field origin and the record using it.

### 7.8 Records

Records define product types.

```lisp
(defrecord ImplementationInputs
  (design Path.design)
  (plan Path.plan)
  (check-commands Path.check-commands)
  (execution-report-target Path.execution-report-target)
  (checks-report-target Path.checks-report-target)
  (review-report-target Path.review-report-target))
```

Records may lower to typed input/output contracts, output bundles, provider result schemas, command result schemas, or internal typed values depending on context.

Records may not contain runtime procedure values. `ProcRef` values are compile-time-only and may not be stored in record fields.

### 7.9 Unions

Unions define tagged variant types.

```lisp
(defunion ImplementationResult
  (COMPLETED
    (execution-report Path.execution-report)
    (checks-report Path.checks-report)
    (review-report Path.review-report)
    (review-decision ReviewDecision))
  (BLOCKED
    (progress-report Path.progress-report)
    (blocker Blocker)))
```

Each union has:

- a discriminant;
- variant names;
- variant-specific fields;
- optional shared fields;
- availability/proof metadata.

Variant-specific fields are accessible only inside proof contexts.

Union values may not contain runtime procedure values. `ProcRef` values are compile-time-only and may not be stored in union fields.

### 7.10 Optional, list, and map types

Parameterized types:

```text
Optional[String]
List[Path.execution-report]
Map[String, Json]
```

Initial or partial implementations may restrict these to structured values whose runtime contracts are already supported. Restrictions must be explicit and source-mapped.

### 7.11 Workflow references

`WorkflowRef[...]` names a workflow signature known at compile time or module-link time.

```text
WorkflowRef[SelectedItemInput -> SelectedItemResult]
WorkflowRef[(DrainCtx SelectionState) -> SelectionResult]
WorkflowRef[() -> C]
```

Workflow references are not runtime code loading. They may support higher-order orchestration when the selected workflow identity remains statically known before lowering.

Workflow refs may not smuggle dynamic runtime dispatch. If a workflow reference crosses a runtime workflow boundary, the design must prove that the lowered runtime representation is an ordinary supported workflow call target, not an arbitrary callable value.

### 7.12 Procedure references

`ProcRef[...]` names a `defproc` signature known at compile time.

```text
ProcRef[PhaseInput -> PhaseResult]
ProcRef[(SelectedItem Design Plan) -> ImplementationResult]
ProcRef[() -> C]
```

`ProcRef` is compile-time only. It must not appear in runtime state, artifact bundles, ledgers, records, unions, workflow outputs, provider outputs, command outputs, or executable runtime plans.

The accepted surface is:

```lisp
(proc-ref implementation/run)

(bind-proc (proc-ref implementation/run)
  :design design
  :plan plan
  :providers providers.implementation)
```

Bare procedure names are not procedure values. Direct calls remain direct:

```lisp
(call implementation/run
  :ctx ctx
  :inputs inputs)
```

## 8. Definition forms

### 8.1 `defenum`

```lisp
(defenum SelectionMode ACTIVE_SELECTION RECOVERED_IN_PROGRESS)
```

Defines scalar enum values.

### 8.2 `defpath`

```lisp
(defpath Path.backlog-active
  :kind relpath
  :under "docs/backlog/active"
  :must-exist true)
```

Defines a path contract refinement.

### 8.3 `defschema`

```lisp
(defschema ProviderRoles
  (execute ProviderRole)
  (review ProviderRole)
  (fix ProviderRole))
```

Defines reusable field structure.

### 8.4 `defrecord`

```lisp
(defrecord SelectedItemInputs
  (selection-mode SelectionMode)
  (selected-item-active-path Path.backlog-active)
  (selected-item-in-progress-path Path.backlog-in-progress)
  (selected-item-context-path Path.state-existing)
  (check-commands-path Path.state-existing))
```

Defines a product type.

### 8.5 `defunion`

```lisp
(defunion SelectedItemResult
  (CONTINUE
    (item-summary Path.work-report)
    (run-state Path.state-existing))
  (BLOCKED
    (item-summary Path.work-report)
    (reason String)
    (stage FailedStage)))
```

Defines a tagged outcome type.

### 8.6 `defun`

```lisp
(defun phase-name->state-key ((phase Symbol)) -> String
  (string/concat (symbol/name phase) "_state"))
```

`defun` defines pure helper logic. It may construct records, construct paths symbolically, select fields, combine strings, compute constants, and build type-level descriptors.

It may not read files, write files, call providers, call workflows, run commands, inspect wall-clock time, generate random values, or allocate hidden state.

A `defun` may evaluate at compile time or lower to pure expression IR, depending on implementation stage.

### 8.7 `defmacro`

```lisp
(defmacro with-phase ((ctx phase-name) &body body)
  ...)
```

Macros transform syntax objects, not raw strings.

Macros may construct frontend AST, introduce hygienic bindings, expand shorthand, and emit source-map frames.

Macros may not perform filesystem I/O, network I/O, provider calls, command calls, wall-clock reads, random generation, contract weakening, or direct executable/runtime emission.

A macro expansion is valid only if the expanded frontend AST passes normal validation. Macros cannot hide effects.

Full hygienic macro support is a component target unless current tests prove a narrower surface.

### 8.8 `defproc`

`defproc` defines reusable workflow behavior.

```lisp
(defproc ensure-approved-plan
  ((ctx PhaseCtx)
   (selected SelectedItemInputs)
   (roadmap RoadmapState)
   (providers PlanProviders))
  -> PlanGateResult
  :effects ((reads selected selected.selected-item-context-path)
            (uses-provider providers.generate providers.review)
            (writes Path.plan-target Path.review-report)
            (updates-state ctx))
  ...)
```

A `defproc` is not necessarily a runtime-callable workflow boundary. It may lower by:

- inlining into the caller;
- lowering to a private generated workflow;
- lowering to a certified runtime effect if such a policy is accepted.

The lowering choice must preserve source maps, type correctness, effect transparency, validation behavior, and deterministic generated names.

`defproc` exists because reusable workflow behavior is semantic, not just syntactic. Examples include `resume-or-start`, `resource-transition`, `review-revise-loop`, `run-provider-phase`, and `finalize-selected-item`.

### 8.9 `defworkflow`

`defworkflow` defines an exported runtime-callable workflow.

```lisp
(defworkflow run-implementation-phase
  ((ctx PhaseCtx)
   (inputs ImplementationInputs)
   (providers ImplementationProviders))
  -> ImplementationResult
  :effects ((reads inputs.design inputs.plan)
            (uses-provider providers.execute providers.review providers.fix)
            (writes Path.execution-report Path.checks-report Path.review-report)
            (updates-state ctx))
  ...)
```

A workflow has:

- a typed input signature;
- a typed output signature;
- declared or inferred effects;
- a body;
- a module-qualified name;
- a target DSL/runtime compatibility version.

Calls to a workflow lower to existing workflow call semantics and must obey version, input, output, effect, and validation rules.

## 9. Expression and control forms

### 9.1 Pure expressions

Pure expressions are side-effect-free and may appear in path construction, record construction, conditions over already-available values, and arguments to procedures/workflows.

```lisp
(let ((x 1) (y 2))
  (+ x y))
```

Pure expressions cannot read files, call providers, call commands, update state, mutate resources, or allocate runtime side effects.

### 9.2 Sequential binding with `let*`

```lisp
(let* ((selected (resolve-selected-item ctx selection))
       (plan (ensure-approved-plan ctx selected providers.plan))
       (implementation (call implementation/run
                         :ctx (phase-ctx ctx 'implementation)
                         :inputs (make-implementation-inputs ctx selected plan)
                         :providers providers.implementation)))
  (finalize-selected-item ctx selected plan implementation))
```

`let*` establishes sequential dependency order. Each binding may reference earlier bindings. Effectful bindings lower to one or more ordered workflow statements. Pure bindings lower to expression IR or generated inputs as appropriate.

The runtime remains deterministic and sequential unless the core runtime explicitly supports parallelism and the frontend proves independence.

### 9.3 Pattern matching

```lisp
(match implementation
  ((COMPLETED completed)
    (publish-completed ctx completed))
  ((BLOCKED blocked)
    (record-blocked ctx blocked)))
```

`match` over a union creates a proof context. Inside a branch, the compiler knows which variant is available and which variant-specific fields may be referenced.

Lowering must retain runtime guard semantics equivalent to `requires_variant` so invalid variant references cannot appear through unchecked paths.

### 9.4 Conditionals

`if` is allowed for pure or already-proven values.

```lisp
(if selected.active?
  (resource-transition ...)
  selected)
```

For union values, prefer `match`. The compiler should warn or reject patterns that manually inspect discriminants and then access variant-only fields without proof.

### 9.5 Loops

Bounded loops may be supported through a form such as:

```lisp
(loop/recur
  :max max-iterations
  :state initial-state
  (fn (state)
    ...))
```

The loop body returns either:

```lisp
(continue new-state)
(done result)
```

Lowering options include a core repeat construct, generated workflow loop, or runtime loop IR if supported. The compiler must preserve boundedness, typed loop state, typed result, effect visibility, and deterministic resume semantics.

Variant proof does not automatically survive across iterations unless an explicit proof-carrying loop contract is accepted.

### 9.6 Workflow calls

```lisp
(call implementation/run
  :ctx implementation-ctx
  :inputs implementation-inputs
  :providers providers.implementation)
```

Checks:

- callee exists;
- callee is visible;
- target DSL/runtime version is compatible;
- argument names match;
- argument types match;
- effects are permitted;
- return type matches the binding or context.

### 9.7 Procedure calls

A direct call to a `defproc` uses ordinary call syntax where the compiler can distinguish procedure and workflow catalogs.

```lisp
(call ensure-approved-plan
  :ctx plan-ctx
  :selected selected
  :roadmap roadmap.current
  :providers providers.plan)
```

After `ProcRef` specialization or `let-proc` lowering, procedure calls must reach the same validation and lowering path as ordinary authored `defproc` calls.

### 9.8 Provider result

A provider call should return structured, typed output.

```lisp
(provider-result providers.review
  :prompt prompts.review-plan
  :inputs (record ReviewInputs
            :design design
            :plan plan)
  :returns ReviewResult)
```

The frontend must make provider effects visible, inject/validate output contracts, and lower to existing provider invocation semantics. Provider output may not produce `ProcRef`, runtime closure values, or executable code.

### 9.9 Command result

A command call should return structured, typed output.

```lisp
(command-result run-checks
  :argv ["python" "-m" "checks.run" inputs.check-commands]
  :returns ChecksResult)
```

Commands must be explicit effects. Inline shell/Python glue should be linted or rejected unless wrapped in a certified command adapter with fixtures and typed output contracts.

Command output may not produce `ProcRef`, runtime closure values, or executable code.

### 9.10 Record construction and field access

```lisp
(record ImplementationInputs
  :design design
  :plan plan
  :execution-report-target (target-path ctx 'execution-report))

inputs.plan
completed.execution-report
```

Field access must be typechecked. Variant-specific field access requires proof.

## 10. Effects and authority

### 10.1 Effect kinds

The frontend must track or infer at least these effect kinds where relevant:

```text
reads(path-or-artifact)
writes(path-or-contract)
publishes(artifact-name)
uses-provider(provider)
uses-command(command)
calls-workflow(workflow)
calls-procedure(proc)
updates-state(context)
writes-snapshot(snapshot-kind)
reads-snapshot(snapshot-ref)
moves-resource(resource, from, to)
updates-ledger(ledger)
materializes-pointer(optional)
allocates-write-root(scope)
```

### 10.2 Effect declarations

Effects may be declared on `defworkflow` and `defproc`:

```lisp
:effects ((reads inputs.design inputs.plan)
          (uses-provider providers.execute)
          (writes Path.execution-report Path.progress-report)
          (updates-state ctx))
```

The compiler may infer additional internal effects, but it must not silently drop effects absent from declarations. A declaration mismatch should produce diagnostics or require an explicit mode that says effects are inferred and explainable.

### 10.3 Effect transparency

Every high-level form must expose its transitive effects after lowering. In particular:

- macros cannot hide effects;
- `defproc` summaries include nested calls;
- `ProcRef` consumers include selected procedure effects after specialization;
- `bind-proc` does not hide effects of bound values or the specialized body;
- `let-proc` generated procedures expose the same effects as equivalent authored `defproc` code;
- future runtime closures cannot capture authority without explicit capability/effect validation.

### 10.4 Capability and authority checks

Effects that imply authority must be backed by explicit values or validated capabilities. Examples:

- provider roles must be typed and explicitly passed;
- command adapters must be certified or linted;
- write roots must be derived or allocated deterministically;
- artifact reads/writes must use path/artifact contracts;
- resource transitions must prove source and destination authority;
- workflow calls must obey version and export boundaries.

## 11. State, contexts, and derived paths

High-level workflow code should use typed contexts instead of hand-managing state paths.

```lisp
(defrecord RunCtx
  (run-id RunId)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root))

(defrecord PhaseCtx
  (run RunCtx)
  (phase-name Symbol)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root))

(defrecord ItemCtx
  (run RunCtx)
  (item-id String)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root)
  (ledger Path.state-existing))
```

Context helpers derive narrower contexts:

```lisp
(phase-ctx item-ctx 'implementation)
(item-ctx drain-ctx selected-item)
```

Derived path/state responsibilities include:

- phase state bundle path;
- snapshot names;
- candidate target paths;
- temporary bundle paths;
- canonical artifact names;
- optional pointer paths;
- observability labels;
- deterministic generated write roots.

Ordinary authors should not write strings such as:

```text
${inputs.state_root}/implementation_state.json
```

unless operating inside explicit low-level interop or legacy adapter code.

## 12. Reports, legacy adapters, and command boundaries

### 12.1 Reports are views

Markdown reports may be written, published, reviewed, and displayed. They must not be parsed as normal semantic state.

Forbidden in ordinary workflow code:

```lisp
:extract (:line-prefix "Blocker Class:")
:parse-markdown-field "Review Decision:"
:grep "APPROVE"
```

### 12.2 Legacy adapters

Legacy parsing may exist only behind an explicit adapter boundary:

```lisp
(deflegacy-adapter parse-old-progress-report
  ((report Path.progress-report))
  -> Blocker
  :deprecated true
  :requires-fixtures true
  (legacy/line-prefix
    :field blocker-class
    :type BlockerClass
    :prefix "Blocker Class:"))
```

Legacy adapters must be marked as migration debt, fixture-tested, linted, and excluded from new standard-library behavior unless an exception is reviewed.

### 12.3 Command adapter contract

Command adapters bridge external scripts or programs into typed workflow semantics. They must declare typed inputs, typed outputs, command effects, fixture expectations, and source-map behavior.

Inline glue is suspect because it tends to hide parsing, filesystem, environment, and process assumptions. It should be linted, rejected, or promoted into a certified adapter.

## 13. Modules, imports, and exports

### 13.1 Module identity

Each module has:

- a module name;
- a language version;
- a target DSL/runtime version;
- imports;
- exports;
- type definitions;
- functions, macros, procedures, and workflows.

### 13.2 Imports

```lisp
(import std/paths)
(import std/paths :as path)
(import neurips/implementation :only (run-implementation-phase ImplementationResult))
```

Imports must be deterministic. Ambiguous imports are invalid.

### 13.3 Exports

```lisp
(export run-implementation-phase ImplementationResult ImplementationInputs)
```

Only exported names are visible to importing modules.

Private procedures may be used internally, including as sources for same-module `ProcRef`. Private procedures from other modules are not referenceable.

### 13.4 Generated names

Generated names must be deterministic, collision-resistant, and unimportable unless explicitly promoted.

Recommended shapes:

```text
%proc-ref.<module>.<procedure>.<stable-hash>
%let-proc.<module>.<enclosing-definition>.<local-name>.<stable-hash>
%private-workflow.<module>.<procedure>.<stable-hash>
```

Generated names may appear in source maps, explain output, debug output, or diagnostics, but user-facing diagnostics should first point to the authored form.

## 14. Procedure model

### 14.1 `defproc` semantics

`defproc` represents reusable workflow behavior. It is not automatically a runtime-callable workflow.

A procedure has:

- a module-qualified identity;
- a parameter list with names and types;
- a return type;
- a body expression;
- declared or inferred effect summary;
- lowering policy;
- source-map identity.

Allowed lowering policies:

| Policy | Meaning |
| --- | --- |
| `inline` | Substitute/lower body into caller while preserving source maps. |
| `private-workflow` | Emit hidden private workflow structure and call it through ordinary workflow call semantics. |
| `auto` | Compiler chooses between inline and private workflow using deterministic policy. |

A procedure lowering policy must not change semantics, hide effects, or create runtime procedure values.

### 14.2 Procedure cycles

Procedure cycles are invalid unless a future design explicitly defines recursion, boundedness, and runtime behavior. `ProcRef` specialization cycles are also invalid unless cycle analysis proves there is no recursive executable expansion.

### 14.3 Procedure visibility

Same-module procedures are visible by local name. Imported procedures are visible only if exported. Private imported procedures are invalid targets for `proc-ref`.

Name collisions with workflows, functions, schemas, records, macros, or generated names must be rejected or diagnosed under explicit namespace rules.

## 15. `ProcRef` and `bind-proc`

### 15.1 Status

`ProcRef` and `bind-proc` are accepted compile-time procedure-composition features. They are the current semantic base for higher-order procedure reuse.

### 15.2 Decision

Workflow Lisp supports higher-order procedural composition through compile-time procedure references.

The accepted model:

1. `ProcRef[...]` types reference named `defproc` definitions.
2. Procedure references resolve at parse/typecheck/module-link time.
3. `(proc-ref name)` creates a compile-time reference to a visible `defproc`.
4. `bind-proc` partially binds named arguments and produces a specialized compile-time procedure reference.
5. Specialization happens before lowered executable/runtime artifacts are produced.
6. Runtime artifacts must contain no unresolved procedure values.
7. Procedure references are not runtime values and may not be stored in state, artifacts, records, unions, ledgers, provider results, command results, workflow outputs, or result bundles.

### 15.3 Syntax

Procedure-reference types:

```text
ProcRef[A -> B]
ProcRef[(A B) -> C]
ProcRef[() -> C]
```

Procedure-reference literal:

```lisp
(proc-ref implementation/run)
```

Partial application:

```lisp
(bind-proc (proc-ref implementation/run)
  :design design
  :plan plan
  :providers providers.implementation)
```

Residual signature example:

```text
Original procedure:
  implementation/run:
    (SelectedItem Design Plan Providers) -> ImplementationResult

Binding:
  :design design
  :plan plan
  :providers providers.implementation

Residual:
  ProcRef[SelectedItem -> ImplementationResult]
```

Bindings are keyword-only. Positional binding, default arguments, variadic keyword bags, and mixed positional/keyword binding are out of scope for the first accepted tranche.

### 15.4 Typechecking rules

The compiler must provide a `ProcRefTypeRef` parallel to workflow-reference typing.

Rules:

- `(proc-ref name)` must resolve to a visible `defproc`.
- The referenced procedure's signature must match the expected `ProcRef`.
- `bind-proc` must receive a `ProcRef`.
- Every bound keyword must name a parameter in the referenced procedure.
- A parameter may be bound at most once.
- Each bound expression must typecheck against the corresponding parameter type.
- The residual signature preserves original parameter order for unbound parameters.
- A zero-argument residual procedure is allowed only where the expected type is `ProcRef[() -> R]`.
- Procedure references are compile-time values only.
- `ProcRef` values may be forwarded through `defproc` parameters typed as `ProcRef[...]`.
- `ProcRef` values may not cross exported runtime workflow boundaries as ordinary structured values.

### 15.5 Specialization rules

Specialization happens before ordinary `defproc` lowering.

The compiler must:

1. resolve the base procedure reference;
2. typecheck and record bound arguments;
3. compute the residual signature;
4. create a deterministic hidden specialized procedure;
5. substitute bound values at the specialized call site;
6. continue through the existing `defproc` validation and lowering path.

Generated specialization names must be deterministic and collision-resistant.

Recommended stable-hash inputs:

- resolved base procedure identity;
- bound parameter names;
- bound expression source identities where available;
- residual signature;
- enclosing module identity;
- compiler/language version if required for replay stability.

### 15.6 Lowering rules

After specialization, lowering sees only ordinary concrete procedure calls.

`defproc` lowering policy applies after specialization:

- `inline` specializes and then inlines;
- `private-workflow` specializes and then emits a hidden private workflow;
- `auto` chooses deterministically.

Executable/runtime artifacts, debug runtime plans, state, and artifact bundles must not contain unresolved `ProcRef` values.

### 15.7 Effect rules

`proc-ref` and `bind-proc` do not introduce runtime effects by themselves.

The caller-visible effect summary for a procedure that accepts or calls a `ProcRef` must include the selected procedure's transitive effects after specialization.

Bound values do not hide effects. If a bound value was produced by an earlier effectful expression, that producer remains visible in normal dataflow. If the specialized procedure later uses the bound value, the procedure's reads/writes/calls/provider/command effects remain visible in the specialized summary.

Effect checking must happen after procedure references are resolved and before lowering commits generated nodes.

### 15.8 Diagnostics

Required stable diagnostic codes:

```text
proc_ref_unknown
proc_ref_literal_required
proc_ref_signature_invalid
proc_ref_runtime_transport_forbidden
proc_ref_binding_unknown
proc_ref_binding_duplicate
proc_ref_binding_type_invalid
proc_ref_specialization_cycle
proc_ref_private_import_invalid
```

Diagnostics should point first to the authored source that the user can fix:

- unknown procedure: `(proc-ref name)`;
- signature mismatch: the argument supplying the ref;
- bad binding name or duplicate binding: the `bind-proc` keyword;
- bad bound value type: the bound expression;
- runtime transport violation: the field/output/state form attempting to carry the `ProcRef`.

### 15.9 Acceptance tests

Positive tests must prove:

- a `defproc` can accept a `ProcRef[...]` parameter;
- `(proc-ref name)` can pass a visible named procedure;
- an imported exported `defproc` can be referenced;
- `bind-proc` binds a subset of arguments and exposes the correct residual signature;
- a specialized procedure can lower inline;
- a specialized procedure can lower as a private workflow when policy requires;
- effect summaries include selected and bound procedure behavior;
- source-map/explain artifacts expose original `defproc`, `proc-ref`, `bind-proc`, specialization, and lowered nodes;
- executable/runtime artifacts contain no unresolved procedure values.

Negative tests must prove:

- unknown procedure reference is rejected;
- signature mismatch is rejected;
- duplicate bound argument is rejected;
- unknown bound argument is rejected;
- bad bound value type is rejected;
- private imported procedure reference is rejected;
- specialization cycle is rejected;
- provider/command outputs cannot produce `ProcRef`;
- records, unions, workflow outputs, artifacts, ledgers, and runtime state cannot contain `ProcRef`.

## 16. `let-proc`

### 16.1 Status

`let-proc` is a proposed follow-on feature. It is not a runtime closure and must not be implemented as one.

### 16.2 Decision

Add `let-proc` as an ergonomic compile-time layer over accepted `ProcRef` / `bind-proc` semantics.

A V1 `let-proc` binding:

- introduces exactly one local procedure name;
- declares explicit residual parameters;
- declares an explicit return type;
- declares explicit identifier captures;
- contains one body expression;
- may be referenced only through `(proc-ref local-name)`;
- closure-converts to a private generated `defproc` equivalent;
- lowers through ordinary `defproc` validation and lowering;
- produces no runtime procedure value.

### 16.3 Syntax

Proposed shape:

```lisp
(let* ((impl-provider providers.implementation))
  (let-proc
    (run-impl
      ((selected SelectedItem)) -> ImplementationResult
      :captures (design plan impl-provider)
      (call implementation/run
        :selected selected
        :design design
        :plan plan
        :providers impl-provider))

    (call iter-proc
      :execute (proc-ref run-impl)
      :input selected)))
```

The local procedure is visible only in the body of the `let-proc` form.

### 16.4 Core invariant

```text
If the equivalent ordinary generated defproc cannot lower,
let-proc cannot lower it either.
```

`let-proc` is lexical syntax over generated `defproc` plus existing `ProcRef` semantics. It is not a new lowering path.

### 16.5 Capture rules

All captures must be explicit.

Rules:

- every captured identifier must resolve in the enclosing lexical environment;
- every use of an outer binding inside the local procedure body must appear in `:captures`;
- captures have the same types as the captured bindings;
- captures become generated parameters on the private generated `defproc` equivalent;
- captures are supplied by generated `bind-proc`-equivalent specialization or equivalent compile-time substitution;
- captures may not include runtime procedure values;
- captures may not smuggle provider roles, command authority, write roots, or state authority without ordinary effect/capability checks.

V1 should reject implicit captures. It should also reject broad capture bags such as `:captures *`.

### 16.6 Lowering

Conceptual lowering:

```text
(let-proc
  (run-impl ((selected SelectedItem)) -> ImplementationResult
    :captures (design plan impl-provider)
    body)
  use-body)

=>

private generated defproc:
  %let-proc.<module>.<enclosing>.<run-impl>.<hash>
    ((design Design)
     (plan Plan)
     (impl-provider ImplementationProvider)
     (selected SelectedItem))
    -> ImplementationResult
    body

compile-time local binding:
  run-impl =
    (bind-proc
      (proc-ref %let-proc.<...>)
      :design design
      :plan plan
      :impl-provider impl-provider)

then lower use-body through ordinary ProcRef and defproc mechanics
```

The generated procedure is private and compiler-internal. It may appear in diagnostics, source maps, and explain/debug output, but it is not importable, exportable, or author-referenceable by generated name.

### 16.7 Effect rules

`let-proc` must expose the same effects as the equivalent generated `defproc`.

A local procedure's effects include:

- effects of its body;
- effects implied by captured values only when those values are used in effectful operations;
- transitive effects of called procedures/workflows;
- selected effects after `ProcRef` specialization.

`let-proc` must not make invalid effectful compositions valid. If effectful `let*`, effectful `match`, workflow calls, provider calls, command calls, or generated write roots cannot lower safely in an ordinary `defproc`, they cannot lower safely inside `let-proc`.

### 16.8 Source maps

Diagnostics and explain output must preserve frames for:

- the `let-proc` form;
- the local procedure name;
- the declared parameters;
- the return type;
- each capture identifier;
- the body expression;
- the generated private procedure;
- generated `bind-proc` or specialization nodes;
- the call site consuming `(proc-ref local-name)`.

User-facing diagnostics should point to authored `let-proc` code before generated names.

### 16.9 Diagnostics

`let-proc` should use stable diagnostic codes before being marked accepted/current.

Required proposed codes:

```text
let_proc_shape_invalid
let_proc_name_invalid
let_proc_param_invalid
let_proc_return_type_invalid
let_proc_capture_unknown
let_proc_capture_duplicate
let_proc_capture_missing
let_proc_capture_forbidden
let_proc_body_invalid
let_proc_generated_proc_invalid
let_proc_effect_boundary_invalid
let_proc_runtime_transport_forbidden
let_proc_source_map_missing
```

### 16.10 V1 restrictions

V1 should reject:

- multiple local procedure bindings in one `let-proc` form;
- recursive local procedures;
- mutually recursive local procedures;
- implicit captures;
- variadic parameters;
- default parameters;
- runtime closure values;
- local procedure values stored in records/unions/state/artifacts;
- export/import of local procedure names;
- provider/command output that creates a local procedure;
- any body that cannot lower through ordinary `defproc` rules.

### 16.11 Acceptance gate

Do not mark `let-proc` implemented until:

1. syntax exists;
2. AST representation exists;
3. capture analysis exists;
4. generated private `defproc` equivalents are created deterministically;
5. generated procedures use ordinary `defproc` validation;
6. captures are explicit and typechecked;
7. effects are preserved;
8. invalid effectful bodies are rejected, not silently lowered;
9. source maps point back to local authored syntax;
10. no runtime procedure or closure value appears in executable/runtime artifacts;
11. positive and negative tests cover same-module and imported contexts;
12. diagnostic codes are stable.

## 17. Runtime closures

### 17.1 Status

Runtime closures are deferred. They are not an implementation target for the current compiler.

### 17.2 Boundary

Runtime closures are runtime-owned callable values. They are separate from `ProcRef`, `bind-proc`, and `let-proc`.

```text
ProcRef / bind-proc  = compile-time procedure references and specialization
let-proc             = lexical syntax over generated defproc + ProcRef
runtime closures     = runtime-owned callable values with runtime semantics
```

Current compile-time procedure features must continue to compile away before executable/runtime artifacts.

### 17.3 Disabled profile

The disabled profile is the current required behavior.

The compiler/runtime must reject authored or runtime closure values with:

```text
runtime_closure_not_enabled
```

Design fixtures may describe closure syntax, invalid examples, registry shapes, diagnostics, or source-map metadata. They must not execute closures or serialize runtime closure values as ordinary data.

### 17.4 Design-fixture profile

A design-fixture profile may validate rejected examples, forbidden shapes, registry metadata, and diagnostics before execution support exists. It still rejects closure execution.

This profile exists to prove that forbidden cases are understood before runtime behavior is added.

### 17.5 Minimum executable profile

Runtime closure implementation may begin only after the repository has:

- completed or explicitly bounded `ProcRef` / `bind-proc` semantics;
- completed or explicitly bounded `let-proc` semantics if `let-proc` is used as motivation;
- a concrete executable IR extension point for checked dynamic invocation;
- a closure-family registry design owned by executable bundles;
- a source-map format for closure creation and invocation;
- an effect/capability model strong enough to reject authority smuggling;
- a deterministic write-root allocation model for repeated dynamic invocation;
- a replay/resume compatibility policy based on executable bundle identity;
- forbidden-shape fixtures proving invalid closures are rejected;
- no fallback to dynamic Python objects, procedure-name strings, serialized code, provider-produced procedures, or unchecked executable IR.

### 17.6 V1 provider-role capture policy

The first executable runtime-closure tranche, if it is ever implemented, should reject provider-role captures categorically.

Any policy that allows provider-role capture requires a later capability-capture tranche with explicit proof obligations. Do not mix that future capability model into V1.

### 17.7 Runtime closure forbidden shapes

Current and disabled-profile behavior must reject:

- closure values in records;
- closure values in unions;
- closure values in workflow outputs;
- closure values in provider outputs;
- closure values in command outputs;
- closure values in artifacts;
- closure values in ledgers;
- closure values in runtime loop state;
- provider-produced procedures;
- serialized procedure code;
- dynamic Python callable objects;
- procedure-name strings used as runtime dispatch;
- closures that capture write roots without deterministic allocation;
- closures that capture provider roles;
- closures that lack source-map provenance;
- closures whose executable bundle identity is not replay/resume safe.

### 17.8 Runtime closure diagnostics

Required or reserved diagnostic codes:

```text
runtime_closure_not_enabled
runtime_closure_shape_invalid
runtime_closure_runtime_transport_forbidden
runtime_closure_registry_missing
runtime_closure_registry_invalid
runtime_closure_capture_forbidden
runtime_closure_capability_invalid
runtime_closure_effect_unsound
runtime_closure_invocation_invalid
runtime_closure_replay_identity_mismatch
runtime_closure_resume_code_mismatch
runtime_closure_source_map_missing
```

## 18. Standard-library lowering contracts

High-level standard-library forms are acceptable only when their lowering is explicit, validated, and source-mapped.

Examples:

| Form | Required lowering property |
| --- | --- |
| `provider-result` | Explicit provider invocation with typed output contract. |
| `command-result` | Explicit command invocation or certified adapter with typed output contract. |
| `produce-one-of` | Typed union construction with one valid variant. |
| `run-provider-phase` | Provider call plus structured result handling and effect summary. |
| `resume-or-start` | Deterministic state/snapshot behavior using existing resume semantics. |
| `review-revise-loop` | Bounded loop with typed review/fix state and visible provider/command effects. |
| `resource-transition` | Validated resource movement with source/destination authority. |
| `finalize-selected-item` | Validated artifact/state finalization, not unchecked writes. |
| `backlog-drain` | Bounded selection/run/gap behavior with typed state and ledger effects. |

A standard-library form is implementation-ready only if it answers:

1. what typed inputs and outputs it has;
2. what effects it emits;
3. what existing workflow statements it lowers to;
4. what validation pass checks it;
5. what source-map frames it emits;
6. what fixtures prove invalid behavior is rejected.

## 19. Lowering contracts

### 19.1 Authoring forms lower to validated workflow structure

Every high-level authoring form must lower to one of:

- existing ordinary workflow dictionaries;
- accepted Core Workflow AST nodes;
- accepted Semantic IR nodes;
- accepted private generated workflow/procedure artifacts;
- explicit legacy adapter boundaries.

If a form cannot lower to accepted structure, it remains a design sketch.

### 19.2 No direct YAML authority

The frontend must not use YAML text as the semantic intermediate. A debug YAML renderer may exist, but it is a projection from typed/lowered structure.

### 19.3 Generated workflow dictionaries

When the current implementation lowers to ordinary workflow dictionaries, those dictionaries must be treated as the authoritative executable artifact only after shared validation.

Generated dictionaries must carry or be accompanied by source-map metadata sufficient to diagnose errors in authored `.orc` terms.

### 19.4 Validation before commit

Lowered artifacts are not executable until validation succeeds. A compile path that returns invalid lowered data must label it as diagnostic/debug data only.

## 20. Source maps and explain output

### 20.1 Source-map requirements

Source maps must represent:

- source file identity;
- span information for syntax nodes;
- macro expansion frames;
- schema expansion frames;
- generated procedure frames;
- generated workflow frames;
- `ProcRef` specialization frames;
- future `let-proc` conversion frames;
- lowered statement/output frames;
- validation diagnostic locations;
- runtime/explain node identity where available.

### 20.2 Diagnostic pointing policy

Diagnostics should point to the most actionable authored form first, then include generated context if helpful.

Examples:

| Problem | Primary location |
| --- | --- |
| Unknown field | field access or record construction field. |
| Unknown variant | branch pattern. |
| Invalid variant-only access | field access outside proof context. |
| Bad path contract | `defpath` or value constructing path. |
| Provider output mismatch | provider-result `:returns` or output field. |
| Command output mismatch | command-result `:returns` or adapter fixture. |
| Unknown procedure reference | `(proc-ref name)`. |
| Bad `bind-proc` keyword | keyword in `bind-proc`. |
| Missing `let-proc` capture | identifier use in local procedure body. |
| Runtime closure attempted | authored closure form or structured field carrying closure. |

### 20.3 Explain output

Explain output may include generated names and internal nodes, but it must map them back to authored source.

For generated procedure specializations, explain output should show:

- base procedure;
- specialization reason;
- bound parameters;
- residual signature;
- generated name;
- lowered policy;
- effect summary;
- source spans.

## 21. Diagnostics policy

Accepted/current features must use stable diagnostic codes. Proposed features must define stable codes before integration.

Diagnostic codes should be namespaced by feature:

```text
type_*
path_*
record_*
union_*
variant_*
workflow_*
procedure_*
proc_ref_*
let_proc_*
runtime_closure_*
effect_*
source_map_*
module_*
validation_*
```

Diagnostics should include:

- code;
- severity;
- source span;
- short message;
- expected type/shape where relevant;
- actual type/shape where relevant;
- generated context when relevant;
- suggested fix when unambiguous.

## 22. Testing strategy

### 22.1 Test categories

Required categories:

1. reader/parser tests;
2. syntax/source-span tests;
3. macro expansion tests where macros are enabled;
4. type definition tests;
5. record/union/path lowering tests;
6. expression typechecking tests;
7. variant-proof tests;
8. effect-summary tests;
9. procedure lowering tests;
10. `ProcRef` / `bind-proc` tests;
11. `let-proc` tests when proposed implementation begins;
12. runtime-closure rejection tests;
13. shared-validation tests;
14. source-map/explain tests;
15. migration/golden tests comparing representative `.orc` to existing workflow behavior.

### 22.2 Positive/negative balance

Every new form needs positive and negative tests.

Positive tests prove lowerability, type correctness, effect summaries, source maps, and shared validation.

Negative tests prove invalid source is rejected before or during shared validation with stable diagnostics.

### 22.3 Oracle/equivalence tests

For migrated workflows, tests should compare `.orc` output to known-good existing workflow behavior at the semantic artifact level, not by requiring identical textual YAML.

Equivalence should check:

- workflow names and boundaries;
- inputs and outputs;
- contracts;
- provider/command calls;
- state writes;
- artifact outputs;
- variant guards;
- resume behavior where relevant;
- observability labels where relevant.

### 22.4 Runtime closure disabled-profile tests

Even before runtime closures are implemented, tests must prove the current system rejects runtime closure values in all forbidden locations.

## 23. Acceptance gates

### 23.1 Gate A: current frontend feature

A feature belongs to the current frontend only if:

- it parses through the current reader;
- it has source spans;
- it typechecks through the current environment;
- it lowers to ordinary workflow dictionaries or an accepted compiler artifact;
- it passes shared validation when executable;
- it has positive and negative tests;
- generated names are deterministic;
- diagnostics preserve source-map intent.

### 23.2 Gate B: accepted compile-time procedure feature

A procedure feature is accepted only if:

- it compiles away before executable/runtime artifacts;
- it uses ordinary `defproc` validation/lowering;
- it preserves effects;
- it preserves source maps;
- it has stable diagnostics;
- it cannot be stored in runtime data;
- it cannot introduce dynamic runtime dispatch.

### 23.3 Gate C: `let-proc`

`let-proc` may move from proposed to accepted/current only when:

- generated `defproc` conversion is implemented;
- explicit capture analysis is implemented;
- missing/duplicate/forbidden captures are rejected;
- invalid effectful bodies are rejected;
- generated source maps are correct;
- no runtime closure/procedure value appears;
- tests cover success, failure, imports, source maps, effects, and shared validation.

### 23.4 Gate D: runtime closures

Runtime closures may move from deferred to implementation planning only when:

- the disabled-profile tests exist and pass;
- executable IR has a checked dynamic invocation shape;
- closure-family registry design is accepted;
- closure creation/invocation source maps are accepted;
- effect/capability capture rules are accepted;
- deterministic write-root allocation is accepted;
- replay/resume policy is accepted;
- provider-role capture is either categorically rejected or governed by an accepted capability-capture design;
- forbidden-shape fixtures exist;
- no dynamic Python object, serialized code, provider-produced procedure, or string-dispatch fallback is used.

## 24. Migration plan for existing docs

### 24.1 Add this document

Add:

```text
docs/design/workflow_lisp_unified_frontend_design.md
```

### 24.2 Re-label old documents

Update old docs with top banners:

For `workflow_lisp_frontend_specification.md`:

```text
Status: superseded umbrella/background design. The authoritative unified
contract is workflow_lisp_unified_frontend_design.md. Keep this document for
rationale and detailed historical sketches.
```

For `workflow_lisp_frontend_mvp_specification.md`:

```text
Status: historical MVP tranche. Some deferred features listed here have since
been implemented or partially implemented. Use the unified design, current tests,
and current source for feature status.
```

For `workflow_lisp_proc_refs_partial_application.md`:

```text
Status: accepted delta, merged into workflow_lisp_unified_frontend_design.md.
Retain this file only for detailed historical rationale until fully removed.
```

For `workflow_lisp_let_proc_local_proc_refs.md`:

```text
Status: proposed delta, summarized in workflow_lisp_unified_frontend_design.md.
Do not mark implemented until the unified let-proc gate is satisfied.
```

For `workflow_lisp_runtime_closures_boundary.md`:

```text
Status: deferred gate, summarized in workflow_lisp_unified_frontend_design.md.
Current behavior remains the disabled profile.
```

### 24.3 Normalize path contract spelling

Use `:must-exist` consistently. Treat target paths as path types with `:must-exist false`, not a separate `:must-exist-target` spelling unless a compatibility alias is required.

### 24.4 Normalize diagnostic policy

Accepted/current features must define stable diagnostic codes. Proposed features must define them before integration. Remove language that leaves diagnostic names implementation-defined for accepted features.

### 24.5 Remove unsupported precision from effort estimates

Implementation effort percentages should be moved to planning docs or substantiated with task breakdowns. Design docs should specify gates, not unsupported precision.

## 25. Open issues

Open issues that require explicit follow-up:

1. **Exact current surface inventory.** Confirm which expression forms are parser/typechecker/lowering-current through tests, not design docs alone.
2. **Module syntax compatibility.** Decide whether both MVP-style and `defmodule` headers remain accepted.
3. **Core AST naming.** Decide whether the current ordinary workflow dictionary boundary should be named Core AST in code or kept distinct until a true syntax-neutral AST is introduced.
4. **Semantic IR status.** Decide which parts of Semantic IR are implemented data structures versus design vocabulary.
5. **Effect graph completeness.** Identify minimum effect checks required before `let-proc` V1.
6. **WorkflowRef runtime boundary.** Clarify exactly when workflow references may cross exported workflow boundaries and what lowerable representation is allowed.
7. **Macro scope.** Distinguish current macro support from full hygienic macro design.
8. **Legacy adapters.** Decide whether legacy adapter syntax is a language feature or a tooling/configuration boundary.
9. **Debug YAML renderer.** Decide whether to keep a renderer and how to prevent it from becoming semantic authority.
10. **Provider-role authority.** Keep provider-role capture forbidden for runtime closures until a full capability-capture model exists.

## 26. Minimal examples

### 26.1 Typed provider result and variant proof

```lisp
(defunion ReviewResult
  (APPROVED
    (review-report Path.review-report))
  (REVISE
    (review-report Path.review-report)
    (revision-guidance String)))

(defworkflow review-plan
  ((ctx PhaseCtx)
   (plan Path.plan)
   (provider ProviderRole))
  -> ReviewResult
  :effects ((reads plan)
            (uses-provider provider)
            (writes Path.review-report)
            (updates-state ctx))

  (let* ((review (provider-result provider
                   :prompt prompts.review-plan
                   :inputs (record ReviewInputs :plan plan)
                   :returns ReviewResult)))
    (match review
      ((APPROVED approved)
        approved)
      ((REVISE revise)
        revise))))
```

### 26.2 Compile-time procedure reference

```lisp
(defproc run-implementation
  ((selected SelectedItem)
   (design Path.design)
   (plan Path.plan)
   (providers ImplementationProviders))
  -> ImplementationResult
  :effects ((reads design plan)
            (uses-provider providers.execute providers.review providers.fix)
            (writes Path.execution-report Path.checks-report Path.review-report))
  ...)

(defproc run-one-selected
  ((selected SelectedItem)
   (execute ProcRef[SelectedItem -> ImplementationResult]))
  -> ImplementationResult
  (call execute :selected selected))

(defworkflow run-selected
  ((selected SelectedItem)
   (design Path.design)
   (plan Path.plan)
   (providers ImplementationProviders))
  -> ImplementationResult

  (let* ((execute (bind-proc (proc-ref run-implementation)
                    :design design
                    :plan plan
                    :providers providers)))
    (call run-one-selected
      :selected selected
      :execute execute)))
```

After specialization, no runtime artifact contains `execute` as a procedure value. The lowered artifact contains ordinary generated procedure/workflow structure.

### 26.3 Proposed `let-proc`

```lisp
(defworkflow run-selected-with-local-impl
  ((selected SelectedItem)
   (design Path.design)
   (plan Path.plan)
   (providers ImplementationProviders))
  -> ImplementationResult

  (let-proc
    (local-impl
      ((item SelectedItem)) -> ImplementationResult
      :captures (design plan providers)
      (call run-implementation
        :selected item
        :design design
        :plan plan
        :providers providers))

    (call run-one-selected
      :selected selected
      :execute (proc-ref local-impl))))
```

This is equivalent to a private generated `defproc` plus compile-time `ProcRef` specialization. It is not a runtime closure.

### 26.4 Runtime closure remains rejected

Invalid:

```lisp
(record SomeOutput
  :callback (lambda (x) (call run-implementation :selected x)))
```

Invalid:

```lisp
(provider-result provider
  :prompt prompts.choose-procedure
  :returns ProcRef[SelectedItem -> ImplementationResult])
```

Both must be rejected. Runtime-provided or runtime-stored callable values are outside the accepted surface.

