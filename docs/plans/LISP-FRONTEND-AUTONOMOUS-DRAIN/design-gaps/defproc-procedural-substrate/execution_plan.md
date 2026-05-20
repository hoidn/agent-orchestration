# Defproc Procedural Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the bounded same-file `defproc` procedural substrate to the existing Workflow Lisp frontend so reusable effectful procedures compile, validate, and lower through the current Stage 3/4 path with explicit effect signatures, deterministic lowering policy, and preserved provenance.

**Architecture:** Keep all new ownership inside `orchestrator/workflow_lisp/`. Insert a frontend-only procedure layer between macro expansion and the current workflow body typing/lowering path: collect `defproc` signatures before body checking, attach frontend-local effect summaries to every typed expression, validate declared procedure effects against inferred transitive summaries, then lower eligible procedures either inline or as hidden private workflows through the existing authored-mapping and shared-validation seam. Runtime semantics stay in `orchestrator/workflow/`; this slice must not generate YAML text, bypass shared validation, or hide command/provider/state effects.

**Tech Stack:** Python 3, dataclasses, the existing `orchestrator.workflow_lisp` compiler/typecheck/lowering modules, shared workflow elaboration/lowering in `orchestrator.workflow`, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as the implementation authority for this slice:

- `docs/index.md`
- `docs/steering.md`
  - currently empty; there are no extra local steering constraints beyond repo policy
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `8.8 defproc`
  - `10. Sequential Binding: let*`
  - `16. Effect System`
  - `38. Intermediate Overview`
  - `51. defproc Lowering`
  - `61. Effect Validation`
  - `74. Source Map Requirements`
  - `100. Stage 2: Procedural Substrate`
  - `106. Procedure Lowering Policy`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `14. Implementation Stages`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; there is no prior execution history to preserve for this gap

## Hard Scope Limits

Implement only the bounded `defproc` substrate from the work-item context:

- same-file top-level `defproc` definition elaboration and forward-reference binding;
- explicit `:effects` parsing, canonicalization, and validation against inferred transitive effect summaries;
- a procedure-call expression surface inside the existing typed-expression pipeline;
- frontend-local effect-summary tracking on every typed expression;
- deterministic `inline`, `private-workflow`, and `auto` lowering resolution;
- inline lowering and hidden private-workflow lowering for eligible procedures;
- private-workflow and `auto` eligibility constrained by the current same-file Stage 3 workflow-call seam;
- provenance that preserves both procedure definition and call-site blame through shared-validation remapping.

Explicit non-goals:

- no standard-library procedure APIs such as `run-provider-phase`, `review-revise-loop`, `resume-or-start`, `resource-transition`, `finalize-selected-item`, or `backlog-drain`;
- no runtime-native effect promotion, queue/ledger backends, new resource movement semantics, or `.orc` runtime entrypoint work;
- no `defun`, modules/imports/exports, higher-order procedure values, workflow refs, or recursive procedure execution model;
- no redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant proof;
- no weakening of the command-adapter contract for `command-result` inside procedures;
- no YAML text generation, markdown report parsing, pointer-as-state bridges, inline semantic shell, or inline semantic Python.

## Current Baseline

The implementation must extend the repo as it exists now:

- `orchestrator/workflow_lisp/compiler.py` currently compiles only definitions plus same-file `defworkflow` forms via `_expanded_syntax_module(...) -> elaborate_definition_module(...) -> elaborate_workflow_definitions(...) -> build_workflow_catalog(...) -> typecheck_workflow_definitions(...) -> lower_workflow_definitions(...)`.
- `orchestrator/workflow_lisp/macros.py` already exists, so procedure support must coexist with the existing macro expansion pass instead of replacing it.
- `orchestrator/workflow_lisp/expressions.py` currently supports `CallExpr`, `WithPhaseExpr`, `PhaseTargetExpr`, `ProviderResultExpr`, and `CommandResultExpr`, but there is no `ProcedureCallExpr`.
- `orchestrator/workflow_lisp/typecheck.py` currently gives `TypedExpr` only `expr`, `type_ref`, `span`, and `form_path`; there is no effect-summary propagation yet.
- `orchestrator/workflow_lisp/workflows.py` is the only same-file callable registry today, and Stage 3 workflow boundary checks already exist via `analyze_workflow_boundary_type(...)`.
- `orchestrator/workflow_lisp/lowering.py` lowers typed workflows, workflow calls, structured results, and phase-scoped translation, but it has no concept of inline procedure frames or generated private procedures.
- `tests/test_workflow_lisp_procedures.py` does not exist yet; macros, structured results, lowering, and first-phase translation tests already exist and must continue to pass.

## Execution Notes

Do not re-decide these during implementation:

- `defproc` is same-file only in this slice.
- Every `defproc` must declare `:effects`.
- `:lowering` is optional and defaults to `auto`.
- Procedure calls use positional arguments only and resolve only against same-file procedures after reserved special forms and explicit workflow `call` handling.
- `auto` may choose `private-workflow` only when the procedure signature is Stage-3-boundary-lowerable, every reachable call site can lower through the existing same-file `call` binding seam, and the procedure has more than one distinct same-file call site.
- `private-workflow` must fail for `Json`, `Provider`, `Prompt`, union-typed boundaries, or any bound arguments that cannot already lower through `_render_call_binding_ref(...)` and flattened imported-bundle mappings.
- Recursive or mutually recursive procedures are rejected with `proc_lowering_cycle`.
- Workflow authored surface stays unchanged; workflow effect summaries are inferred frontend metadata, not a new authored `:effects` clause.
- Structured bundles remain authority, reports stay views, artifact values stay authority, and pointer files stay representations.
- Any path that touches `command-result` must continue obeying `docs/design/workflow_command_adapter_contract.md`.

## File Ownership

Create:

- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/procedures.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/fixtures/workflow_lisp/valid/defproc_inline.orc`
- `tests/fixtures/workflow_lisp/valid/defproc_private_workflow.orc`
- `tests/fixtures/workflow_lisp/invalid/procedure_effect_mismatch.orc`
- `tests/fixtures/workflow_lisp/invalid/procedure_cycle.orc`
- `tests/fixtures/workflow_lisp/invalid/procedure_private_boundary_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/procedure_arity_mismatch.orc`

Modify:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_lowering.py`

Modify only if a focused failing test proves the need:

- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/macros.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_phase_translation.py`

Reuse without broadening ownership:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/sexpr.py`
- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/phase.py`
- shared workflow validation/runtime modules under `orchestrator/workflow/`

## Locked Contracts

Keep the new frontend surface exact and bounded.

Authoring shape for this slice:

```lisp
(defproc ensure-approved-plan
  ((ctx PhaseCtx)
   (selected SelectedItemInputs)
   (providers PlanProviders))
  -> PlanGateResult
  :effects
    ((reads selected selected.selected-item-context-path)
     (uses-provider providers.generate providers.review)
     (writes Path.plan-target Path.review-report)
     (updates-state ctx))
  :lowering auto
  body)
```

Rules:

- top-level same-file `defproc` only;
- parameter list, `->`, return type, and exactly one body expression are required;
- `:effects` is required and must normalize to a canonical typed effect signature;
- `:lowering` accepts only `inline`, `private-workflow`, or `auto`;
- omission of `:lowering` means `auto`;
- procedure calls are headed lists such as `(ensure-approved-plan ctx selected providers.plan)`;
- workflow calls remain explicit `(call workflow-name :arg value ...)`;
- reserved special forms keep precedence over procedure-name resolution.

Required new frontend-local types:

```python
# orchestrator/workflow_lisp/effects.py
@dataclass(frozen=True)
class ReadEffect: ...

@dataclass(frozen=True)
class WriteEffect: ...

@dataclass(frozen=True)
class PublishEffect: ...

@dataclass(frozen=True)
class UsesProviderEffect: ...

@dataclass(frozen=True)
class UsesCommandEffect: ...

@dataclass(frozen=True)
class CallsWorkflowEffect: ...

@dataclass(frozen=True)
class UpdatesStateEffect: ...

EffectAtom = (
    ReadEffect
    | WriteEffect
    | PublishEffect
    | UsesProviderEffect
    | UsesCommandEffect
    | CallsWorkflowEffect
    | UpdatesStateEffect
)

@dataclass(frozen=True)
class ProcedureCallEdge:
    callee_name: str

@dataclass(frozen=True)
class EffectSummary:
    direct_effects: frozenset[EffectAtom]
    transitive_effects: frozenset[EffectAtom]
    procedure_edges: frozenset[ProcedureCallEdge]
```

```python
# orchestrator/workflow_lisp/procedures.py
@dataclass(frozen=True)
class ProcedureParam: ...

class ProcedureLoweringMode(StrEnum):
    INLINE = "inline"
    PRIVATE_WORKFLOW = "private-workflow"
    AUTO = "auto"

@dataclass(frozen=True)
class ProcedureDef: ...

@dataclass(frozen=True)
class ProcedureSignature: ...

@dataclass(frozen=True)
class TypedProcedureDef: ...

@dataclass(frozen=True)
class ProcedureCatalog:
    signatures_by_name: Mapping[str, ProcedureSignature]
    definitions_by_name: Mapping[str, ProcedureDef]
    call_graph: Mapping[str, frozenset[str]]
```

```python
# orchestrator/workflow_lisp/expressions.py
@dataclass(frozen=True)
class ProcedureCallExpr:
    callee_name: str
    args: tuple[ExprNode, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
```

```python
# orchestrator/workflow_lisp/typecheck.py
@dataclass(frozen=True)
class TypedExpr:
    expr: ExprNode
    type_ref: TypeRef
    effect_summary: EffectSummary
    span: SourceSpan
    form_path: tuple[str, ...]
```

```python
# orchestrator/workflow_lisp/compiler.py or workflows.py
@dataclass(frozen=True)
class Stage3CompileResult:
    module: WorkflowLispModule
    workflow_catalog: WorkflowCatalog
    procedure_catalog: ProcedureCatalog
    extern_environment: ExternEnvironment
    command_boundary_environment: CommandBoundaryEnvironment
    typed_procedures: tuple[TypedProcedureDef, ...]
    typed_workflows: tuple[TypedWorkflowDef, ...]
    lowered_workflows: tuple[LoweredWorkflow, ...]
    validated_bundles: Mapping[str, LoadedWorkflowBundle]
```

Required diagnostics for this slice:

- `procedure_definition_duplicate`
- `procedure_effect_missing`
- `procedure_effect_invalid`
- `procedure_call_unknown`
- `procedure_arity_mismatch`
- `procedure_return_type_invalid`
- `procedure_effect_mismatch`
- `proc_lowering_cycle`
- `proc_private_workflow_boundary_invalid`
- `proc_lowering_annotation_invalid`

Diagnostic precedence for same-file headed lists:

- reserved special forms and explicit workflow `(call ...)` keep their existing diagnostics;
- any other non-reserved symbol-headed list is now interpreted as a procedure-call surface for this slice;
- if that head does not resolve to a same-file procedure, raise `procedure_call_unknown` instead of the generic `expression_form_unknown` fallback.

Keep these existing diagnostics authoritative where they already fit:

- `type_unknown`
- `type_mismatch`
- `return_type_mismatch`
- `workflow_boundary_type_invalid`
- `shared_validation_error`
- command-adapter diagnostics already emitted by `command-result`

Private-workflow naming and provenance contract:

- generated private workflow names are deterministic and module-scoped, for example `%neurips.implementation.ensure-approved-plan.v1`;
- every generated core/workflow node created from a procedure must retain:
  - procedure definition span/form path
  - procedure call-site span/form path
  - macro expansion stack, if any
- shared-validation remaps must render procedure notes in addition to existing macro notes when a generated node originates from a procedure frame.

## Task 1: Re-Baseline Fixtures And Add Failing Procedure Tests

**Files:**

- Create: `tests/test_workflow_lisp_procedures.py`
- Create: `tests/fixtures/workflow_lisp/valid/defproc_inline.orc`
- Create: `tests/fixtures/workflow_lisp/valid/defproc_private_workflow.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/procedure_effect_mismatch.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/procedure_cycle.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/procedure_private_boundary_invalid.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/procedure_arity_mismatch.orc`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Author fixtures that pin the bounded substrate behaviors**

Create fixtures with one clear responsibility each:

- `defproc_inline.orc`: same-file forward-referenced `defproc` used from a workflow body, explicit `:effects`, `:lowering inline`, positional arguments, and an effectful body that exercises nested typed expression propagation.
- `defproc_private_workflow.orc`: one boundary-lowerable procedure reused from more than one call site so `auto` or explicit `private-workflow` can lower it to a hidden generated workflow.
- `procedure_effect_mismatch.orc`: declared `:effects` omit or misstate a transitive effect so the compiler raises `procedure_effect_mismatch`.
- `procedure_cycle.orc`: recursive or mutually recursive procedures so cycle rejection is deterministic.
- `procedure_private_boundary_invalid.orc`: a procedure whose signature or reachable call bindings include a non-lowerable boundary type such as a union or `Json`, proving `private-workflow` rejection.
- `procedure_arity_mismatch.orc`: wrong positional argument count at a procedure call site.

- [ ] **Step 2: Add failing focused tests before implementation**

In `tests/test_workflow_lisp_procedures.py`, add failing tests that lock the intended contracts:

- procedure catalog collection before body checking so forward references succeed;
- procedure-call elaboration for same-file headed lists;
- unknown non-reserved symbol-headed lists raise `procedure_call_unknown`;
- required `:effects` presence and canonical mismatch rejection;
- cycle rejection with deterministic source spans;
- `auto` resolving to inline for single-use or non-boundary-lowerable procedures;
- `auto` or explicit `private-workflow` resolving to generated workflows only when the Stage 3 boundary seam is satisfied;
- provenance notes carrying both call site and definition site on remapped diagnostics.

Prefer exact test names along these lines:

```python
def test_compile_stage3_collects_defproc_catalog_before_body_checking() -> None: ...
def test_typecheck_supports_same_file_procedure_calls() -> None: ...
def test_elaboration_rejects_unknown_same_file_procedure_call_heads() -> None: ...
def test_typecheck_rejects_procedure_effect_mismatch() -> None: ...
def test_compile_rejects_recursive_procedure_cycle() -> None: ...
def test_lowering_generates_private_workflow_for_reused_boundary_lowerable_procedure() -> None: ...
def test_lowering_rejects_private_workflow_for_non_boundary_type() -> None: ...
```

- [ ] **Step 3: Register compatibility expectations in existing test modules**

Update existing focused tests only where they prove procedure integration:

- `tests/test_workflow_lisp_expressions.py`: a non-reserved headed list now elaborates as `ProcedureCallExpr` when the head resolves to a same-file procedure.
- `tests/test_workflow_lisp_expressions.py`: a non-reserved symbol-headed list whose head does not resolve to a same-file procedure raises `procedure_call_unknown`.
- `tests/test_workflow_lisp_workflows.py`: `compile_stage3_module(...)` exposes procedure catalog and typed procedures without changing ordinary workflow signatures.
- `tests/test_workflow_lisp_lowering.py`: generated private workflows appear in the lowered set with deterministic names and preserve shared-validation-compatible call surfaces.
- `tests/test_workflow_lisp_diagnostics.py`: remapped diagnostics render procedure definition and call-site notes in stable order.

- [ ] **Step 4: Collect and run the new failing selectors**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_workflow_lisp_procedures.py -q
```

Expected before implementation:

- collect-only succeeds and lists the new procedure tests;
- the test run fails on missing procedure/effect/lowering support, not on fixture loading or unrelated regressions.

## Task 2: Add Procedure And Effect Models, Then Rewire The Compiler Pipeline

**Files:**

- Create: `orchestrator/workflow_lisp/effects.py`
- Create: `orchestrator/workflow_lisp/procedures.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`

- [ ] **Step 1: Implement canonical frontend-local effect types and normalization helpers**

In `orchestrator/workflow_lisp/effects.py`:

- define the typed effect atoms from the architecture;
- add parsing helpers that turn authored `:effects` lists into deterministic canonical sets;
- add union/merge helpers for ordered child summaries and transitive-summary comparison;
- keep reserved effect kinds out of scope rather than admitting opaque stringly typed effects.

- [ ] **Step 2: Implement `defproc` AST, signature, and catalog support**

In `orchestrator/workflow_lisp/procedures.py`:

- elaborate top-level `defproc` forms from expanded syntax;
- validate required shape: name, params, `->`, return type, `:effects`, optional `:lowering`, and exactly one body;
- resolve parameter and return type refs through the existing `FrontendTypeEnvironment`;
- parse and canonicalize declared effects;
- build a same-file `ProcedureCatalog` before any procedure or workflow body is checked;
- reject duplicate procedure definitions and invalid lowering annotations with the new diagnostics.

- [ ] **Step 3: Reorder the compiler to register all callable signatures before body checking**

Update `orchestrator/workflow_lisp/compiler.py` so `compile_stage3_module(...)` performs:

1. macro expansion;
2. definition elaboration and type-environment creation;
3. workflow elaboration;
4. procedure elaboration;
5. workflow and procedure signature registration;
6. procedure body typing;
7. procedure call-graph and effect validation;
8. workflow body typing using resolved procedure summaries;
9. lowering-plan resolution and lowering;
10. shared validation.

The public entry point stays `compile_stage3_module(...)`; do not create a second public compiler API for procedures.

- [ ] **Step 4: Extend compile results without breaking existing Stage 3 consumers**

Add `procedure_catalog` and `typed_procedures` to `Stage3CompileResult`, and update `__init__.py` exports if the package currently re-exports compile-stage surfaces. Preserve existing fields and ordering semantics so current tests that inspect workflows still pass with additive assertions only.

- [ ] **Step 5: Run the catalog-level focused selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_workflow_lisp_workflows.py -q
```

Expected after this task:

- duplicate/malformed procedure definitions fail deterministically;
- forward references resolve at the catalog level;
- tests still fail only on not-yet-implemented expression typing or lowering branches.

## Task 3: Extend Expression Typing And Effect Validation

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] **Step 1: Add `ProcedureCallExpr` elaboration without disturbing existing special forms**

Update `orchestrator/workflow_lisp/expressions.py` so headed lists elaborate in this order:

1. reserved special forms keep their existing meaning;
2. explicit workflow `(call ...)` stays unchanged;
3. any other headed list whose head resolves to a same-file procedure becomes `ProcedureCallExpr`;
4. any other non-reserved symbol-headed list raises `procedure_call_unknown`;
5. non-symbol heads and malformed lists keep the existing structural parse diagnostics.

Keep procedure arguments positional only in this slice.

- [ ] **Step 2: Attach `EffectSummary` to every typed expression**

Update `TypedExpr` and the recursive typechecker so:

- pure literals, names, record construction, and type-safe field access produce empty summaries;
- `provider-result` produces `UsesProviderEffect` plus the write effect for its structured bundle root;
- `command-result` produces `UsesCommandEffect` plus the write effect for its structured bundle root;
- workflow `call` produces `CallsWorkflowEffect` plus the callee workflow's inferred summary;
- procedure `call` records a `ProcedureCallEdge` during first-pass checking and uses the callee declared signature for type/arity/return validation.

- [ ] **Step 3: Validate procedure calls, arity, return types, and effect declarations**

In `orchestrator/workflow_lisp/typecheck.py` and `orchestrator/workflow_lisp/procedures.py`:

- typecheck positional procedure arguments against declared parameter order;
- resolve the return type of each procedure call;
- compute direct expression summaries for each procedure body;
- build the same-file procedure call graph;
- reject recursive graphs with `proc_lowering_cycle`;
- compute transitive effect summaries by walking procedure and workflow call edges;
- compare normalized declared effects against inferred transitive effects exactly;
- infer workflow summaries without introducing a new authored workflow effect surface.

- [ ] **Step 4: Add stable diagnostic rendering for procedure provenance**

Extend diagnostics/origin helpers so procedure-generated notes render in deterministic order and coexist with existing macro notes. The rendered message must still begin with the generated node's primary span, then append notes for:

- procedure call site;
- procedure definition site;
- macro expansion stack, when present.

- [ ] **Step 5: Run focused typing and effect selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_workflows.py -q
```

Expected after this task:

- procedure-call typing passes;
- arity/effect/cycle diagnostics pass;
- existing workflow typing still passes with additive procedure support only.

## Task 4: Implement Deterministic Lowering Modes And Shared-Validation Provenance

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Resolve lowering mode deterministically**

Implement compiler-owned mode selection:

- `inline` always stays inline when the graph is acyclic;
- `private-workflow` succeeds only when parameter and return types pass `analyze_workflow_boundary_type(...)` and every reachable call site can lower through the existing same-file call-binding seam;
- `auto` picks `private-workflow` only for boundary-lowerable procedures with more than one distinct reachable same-file call site; otherwise it resolves to `inline`.

Do not add heuristics beyond these locked rules.

- [ ] **Step 2: Lower inline procedures through fresh lowering frames**

In `orchestrator/workflow_lisp/lowering.py`:

- lower argument expressions in author order;
- bind them into a fresh local frame for the callee parameters;
- lower the already-typed procedure body without re-elaboration or re-typechecking;
- use deterministic generated-name prefixes derived from caller workflow/procedure, callee procedure name, and call ordinal;
- merge generated steps, artifacts, and hidden inputs back into the caller context.

- [ ] **Step 3: Generate hidden private workflows through the existing workflow seam**

For `private-workflow` procedures:

- generate one deterministic hidden workflow per procedure definition;
- give it a stable name like `%<module>.<procedure>.v1`;
- lower its signature only through the existing workflow boundary rules and flattened imported-bundle mapping behavior;
- lower each procedure call site to an ordinary same-file workflow call using the current `_render_call_binding_ref(...)` and managed-input handling;
- reject any procedure whose reachable call sites cannot be expressed through the current seam with `proc_private_workflow_boundary_invalid`.

- [ ] **Step 4: Preserve definition and call-site provenance through shared validation**

Extend lowering-origin tracking so generated steps, inputs, outputs, and paths can be blamed on both:

- the original `defproc` definition;
- the specific procedure call site that caused the generated node.

The shared-validation remap path must continue to surface existing validation errors, but now with procedure notes attached when the generated node came from a procedure lowering frame.

- [ ] **Step 5: Run focused lowering selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_workflow_lisp_diagnostics.py -q
```

Expected after this task:

- inline lowering emits deterministic step names and hidden inputs;
- private-workflow lowering emits hidden workflow mappings and ordinary same-file call steps;
- shared-validation remaps preserve procedure provenance.

## Task 5: Run The Required Regression Stack And Finish With Visible Evidence

**Files:**

- Modify only if a targeted failure proves necessity: `tests/test_workflow_lisp_structured_results.py`
- Modify only if a targeted failure proves necessity: `tests/test_workflow_lisp_macros.py`
- Modify only if a targeted failure proves necessity: `tests/test_workflow_lisp_phase_translation.py`

- [ ] **Step 1: Re-run the exact verification contract from `check_commands.json`**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_workflow_lisp_phase_translation.py::test_runtime_completed_phase_translation_matches_oracle_shape tests/test_workflow_lisp_phase_translation.py::test_runtime_blocked_phase_translation_matches_oracle_shape -q
python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_phase_translation.py -q
python -m pytest tests/test_workflow_lisp_reader.py tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_phase_translation.py tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_procedures.py -q
```

Expected:

- the new procedure module collects successfully;
- focused procedure tests pass;
- expression/workflow/lowering regressions pass;
- the phase-translation runtime smoke selectors still pass;
- the full focused Workflow Lisp frontend stack passes.

- [ ] **Step 2: Fix only demonstrated regressions**

If macro, structured-result, or phase-translation tests fail:

- inspect the specific failure first;
- patch only the minimal compatibility surface needed;
- do not widen this work into macro redesign, phase-library work, or broader workflow-surface changes.

- [ ] **Step 3: Capture completion evidence**

Before handing the slice off as done, record:

- which files changed;
- which of the commands above passed;
- whether any `modify only if failing test proves need` files were touched and why;
- any residual limitation intentionally deferred by the bounded scope, if one remains.

Do not claim completion from inspection alone; completion requires fresh passing command output.
