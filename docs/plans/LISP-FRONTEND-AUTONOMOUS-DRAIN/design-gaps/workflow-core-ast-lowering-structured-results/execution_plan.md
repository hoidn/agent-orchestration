# Workflow Core AST Lowering And Structured Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete and verify the bounded Workflow Lisp MVP Stage 3 slice so typed `defworkflow` forms, same-file `call`, `provider-result`, and `command-result` lower into authored workflow mappings, validate through the existing shared elaboration/lowering seam, and preserve authored-span diagnostics for generated workflow surfaces.

**Architecture:** Keep `orchestrator/workflow_lisp/` as the only frontend-owned boundary, preserve Stage 1 definitions plus Stage 2 type/proof checking as the source-language authority, and reuse the existing authored-workflow bridge by lowering to in-memory workflow mappings that pass through `elaborate_surface_workflow(...)` and `lower_surface_workflow(...)`. Workflow boundaries remain record-only in this tranche; structured provider/command results may still use record or union returns internally, provider/prompt references remain compiler-known externs, and same-file `call` lowering must use in-memory imported bundles plus generated hidden relpath write roots rather than authored `imports` paths or YAML text.

**Tech Stack:** Python 3 dataclasses, `orchestrator.workflow_lisp`, `orchestrator.workflow.elaboration`, `orchestrator.workflow.lowering`, `orchestrator.workflow.loaded_bundle.LoadedWorkflowBundle`, `orchestrator.loader.WorkflowLoader`, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Read these before implementation and treat them as design authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `14. Workflow Calls`
  - `22. Provider Result`
  - `23. Command Result`
  - `44. Typed Frontend AST`
  - `50. defworkflow Lowering`
  - `52. call Lowering`
  - `54. provider-result Lowering`
  - `59. Validation Sequence`
  - `60. Type Validation`
  - `61. Effect Validation`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `7. Provider And Command Results`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/architecture-review.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Reference implementation shapes when lowering:

- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/loaded_bundle.py`
- `workflows/examples/call_subworkflow_demo.yaml`
- `workflows/examples/match_demo.yaml`

## Current Repo Baseline

Assume this exact starting point:

- Stage 1 and Stage 2 frontend code already exists under `orchestrator/workflow_lisp/`.
- Stage 3-oriented modules already exist in the checkout:
  - `orchestrator/workflow_lisp/workflows.py`
  - `orchestrator/workflow_lisp/contracts.py`
  - `orchestrator/workflow_lisp/lowering.py`
  - `orchestrator/workflow_lisp/compiler.py`
- Stage 3-oriented tests and fixtures already exist:
  - `tests/test_workflow_lisp_workflows.py`
  - `tests/test_workflow_lisp_structured_results.py`
  - `tests/test_workflow_lisp_lowering.py`
  - `tests/fixtures/workflow_lisp/valid/structured_results.orc`
  - `tests/fixtures/workflow_lisp/invalid/shared_validation_remap.orc`
- `compile_stage3_module(...)` already exists. Preserve its additive relationship to `compile_stage1_module(...)`; do not collapse the two entrypoints together.
- `progress_ledger.json` is still empty, so treat the approved design docs, the current repo contents, and visible pytest output as authority rather than any recorded partial-progress state.

Execution rule for this plan: if current code diverges from the approved architecture, the architecture and the tests written from this plan win.

## Hard Scope Limits

Implement only the bounded Stage 3 slice described in the work-item context:

- same-file `defworkflow` elaboration and signature registration;
- effectful typing for `call`, `provider-result`, and `command-result`;
- workflow-boundary lowering only for types the shared surface already supports, with record-only workflow returns in this tranche;
- deterministic `output_bundle` and `variant_output` derivation for provider and command steps;
- explicit Stage 3 rejection of `Json` on workflow boundaries and generated structured-result contracts;
- compiler-known provider/prompt extern bindings that lower directly to existing provider-step surfaces;
- compiler-known command boundary bindings that classify `command-result` as plain external tool or certified adapter only;
- generated hidden relpath workflow inputs for structured-result managed write roots;
- same-file `call` lowering through compiler-generated aliases backed by in-memory imported bundles, not authored `imports` paths;
- workflow-return lowering only through current legal export surfaces: step artifacts or structured statement outputs;
- origin-based remapping of shared-validation failures back to authored `.orc` spans.

Explicit non-goals:

- no `defproc`, macros, imports/modules, higher-order workflow refs, or standard-library phase/resource/drain procedures;
- no runtime loader or CLI support for `.orc`;
- no new runtime execution semantics, no YAML generation, and no second validator path;
- no union workflow-boundary exports, optional workflow outputs, or provider/prompt transport across `call`;
- no adapter registries, legacy adapter framework, report parsing, pointer-authority changes, or runtime-native effects;
- no redesign of the shared Core Workflow AST, Semantic IR, SourceMap, or runtime proof model.

## Non-Negotiable Stage 3 Rules

Do not re-decide any of these during execution:

- Lower to in-memory authored workflow mappings, not YAML text and not frontend-specific runtime execution.
- Validate lowered workflows by calling `elaborate_surface_workflow(...)` and then `lower_surface_workflow(...)` with real in-memory imported bundles for same-file callees.
- Workflow boundaries are record-only in this tranche. `defworkflow` returns may not be unions.
- `Json` is a frontend-local primitive only. Reject it on workflow parameters, workflow return fields, and emitted `output_bundle` / `variant_output` field contracts with a frontend diagnostic instead of coercing it to `string`.
- `Provider` and `Prompt` values are compiler-known extern bindings, not workflow parameters and not `call` transport.
- `command-result` may use only validated `ExternalToolBinding` or `CertifiedAdapterBinding` entries. Generic semantic script wrappers remain compile-time errors.
- Same-file workflows that emit structured results must expose compiler-generated hidden relpath inputs for bundle write roots.
- Same-file `call` lowering must bind those hidden inputs with deterministic relpaths and supply the callee bundle via `imported_bundles`, not authored `imports`.
- Workflow outputs may lower only from legal existing shared surfaces: step artifacts or structured statement outputs.
- Shared-validation failures mentioning generated ids, paths, or flattened field names must remap to authored `.orc` spans or fail with `source_map_missing`.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/__init__.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/fixtures/workflow_lisp/valid/type_definitions.orc`
- `tests/fixtures/workflow_lisp/valid/structured_results.orc`
- `tests/fixtures/workflow_lisp/invalid/shared_validation_remap.orc`

Modify only if a targeted failing test proves the need:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/loader.py`

Do not broaden ownership into `orchestrator/workflow/` runtime code unless the lowering bridge genuinely cannot be implemented with the current shared helpers.

## Required Diagnostics

Preserve or add these Stage 3 diagnostic codes as the execution target:

- `workflow_definition_duplicate`
- `workflow_param_duplicate`
- `workflow_boundary_type_invalid`
- `workflow_return_type_invalid`
- `workflow_call_unknown`
- `workflow_signature_mismatch`
- `workflow_return_not_exportable`
- `return_type_mismatch`
- `provider_result_return_type_invalid`
- `provider_result_provider_invalid`
- `provider_result_prompt_invalid`
- `command_result_return_type_invalid`
- `command_result_argv_invalid`
- `command_adapter_missing_contract`
- `json_surface_unsupported`
- `inline_python_command_in_workflow`
- `inline_shell_command_in_workflow`
- `source_map_missing`

## Task 1: Re-Baseline Fixtures And Boundary Tests

**Files:**

- Modify: `tests/fixtures/workflow_lisp/valid/type_definitions.orc`
- Modify: `tests/fixtures/workflow_lisp/valid/structured_results.orc`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`

- [ ] **Step 1: Align the valid fixtures to the approved Stage 3 boundary model**

Keep the valid fixtures centered on these approved surfaces:

- `WorkReport` as the relpath boundary type;
- `ChecksResult` as a record returned directly from `command-result`;
- `ImplementationState` as the internal union returned by `provider-result`;
- `ImplementationSummary` as the record exported at workflow boundaries;
- one same-file caller that invokes a record-returning callee.

Do not keep `Provider`, `Prompt`, or `Json` on workflow parameters or return records in the valid fixtures.

- [ ] **Step 2: Replace stale assumptions with failing boundary tests**

Update or add tests so they fail first for these exact Stage 3 rules:

- workflow returns must be records, not unions;
- workflow params may not use `Provider`, `Prompt`, or `Json`;
- workflow return records may not contain `Provider`, `Prompt`, or `Json`;
- same-file `call` remains valid only when the callee boundary lowers to supported shared contracts.

Prefer `tmp_path` fixtures for one-off invalid inputs instead of creating many permanent `.orc` files.

- [ ] **Step 3: Add tests for the compiler-known symbol model**

In `tests/test_workflow_lisp_workflows.py`, cover that:

- `providers.execute` and `prompts.implementation.execute` elaborate as exact symbol references, not dotted field access;
- valid same-file calls do not transport provider/prompt values through workflow params;
- union workflow returns are rejected during workflow catalog construction or immediate boundary validation, not deferred until lowering.

- [ ] **Step 4: Run collection on the touched modules**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py -q
```

Expected: collection succeeds and the new Stage 3 rejection tests appear.

## Task 2: Tighten Workflow Boundary Validation And Contract Derivation

**Files:**

- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `tests/test_workflow_lisp_workflows.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`

- [ ] **Step 1: Centralize recursive boundary analysis**

Use one recursive helper shared across workflow signature building and contract derivation that answers:

- whether the type can lower through the current workflow boundary surface;
- whether it encountered `Json`;
- whether it encountered `Provider` or `Prompt`;
- whether it encountered a union at the workflow boundary.

This helper must recurse through record fields and path contracts. Do not duplicate Stage 3 boundary rules in multiple files.

- [ ] **Step 2: Enforce record-only workflow signatures**

In `build_workflow_catalog(...)`:

- require workflow return types to resolve to `RecordTypeRef`;
- reject union returns with `workflow_return_type_invalid` or `workflow_boundary_type_invalid`;
- reject parameters and return fields that use `Json`, `Provider`, or `Prompt` immediately, before lowering.

Keep provider and command result types as `RecordTypeRef | UnionTypeRef`; only workflow boundaries are record-only.

- [ ] **Step 3: Reject unsupported primitives in contract lowering**

In `contracts.py`:

- remove any weakening of `Json`, `Provider`, or `Prompt` into shared scalar contracts;
- reject those types on generated workflow-boundary contracts and structured-result bundle fields;
- keep record input/output flattening;
- do not introduce union workflow-output flattening in this tranche.

- [ ] **Step 4: Preserve origin metadata for flattened boundary fields**

Keep or extend flattened field metadata so the lowering bridge can map:

- flattened workflow input names;
- flattened workflow output names;
- generated hidden write-root input names.

- [ ] **Step 5: Run the boundary-focused selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_workflows.py -q
python -m pytest tests/test_workflow_lisp_structured_results.py -q
```

Expected: boundary rejection and structured-result contract tests pass before lowering-bridge adjustments begin.

## Task 3: Harden Extern And Command-Boundary Typing

**Files:**

- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`

- [ ] **Step 1: Validate the compile-time extern environment**

Preserve or tighten `ProviderExtern`, `PromptExtern`, and `ExternEnvironment` so they:

- require non-empty authored symbol names and non-empty provider ids / asset paths;
- keep bindings keyed by exact authored symbol name;
- allow `NameExpr("providers.execute")` and `NameExpr("prompts.implementation.execute")` to resolve through the initial value environment without inventing a new expression surface.

- [ ] **Step 2: Validate command boundary classes**

Preserve or tighten `ExternalToolBinding`, `CertifiedAdapterBinding`, and `CommandBoundaryEnvironment`.

Rules to enforce:

- `ExternalToolBinding.stable_command` is a non-empty argv identity prefix;
- `CertifiedAdapterBinding` requires stable command identity, input contract, output type name, visible effects, path-safety metadata, source-map behavior, and fixture identifiers;
- semantic commands without a certified adapter fail with `command_adapter_missing_contract`.

- [ ] **Step 3: Thread both environments through workflow typechecking**

Update `typecheck_workflow_definitions(...)` and `typecheck_expression(...)` so:

- the initial value environment includes provider/prompt extern bindings;
- `provider-result` validates that the provider operand resolves to a provider extern, not a workflow-boundary value;
- `provider-result` validates that the prompt operand resolves to a prompt extern;
- `command-result` resolves the boundary name against `CommandBoundaryEnvironment`;
- argv validation still rejects `python -c`, `python -`, `bash -c`, `sh -c`, heredoc-style shell wrappers, and one-string shell wrappers;
- the rendered argv head matches the binding's stable command identity.

- [ ] **Step 4: Add tests for both accepted command classes and failure modes**

In `tests/test_workflow_lisp_structured_results.py`, write failing tests first for:

- accepted plain external tool bindings;
- accepted certified adapter bindings;
- rejected semantic commands without certified adapter metadata;
- rejected provider/prompt operands when the extern environment is missing or mismatched.

- [ ] **Step 5: Re-run the structured-result selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_structured_results.py -q
```

Expected: all extern and command-boundary typing tests pass before lowering-bridge verification.

## Task 4: Stabilize The Lowering Bridge For Authored Mapping Generation

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/fixtures/workflow_lisp/invalid/shared_validation_remap.orc`

- [ ] **Step 1: Re-baseline lowering tests around approved Stage 3 outputs**

In `tests/test_workflow_lisp_lowering.py`, keep or add failing tests that assert:

- lowered workflows are authored mappings, not YAML text and not direct `SurfaceWorkflow` instances;
- provider-result lowering emits `provider`, `asset_file`, `inject_output_contract`, and either `output_bundle` or `variant_output`;
- command-result lowering emits `command` plus the correct structured result contract;
- same-file calls lower through compiler-generated aliases and do not author `imports`;
- lowered workflow inputs include generated hidden relpath write-root inputs;
- record workflow outputs lower from legal `root.steps...artifacts...` or match-statement output surfaces;
- shared-validation failures remap to authored spans.

- [ ] **Step 2: Preserve deterministic lowering names and path conventions**

Keep the lowering bridge deterministic for:

- step ids;
- match step ids;
- local call step ids and aliases;
- generated hidden write-root input names;
- call-scoped write-root relpaths.

Preserve these patterns:

```text
__write_root__<workflow_name>__<authored_step_id>__result_bundle
```

and

```text
.orchestrate/workflow_lisp/calls/<caller_workflow>/<call_step_id>/<callee_workflow>/<managed_input_name>.json
```

If current naming differs slightly, normalize to one documented scheme and update tests accordingly.

- [ ] **Step 3: Lower only the approved Stage 3 expression forms**

Support and verify lowering for:

- direct `command-result` returning a record workflow result;
- direct same-file `call` returning a record workflow result;
- `let*` lowering for sequential bindings used by the fixtures;
- `match` lowering over a union result so a workflow may use `provider-result` internally and still export a record boundary.

Lowering rules:

- build one authored mapping per `TypedWorkflowDef`;
- set `version: "2.14"` and the authored workflow name;
- flatten record inputs and outputs through `contracts.py`;
- add generated hidden write-root inputs for every structured-result-producing step;
- for provider steps, lower provider id from `ProviderExtern.provider_id` and prompt asset path from `PromptExtern.asset_file`;
- for command steps, lower `stable_command` plus rendered argv tail into the shared `command:` list;
- for same-file calls, lower `call:` plus `with:` bindings for authored args and generated write-root inputs.

- [ ] **Step 4: Keep workflow returns on legal shared export surfaces**

Implement or tighten one helper that turns the terminal typed body into workflow outputs:

- direct record-producing step return:
  - workflow outputs come from `root.steps.<StepName>.artifacts.<field>`
- `match` return:
  - lower to shared `match:` with explicit `outputs:` per case
  - workflow outputs come from `root.steps.<MatchStep>.artifacts.return__<field>`
- record projection return:
  - allow only fields that resolve to legal existing artifact refs or statement outputs

If a return field comes only from a literal, workflow input, or other non-exportable lexical value, raise `workflow_return_not_exportable`.

- [ ] **Step 5: Keep the remap fixture focused on shared validation**

`tests/fixtures/workflow_lisp/invalid/shared_validation_remap.orc` must:

- pass Stage 1 and Stage 2 typing;
- lower successfully;
- fail only during shared validation;
- mention a generated field or path so origin remapping is exercised.

An unsafe relpath `under` value such as `"../escape"` is acceptable if it still isolates the failure to shared validation.

- [ ] **Step 6: Run the lowering suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -q
```

Expected: lowering-shape, same-file call, and remap tests pass.

## Task 5: Reuse The Shared Validation Seam And Harden The Compiler API

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Validate lowered workflows through real imported bundles**

`validate_lowered_workflows(...)` must:

- build a local same-file call graph;
- reject cycles before shared elaboration produces opaque loader failures;
- instantiate `WorkflowLoader(workspace_root)`;
- supply already-validated callees through `imported_bundles`;
- call `elaborate_surface_workflow(...)`;
- immediately call `lower_surface_workflow(...)`;
- return the resulting `LoadedWorkflowBundle` objects keyed by workflow name.

Prefer a small frontend-local helper that primes loader state instead of broad loader refactors.

- [ ] **Step 2: Remap shared-validation failures through `LoweringOriginMap`**

When shared validation fails, remap in this order:

1. generated step id
2. generated hidden input name
3. generated workflow output name
4. generated bundle path
5. workflow-level fallback

If no authored origin can be proven, raise `source_map_missing` instead of leaking raw generated identifiers.

- [ ] **Step 3: Preserve the additive Stage 3 compiler pipeline**

`compile_stage3_module(...)` must keep this order:

1. `read_sexpr_file(path)`
2. `build_syntax_module(parse_tree)`
3. `elaborate_definition_module(...)`
4. Stage 1 definition validation
5. `FrontendTypeEnvironment.from_module(module)`
6. `elaborate_workflow_definitions(module_syntax)`
7. `build_workflow_catalog(...)`
8. `build_extern_environment(...)`
9. `build_command_boundary_environment(...)`
10. `typecheck_workflow_definitions(...)`
11. `lower_workflow_definitions(...)`
12. optional `validate_lowered_workflows(...)`

Do not regress `compile_stage1_module(...)`.

- [ ] **Step 4: Export and test the intended Stage 3 public surface**

At minimum preserve or expose:

- `compile_stage3_module`
- `Stage3CompileResult`
- `ProviderExtern`
- `PromptExtern`
- `ExternEnvironment`
- `ExternalToolBinding`
- `CertifiedAdapterBinding`
- `CommandBoundaryEnvironment`
- `LoweredWorkflow`
- `LoweringOriginMap`
- `lower_workflow_definitions`
- `validate_lowered_workflows`

In `tests/test_workflow_lisp_lowering.py`, add or keep coverage that:

- `compile_stage3_module(..., validate_shared=False)` returns typed workflows plus authored mappings without bundles;
- `compile_stage3_module(..., validate_shared=True)` returns validated bundles;
- missing extern or command-boundary bindings fail before lowering leaks bad mappings;
- shared-validation failures surface remapped `LispFrontendCompileError` diagnostics.

- [ ] **Step 5: Run the targeted Stage 3 suite together**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py -q
```

Expected: the full Stage 3 targeted suite passes.

## Task 6: Full Verification And Completion Notes

**Files:**

- No further code changes unless a verification failure requires one

- [ ] **Step 1: Run the exact deterministic checks for this work item**

Run in order:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_workflow_lisp_workflows.py -q
python -m pytest tests/test_workflow_lisp_structured_results.py -q
python -m pytest tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
python -m pytest tests/test_workflow_lisp_reader.py tests/test_workflow_lisp_definitions.py tests/test_workflow_lisp_diagnostics.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q
```

- [ ] **Step 2: Record implementation evidence in the completion handoff**

Completion notes must explicitly state:

- which files changed;
- that workflow boundaries are record-only and reject `Json` / `Provider` / `Prompt`;
- that provider/prompt externs and command boundary bindings are compile-time inputs;
- that same-file `call` validation reuses in-memory imported bundles plus generated hidden write-root inputs;
- the exact pytest commands run and whether they passed;
- any intentionally deferred edge cases that remain out of scope.

## Acceptance Checklist

The work item is complete only when all of these are true:

- `defworkflow` forms elaborate into a dedicated workflow-definition layer with same-file signature registration.
- workflow boundaries reject unsupported types, especially union returns and any `Provider`, `Prompt`, or `Json` transport.
- `call`, `provider-result`, and `command-result` typecheck against Stage 1 and Stage 2 authority plus the extern / command-boundary environments.
- record and union result types generate deterministic `output_bundle` or `variant_output` contracts whose bundle paths flow through generated hidden relpath inputs.
- lowered provider steps derive `provider` and `asset_file` from validated compiler-known extern bindings.
- lowered `command-result` steps come only from validated plain external-tool or certified-adapter bindings.
- same-file `call` lowers through compiler-generated aliases backed by real in-memory `LoadedWorkflowBundle` imports, without authored `imports`.
- workflow returns lower only through existing legal shared output surfaces.
- shared-validation failures on generated steps, hidden inputs, flattened fields, or bundle paths remap to authored `.orc` spans.
- inline shell/Python command glue remains a compile-time error.
- every verification command listed above passes.

## Risks And Guardrails

- Risk: implementation broadens into a new validator.
  Guardrail: always route final validation through `elaborate_surface_workflow(...)` and `lower_surface_workflow(...)`.

- Risk: stale fixtures keep invalid Stage 3 semantics alive.
  Guardrail: re-baseline `structured_results.orc` and the workflow/structured-result tests first.

- Risk: `Json` rejection gets enforced in one layer and silently weakened in another.
  Guardrail: use one recursive boundary helper and reuse it from both workflow-boundary validation and contract derivation.

- Risk: same-file call lowering hard-codes bundle paths inside callees.
  Guardrail: every structured-result-producing callee exposes generated relpath inputs, and callers bind them explicitly.

- Risk: shared-validation remapping becomes brittle string matching.
  Guardrail: centralize origin-map lookups and test remapping on generated step ids, flattened field names, hidden input names, and generated paths.
