# Workflow Lisp Native Transportable Returns Implementation Plan

> **Status:** Reviewed implementation plan, execution gated. Do not begin implementation
> until procedure-first Roadmap Gates S3 and S4 are complete, the
> semantic-migration freeze has lifted, and Task 1 has re-anchored every owner
> against the current checkout.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow every currently transportable Workflow Lisp type to return directly from providers, commands, procedures, workflow calls, and public workflows using direct JSON roots and a compiler-owned `__result__` artifact.

**Architecture:** Generalize the existing structured-result and workflow-boundary contract derivation instead of adding a second output primitive. Root values lower to one `output_bundle` field named `__result__` with `json_pointer: ""`; public/reusable workflow boundaries expose one generated `outputs.__result__`, and the compiler binds it back to the declared source type. DSL v2.15 owns the widened public output contract, while existing record/union v2.14 routes remain non-regressive.

**Tech Stack:** Workflow Lisp parser/type environment/typechecking, classic and WCC lowering, DSL loader v2.15, output contracts, source maps, runtime plans, executor state/resume, adjudication, dashboard projections, pytest.

---

## Authority And Scope

- Accepted design: `docs/design/workflow_lisp_native_transportable_returns.md`
- Parent frontend contract: `docs/design/workflow_lisp_frontend_specification.md`
- Runtime foundation: `docs/design/workflow_lisp_runtime_migration_foundation.md`
- Source-map contract: `docs/design/workflow_lisp_source_map.md`
- Normative targets: `specs/dsl.md`, `specs/io.md`, `specs/providers.md`, `specs/versioning.md`
- Dependent plan: `docs/plans/2026-07-10-workflow-lisp-typed-result-guidance-plan.md`

This plan does not implement `(result T ...)`, field annotations, guidance wire
keys, or example validation. All acceptance fixtures use plain `-> T` and
`:returns T`. DSL v2.15 is not promoted as complete until the dependent typed
result guidance plan also passes its normative and integration gates.

## Working-Tree And Entry-Gate Rules

- Work from the repository root; do not create a worktree.
- Preserve unrelated user changes and stage only files named by the active task.
- Re-run Task 1 after any Stage 1-3 migration commit that changes frontend,
  lowering, loader, runtime-plan, source-map, adjudication, or executor owners.
- Use fresh output for every task gate. Do not infer success from the design's
  isolated validator feasibility probe.

### Task 1: Rebaseline owners and lock the v2.15 execution boundary

**Files:**
- Modify: `docs/plans/2026-07-10-workflow-lisp-native-transportable-returns-plan.md`
- Inspect: `orchestrator/workflow_lisp/contracts.py`
- Inspect: `orchestrator/workflow_lisp/typecheck_effects.py`
- Inspect: `orchestrator/workflow_lisp/workflows.py`
- Inspect: `orchestrator/workflow_lisp/lowering/`
- Inspect: `orchestrator/workflow_lisp/source_map.py`
- Inspect: `orchestrator/loader.py`
- Inspect: `orchestrator/contracts/output_contract.py`
- Inspect: `orchestrator/contracts/prompt_contract.py`
- Inspect: `orchestrator/workflow/runtime_plan.py`
- Inspect: `orchestrator/workflow/adjudication/`
- Inspect: `orchestrator/dashboard/server.py`

- [ ] **Step 1: Record the post-S3 baseline**

Run:

```bash
git log -1 --date=iso-strict --format='%H %ad %s'
git status --short
```

Record the commit and only in-scope ownership changes in this plan. Expected:
Gate S3 is documented complete and unrelated dirty paths remain untouched.

- [ ] **Step 2: Re-anchor every named symbol**

Run:

```bash
rg -n "derive_structured_result_contract|derive_workflow_signature_contracts|_output_contracts_for_type|_output_bundle_fields|_record_output_refs|WorkflowSignature|validate_output_bundle|render_output_bundle_contract_block" orchestrator tests
rg -n '"2\.14"|target_dsl_version="2\.14"|version.*2\.14' orchestrator/workflow_lisp orchestrator/loader.py tests
```

Expected: every implementation task below names a live owner; update stale
paths before code changes. Hard-coded version findings must be classified as
source-version policy, generated executable version, compatibility fixture, or
legacy evidence.

- [ ] **Step 3: Capture the narrow pre-change test baseline**

Run:

```bash
pytest -q tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_workflow_refs.py tests/test_output_contract_collections.py tests/test_prompt_contract_injection.py
```

Expected: PASS, or record exact pre-existing failure identities without
weakening later gates.

- [ ] **Step 4: Commit the evidence-only rebaseline if the plan changed**

```bash
git add docs/plans/2026-07-10-workflow-lisp-native-transportable-returns-plan.md
git commit -m "Rebaseline native return implementation owners"
```

### Task 2: Add the unreleased v2.15 preview and output-schema gates

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow_lisp/syntax.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Test: `tests/test_loader_validation.py`
- Test: `tests/test_workflow_lisp_workflows.py`
- Test: `tests/test_workflow_lisp_lowering.py`

- [ ] **Step 1: Write failing v2.15 preview and header tests**

Add tests proving:

```python
v215_workflow = {
    "version": "2.15",
    "name": "v215-root-result",
    "steps": [{"name": "emit", "command": ["python", "-c", "print('true')"]}],
}
with pytest.raises(WorkflowValidationError, match="Unsupported version '2.15'"):
    self.loader.load(self.write_workflow(v215_workflow))

preview_loader = WorkflowLoader(self.workspace)
preview_loader._enabled_preview_versions = frozenset({"2.15"})
assert preview_loader.load(self.write_workflow(v215_workflow)).surface.version == "2.15"
```

- v2.15 public `outputs` accept `optional`, `list`, and `map` schemas;
- v2.14 authored YAML still rejects those public collection outputs;
- Workflow Lisp accepts `(:target-dsl "2.15")` without rejecting 2.14; and
- compiled executable mappings use the source module's target DSL rather than
  a hard-coded `2.14`.

- [ ] **Step 2: Run the RED selectors**

```bash
pytest -q tests/test_loader_validation.py -k 'v215 or collection_output'
pytest -q tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py -k 'target_dsl or v215'
```

Expected: FAIL because v2.15 and public collection outputs are not accepted.

- [ ] **Step 3: Implement the minimal unreleased preview/schema widening**

Add `2.15` to `VERSION_ORDER` but not `SUPPORTED_VERSIONS`. Introduce the
private, default-empty `_enabled_preview_versions` loader gate and enable only
`2.15` from Workflow Lisp's compiler-owned validation call. Direct public YAML
loading must continue to reject v2.15 until the guidance plan's final promotion
task. Make
`_supported_output_types(version)` include collection schemas for public
workflow outputs only inside that preview at v2.15, while preserving the
existing private-v2.14 lane.
Thread `WorkflowLispSyntaxModule.target_dsl_version` into generated executable mappings;
do not mass-upgrade existing 2.14 sources or stdlib modules.

- [ ] **Step 4: Run focused and collection checks**

```bash
pytest -q tests/test_loader_validation.py -k 'version or output or collection'
pytest -q tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py -k 'target_dsl or boundary'
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/loader.py orchestrator/workflow_lisp/syntax.py orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/wcc tests/test_loader_validation.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py
git commit -m "Add unreleased v2.15 workflow output preview"
```

### Task 3: Generalize result types and root contract derivation

**Files:**
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py`
- Test: `tests/test_workflow_lisp_workflows.py`
- Test: `tests/test_workflow_lisp_structured_results.py`
- Test: `tests/test_output_contract_collections.py`
- Create: `tests/fixtures/workflow_lisp/valid/native_transportable_returns.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/native_return_type_not_transportable.orc`

- [ ] **Step 1: Write failing transportability tests**

Cover `Bool`, `Int`, `Float`, `String`, enum, path, `Optional[Bool]`,
`List[Int]`, and `Map[String, Float]` across workflow, provider, and command
return declarations. Reject `Json`, `Provider`, `Prompt`, `ProcRef`, nested
union, and record/union collection elements under current rules.

Assert the root contract exactly:

```python
assert contract.contract_kind == "output_bundle"
assert contract.payload["fields"] == [{
    "name": "__result__",
    "json_pointer": "",
    "type": "bool",
    "source_map_subject": {
        "subject_kind": "output_bundle_field",
        "subject_name": f"{step_id}::root-result::__result__",
        "workflow_name": workflow_name,
    },
}]
```

- [ ] **Step 2: Run RED tests and collect new fixtures**

```bash
pytest --collect-only -q tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py
pytest -q tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py -k 'native or transportable or scalar_return'
```

Expected: collection succeeds; behavior tests fail on record/union guards.

- [ ] **Step 3: Implement one shared transportability decision**

In `contracts.py`, widen `GeneratedBundleContract.type_ref` to `TypeRef`, add
`is_transportable_result_type(type_ref)`, and extend
`derive_structured_result_contract(...)` with the root field. Reuse
`_structured_result_field_definition(...)`; do not add parallel type allowlists.
Add a `result_shape` property whose only values are `root_value`,
`record_value`, and `union_value`.

In `workflows.py` and `typecheck_effects.py`, replace record/union checks with
the shared predicate while preserving legacy phase-specific restrictions and
stable diagnostic codes.

- [ ] **Step 4: Run contract/type suites**

```bash
pytest -q tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_output_contract_collections.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/contracts.py orchestrator/workflow_lisp/workflows.py orchestrator/workflow_lisp/typecheck_effects.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_output_contract_collections.py tests/fixtures/workflow_lisp/valid/native_transportable_returns.orc tests/fixtures/workflow_lisp/invalid/native_return_type_not_transportable.orc
git commit -m "Generalize Workflow Lisp result contracts"
```

### Task 4: Lower provider and command root results directly

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify: `orchestrator/workflow_lisp/lowering/values.py`
- Modify: `orchestrator/contracts/prompt_contract.py`
- Test: `tests/test_workflow_lisp_structured_results.py`
- Test: `tests/test_workflow_lisp_lowering.py`
- Test: `tests/test_prompt_contract_injection.py`
- Test: `tests/test_workflow_output_contract_integration.py`

- [ ] **Step 1: Add RED provider/command lowering tests**

Assert that a plain `:returns Bool` produces an `output_bundle` root field,
that terminal refs bind `root.steps.<step>.artifacts.__result__`, and that the
prompt contract represents a JSON value rather than claiming an object.
Tests must inspect structured contract data or behavioral output, not literal
prompt phrasing.

- [ ] **Step 2: Run RED tests**

```bash
pytest -q tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py tests/test_prompt_contract_injection.py -k 'root_result or native_bool'
```

Expected: FAIL because non-record result refs and prompt shape are absent.

- [ ] **Step 3: Implement direct effect lowering**

Extend result-ref helpers so root values expose `__result__`. Teach prompt
rendering to detect a single empty-pointer field and render a root JSON schema.
Keep `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, wrong-path failure, and stdout
non-authority unchanged.

- [ ] **Step 4: Run focused integration tests**

```bash
pytest -q tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py tests/test_prompt_contract_injection.py tests/test_workflow_output_contract_integration.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/lowering/effects.py orchestrator/workflow_lisp/lowering/values.py orchestrator/contracts/prompt_contract.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py tests/test_prompt_contract_injection.py tests/test_workflow_output_contract_integration.py
git commit -m "Lower direct provider and command return values"
```

### Task 5: Materialize pure, conditional, loop, and procedure root values

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/pure_projection.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/values.py`
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `orchestrator/workflow_lisp/wcc/route.py`
- Test: `tests/test_workflow_lisp_pure_projection_runtime.py`
- Test: `tests/test_workflow_lisp_lowering.py`
- Test: `tests/test_workflow_lisp_procedures.py`
- Test: `tests/test_workflow_lisp_wcc_m4.py`

- [ ] **Step 1: Add RED materialization tests**

Cover a literal `Bool`, a pure expression, both arms of an `if`, a bounded loop
result, and an effectful procedure whose terminal result is root-valued. Assert
the materialization bundle uses `json_pointer: ""`, not `/result` or a wrapper.

- [ ] **Step 2: Run RED tests**

```bash
pytest -q tests/test_workflow_lisp_pure_projection_runtime.py tests/test_workflow_lisp_lowering.py -k 'root or scalar_return or collection_return'
```

Expected: FAIL on `/result`, missing output refs, or boundary rejection.

- [ ] **Step 3: Implement one root materialization convention**

Make `_output_contracts_for_type`, `_output_bundle_fields`, join-output helpers,
and WCC defunctionalization use `__result__` plus the empty pointer only for
root-valued results. Preserve existing record/union pointers and names.

- [ ] **Step 4: Run classic/WCC and procedure suites**

```bash
pytest -q tests/test_workflow_lisp_pure_projection_runtime.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_wcc_m4.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

Stage the named Task 5 owners and tests, then commit:

```bash
git add orchestrator/workflow_lisp/lowering/pure_projection.py orchestrator/workflow_lisp/lowering/core.py orchestrator/workflow_lisp/lowering/values.py orchestrator/workflow_lisp/wcc/defunctionalize.py orchestrator/workflow_lisp/wcc/route.py tests/test_workflow_lisp_pure_projection_runtime.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_wcc_m4.py
git commit -m "Materialize root-valued Workflow Lisp returns"
```

### Task 6: Carry root values across workflow boundaries and calls

**Files:**
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- Modify: `orchestrator/workflow_lisp/lowering/values.py`
- Modify: `orchestrator/workflow_lisp/entry_publication.py`
- Modify: `orchestrator/workflow_lisp/build_artifacts.py`
- Modify: `orchestrator/workflow/signatures.py`
- Modify: `orchestrator/workflow/executor.py`
- Test: `tests/test_workflow_lisp_workflows.py`
- Test: `tests/test_workflow_lisp_workflow_refs.py`
- Test: `tests/test_subworkflow_calls.py`
- Test: `tests/test_workflow_lisp_modules.py`

- [ ] **Step 1: Add RED boundary/call tests**

Assert a v2.15 scalar/collection workflow derives:

```python
assert outputs["__result__"].definition["from"] == {
    "ref": "root.steps.<terminal>.artifacts.__result__"
}
```

and an ordinary/imported `call` exposes the outer call artifact and binds it as
the declared type. Include finalization suppression and negative v2.14 public
root-return cases for scalar, enum, path, optional, list, and map. Require one
stable diagnostic telling the author to declare `(:target-dsl "2.15")`.

- [ ] **Step 2: Run RED tests**

```bash
pytest -q tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_workflow_refs.py tests/test_subworkflow_calls.py tests/test_workflow_lisp_modules.py -k 'root_result or collection_return or native_return'
```

Expected: FAIL because workflow signatures and calls assume flattened records.

- [ ] **Step 3: Implement boundary projection and call reconstruction**

Set `result_shape="root_value"` while preserving `record_value` and
`union_value` for the other shapes. Keep the existing boundary compatibility
key as `return_kind="record"|"union"` and add `return_kind="root"`; update
`entry_publication.py`, build artifact serialization, signatures, and executor
consumers explicitly. Add one flattened/generated output named `__result__`.
Thread it through terminal normalization, call output export,
outer-step artifacts, imported signature recovery, and typed call bindings.
Do not expose `__result__` as a Workflow Lisp field.

- [ ] **Step 4: Run workflow/call suites**

```bash
pytest -q tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_workflow_refs.py tests/test_subworkflow_calls.py tests/test_workflow_lisp_modules.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/contracts.py orchestrator/workflow_lisp/workflows.py orchestrator/workflow_lisp/lowering/core.py orchestrator/workflow_lisp/lowering/workflow_calls.py orchestrator/workflow_lisp/lowering/values.py orchestrator/workflow_lisp/entry_publication.py orchestrator/workflow_lisp/build_artifacts.py orchestrator/workflow/signatures.py orchestrator/workflow/executor.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_workflow_refs.py tests/test_subworkflow_calls.py tests/test_workflow_lisp_modules.py
git commit -m "Carry direct values across workflow calls"
```

### Task 7: Extend root-field source lineage

**Files:**
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/lowering/origins.py`
- Modify: `orchestrator/workflow_lisp/source_map.py`
- Modify: `orchestrator/workflow/frontend_origins.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `orchestrator/contracts/output_contract.py`
- Test: `tests/test_workflow_lisp_source_map.py`
- Test: `tests/test_workflow_lisp_runtime_source_map.py`
- Test: `tests/test_workflow_semantic_ir.py`
- Test: `tests/test_runtime_observability.py`
- Test: `tests/test_output_contract.py`

- [ ] **Step 1: Add RED subject/origin tests**

Require `output_bundle_field` subject identity
`<step-id>::root-result::__result__`, a `contract_fields` origin at the authored
return span, generated-output lineage for the workflow boundary, and resolved
runtime violations that display the authored return rather than only the step.

- [ ] **Step 2: Run RED tests**

```bash
pytest -q tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_runtime_source_map.py tests/test_workflow_semantic_ir.py tests/test_runtime_observability.py tests/test_output_contract.py -k 'output_bundle_field or root_result'
```

Expected: FAIL because the source-map bridge accepts only variant field subjects.

- [ ] **Step 3: Implement additive lineage**

Generalize contract-field origin filtering and validation to
`output_bundle_field`, carry the subject in root field specs, attach it to
ordinary bundle violations, and teach `CompiledFrontendIndex` to resolve it.
Preserve old v1 maps and enclosing-step fallback.

- [ ] **Step 4: Run source-map and integration suites**

```bash
pytest -q tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_runtime_source_map.py tests/test_workflow_semantic_ir.py tests/test_runtime_observability.py tests/test_output_contract.py tests/test_workflow_output_contract_integration.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

Stage the named Task 7 paths and commit:

```bash
git add orchestrator/workflow_lisp/contracts.py orchestrator/workflow_lisp/lowering/origins.py orchestrator/workflow_lisp/source_map.py orchestrator/workflow/frontend_origins.py orchestrator/workflow/semantic_ir.py orchestrator/contracts/output_contract.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_runtime_source_map.py tests/test_workflow_semantic_ir.py tests/test_runtime_observability.py tests/test_output_contract.py
git commit -m "Attribute root result contract violations"
```

### Task 8: Prove state, resume, runtime-plan, and dashboard handling

**Files:**
- Modify: `orchestrator/workflow_lisp/lexical_checkpoints.py`
- Modify: `orchestrator/workflow/runtime_plan.py`
- Modify: `orchestrator/dashboard/server.py`
- Modify: `orchestrator/dashboard/projection.py` only if its RED test proves an
  empty-pointer assumption
- Test: `tests/test_resume_command.py`
- Test: `tests/test_workflow_lisp_pure_projection_runtime.py`
- Test: `tests/test_workflow_ir_lowering.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`
- Test: `tests/test_workflow_state_projection.py`
- Test: `tests/test_dashboard_server.py`
- Test: `tests/test_dashboard_projection.py`

- [ ] **Step 1: Add RED state/consumer tests**

Persist and resume `artifacts.__result__` for scalar, optional-null, and list
roots. Assert runtime-plan artifact entries and dashboard empty-pointer preview
show the value without treating it as an object field.

- [ ] **Step 2: Run RED tests**

```bash
pytest -q tests/test_resume_command.py tests/test_workflow_lisp_pure_projection_runtime.py tests/test_workflow_ir_lowering.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_state_projection.py tests/test_dashboard_server.py tests/test_dashboard_projection.py -k 'root_result or empty_pointer'
```

Expected: FAIL only where consumers assume non-empty pointers/record fields.

- [ ] **Step 3: Patch the narrow consumers**

Reuse ordinary artifact persistence and digests. Update only consumers whose
RED tests fail; do not introduce a second state store or root-value ledger.

- [ ] **Step 4: Run state/resume/dashboard suites**

```bash
pytest -q tests/test_resume_command.py tests/test_workflow_lisp_lexical_checkpoint_default_resume.py tests/test_workflow_ir_lowering.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_state_projection.py tests/test_dashboard_server.py tests/test_dashboard_projection.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

Stage only named consumers whose RED tests required changes and commit:

```bash
git commit -m "Support root results in runtime projections"
```

### Task 9: Prove adjudication, promotion, rollback, and resume

**Files:**
- Modify: `orchestrator/workflow/adjudication/evidence.py` only if RED tests require it
- Modify: `orchestrator/workflow/adjudication/promotion.py` only if RED tests require it
- Modify: `orchestrator/workflow/adjudication_helpers.py` only if RED tests require it
- Test: `tests/test_adjudicated_provider_runtime.py`
- Test: `tests/test_adjudicated_provider_promotion.py`
- Test: `tests/test_adjudicated_provider_resume.py`
- Test: `tests/test_adjudicated_provider_outcomes.py`

- [ ] **Step 1: Add RED adjudication tests**

Use a candidate bundle whose entire document is `true`, select it, promote the
declared bundle, revalidate the parent, resume a committed promotion, and prove
rollback on parent validation failure. Assert candidate/evaluator stdout does
not become the result.

- [ ] **Step 2: Run RED tests**

```bash
pytest -q tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_resume.py tests/test_adjudicated_provider_outcomes.py -k 'root_result or empty_pointer'
```

Expected: PASS if consumers are already generic; otherwise fail at the exact
object/pointer assumption to patch.

- [ ] **Step 3: Implement only evidence-backed fixes**

Preserve the existing staged promotion transaction and `_resolve_json_pointer`
empty-root behavior. Do not special-case `Bool` or `__result__` outside generic
contract iteration.

- [ ] **Step 4: Run all adjudication suites**

```bash
pytest -q tests/test_adjudicated_provider_baseline.py tests/test_adjudicated_provider_loader.py tests/test_adjudicated_provider_outcomes.py tests/test_adjudicated_provider_promotion.py tests/test_adjudicated_provider_resume.py tests/test_adjudicated_provider_runtime.py tests/test_adjudicated_provider_scoring.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

Commit only if production changes were required; otherwise record the passing
evidence in the plan without an empty commit.

### Task 10: End-to-end compatibility and normative closure

**Files:**
- Create: `tests/fixtures/workflow_lisp/valid/native_bool_provider_branch.orc`
- Create: `tests/fixtures/workflow_lisp/valid/native_bool_command_branch.orc`
- Create: `tests/test_workflow_lisp_native_returns_e2e.py`
- Test: `tests/test_artifact_dataflow_integration.py`
- Test: `tests/test_workflow_state_projection.py`
- Test: `tests/test_workflow_lisp_migration_parity.py`
- Test: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `docs/design/workflow_lisp_frontend_specification.md`
- Modify: `docs/design/workflow_lisp_type_catalog.md`
- Modify: `docs/design/workflow_lisp_source_map.md`
- Modify: `specs/dsl.md`
- Modify: `specs/io.md`
- Modify: `specs/providers.md`
- Modify: `specs/versioning.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/plans/2026-07-10-workflow-lisp-native-transportable-returns-plan.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md`
- Modify: `docs/index.md`

- [ ] **Step 1: Add the declarative end-to-end acceptance test**

Compile and execute real preview-v2.15 `.orc` provider and command results that
each write direct JSON `true`, branch on the resulting `Bool`, persist state,
resume, and assert no wrapper, stdout extraction, authored `__result__` access,
or name-specific lowering.

- [ ] **Step 2: Add record/union non-regression comparisons**

Compile representative existing record and union fixtures before/after the
feature and compare normalized executable contracts, source identities, and
checkpoint identities. Differences require explicit review; do not update
goldens reflexively.

- [ ] **Step 3: Audit persisted schema readers and projections**

Inventory every build/executable/runtime-plan schema reader before deciding
whether its schema version changes. Add artifact-lineage, state-projection, and
migration-parity assertions for `__result__`; record the evidence-based
build/executable schema version decision in the plan and normative docs.

- [ ] **Step 4: Run the narrow-to-broad verification ladder**

```bash
pytest --collect-only -q tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py
pytest -q tests/test_workflow_lisp_native_returns_e2e.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_workflow_refs.py tests/test_workflow_lisp_pure_projection_runtime.py tests/test_workflow_lisp_source_map.py
pytest -q tests/test_output_contract.py tests/test_output_contract_collections.py tests/test_prompt_contract_injection.py tests/test_workflow_output_contract_integration.py tests/test_subworkflow_calls.py tests/test_artifact_dataflow_integration.py tests/test_workflow_state_projection.py tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_build_artifacts.py
python -m orchestrator --help
```

Expected: all pass. Then run the repository's post-S3 broad Workflow Lisp and
orchestrator smoke gates recorded by Task 1.

- [ ] **Step 5: Update normative and authoring docs**

Specify v2.15 public collection outputs, direct JSON roots, empty pointers,
hidden artifact ownership, prompt behavior, source lineage, compatibility, the
persisted-schema audit decision, and the fact that ordinary loader entrypoints
still reject v2.15 until typed guidance lands.

- [ ] **Step 6: Request implementation review**

Use `superpowers:requesting-code-review` with the accepted design, exact commit
range, and fresh verification output. Resolve findings with
`superpowers:receiving-code-review`.

- [ ] **Step 7: Commit native-return closure**

Stage the named Task 10 paths and commit:

```bash
git add tests/fixtures/workflow_lisp/valid/native_bool_provider_branch.orc tests/fixtures/workflow_lisp/valid/native_bool_command_branch.orc tests/test_workflow_lisp_native_returns_e2e.py tests/test_artifact_dataflow_integration.py tests/test_workflow_state_projection.py tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_build_artifacts.py docs/design/workflow_lisp_frontend_specification.md docs/design/workflow_lisp_type_catalog.md docs/design/workflow_lisp_source_map.md specs/dsl.md specs/io.md specs/providers.md specs/versioning.md docs/lisp_workflow_drafting_guide.md docs/capability_status_matrix.md docs/plans/2026-07-10-workflow-lisp-native-transportable-returns-plan.md docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md docs/index.md
git commit -m "Complete native transportable return substrate"
```

## Native-Return Completion Gate

- All currently transportable type families return directly at every accepted boundary.
- Provider/command roots are direct JSON and runtime-authoritative.
- Workflow outputs/calls use compiler-owned `__result__` without source leakage.
- Classic/WCC, pure/effectful, state/resume, adjudication, dashboard, and source maps pass.
- Existing record/union contracts are non-regressive.
- v2.15 normative text is present but capability promotion waits for the dependent guidance plan.
- The roadmap selects typed result guidance next, not the procedure-first pilot.
