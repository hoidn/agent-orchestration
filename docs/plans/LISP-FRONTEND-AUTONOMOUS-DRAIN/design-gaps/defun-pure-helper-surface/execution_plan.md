# Workflow Lisp `defun` Pure Helper Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bounded Workflow Lisp `defun` pure-helper surface so `.orc` modules can declare importable pure helpers, call them positionally from helper/procedure/workflow bodies, reject effectful helper semantics deterministically, and normalize helper calls away before lowering reaches runtime-facing workflow machinery.

**Architecture:** Keep `defun` entirely frontend-local inside `orchestrator/workflow_lisp/`. Add one helper-definition layer in `functions.py`, extend the existing module graph and direct-head call resolution to include helpers, typecheck helper calls through the current typed-expression substrate, and normalize helper calls into `let*` plus existing pure expression nodes before procedure/workflow lowering. Reuse the current compile pipeline, `LispFrontendDiagnostic`, `EffectSummary`, `LoweringOriginMap`, source-map bridge, and linked-module compilation flow rather than adding a compile-time evaluator or a new runtime helper boundary.

**Tech Stack:** Python dataclasses, `orchestrator/workflow_lisp`, shared `orchestrator.workflow` validation/runtime surfaces, pytest, existing Workflow Lisp fixtures under `tests/fixtures/workflow_lisp/`, and the existing `python -m orchestrator compile ...` CLI smoke path.

---

## Fixed Inputs

Read these before implementation and treat them as authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `8.6 defun`
  - `10. Sequential Binding: let*`
  - `11. Pattern Matching`
  - `38. Intermediate Overview`
  - `44. Typed Frontend AST`
  - `50. defworkflow Lowering`
  - `51. defproc Lowering`
  - `60. Type Validation`
  - `61. Effect Validation`
  - `74. Source Map Requirements`
  - `99. Stage 1: Frontend Core Without Workflow Execution`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defun-pure-helper-surface/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/3/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/3/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Reference these implementation seams before editing:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_workflows.py`

## Current Repo Baseline

Assume this exact starting point:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `progress_ledger.json` is still `{"ledger_version":1,"events":[]}`.
- `orchestrator/workflow_lisp/functions.py` does not exist yet.
- `orchestrator/workflow_lisp/definitions.py` still treats only `defenum`, `defpath`, `defrecord`, and `defunion` as type definitions and rejects `defun` as an unsupported definition form.
- `orchestrator/workflow_lisp/compiler.py` still omits `defun` from definition-only filtering, Stage 1 top-level admission, and linked catalog construction.
- `orchestrator/workflow_lisp/macros.py` still omits `defun` from both the reserved macro-name set and the allowed expanded top-level heads.
- `orchestrator/workflow_lisp/modules.py` exports and imports only types, macros, procedures, and workflows; there is no helper namespace.
- `orchestrator/workflow_lisp/expressions.py` supports `ProcedureCallExpr` but no frontend-local pure-function call node.
- `orchestrator/workflow_lisp/typecheck.py` already carries `effect_summary` on each `TypedExpr`, which is the effect-accounting seam for helper calls, but it has no function catalog input and no helper-purity path.
- `tests/test_workflow_lisp_modules.py` already exists from the module slice, so helper import/export coverage must extend that suite rather than replacing it.

Execution rule for this plan: if the current checkout diverges from the approved implementation architecture, the approved architecture and the failing tests written from this plan win. If a focused failing test shows the frontend-owned contract is insufficient, stop implementation, record the failure as an architecture gap, and revise the approved architecture/plan rather than patching shared runtime ownership boundaries.

## Hard Scope Limits

Implement only the bounded `defun-pure-helper-surface` slice:

- top-level `defun` definition parsing and elaboration;
- same-file and imported helper catalogs with forward references;
- module export/import support for helpers;
- direct-head helper call resolution inside expressions;
- helper/procedure direct-head namespace collision checks;
- helper purity validation over the currently implemented pure expression surface;
- helper arity, return-type, and cycle validation;
- pre-lowering helper-call normalization into existing pure expression nodes;
- helper-aware diagnostics and provenance notes;
- focused fixtures and tests for syntax, imports, purity, typing, normalization, and lowering compatibility.

Explicit non-goals:

- no new pure stdlib primitives such as arithmetic, string concatenation, or path join;
- no general compile-time evaluator, partial evaluator, or helper execution during macro expansion;
- no effectful helper surface, `defproc` redesign, or workflow-boundary redesign;
- no new runtime call boundary, no helper bundles, and no shared Core AST / Semantic IR redesign;
- no new persisted artifacts beyond the existing diagnostics/source-map/build outputs;
- no changes to shared runtime modules under `orchestrator/workflow/`; if a focused failing test shows the frontend-owned contract cannot meet the slice, stop and escalate for architecture/plan revision instead of widening implementation ownership in this work item.

## Locked Contracts

Do not re-decide these during implementation.

Helper surface:

```lisp
(defun helper-name
  ((arg Type) ...)
  -> ReturnType
  body)
```

Compilation-order contract:

1. elaborate type definitions;
2. elaborate raw helper definitions;
3. elaborate raw procedure definitions;
4. elaborate raw workflow definitions;
5. derive export surfaces including helper exports;
6. build import scope;
7. resolve helper signatures from local and imported definitions;
8. typecheck helper bodies;
9. typecheck procedures and workflows against the completed helper catalog;
10. normalize helper calls before any lowering path that expects only existing lowerable expressions.

Namespace contract:

- `defun` and `defproc` share one visible direct-head namespace.
- Workflows remain separate because they require explicit `call`.
- Local and imported helper/procedure name collisions must fail deterministically instead of using resolution order.

Purity contract:

- legal helper-body forms in this slice:
  - literals
  - lexical name references
  - field access
  - `record`
  - `let*`
  - `match`
  - helper-to-helper `FunctionCallExpr`
- explicitly illegal anywhere inside a helper body:
  - workflow `call`
  - `ProcedureCallExpr`
  - `provider-result`
  - `command-result`
  - `with-phase`
  - `phase-target`
  - `run-provider-phase`
  - `produce-one-of`
  - `review-revise-loop`
  - `resume-or-start`
  - `resource-transition`
  - `finalize-selected-item`
  - `backlog-drain`
- helper purity is an authored contract, not an inferred empty-effect heuristic; emit `pure_function_has_effect` whenever one of the forbidden surfaces appears.

Normalization contract:

```text
(helper arg1 arg2)
  =>
(let* ((p1 arg1)
       (p2 arg2))
  helper-body)
```

Rules:

- evaluate arguments once and in order;
- preserve helper parameter names in the generated `let*` bindings;
- recursively normalize nested helper calls until no `FunctionCallExpr` remains;
- run normalization after successful typing and before procedure/workflow lowering;
- helpers stay compile-time/frontend-local and disappear before runtime-facing lowering.

Diagnostic contract:

- add these helper-specific codes unless an existing code already matches exactly:
  - `function_definition_duplicate`
  - `function_call_unknown`
  - `function_arity_mismatch`
  - `function_cycle`
  - `pure_function_has_effect`
  - `function_return_type_invalid`
  - `callable_name_collision`
- continue reusing generic codes where they already fit exactly:
  - `type_unknown`
  - `type_mismatch`
  - `name_unknown`
  - `variant_ref_unproved`
  - existing module import/export ambiguity codes

Internal API contract for the new helper layer:

```text
FunctionParam
FunctionDef
FunctionSignature
TypedFunctionDef
FunctionCatalog
elaborate_function_definitions(...)
build_function_catalog(...)
typecheck_function_definitions(...)
validate_function_cycles(...)
normalize_function_calls(...)
```

The exact helper can be split further if needed, but the implementation must still provide:

- a raw helper-definition elaboration step;
- a signature catalog usable before body typing;
- a typed helper-definition result;
- a cycle-validation step;
- a normalization entrypoint callable from `compiler.py`.

## File Ownership

Create:

- `orchestrator/workflow_lisp/functions.py`
- `tests/test_workflow_lisp_functions.py`
- `tests/fixtures/workflow_lisp/valid/defun_local.orc`
- `tests/fixtures/workflow_lisp/valid/defun_forward_ref.orc`
- `tests/fixtures/workflow_lisp/invalid/defun_effectful.orc`
- `tests/fixtures/workflow_lisp/invalid/defun_cycle.orc`
- `tests/fixtures/workflow_lisp/invalid/defun_proc_name_collision.orc`
- `tests/fixtures/workflow_lisp/modules/valid/imported_defun/entry.orc`
- `tests/fixtures/workflow_lisp/modules/valid/imported_defun/neurips/helpers.orc`
- `tests/fixtures/workflow_lisp/modules/valid/imported_defun/neurips/types.orc`

Modify:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_expressions.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_macros.py`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_workflows.py`

Modify only if a focused failing test proves it is necessary:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/build.py`
- `tests/test_workflow_lisp_diagnostics.py`

Do not broaden ownership into:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/source_map.py`
- shared runtime/validation modules under `orchestrator/workflow/`

## Task 1: Lock Fixtures And Failing Tests

**Files:**

- Create: `tests/test_workflow_lisp_functions.py`
- Create: the helper fixtures listed in File Ownership
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_macros.py`

- [ ] **Step 1: Add valid and invalid helper fixtures that pin the contract**

Create fixtures that prove one rule each:

- `valid/defun_local.orc`
  - one local helper used from a workflow;
- `valid/defun_forward_ref.orc`
  - one helper calling another helper defined later in the file;
- `invalid/defun_effectful.orc`
  - helper body contains one forbidden effectful form such as `command-result`;
- `invalid/defun_cycle.orc`
  - two helpers calling each other;
- `invalid/defun_proc_name_collision.orc`
  - local `defun` and `defproc` share the same visible name;
- `modules/valid/imported_defun/...`
  - entry workflow imports one helper from another module and compiles through the linked entrypoint flow.

- [ ] **Step 2: Add failing helper-focused tests before implementation**

In `tests/test_workflow_lisp_functions.py`, add narrow tests for:

- local helper catalog construction before body checking;
- helper forward references;
- helper return-type checking;
- `pure_function_has_effect` on forbidden surfaces;
- `function_cycle` on direct and mutual recursion;
- helper call normalization removing `FunctionCallExpr` before lowering;
- one imported-helper compile smoke using the linked module entrypoint helper graph.

Augment existing suites with targeted assertions:

- `tests/test_workflow_lisp_expressions.py`
  - elaboration produces `FunctionCallExpr` for visible helpers;
  - unknown bare call heads still fail deterministically;
- `tests/test_workflow_lisp_modules.py`
  - helper exports appear in `functions_by_name`;
  - imported helpers resolve to canonical `<module>::<member>` keys;
  - helper/procedure visible-name collisions fail during import-scope construction;
- `tests/test_workflow_lisp_procedures.py`
  - procedures can call pure helpers and preserve only argument effects;
- `tests/test_workflow_lisp_workflows.py`
  - workflows can call local/imported helpers and still lower through existing workflow boundaries;
- `tests/test_workflow_lisp_lowering.py`
  - lowering sees only normalized pure nodes and no surviving `FunctionCallExpr`;
- `tests/test_workflow_lisp_macros.py`
  - `defun` is a reserved macro name;
  - macro expansion may emit top-level `defun`.

- [ ] **Step 3: Run collect-only on the touched test modules**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_macros.py -q
```

Expected: collection succeeds and the new helper tests appear.

- [ ] **Step 4: Run the narrow helper tests and confirm they fail first**

Run:

```bash
python -m pytest tests/test_workflow_lisp_functions.py -q
```

Expected: FAIL because the helper layer does not exist yet.

## Task 2: Add Helper Definitions, Catalogs, And Top-Level Admission

**Files:**

- Create: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/definitions.py`
- Modify: `orchestrator/workflow_lisp/macros.py`
- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`

- [ ] **Step 1: Add raw and typed helper-definition models in `functions.py`**

Implement the dedicated frontend-local data model:

```text
FunctionParam
FunctionDef
FunctionSignature
TypedFunctionDef
FunctionCatalog
```

`FunctionCatalog` must at least expose:

- `signatures_by_name`
- `definitions_by_name`
- `call_graph`

Use canonical module-qualified names in the same shape already used by procedures and workflows:

```text
<module-name>::<member-name>
```

- [ ] **Step 2: Admit `defun` in the top-level pipeline without making it a type definition**

Patch `compiler.py`, `definitions.py`, and any existing definition-only filtering helpers so that:

- Stage 1 top-level validation accepts `defun`;
- definition-only extraction strips `defun` before `elaborate_definition_module(...)`;
- `WorkflowLispModule.definitions` remains type-only authority;
- helper forms are elaborated through `functions.py`, not through `definitions.py`.

- [ ] **Step 3: Extend macro rules and module export surfaces**

Patch `macros.py` so:

- `defun` is reserved as a macro name;
- expanded top-level `defun` forms are accepted.

Patch `modules.py` so:

- `ModuleExportSurface` gains `functions_by_name`;
- `ModuleImportScope` gains `function_bindings` and `resolve_function_name(...)`;
- helper exports/imports stay compile-time/frontend-local only;
- helper/procedure visible-name conflicts raise `callable_name_collision` before call resolution becomes order-dependent.

- [ ] **Step 4: Run the helper/module/macro selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py -k "defun or function" -q
```

Expected: PASS for top-level admission, reserved-name handling, and helper export/import scope tests.

## Task 3: Add `FunctionCallExpr` Elaboration And Helper-Aware Typechecking

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `tests/test_workflow_lisp_expressions.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_workflows.py`

- [ ] **Step 1: Add `FunctionCallExpr` and direct-head helper resolution**

In `expressions.py`, add:

```text
FunctionCallExpr(callee_name, args, span, form_path, expansion_stack)
```

Update `elaborate_expression(...)` so list-head resolution order is:

1. special forms;
2. explicit workflow `call`;
3. visible helper call;
4. visible procedure call;
5. unknown-call diagnostic.

Use canonical helper names when resolving imported helpers. Preserve call-site span, form path, and expansion stack exactly as authored.

- [ ] **Step 2: Thread helper catalogs through expression typechecking**

Update `typecheck.py` so `typecheck_expression(...)` accepts a `function_catalog` and handles `FunctionCallExpr` by:

- checking arity positionally;
- typing each argument through the existing recursive path;
- checking the helper return type against the catalog signature;
- computing helper-call effect summary as `merge(arg.effects...)` with no direct helper effect atoms.

Do not inline or normalize during typechecking. The typed helper call must still exist until the dedicated normalization pass runs.

- [ ] **Step 3: Build helper signatures before procedure/workflow body typing**

Patch `compiler.py` so linked and single-file Stage 3 flows:

- elaborate raw helper definitions before raw procedure/workflow definitions depend on them;
- canonicalize local helper names with the current module key;
- build local/imported helper signature catalogs before helper body typing;
- pass the finished helper catalog into helper, procedure, and workflow body typechecking.

- [ ] **Step 4: Run the expression/procedure/workflow selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py -k "defun or pure_function or helper" -q
```

Expected: PASS for helper call elaboration, helper call typing, and workflow/procedure helper-use regressions.

## Task 4: Enforce Helper Purity, Return Types, And Cycles

**Files:**

- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_functions.py`

- [ ] **Step 1: Typecheck helper bodies against the pure expression subset**

Implement `typecheck_function_definitions(...)` in `functions.py` so helper bodies:

- start from a value environment containing only helper parameters;
- reuse the existing type environment and proof rules;
- may call only other helpers through `FunctionCallExpr`;
- reject every forbidden effectful expression family with `pure_function_has_effect`.

This validation must inspect authored helper bodies explicitly. Do not rely on an empty `EffectSummary` to imply purity.

- [ ] **Step 2: Validate exact helper return types**

When a helper body resolves to a type different from the declared return type, raise `function_return_type_invalid`. Do not weaken this into a generic compatibility check.

- [ ] **Step 3: Build and validate the helper call graph**

From typed helper bodies, derive a call graph keyed by canonical helper name and reject:

- direct recursion;
- mutual recursion;
- any longer helper-only cycle.

Use `function_cycle` and include the authored helper span as primary blame.

- [ ] **Step 4: Re-run the focused helper unit tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_functions.py -q
```

Expected: PASS for purity, return-type, arity, forward-reference, and cycle coverage.

## Task 5: Normalize Helper Calls Before Lowering And Preserve Provenance

**Files:**

- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_functions.py`

- [ ] **Step 1: Implement the helper-call normalization pass**

Add a normalization entrypoint that rewrites typed helper, procedure, and workflow bodies from:

```text
FunctionCallExpr(helper, args...)
```

into:

```text
LetStarExpr(bindings=((param_1, arg_1), ...), body=helper_body_clone)
```

Requirements:

- preserve single evaluation of arguments and their authored ordering;
- clone the callee body with provenance retained on the cloned nodes;
- normalize nested helper calls recursively until no `FunctionCallExpr` remains;
- leave helper-free expressions unchanged.

- [ ] **Step 2: Insert normalization at the compiler seam that precedes lowering**

Patch `compiler.py` so normalization runs after helper/procedure/workflow typing has succeeded and before:

- authored workflow mapping generation;
- procedure lowering decisions such as inline versus private-workflow lowering;
- workflow lowering and shared validation.

Do not let runtime-facing lowering paths invent first-class helper behavior.

- [ ] **Step 3: Preserve call-site blame with helper-definition notes**

Use the existing diagnostic and lowering-origin plumbing so:

- primary blame remains on the authored helper call site;
- helper-definition span/name may appear as supporting context when a normalized body later causes a lowering or shared-validation failure;
- no new persisted provenance artifact is introduced.

- [ ] **Step 4: Run the lowering-focused regression selector**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k "defun or pure_function or helper" -q
```

Expected: PASS and no lowered workflow or procedure path should still contain `FunctionCallExpr`.

## Task 6: Final Verification And Compile Smoke

**Files:**

- Modify only as needed to fix any failing verification uncovered by this task.

- [ ] **Step 1: Run the focused repo command set from the approved architecture**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_macros.py -q
python -m pytest tests/test_workflow_lisp_functions.py -q
python -m pytest tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_macros.py -k "defun or function" -q
python -m pytest tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py -k "defun or pure_function or helper" -q
python -m orchestrator compile tests/fixtures/workflow_lisp/modules/valid/imported_defun/entry.orc --entry-workflow orchestrate --source-root tests/fixtures/workflow_lisp/modules/valid/imported_defun --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json
```

Expected:

- collect-only succeeds;
- helper unit tests pass;
- module and macro helper regressions pass;
- procedure/workflow/lowering helper regressions pass;
- CLI compile smoke succeeds for the imported-helper fixture graph.

- [ ] **Step 2: Verify the final acceptance conditions**

Confirm all of the following are true:

- `.orc` files may declare top-level `defun` helpers without definition-form rejection;
- helpers support same-file forward references and imported references through the linked module graph;
- helper bodies reject effectful forms with deterministic diagnostics;
- helper calls typecheck positionally and preserve only argument effect summaries;
- helper cycles are rejected deterministically;
- helper calls are normalized away before lowering reaches runtime-facing workflow machinery;
- helper-free existing workflows and procedures still pass the touched regression selectors unchanged.

- [ ] **Step 3: Record completion evidence in the implementation notes or handoff**

When handing off execution, include:

- which files were created or modified;
- the exact verification commands run;
- whether any optional files from the “modify only if necessary” list were touched and why.
