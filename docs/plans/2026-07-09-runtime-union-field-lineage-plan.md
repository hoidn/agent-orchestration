# Runtime Union Field Lineage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry authored Workflow Lisp union variant-field identity through generated runtime contracts, source maps, Semantic IR, and executor contract violations so a runtime missing/forbidden field points to the exact authored declaration.

**Architecture:** Contract derivation creates opaque `variant_output_field` subjects and lowering-owned origin bindings. Classic and WCC lowering register those bindings in the existing validation-subject catalog; the canonical source map persists `contract_fields`, while runtime contracts retain only subject references. Runtime validation serializes subjects, the compiled frontend index resolves them, and the executor enriches each violation with structured origins while preserving old-v1 and YAML fallback behavior.

**Tech Stack:** Python dataclasses and mappings, Workflow Lisp lowering/build pipeline, JSON source-map sidecars, Semantic IR, pytest.

---

## Governing contracts

- `docs/design/workflow_lisp_source_map.md` is the accepted component design.
- `docs/design/workflow_lisp_frontend_specification.md` section 74 is the
  parent frontend contract.
- `docs/plans/2026-07-08-boundary-report-followups.md` Task 5 case 5 owns the
  coverage gate this plan unblocks.
- `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md` keeps
  the drain migration paused until the boundary plan closes.

## Working-tree and execution rules

- Run from `/home/ollie/Documents/agent-orchestration`.
- Do not create a worktree. Preserve all unrelated modified files.
- Stage and commit only the explicit files changed by the current task.
- Follow TDD: add the named test, observe the intended failure, implement the
  minimum production behavior, and rerun the narrow selector.
- Do not assert literal diagnostic phrasing. Assert codes, subject identity,
  structured context, origin structure, and dataflow.
- If a test module is created or a test is renamed, run `pytest --collect-only`
  on that module before the behavioral selector.
- A production-path integration test must compile a real `.orc` source. A
  hand-authored source-map dictionary is compatibility coverage, not acceptance
  evidence.
- The source-map schema identifier remains `workflow_lisp_source_map.v1`; all
  new sections and fields are additive and optional to readers.
- After each task, inspect `git status --short`, `git diff --check`, and the
  exact staged diff before committing.

### Task 1: Derive stable field subjects without changing semantic fingerprints

> **Status (completed 2026-07-09):** Landed in `aa5d8943`, with reusable-state
> consumer compatibility in `9a129272` and strict subject serialization in
> `53e86816`. Specification and code-quality reviews approved the final range;
> 148 affected-module tests and 28 output-contract tests pass.

**Files:**
- Modify: `orchestrator/exceptions.py`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Create: `tests/test_exceptions.py`
- Test: `tests/test_workflow_lisp_structured_results.py`
- Test: `tests/test_workflow_lisp_phase_stdlib.py`

- [x] **Step 1: Add RED contract-derivation coverage**

Add a test that obtains the `ImplementationAttempt` union type from a compiled
real source or the suite's existing type-environment helper, then calls
`derive_structured_result_contract` with workflow `demo/module::entry` and step
`execute`. Assert:

```python
completed = contract.payload["variants"]["COMPLETED"]["fields"]
blocked = contract.payload["variants"]["BLOCKED"]["fields"]
assert completed[0]["source_map_subject"] == {
    "subject_kind": "variant_output_field",
    "subject_name": "execute::ImplementationAttempt::COMPLETED::execution_report_path",
    "workflow_name": "demo/module::entry",
}
assert blocked[0]["source_map_subject"]["subject_name"].startswith(
    "execute::ImplementationAttempt::BLOCKED::"
)
assert {binding.subject_ref.subject_name for binding in contract.field_origins}
```

Add a second union with the same compatible `report` field in both variants.
Assert its shared field has no singular `source_map_subject` and has exactly
these keys:

```python
assert set(shared["source_map_subjects_by_variant"]) == {"ACCEPTED", "REJECTED"}
assert shared["source_map_subjects_by_variant"]["ACCEPTED"] != (
    shared["source_map_subjects_by_variant"]["REJECTED"]
)
```

Run:

```bash
pytest tests/test_workflow_lisp_structured_results.py -q -k 'field_subject or shared_field_subject'
```

Expected: FAIL because `GeneratedBundleContract` has no `field_origins` and
field specs have no source-map subject metadata.

- [x] **Step 2: Add RED tests for the frontend-neutral subject wire format**

Create `tests/test_exceptions.py` with focused tests that import the planned
shared functions, round-trip a `ValidationSubjectRef` through the exact
three-key mapping, and assert malformed optional metadata parses as `None`
without inventing a workflow.

Both Workflow Lisp contract generation and runtime output validation import
these helpers. Neither layer defines a second serializer or imports the other.

Run:

```bash
pytest --collect-only tests/test_exceptions.py -q
pytest tests/test_exceptions.py -q -k 'validation_subject_ref'
```

Expected: collection or the behavioral selector FAILS at import because the
helpers do not exist yet. This is the required RED result.

- [x] **Step 3: Implement the frontend-neutral subject wire format**

In `orchestrator/exceptions.py`, add the shared serializer and defensive parser
specified by Step 2. The parser returns `None` for malformed optional metadata;
it does not raise or invent a workflow.

Both Workflow Lisp contract generation and runtime output validation import
these helpers. Neither layer defines a second serializer or imports the other.

Run:

```bash
pytest --collect-only tests/test_exceptions.py -q
pytest tests/test_exceptions.py -q -k 'validation_subject_ref'
```

Expected: PASS.

- [x] **Step 4: Implement the contract-owned lineage model**

In `contracts.py`:

- add a frozen `GeneratedContractFieldOrigin` containing
  `subject_ref: ValidationSubjectRef`, `span: SourceSpan`, and
  `form_path: tuple[str, ...]`;
- add `field_origins: tuple[GeneratedContractFieldOrigin, ...] = ()` to
  `GeneratedBundleContract`;
- use the shared serializer from `orchestrator.exceptions`;
- generate opaque subject names as
  `<step-id>::<union-type>::<variant>::<flattened-field-name>`;
- add `source_map_subject` to variant-specific field dictionaries;
- add `source_map_subjects_by_variant` to shared field dictionaries;
- point a flattened nested-record leaf to the enclosing union field's span;
- construct its deterministic form path as
  `("workflow-lisp", "defunion", union-name, variant-name, field-name)`;
  flattened nested leaves from that union field retain the same declaration
  path because the include site is the lineage authority;
- preserve deterministic variant and field order and de-duplicate identical
  bindings by the full `(kind, name, workflow)` identity.

- [x] **Step 5: Prove provenance does not alter reusable-state fingerprints**

In `tests/test_workflow_lisp_phase_stdlib.py`, derive reusable-state metadata
for the same union twice: once through the new contract result and once from a
recursively stripped semantic payload that removes only
`source_map_subject`/`source_map_subjects_by_variant`. Assert the fingerprint
matches the pre-lineage semantic digest and the returned structured contract
still carries runtime subject metadata.

Run:

```bash
pytest tests/test_workflow_lisp_phase_stdlib.py -q -k 'fingerprint and provenance'
```

Expected before the normalization change: FAIL because the new keys affect the
digest.

- [x] **Step 6: Normalize only the fingerprint input**

Add a recursive helper that removes the two provenance-only keys when
constructing the JSON value hashed by
`derive_reusable_state_contract_metadata`. Do not remove them from the returned
structured contract and do not ignore any semantic contract key.

- [x] **Step 7: Run Task 1 checks and commit**

```bash
pytest --collect-only tests/test_exceptions.py -q
pytest tests/test_exceptions.py -q -k 'validation_subject_ref'
pytest tests/test_workflow_lisp_structured_results.py -q -k 'field_subject or shared_field_subject'
pytest tests/test_workflow_lisp_phase_stdlib.py -q -k 'fingerprint and provenance'
git diff --check -- orchestrator/exceptions.py orchestrator/workflow_lisp/contracts.py tests/test_exceptions.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py
git add -- orchestrator/exceptions.py orchestrator/workflow_lisp/contracts.py tests/test_exceptions.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_phase_stdlib.py
git commit -m "Derive runtime union field subjects"
```

Expected: PASS.

### Task 2: Register field origins and persist canonical source-map entries

> **Status (completed 2026-07-09):** Landed in `87a3b487`, with inline
> procedure catalog sharing in `9b605ba7` and fail-closed duplicate/missing
> subject handling in `256ac49c`. Specification and code-quality reviews
> approved the final range; 59 affected-module tests pass.

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/context.py`
- Modify: `orchestrator/workflow_lisp/lowering/origins.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify when the runtime contract is attached: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify when the runtime contract is attached: `orchestrator/workflow_lisp/lowering/values.py`
- Modify when the runtime contract is attached: `orchestrator/workflow_lisp/lowering/control_match.py`
- Modify when the runtime contract is attached: `orchestrator/workflow_lisp/lowering/phase_flow.py`
- Modify when the runtime contract is attached: `orchestrator/workflow_lisp/lowering/phase_resource.py`
- Modify when the runtime contract is attached: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify when the runtime contract is attached: `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/source_map.py`
- Test: `tests/test_workflow_lisp_source_map.py`

- [x] **Step 1: Add the RED production-compile source-map test**

Use a real `.orc` fixture containing two variants with a compatible same-name
field on distinct lines and a provider or command structured result. Compile
through `_build_source_map_document`. Assert:

```python
workflow = document.workflows[workflow_name]
accepted = next(
    entry for key, entry in workflow.contract_fields.items()
    if "::ACCEPTED::report" in key
)
rejected = next(
    entry for key, entry in workflow.contract_fields.items()
    if "::REJECTED::report" in key
)
assert accepted.origin_key != rejected.origin_key
assert accepted.line != rejected.line
assert accepted.entity_kind == rejected.entity_kind == "variant_output_field"
assert all(
    any(binding.origin_key == entry.origin_key for binding in workflow.validation_subjects)
    for entry in (accepted, rejected)
)
```

Also replace one field binding with a dangling origin and assert
`source_map_validation_ref_missing`, without matching message text.

Run:

```bash
pytest tests/test_workflow_lisp_source_map.py -q -k 'contract_field or union_field_lineage'
```

Expected: FAIL because `WorkflowSourceMap` has no `contract_fields`.

- [x] **Step 2: Add shared lowering registration ownership**

Add `generated_contract_field_bindings` to `_LoweringContext`. Initialize an
empty list in both classic and WCC root contexts; inline procedure contexts
must share the parent's list. Add one lowering helper that converts each
`GeneratedContractFieldOrigin` into the existing lowering
`ValidationSubjectBinding`, assigns a `variant_output_field` origin key, and
appends only unseen subject identities.

Immediately call that helper after each `derive_structured_result_contract`
whose payload is attached to an executable step. Audit every call reported by:

```bash
rg -n 'derive_structured_result_contract\(' orchestrator/workflow_lisp -g '*.py'
```

Document static-only exceptions in a short code comment beside the call; do
not register reusable-state analysis or boundary-projection-only derivations.

- [x] **Step 3: Carry custom bindings into the classic origin map**

Extend `_build_validation_subject_bindings` with explicit extra bindings.
Classic `LoweringOriginMap` construction must combine standard subjects with
the context's field bindings and retain their already assigned origin keys.
Do not infer field origins by scanning the generated mapping.

- [x] **Step 4: Persist and validate `contract_fields`**

In `source_map.py`:

- add `contract_fields: Mapping[str, SourceMapEntry]` to
  `WorkflowSourceMap`;
- build it only from `variant_output_field` lowering bindings;
- include it in `_iter_origin_entries`;
- require every `contract_fields` key to have one matching validation subject;
- retain `SOURCE_MAP_SCHEMA_VERSION = "workflow_lisp_source_map.v1"`;
- do not change the canonical coverage key set solely for this additive
  section.

- [x] **Step 5: Run Task 2 checks and commit**

```bash
pytest tests/test_workflow_lisp_source_map.py -q -k 'contract_field or union_field_lineage'
pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_source_map.py -q
git diff --check -- orchestrator/workflow_lisp/contracts.py orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/source_map.py tests/test_workflow_lisp_source_map.py
git add -- orchestrator/workflow_lisp/lowering/context.py orchestrator/workflow_lisp/lowering/origins.py orchestrator/workflow_lisp/lowering/core.py orchestrator/workflow_lisp/lowering/effects.py orchestrator/workflow_lisp/lowering/values.py orchestrator/workflow_lisp/lowering/control_match.py orchestrator/workflow_lisp/lowering/phase_flow.py orchestrator/workflow_lisp/lowering/phase_resource.py orchestrator/workflow_lisp/lowering/phase_scope.py orchestrator/workflow_lisp/lowering/phase_stdlib.py orchestrator/workflow_lisp/source_map.py tests/test_workflow_lisp_source_map.py
git commit -m "Persist authored union field lineage"
```

Expected: PASS. Stage only files actually changed after the call-site audit.

### Task 3: Preserve field lineage through WCC, aliases, and Semantic IR

> **Status (completed 2026-07-09):** Landed in `af518da7` and passed
> specification and code-quality review. Focused route/alias and Semantic IR
> selectors pass; source-map plus drain suites pass 88 tests. The three full
> Semantic IR failures match the recorded pre-existing baseline identities.

**Files:**
- Modify: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Modify: `orchestrator/workflow_lisp/lowering/origins.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_drain.py`
- Modify: `orchestrator/workflow/semantic_ir.py`
- Test: `tests/test_workflow_lisp_source_map.py`
- Test: `tests/test_workflow_lisp_drain_stdlib.py`
- Test: `tests/test_workflow_semantic_ir.py`

- [x] **Step 1: Add RED route-completeness tests**

Compile the same union-result source with `lowering_route="legacy"` and
`lowering_route="wcc_m4"`; assert their `contract_fields` subject identities
and authored spans match. Add a focused inline-procedure case and assert its
child-emitted field binding reaches the parent source map.

Use the existing drain same-file clone/rebind helper to create an alias and
assert every embedded contract subject and every source-map validation subject
has the alias as `workflow_name`, with no subjects dropped.

Run:

```bash
pytest tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_drain_stdlib.py -q -k 'contract_field and (wcc or inline or alias or rekey)'
```

Expected: FAIL on WCC construction and alias rekeying.

- [x] **Step 2: Carry bindings through WCC and inline contexts**

Pass `context.generated_contract_field_bindings` into the WCC-created
`LoweringOriginMap` exactly as classic lowering does. Confirm inline procedure
contexts share, rather than copy, the list so bindings registered during the
call survive return to the parent.

- [x] **Step 3: Rekey origins and embedded contract subjects together**

Extend `_rekey_origin_map` to preserve custom field bindings while replacing
their `workflow_name` and origin-key workflow prefix. In the drain clone helper,
rewrite only subject dictionaries under `source_map_subject` and
`source_map_subjects_by_variant`; leave semantic contract fields unchanged.

- [x] **Step 4: Add RED Semantic IR bridge coverage**

Extend the existing source-map bridge test to build a real source map with
`contract_fields` and assert a `SemanticSourceMapBridgeEntry` exists for every
`variant_output_field` subject. Add two negative/compatibility assertions:

- a field subject referencing a missing `contract_fields` origin fails with
  `semantic_ir_invalid` and carries that subject ref;
- an old v1 payload with no `contract_fields` and no field subjects still
  derives Semantic IR.

Run:

```bash
pytest tests/test_workflow_semantic_ir.py -q -k 'source_map and (contract_field or old_v1)'
```

Expected: FAIL because `_source_map_origin_keys` and
`_supported_source_map_subject_keys` omit `contract_fields`.

- [x] **Step 5: Extend the Semantic IR source-map consumer**

Add `contract_fields` to origin-section indexing and add supported
`("variant_output_field", subject_name, workflow_name)` identities from that
section. Do not require the section when absent. Preserve the current fail-closed
behavior for a declared subject whose origin is absent or unsupported.

- [x] **Step 6: Run Task 3 checks and commit**

```bash
pytest tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_drain_stdlib.py -q -k 'contract_field and (wcc or inline or alias or rekey)'
pytest tests/test_workflow_semantic_ir.py -q -k 'source_map and (contract_field or old_v1)'
git diff --check -- orchestrator/workflow_lisp/wcc/defunctionalize.py orchestrator/workflow_lisp/lowering/origins.py orchestrator/workflow_lisp/lowering/phase_drain.py orchestrator/workflow/semantic_ir.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_semantic_ir.py
git add -- orchestrator/workflow_lisp/wcc/defunctionalize.py orchestrator/workflow_lisp/lowering/origins.py orchestrator/workflow_lisp/lowering/phase_drain.py orchestrator/workflow/semantic_ir.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_semantic_ir.py
git commit -m "Bridge union field lineage across lowering routes"
```

Expected: PASS.

### Task 4: Serialize violation subjects and resolve them at runtime

> **Status (completed 2026-07-09):** Landed in `bb24aa3b`, with
> workflow-qualified fallback, malformed-binding rejection, and failed-sidecar
> caching in `7018b9ca`. Specification and code-quality reviews approved the
> final range; 54 affected-module tests pass.

**Files:**
- Modify: `orchestrator/contracts/output_contract.py`
- Modify: `orchestrator/workflow/frontend_origins.py`
- Test: `tests/test_output_contract.py`
- Test: `tests/test_runtime_observability.py`

- [x] **Step 1: Add RED output-validator subject tests**

Extend the existing missing-active and forbidden-inactive tests with subject
metadata in the field specs. Assert exact structured `subject_refs`, including
the selected variant for a missing shared field:

```python
violation = exc_info.value.violations[0]
assert violation["subject_refs"] == [{
    "subject_kind": "variant_output_field",
    "subject_name": "execute::Decision::COMPLETED::report",
    "workflow_name": "demo/module::entry",
}]
```

Also assert a subject-free contract produces the current dictionary without a
`subject_refs` key.

Run:

```bash
pytest tests/test_output_contract.py -q -k 'variant and subject'
```

Expected: FAIL because `ContractViolation` has no subjects.

- [x] **Step 2: Implement additive subject serialization**

Add `subject_refs: tuple[ValidationSubjectRef, ...] = ()` to
`ContractViolation`. Serialize with stable first-seen de-duplication and omit
the key when empty. Use the defensive parser from
`orchestrator.exceptions` for:

- required/invalid selected variant fields via `source_map_subject`;
- forbidden inactive fields via that inactive field's subject;
- shared fields via `source_map_subjects_by_variant[selected_variant]`.

Do not change contract codes, validity, artifact parsing, or message wording.

- [x] **Step 3: Add RED compiled-index resolution tests**

Write one source-map payload containing `contract_fields`, one field validation
subject, and one step origin. Construct `CompiledFrontendIndex` through normal
`WorkflowProvenance` and assert:

```python
assert index.origins_for_subject_refs([serialized_ref]) == [field_origin]
assert index.origins_for_subject_refs([unknown_ref], fallback_step=("Run", "run")) == [step_origin]
```

Also load the existing old-v1 payload shape and assert construction and step
lookup are unchanged.

Run:

```bash
pytest tests/test_runtime_observability.py -q -k 'subject_ref or contract_field_origin'
```

Expected: FAIL because the index has no subject/origin catalogs.

- [x] **Step 4: Implement indexed subject lookup**

In `frontend_origins.py`, index all origin sections, including optional
`contract_fields`, by `origin_key`; index validation subjects by the full
`(kind, name, workflow)` key; and add `origins_for_subject_refs`. Accept
`ValidationSubjectRef` objects and serialized mappings. Return ordered,
de-duplicated origins. If no field origin resolves and an explicit fallback
step is supplied, use `origin_for_step`. Never read or compile `.orc` source.

- [x] **Step 5: Run Task 4 checks and commit**

```bash
pytest tests/test_output_contract.py -q -k 'variant and subject'
pytest tests/test_runtime_observability.py -q -k 'subject_ref or contract_field_origin'
git diff --check -- orchestrator/contracts/output_contract.py orchestrator/workflow/frontend_origins.py tests/test_output_contract.py tests/test_runtime_observability.py
git add -- orchestrator/contracts/output_contract.py orchestrator/workflow/frontend_origins.py tests/test_output_contract.py tests/test_runtime_observability.py
git commit -m "Resolve runtime contract field origins"
```

Expected: PASS.

### Task 5: Enrich real executor violations through the production build path

> **Status (completed 2026-07-09):** Landed in `194ad866`, with the exact
> selected-field subject identity pinned in `962daa2d`. Specification and
> code-quality reviews approved the final range; the five production-path and
> compatibility tests pass, and the known output-bundle baseline failure is
> unchanged.

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Create: `tests/test_workflow_lisp_runtime_source_map.py`
- Modify only if a shared helper is necessary: `tests/test_workflow_lisp_source_map.py`

- [x] **Step 1: Write the RED declarative acceptance test**

Create a real `.orc` module with `ACCEPTED.report` and `REJECTED.report` on
different lines and a command-result or provider-result returning that union.
Build it with `build_frontend_bundle`, run the resulting workflow through the
ordinary executor using the suite's deterministic fake command/provider, and
make the selected `ACCEPTED` bundle omit `report`.

Assert the persisted step error contains:

```python
violation = step_state["error"]["context"]["violations"][0]
assert violation["type"] == "variant_required_field_missing"
assert violation["context"]["variant"] == "ACCEPTED"
assert violation["context"]["name"] == "report"
assert violation["subject_refs"][0]["subject_kind"] == "variant_output_field"
assert len(violation["source_origins"]) == 1
origin = violation["source_origins"][0]
assert origin["entity_kind"] == "variant_output_field"
assert origin["line"] == accepted_report_line
assert origin["line"] != rejected_report_line
```

Do not mock `CompiledFrontendIndex` and do not hand-author the source map.

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_runtime_source_map.py -q
pytest tests/test_workflow_lisp_runtime_source_map.py -q
```

Expected: collect succeeds; test FAILS because executor violations have no
`source_origins`.

- [x] **Step 2: Enrich each violation in the executor**

In `_apply_expected_outputs_contract`, copy each serialized violation and call
the frontend index with its `subject_refs` plus the current step name/id as
fallback. Add `source_origins` only when resolution returns origins. Preserve
the original code, message, context, subject order, failure status, and exit
code. A malformed optional subject or source-map sidecar must not replace the
contract failure with an executor exception.

- [x] **Step 3: Add fallback and multiple-violation assertions**

Add tests proving:

- an old/source-free contract violation gets the generated step origin when a
  source map has one;
- YAML/no-provenance execution retains its existing violation payload and does
  not gain an invented origin;
- two field violations receive independent origin arrays.

- [x] **Step 4: Run Task 5 checks and commit**

```bash
pytest --collect-only tests/test_workflow_lisp_runtime_source_map.py -q
pytest tests/test_workflow_lisp_runtime_source_map.py -q
pytest tests/test_workflow_output_contract_integration.py tests/test_runtime_observability.py tests/test_output_contract.py -q
git diff --check -- orchestrator/workflow/executor.py tests/test_workflow_lisp_runtime_source_map.py
git add -- orchestrator/workflow/executor.py tests/test_workflow_lisp_runtime_source_map.py
git commit -m "Attribute runtime union field violations"
```

Expected: PASS.

### Task 6: Close the boundary gate and hand the roadmap to the drain migration

**Files:**
- Modify: `docs/plans/2026-07-08-boundary-report-followups.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md`
- Modify: `docs/index.md`
- Modify if status materially changes: `docs/capability_status_matrix.md`

- [ ] **Step 1: Run the boundary plan's previously blocked case**

```bash
pytest tests/test_workflow_lisp_runtime_source_map.py tests/test_workflow_lisp_source_map.py -q -k 'union_field or contract_field or runtime'
```

Record the exact acceptance test id and implementation commit in Task 5 case 5.
Mark only its now-complete steps; do not rewrite cases 2 or 3.

- [ ] **Step 2: Perform historical fixture reconciliation**

Run the boundary plan Task 6 commands against the current checkout and record
the result in its final execution handoff. Do not restore or delete historical
fixtures and do not edit the closed Phase-1 deletion plan.

- [ ] **Step 3: Run the boundary final gate**

```bash
rg -n 'proof-gated' docs/design/*.md
pytest tests/test_workflow_lisp_variant_proofs.py tests/test_workflow_lisp_structured_results.py tests/test_output_contract.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_runtime_source_map.py -q
```

Classify residual terminology hits and record the exact pass count. Only then
mark the boundary plan complete and remove the pause wording from routing docs.

- [ ] **Step 4: Run implementation-wide verification**

```bash
pytest --collect-only tests/test_workflow_lisp_runtime_source_map.py -q
pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_source_map.py tests/test_workflow_semantic_ir.py tests/test_output_contract.py tests/test_runtime_observability.py tests/test_workflow_lisp_runtime_source_map.py tests/test_workflow_output_contract_integration.py -q
python -m orchestrator --help >/tmp/runtime-union-field-lineage-smoke.txt
```

Then run the full suite and compare failures by test identity with the recorded
pre-plan baseline (six known failures at `2f8d35f5`, unless the baseline has
been intentionally updated by an intervening commit):

```bash
pytest -q
```

Do not weaken or skip a new failure. Record exact counts and identities.

- [ ] **Step 5: Route the next active plan and commit closure**

Update the sequence, activation plan, and index so
`docs/plans/2026-07-07-drain-migration-g8-retirement.md` Phase 1 Task 1.1 is the
next active roadmap work. Keep the semantic-migration freeze in force.

```bash
git diff --check -- docs/plans/2026-07-08-boundary-report-followups.md docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md docs/index.md docs/capability_status_matrix.md
git add -- docs/plans/2026-07-08-boundary-report-followups.md docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md docs/plans/2026-07-09-procedure-first-roadmap-activation-plan.md docs/index.md
git add -- docs/capability_status_matrix.md  # only if changed
git commit -m "Close runtime union field lineage gate"
```

Expected: the boundary plan is complete and the governing roadmap points to
the drain migration without claiming that the drain itself has begun.

## Completion handoff

After Task 6, immediately continue with
`docs/plans/2026-07-07-drain-migration-g8-retirement.md` Phase 1 under
Subagent-Driven Development. Do not ask for a second roadmap confirmation; the
user approved continuous roadmap execution. Stop only on a failed gate, an
unresolved design decision, or overlap with uncommitted work in a required
file.
