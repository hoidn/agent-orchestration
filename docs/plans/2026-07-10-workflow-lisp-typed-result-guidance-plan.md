# Workflow Lisp Typed Result Guidance Implementation Plan

> **Status:** Complete. Both typed-return waves have passed their implementation
> gates, and DSL v2.15 is public. The resolved-effect substrate is next.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional, typed, source-mapped guidance to every Workflow Lisp return occurrence and to record/union payload fields, and render that guidance in v2.15 provider output contracts without changing runtime value semantics.

**Architecture:** Introduce a compile-time `ReturnSpec` plus immutable field guidance metadata, validate examples as pure constants against existing structured-result schemas, and preserve metadata through schemas, imports, specialization, flattening, and union sharing. Lower effect-boundary metadata into the accepted v2.15 `guidance`, direct field guidance, `guidance_context`, and `guidance_by_variant` wire shapes. Lower callable/workflow overall-return metadata once into top-level `result_guidance`, a sibling of `outputs` that works for scalar, record, and union returns without changing output shape. The loader validates metadata, the prompt renderer consumes effect-boundary guidance, shared IR carries overall-return guidance, and output value validation ignores both.

**Tech Stack:** Workflow Lisp syntax/elaboration/typechecking, schema/module/generic specialization, structured-result contract lowering, DSL loader v2.15, prompt rendering, source maps, Semantic/Executable IR, pytest.

---

## Authority And Scope

- Accepted design: `docs/design/workflow_lisp_native_transportable_returns.md`
- Prerequisite plan: `docs/plans/2026-07-10-workflow-lisp-native-transportable-returns-plan.md`
- Superseded provisional plan:
  `docs/plans/2026-07-09-workflow-lisp-structured-result-field-guidance-plan.md`

This plan owns `(result T ...)`, field annotations, typed examples, metadata
composition, public v2.15 guidance wire schemas, prompts, and runtime-neutrality
evidence. It does not change transportability, root artifact identity, workflow
call carriage, runtime value parsers, or record/union proof semantics.

### Task-5 review amendment (2026-07-13)

The first Task-5 implementation review exposed two design/plan gaps rather
than an acceptable record/union exception:

1. overall `defworkflow`/effectful-`defproc` guidance had no public workflow
   container, so attaching it to `outputs.__result__` worked only for direct
   roots and dropped record/union guidance; and
2. structural production callers invoked contract derivation without a type
   environment, while the new implementation implicitly expanded annotated
   definition fields and could raise `TypeError` on examples.

The accepted remediation is top-level v2.15 `result_guidance`, a closed
non-empty `{description?, format_hint?, example?}` payload beside `outputs`.
It never becomes a pseudo-output and does not change runtime output maps.
Task 5 emits it and splits prompt-guided from guidance-free contract
derivation; Task 6 validates its public DSL schema; Task 8 carries it through
Surface/Core/Semantic/Executable IR; Task 9 documents and promotes the complete
contract. Task 7 renders only effect-boundary guidance and must not treat
`result_guidance` as a provider instruction.

## Wave-1 Handoff Intake (2026-07-11)

Recorded at native-returns wave-1 closure (commits `bccbd7b0..7c6fa439`; whole-wave
review verdict READY). Items this plan's executors must see; sources are the wave's
per-task reviews and the whole-wave review's triage.

**Promotion blockers — resolve or explicitly waive before `2.15` enters
`SUPPORTED_VERSIONS`:**
1. Root-valued `command-result` binding immediately preceding a lexical checkpoint
   yields an empty compile-time restore-descriptor set; resume across a later failed
   boundary FAIL_CLOSEDs for that shape (fail-closed, zero production exposure today;
   recorded in the wave-1 plan's Task 10 Step-3 audit). Root+command-result specific.
2. `loader.py:~5022` `_supported_output_types` widening is preview-version-scoped, not
   boundary-scoped: at promotion, public authored v2.15 YAML would silently gain
   collection-typed `output_bundle`/`variant_output`/`expected_outputs` fields unless
   the widening is re-scoped or that outcome is deliberately accepted. This plan's
   Task 9 Step 6 gate covers it; do not weaken that gate.

**Wave-2-owned cleanups (fold into the natural task):**
3. Design-doc cross-reference comments on the v2.15 gate surfaces
   (`loader.py:120/193/846-856/5022`, `syntax.py:516`).
4. Loader guard: reject empty `json_pointer` with sibling fields
   (`loader.py:~3349-3356`) when this plan rewrites that validator region.
5. Version-comparator cross-reference (`workflows.py` tuple-compare vs loader
   `_version_at_least` index-compare) when promotion touches version logic.
6. `"return"`/`"__result__"` literal pair across ≥6 modules → single
   `TERMINAL_MEMBER_NAMES` seam (guidance adds more consumers of this seam); include
   the capture-side dead `"return" in artifacts` branch in `capture_restore_payload`.
7. `target_dsl_version: str = "2.14"` silent default on eight lowering entry points
   (`compiler.py`, `wcc/defunctionalize.py` ×5, `wcc/lower.py`) → keyword-required
   when guidance threading touches these signatures.
8. Drafting-guide version-boundary precision: only PUBLIC workflow root returns need
   `(:target-dsl "2.15")`; internal roots compile at 2.14. Add the item-1 resume
   caveat to user-facing docs.
9. Private-workflow proc lane root policy is implicit (record/union-only, fail-closed
   at `lowering/procedures.py:154-160`): make roots-there an explicit decision.

**Not this plan's scope (recorded here for visibility):** the pre-existing WCC
fail-closed resume policy past failed command/provider boundaries (record and root
alike) is a production `orchestrator resume` limitation needing its own backlog item.

## Working-Tree And Entry-Gate Rules

- Work from the repository root; do not create a worktree.
- Preserve unrelated changes and stage only the active task's files.
- Re-run Task 1 if native-return review changes any syntax, contract, source-map,
  loader, or prompt ownership named below.
- Do not promote v2.15 between the native-return and guidance completion gates.

### Task 1: Rebaseline against the accepted native-return substrate

**Files:**
- Modify: `docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md`
  only if ownership changed
- Inspect: `orchestrator/workflow_lisp/definitions.py`
- Inspect: `orchestrator/workflow_lisp/expressions.py`
- Inspect: `orchestrator/workflow_lisp/workflows.py`
- Inspect: `orchestrator/workflow_lisp/contracts.py`
- Inspect: `orchestrator/workflow_lisp/type_env.py`
- Inspect: `orchestrator/workflow_lisp/compiler.py`
- Inspect: `orchestrator/workflow_lisp/source_map.py`
- Inspect: `orchestrator/loader.py`
- Inspect: `orchestrator/contracts/prompt_contract.py`

- [ ] **Step 1: Verify the prerequisite evidence**

Run the native-return completion selectors and confirm the current commit is the
reviewed completion commit. Record the commit and exact owner paths here.

- [ ] **Step 2: Audit existing metadata and syntax seams**

```bash
rg -n "class RecordField|_elaborate_field_member|returns_type_name|return_type_name|derive_structured_result_contract|_flatten_structured_result_field|_shared_variant_structured_result_fields" orchestrator/workflow_lisp tests
rg -n "description|format_hint|example|guidance" orchestrator/loader.py orchestrator/contracts tests/test_prompt_contract_injection.py tests/test_loader_validation.py
```

Expected: the existing prompt renderer has legacy guidance support, but
Workflow Lisp definitions and v2.15 guidance containers are not implemented.

- [ ] **Step 3: Capture the prerequisite test baseline**

```bash
pytest -q tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_source_map.py tests/test_loader_validation.py tests/test_prompt_contract_injection.py
```

Expected: PASS.

- [ ] **Step 4: Commit a rebaseline note only if paths changed**

```bash
git add docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md
git commit -m "Rebaseline typed result guidance owners"
```

### Task 2: Parse immutable return and field guidance

**Files:**
- Create: `orchestrator/workflow_lisp/result_guidance.py`
- Modify: `orchestrator/workflow_lisp/definitions.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Test: `tests/test_workflow_lisp_functions.py`
- Test: `tests/test_workflow_lisp_procedures.py`
- Test: `tests/test_workflow_lisp_workflows.py`
- Test: `tests/test_workflow_lisp_structured_results.py`
- Test: `tests/test_workflow_lisp_expressions.py`

- [ ] **Step 1: Write RED syntax/elaboration tests**

Cover plain `Bool`, redundant `(result Bool)`, and:

```lisp
(result Bool
  :description "True only when no blockers remain."
  :format-hint "JSON boolean."
  :example true)
```

at `defun`, `defproc`, `defworkflow`, `provider-result`, and `command-result`
return positions. Cover field forms `(approved Bool :description ... :example
true)`. Reject unknown keys, duplicate keys, empty description/format strings,
annotations in parameter/type positions, and enum-member/union-variant guidance.

- [ ] **Step 2: Run RED tests and collect new modules**

```bash
pytest --collect-only -q tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py
pytest -q tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py -k 'guidance or return_spec or annotated_field'
```

Expected: FAIL because return types require symbols and fields require two items.

- [ ] **Step 3: Add the immutable metadata model**

In `result_guidance.py`, add focused dataclasses:

```python
@dataclass(frozen=True)
class ResultGuidance:
    description: str | None = None
    format_hint: str | None = None
    example_expr: SyntaxNode | None = None

@dataclass(frozen=True)
class ReturnSpec:
    type_name: str
    guidance: ResultGuidance | None
    span: SourceSpan
```

Import `SyntaxNode` from `orchestrator.workflow_lisp.syntax`. Extend
`RecordField` and union payload fields with optional `ResultGuidance`; keep the
plain two-item field and plain symbol return forms byte-equivalent where their
dataclass serialization is observable. Replace separate return-type-name copies
in `functions.py`, `procedures.py`, `workflows.py`, and WCC elaboration with
`ReturnSpec` carriage; do not leave guidance on the classic route only.

- [ ] **Step 4: Run syntax/elaboration tests**

```bash
pytest -q tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_expressions.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/result_guidance.py orchestrator/workflow_lisp/definitions.py orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/functions.py orchestrator/workflow_lisp/procedures.py orchestrator/workflow_lisp/workflows.py orchestrator/workflow_lisp/wcc/elaborate.py orchestrator/workflow_lisp/__init__.py tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_expressions.py
git commit -m "Parse typed result guidance"
```

### Task 3: Validate guidance and typed constant examples

**Files:**
- Modify: `orchestrator/workflow_lisp/result_guidance.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/lowering/pure_projection.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/typecheck_pure_ops.py`
- Use: `orchestrator/workflow/pure_expr.py` without adding a second evaluator
- Test: `tests/test_workflow_lisp_structured_results.py`
- Test: `tests/test_workflow_lisp_expressions.py`
- Test: `tests/test_workflow_lisp_procedures.py`
- Create: `tests/fixtures/workflow_lisp/invalid/result_guidance_example_type_mismatch.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/result_guidance_example_effectful.orc`

- [ ] **Step 1: Write RED validation tests**

Require examples to be effect-free compile-time constants and validate them
through the same structured-result schema as runtime values. Cover scalar,
enum, optional, list, map, record, union, and path examples. A path example must
pass type/path-safety checks but must not enforce `must_exist_target` at compile
time.

- [ ] **Step 2: Run RED tests**

```bash
pytest -q tests/test_workflow_lisp_structured_results.py -k 'guidance_example'
```

Expected: FAIL because examples are stored but not checked.

- [ ] **Step 3: Implement one validation path**

Elaborate examples through `expressions.py`, reject bindings/effects using the
ordinary typecheck and pure-op rules, then lower/evaluate closed expressions
through `lowering/pure_projection.py` and `workflow/pure_expr.py`. Reuse the
structured-result schema derivation. Convert the constant to JSON-native data,
validate it without
filesystem existence enforcement, and emit stable guidance-specific diagnostics
at the example span. Do not add example-specific type allowlists.

- [ ] **Step 4: Prove runtime/type identity neutrality**

Add assertions that annotated and unannotated types compare identically,
specialize to the same identity, produce the same semantic fingerprint, and
accept/reject the same runtime values.

- [ ] **Step 5: Run type/constant suites and commit**

```bash
pytest -q tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_procedures.py
git add orchestrator/workflow_lisp/result_guidance.py orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/lowering/pure_projection.py orchestrator/workflow_lisp/typecheck.py orchestrator/workflow_lisp/typecheck_pure_ops.py tests/fixtures/workflow_lisp/invalid/result_guidance_example_type_mismatch.orc tests/fixtures/workflow_lisp/invalid/result_guidance_example_effectful.orc tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_expressions.py tests/test_workflow_lisp_procedures.py
git commit -m "Validate typed result examples"
```

### Task 4: Preserve guidance through schemas, modules, and specialization

**Files:**
- Modify: `orchestrator/workflow_lisp/definitions.py`
- Modify: `orchestrator/workflow_lisp/type_env.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Modify: `orchestrator/workflow_lisp/procedures.py`
- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Test: `tests/test_workflow_lisp_functions.py`
- Test: `tests/test_workflow_lisp_procedures.py`
- Test: `tests/test_workflow_lisp_modules.py`
- Test: `tests/test_workflow_lisp_structured_results.py`
- Test: `tests/test_workflow_lisp_generic_stdlib_composition.py`

- [ ] **Step 1: Add RED composition tests**

Prove `defschema` inclusion retains guidance, included/local duplicate fields
remain errors, imports/re-exports preserve metadata, and generic specialization
does not include guidance in type/specialization identity.

- [ ] **Step 2: Run RED tests**

```bash
pytest -q tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_generic_stdlib_composition.py -k 'guidance or schema_include or specialization'
```

Expected: FAIL where reconstruction drops metadata.

- [ ] **Step 3: Thread metadata through the canonical definition pipeline**

Preserve immutable guidance whenever fields/return specs are copied,
canonicalized, imported, re-exported, or specialized. Do not create an override
mechanism or alter duplicate-field behavior.

- [ ] **Step 4: Run module/parametric suites**

```bash
pytest -q tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_generic_stdlib_composition.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

Stage the exact Task 4 paths and commit:

```bash
git add orchestrator/workflow_lisp/definitions.py orchestrator/workflow_lisp/type_env.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/functions.py orchestrator/workflow_lisp/procedures.py orchestrator/workflow_lisp/procedure_specialization.py orchestrator/workflow_lisp/wcc/elaborate.py tests/test_workflow_lisp_functions.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_generic_stdlib_composition.py
git commit -m "Preserve result guidance through composition"
```

### Task 5: Derive canonical fixed, nested, and union guidance contracts

**Files:**
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/result_guidance.py`
- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify: `orchestrator/workflow_lisp/lowering/values.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Test: `tests/test_workflow_lisp_structured_results.py`
- Test: `tests/test_workflow_lisp_lowering.py`
- Test: `tests/test_prompt_contract_injection.py`
- Test: `tests/test_workflow_output_contract_integration.py`

- [ ] **Step 1: Add RED wire-shape tests**

Assert exact design shapes for:

- root `__result__` direct guidance;
- bundle-level record/union `guidance`;
- leaf guidance plus ordered ancestor `guidance_context` using RFC 6901 paths;
- variant-specific guidance; and
- structurally shared fields with differing `guidance_by_variant`; and
- top-level `result_guidance` for direct, record, union, and generated private
  procedure workflows, with their output maps unchanged.

Test prefix validation, shallow-to-deep ordering, mutually exclusive direct and
variant guidance, discriminant-key ordering, and deep-JSON canonical deduplication.
Compile provider-result and command-result root guidance through both classic
and WCC routes and assert the resulting executable contract—not a hand-built
test contract—is the contract consumed by the prompt renderer.

- [ ] **Step 2: Run RED tests**

```bash
pytest -q tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py tests/test_prompt_contract_injection.py tests/test_workflow_output_contract_integration.py -k 'guidance_context or guidance_by_variant or bundle_guidance or compiled_root_guidance'
```

Expected: FAIL because contract flattening drops guidance.

- [ ] **Step 3: Implement canonical effect-boundary projection once**

Build one normalized JSON-native guidance payload function. Carry ancestor
contexts separately during flattening. Compute runtime sharedness from field
schema/pointer only, then attach direct or variant-keyed guidance using the
accepted deduplication rules. Never concatenate descriptions. Add guidance to
`LowerableProviderResult` and `LowerableCommandResult`, populate it in classic
lowering and every WCC construction/reconstruction site, and pass it to
the prompt-guided contract derivation API for occurrence-specific results. Do
not attach workflow/procedure overall-return guidance to generated output
definitions.

- [ ] **Step 4: Emit one overall-return container and make derivation intent explicit**

Normalize the `defworkflow` or generated private-procedure `ReturnSpec`
guidance once and emit it as top-level `result_guidance` beside `outputs`.
Use exactly the closed non-empty keys `description`, `format_hint`, and
JSON-native `example`; never emit `guidance_context`. Emit the same shape for a
direct `__result__`, flattened `return__*` record, or flattened union. Do not
alter output definitions, refs, generated names, public/private classification,
or runtime values.

Split contract derivation into explicit APIs:

- `derive_structured_result_contract(...)` is guidance-free, never inspects
  root or definition-field guidance, and never requires `type_env`;
- `derive_prompt_guided_structured_result_contract(...)` requires `type_env`
  and owns root, leaf, ancestor-context, and variant guidance normalization;
  and
- both use one private structural derivation implementation so schemas and
  lineage cannot drift.

Provider/command lowering must call the prompt-guided API. Reusable-state,
materialization, phase, control-flow, and other runtime-only production callers
must remain on the guidance-free API. Add a regression using an annotated
record/union definition with examples through
`derive_reusable_state_contract_metadata(...)` and at least one other
production guidance-free caller; neither may raise or emit guidance without a
type environment. A guided example call without its required environment must
fail at the named API boundary with a deliberate diagnostic/`TypeError`, not
from an incidental nested field walk.

- [ ] **Step 5: Run structured-result/lowering suites**

```bash
pytest -q tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py tests/test_prompt_contract_injection.py tests/test_workflow_output_contract_integration.py
```

Expected: PASS with existing unannotated contract assertions unchanged.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/workflow_lisp/contracts.py orchestrator/workflow_lisp/result_guidance.py orchestrator/workflow_lisp/lowering/effects.py orchestrator/workflow_lisp/lowering/values.py orchestrator/workflow_lisp/lowering/core.py orchestrator/workflow_lisp/wcc/defunctionalize.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py tests/test_prompt_contract_injection.py tests/test_workflow_output_contract_integration.py
git commit -m "Lower canonical typed result guidance"
```

### Task 6: Validate the public v2.15 guidance schema

**Files:**
- Modify: `orchestrator/loader.py`
- Test: `tests/test_loader_validation.py`

- [ ] **Step 1: Add RED loader tests for every container**

Cover direct field keys, bundle `guidance`, `guidance_context`,
`guidance_by_variant`, and top-level `result_guidance`. Reject them before
v2.15; reject unknown/nested keys,
empty strings/payloads, non-JSON examples, invalid/non-prefix/out-of-order
context pointers, unknown variants, direct/variant coexistence, and examples
that violate a field schema.

For `result_guidance`, require at least one declared output and accept only the
closed `description`, `format_hint`, and `example` vocabulary. Treat an
explicit JSON `null` example as a present value. Reject `guidance_context` and
do not try to validate the example against flattened output fields; the shared
loader owns JSON compatibility, while Workflow Lisp already typechecked it
against the unflattened declared return.

- [ ] **Step 2: Run RED loader tests**

```bash
pytest -q tests/test_loader_validation.py -k 'guidance or v215'
```

Expected: FAIL because the loader relies on unknown-key tolerance.

- [ ] **Step 3: Add focused loader validators**

Keep guidance validation separate from `_validate_output_schema_spec` value
semantics, but call it from output-bundle and variant-field validation. Use the
discriminant `allowed` order as the canonical variant order. Bundle examples
and top-level `result_guidance` examples need JSON compatibility only; field
examples use their field schema. Add `result_guidance` to the v2.15 top-level
known-field set without making v2.15 generally supported yet.

- [ ] **Step 4: Run loader suites and commit**

```bash
pytest -q tests/test_loader_validation.py
git add orchestrator/loader.py tests/test_loader_validation.py
git commit -m "Validate v2.15 result guidance contracts"
```

### Task 7: Render canonical provider guidance

**Files:**
- Modify: `orchestrator/contracts/prompt_contract.py`
- Test: `tests/test_prompt_contract_injection.py`

- [ ] **Step 1: Add behavioral RED renderer tests**

Construct fixed, root, nested-context, shared-variant, and bundle-guidance
contracts. Assert every semantic guidance value is represented once in the
rendered contract and examples use canonical JSON. Do not assert literal prompt
phrasing; parse/inspect stable structured sections or semantic tokens.

- [ ] **Step 2: Run RED tests**

```bash
pytest -q tests/test_prompt_contract_injection.py -k 'guidance or root_result'
```

Expected: FAIL on new containers and non-string examples.

- [ ] **Step 3: Implement renderer support**

Render bundle guidance before fields, contexts shallow-to-deep, and variant
payloads in discriminant order. Serialize examples with canonical JSON. Keep
prompt text a view over the validated executable contract.

Do not render top-level `result_guidance` into a provider step prompt. It
describes the workflow/callable return, whereas the producing provider or
command receives its occurrence-specific `output_bundle`/`variant_output`
guidance.

- [ ] **Step 4: Run prompt/output integration suites and commit**

```bash
pytest -q tests/test_prompt_contract_injection.py tests/test_workflow_output_contract_integration.py
git add orchestrator/contracts/prompt_contract.py tests/test_prompt_contract_injection.py tests/test_workflow_output_contract_integration.py
git commit -m "Render typed result guidance for providers"
```

### Task 8: Preserve IR/source ownership and prove runtime neutrality

**Files:**
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow/surface_ast.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/core_ast.py`
- Modify: `orchestrator/workflow/lowering.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow_lisp/source_map.py` only if accepted metadata needs a bridge change
- Test: `tests/test_workflow_surface_ast.py`
- Test: `tests/test_workflow_core_ast.py`
- Test: `tests/test_workflow_ir_lowering.py`
- Test: `tests/test_workflow_semantic_ir.py`
- Test: `tests/test_workflow_lisp_source_map.py`
- Test: `tests/test_workflow_lisp_runtime_source_map.py`
- Test: `tests/test_workflow_lisp_phase_stdlib.py`
- Test: `tests/test_workflow_lisp_checkpoint_identity_comparison.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`
- Test: `tests/test_output_contract.py`
- Test: `tests/test_output_contract_collections.py`

- [ ] **Step 1: Add RED IR/source tests**

Assert Semantic IR retains authored type plus guidance without changing type
identity, Executable IR carries the normalized wire metadata, guidance errors
point to exact annotations, and runtime field violations still resolve through
the native-return/variant field subjects.

Assert top-level `result_guidance` survives exactly through
`SurfaceWorkflow.result_guidance`, `CoreWorkflowAST.result_guidance`,
`SemanticWorkflow.result_guidance`, and
`ExecutableWorkflow.result_guidance` for direct, record, union, and generated
private-procedure returns. Core/Semantic/Executable JSON projections emit the
key only when present; unannotated artifact payloads remain unchanged, so the
additive optional metadata retains the current internal `*.v1` schema ids.
Runtime-plan projections must not acquire a copy.

- [ ] **Step 2: Add runtime-neutrality comparisons**

For identical values, annotated and unannotated contracts must produce equal
validity, artifacts, routing, exit behavior, reusable-state semantic contract
fingerprints, checkpoint identities, and resume results. Guidance keys must
never be read by `_parse_output_bundle_value` or variant value validation.
Adding or removing `result_guidance` must likewise leave outputs, bound
addresses, runtime plans, state projections, and checkpoint identities equal.

- [ ] **Step 3: Run RED tests**

```bash
pytest -q tests/test_workflow_semantic_ir.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_runtime_source_map.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_checkpoint_identity_comparison.py tests/test_workflow_lisp_build_artifacts.py tests/test_output_contract.py tests/test_output_contract_collections.py -k 'guidance or neutrality'
```

Expected: fail only on missing metadata/source behavior; value comparisons
should expose any accidental semantic coupling.

- [ ] **Step 4: Implement the narrow IR/source/fingerprint changes**

Retain normalized guidance in Semantic/Executable IR and prompt contracts, but
strip `guidance`, `description`, `format_hint`, `example`,
`guidance_context`, and `guidance_by_variant` in
`_strip_contract_provenance_for_fingerprint` (rename the helper/set to reflect
non-runtime metadata if clearer). Do not strip type, pointer, path, optionality,
or variant-validity data. Preserve source ownership at exact annotation spans.

Elaboration freezes the validated top-level payload on `SurfaceWorkflow`;
Core-AST construction and executable lowering copy it without reinterpretation;
Semantic derivation records it on the owning `SemanticWorkflow`, beside that
workflow's output-contract ids. Serializers omit the field when absent. Include
`result_guidance` in all non-runtime metadata stripping used by fingerprints or
checkpoint identity.

- [ ] **Step 5: Run the full IR, identity, and runtime-neutrality suites**

```bash
pytest -q tests/test_workflow_semantic_ir.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_runtime_source_map.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_checkpoint_identity_comparison.py tests/test_workflow_lisp_build_artifacts.py tests/test_output_contract.py tests/test_output_contract_collections.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

Stage the exact Task 8 paths that changed and commit:

```bash
git add orchestrator/workflow_lisp/contracts.py orchestrator/workflow/surface_ast.py orchestrator/workflow/elaboration.py orchestrator/workflow/core_ast.py orchestrator/workflow/lowering.py orchestrator/workflow/semantic_ir.py orchestrator/workflow/executable_ir.py orchestrator/workflow_lisp/source_map.py tests/test_workflow_surface_ast.py tests/test_workflow_core_ast.py tests/test_workflow_ir_lowering.py tests/test_workflow_semantic_ir.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_runtime_source_map.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_checkpoint_identity_comparison.py tests/test_workflow_lisp_build_artifacts.py tests/test_output_contract.py tests/test_output_contract_collections.py
git commit -m "Preserve typed guidance provenance and neutrality"
```

### Task 9: End-to-end documentation and v2.15 promotion gate

**Files:**
- Create: `tests/fixtures/workflow_lisp/valid/native_bool_return_guidance.orc`
- Create: `tests/test_workflow_lisp_result_guidance_e2e.py`
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_type_catalog.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `specs/dsl.md`
- Modify: `specs/io.md`
- Modify: `specs/providers.md`
- Modify: `specs/versioning.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify: `docs/design/README.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md`
- Modify: `docs/plans/2026-07-09-workflow-lisp-structured-result-field-guidance-plan.md`

- [ ] **Step 1: Add the declarative annotated-provider scenario**

Compile and execute a real v2.15 `.orc` provider returning direct `true` with
root guidance. Prove the provider receives the semantic contract, runtime state
matches the unannotated case, the source branch consumes `Bool`, and no wrapper,
stdout extraction, or authored hidden artifact appears.

Prove separately that the workflow's overall guidance is present once as
top-level `result_guidance`, survives the loaded bundle and emitted
Core/Semantic/Executable artifacts, and is not injected into the provider's
occurrence-specific output instructions.

- [ ] **Step 2: Add nested/union end-to-end contract checks**

Compile one nested record and one union with differing shared-field guidance.
Validate prompt metadata, selected-variant runtime behavior, and exact source
origins without asserting prompt prose.

- [ ] **Step 3: Run the verification ladder**

```bash
pytest --collect-only -q tests/test_workflow_lisp_structured_results.py tests/test_prompt_contract_injection.py tests/test_loader_validation.py
pytest -q tests/test_workflow_lisp_result_guidance_e2e.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_source_map.py
pytest -q tests/test_loader_validation.py tests/test_prompt_contract_injection.py tests/test_output_contract.py tests/test_output_contract_collections.py tests/test_workflow_output_contract_integration.py
python -m orchestrator --help
```

Expected: all pass. Then run the post-S3 broad Workflow Lisp and orchestrator
smoke gates recorded in Task 1.

- [ ] **Step 4: Align normative/design/authoring docs**

Document exact source syntax, v2.15 wire containers and validation, typed
examples, path-example non-existence behavior, composition rules, prompt-only
semantics, top-level overall-return `result_guidance`, and the now-complete
native-return plus guidance release contract.

- [ ] **Step 5: Promote v2.15 only after the combined gate passes**

Move `2.15` from the compiler-only preview path into
`WorkflowLoader.SUPPORTED_VERSIONS`, remove the compiler preview enablement if
it is no longer needed, and prove ordinary YAML and Workflow Lisp loader paths
accept the complete schema. Before this step, ordinary loader entrypoints must
still reject v2.15. Update `specs/io.md` with the exact `guidance`,
`guidance_context`, `guidance_by_variant`, and top-level `result_guidance`
wire containers.

- [ ] **Step 6: Run the fresh post-promotion gate**

```bash
pytest -q tests/test_loader_validation.py tests/test_workflow_lisp_result_guidance_e2e.py -k 'v215 or guidance or collection_output'
```

Expected: ordinary YAML and Workflow Lisp entrypoints accept the complete
v2.15 schema; v2.14 rejects every guidance container; and v2.15 public optional,
list, and map outputs remain accepted without the preview-only condition.
The gate also proves v2.14 rejects top-level `result_guidance`, v2.15 accepts
it for direct and flattened output maps, and no runtime output/state shape
changes when it is present.

- [ ] **Step 7: Request implementation review**

Use `superpowers:requesting-code-review`; resolve findings with
`superpowers:receiving-code-review`. Do not promote capability status from
planning or isolated renderer tests.

- [ ] **Step 8: Commit and route the pilot next**

```bash
git add tests/fixtures/workflow_lisp/valid/native_bool_return_guidance.orc tests/test_workflow_lisp_result_guidance_e2e.py orchestrator/loader.py orchestrator/workflow_lisp/lowering/core.py tests/test_loader_validation.py docs/design/workflow_lisp_frontend_specification.md docs/design/workflow_lisp_type_catalog.md docs/lisp_workflow_drafting_guide.md specs/dsl.md specs/io.md specs/providers.md specs/versioning.md docs/capability_status_matrix.md docs/index.md docs/design/README.md docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md docs/plans/2026-07-09-workflow-lisp-structured-result-field-guidance-plan.md docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md
git commit -m "Complete Workflow Lisp typed result guidance"
```

Update roadmap routing only after fresh evidence proves both plans complete.

## Typed-Guidance Completion Gate

- Plain returns remain canonical and native transport remains unchanged.
- `(result T ...)` and payload-field guidance compile on every accepted site.
- Examples are typed pure constants; path existence is not checked at compile time.
- Schema/include/import/specialization/flattening/union composition matches the design.
- Public v2.15 guidance schemas validate strictly and render canonically.
- Overall scalar/record/union/private-procedure return guidance uses one
  top-level `result_guidance` container and survives Surface/Core/Semantic/
  Executable IR without changing outputs or runtime plans.
- Guidance-free production contract callers require no type environment and
  cannot accidentally expand field guidance; provider/command callers opt into
  the prompt-guided API with an explicit environment.
- Ordinary loader entrypoints accept v2.15 only after the complete combined
  native-return and typed-guidance gate passes.
- Annotated/unannotated runtime behavior is identical.
- Normative specs, frontend design, drafting guide, indexes, capability matrix, and roadmap agree.
- v2.15 is public; the resolved-effect substrate is next, followed by the
  procedure-first pilot.
