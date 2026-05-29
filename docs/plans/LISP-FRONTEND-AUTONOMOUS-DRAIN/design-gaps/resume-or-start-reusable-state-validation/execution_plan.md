# Resume-Or-Start Reusable-State Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the selected Workflow Lisp frontend design gap so `resume-or-start` has an explicit reusable-state validation contract, certified validator/loader boundaries, and one normalized typed result path for both resumed and fresh execution.

**Architecture:** Keep frontend ownership in `orchestrator/workflow_lisp/` and shared runtime semantics under `orchestrator/workflow/`. Reuse the existing read -> syntax -> macro expansion -> definitions/procedures/workflows -> typecheck -> lowering -> shared-validation seam; derive reusable-state schema authority from the existing structured-result contract machinery instead of inventing a second version system; lower reuse through validator `command-result` -> typed `match` -> fixed-output loader `command-result` or authored `:start`.

**Tech Stack:** Python 3, dataclasses, existing `orchestrator.workflow_lisp` compiler/typecheck/lowering pipeline, `CertifiedAdapterBinding`, shared structured-result validation, pytest, and `.orc` fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `28. resume-or-start`
  - `59. Validation Sequence`
  - `62. Contract Validation`
  - `64. Snapshot Validation`
  - `65. Pointer Authority Validation`
  - `66. Report-Authority Validation`
  - `74. Source Map Requirements`
  - `103. Stage 5: Phase And Context Library`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
  - `Classification Model`
  - `Certified Command Adapter`
  - `Adapter Validation`
  - `resume-or-start Requirement`
  - `Runtime-Native Promotion Criteria`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_language_design_principles.md`
- `specs/dsl.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

Current checkout notes that must not be rediscovered during implementation:

- `docs/steering.md` is empty in this checkout, so it adds no extra local steering beyond repo instructions.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` currently has no events, so do not infer partial completion from the ledger.
- The current tree already contains adjacent Stage 5 `resume-or-start` scaffolding, plus adapter and fixture stubs in the planned paths. Extend that surface; do not add parallel recovery abstractions elsewhere.

## Hard Scope Limits

Implement only this bounded slice:

- one explicit compile-time reusable-state contract for authored `resume-or-start`;
- derivation of reusable-state schema/version authority from existing structured-result contract machinery;
- compiler-derived reusable artifact requirements from the authored reusable result shape;
- one certified validator binding:
  - `validate_reusable_phase_state`
- one shared loader backend plus compiler-generated fixed-output loader bindings:
  - `load_canonical_phase_result__<ReturnTypeName>`
- exact `START` fallback behavior for:
  - missing canonical bundle
  - present bundle whose terminal union variant is not reusable
- exact hard-failure behavior for stale, malformed, pointer-backed, unsafe, digest-mismatched, or contract-mismatched prior state;
- normalization of resumed and fresh branches to the same authored return type.

Explicit non-goals:

- no expansion of Stage 5 beyond the selected reusable-state slice;
- no runtime-native resume primitive or generalized state-reuse mechanism;
- no resource/drain lowering, queue semantics, or ledger redesign;
- no report parsing, pointer-as-state, inline semantic shell/Python glue, or uncataloged wrappers;
- no redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, variant proof, or runtime state storage;
- no second bundle-version field or alternate schema-validation subsystem.

## File Ownership

Create:

- `tests/fixtures/workflow_lisp/invalid/resume_or_start_record_valid_when_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/resume_or_start_pointer_authority_invalid.orc`

Modify:

- `orchestrator/workflow_lisp/adapters/load_canonical_phase_result.py`
- `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `tests/test_loader_validation.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_neurips_plan_gate_recovery.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
- `tests/fixtures/workflow_lisp/invalid/resume_or_start_contract_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/resume_or_start_uncertified_adapter.orc`

Modify only if a focused failing test proves the need:

- `orchestrator/workflow_lisp/diagnostics.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/fixtures/workflow_lisp/valid/neurips_plan_gate_resume.orc`

Reuse without widening ownership:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/phase.py`
- shared modules under `orchestrator/workflow/`

## Required Contracts

Keep these contracts fixed during implementation:

- The compile-time reusable-state object is explicit and frontend-local. If the current name is still `ResumeValidationSpec`, either evolve it in place or rename it to match the architecture, but the resulting fields must cover:
  - `resume_from_expr`
  - `return_type_ref`
  - `structured_contract_kind`
  - `expected_contract_fingerprint`
  - `reusable_variants`
  - `artifact_requirements`
  - `validator_binding_name`
  - `loader_binding_name`
  - `source_map_behavior`
- Reusable artifact requirements are compiler-derived, not authored string lists. They recurse through reusable record fields and include only relpath-valued fields that already require existence.
- The reusable-state schema/version authority is the structured-result contract fingerprint:
  - target DSL version
  - authored return type name
  - contract kind (`record` or `union`)
  - normalized structured-result contract digest
- `resume-or-start` lowers through:

```text
validate_reusable_phase_state
match ResumeReuseDecision
load_canonical_phase_result__<ReturnTypeName>
```

- `ResumeReuseDecision` exposes only:
  - `REUSE(source_bundle_path, source_bundle_sha256, matched_variant?)`
  - `START(reason_code)` where `reason_code` is `MISSING_BUNDLE` or `VARIANT_NOT_REUSABLE`
- Union returns require non-empty `:valid-when`.
- Record returns forbid `:valid-when`.
- `:resume-from` must be canonical structured state, not pointer text or prose reports.
- The loader must revalidate the approved bundle digest before emitting any typed result.
- Stable hard-failure error codes must include:
  - `resume_state_path_unsafe`
  - `resume_state_pointer_authority_forbidden`
  - `resume_state_contract_fingerprint_mismatch`
  - `resume_state_bundle_schema_invalid`
  - `resume_state_required_artifact_missing`
  - `resume_state_bundle_mutated_before_load`
  - `resume_state_loader_schema_invalid`
- Generated steps and diagnostics must preserve authored `resume-or-start` spans through the existing source-map/origin-map path.

## Task 1: Lock The Slice With Fixtures And Failing Tests

**Files:**

- Create: `tests/fixtures/workflow_lisp/invalid/resume_or_start_record_valid_when_invalid.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/resume_or_start_pointer_authority_invalid.orc`
- Modify: `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/resume_or_start_contract_invalid.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/resume_or_start_uncertified_adapter.orc`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_neurips_plan_gate_recovery.py`

- [ ] **Step 1: Expand the valid `resume-or-start` fixture**

Ensure `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc` covers both supported result shapes:

- one record-returning `resume-or-start` without `:valid-when`;
- one union-returning `resume-or-start` with reusable variants;
- one canonical `:resume-from` relpath input;
- one `:start` branch that lowers through the existing structured-result path instead of inline recovery glue.

- [ ] **Step 2: Add focused invalid fixture coverage**

Create or extend fixtures for:

- record return using `:valid-when` when it must be forbidden;
- pointer-backed `:resume-from` authority misuse;
- contract-mismatch or malformed reusable bundle input;
- uncertified validator/loader binding usage.

- [ ] **Step 3: Add failing tests before implementation**

Add or extend tests so the current tree fails for the missing contract details, not for unrelated syntax:

- phase-stdlib/typecheck tests for union-vs-record `:valid-when` rules;
- lowering tests for deterministic generated loader binding names and decision/loader step wiring;
- adapter tests for validator `START` vs hard-failure behavior and loader digest revalidation;
- procedure/regression tests to prove resumed and fresh branches normalize to the same return type.

Suggested test names:

```python
test_typecheck_rejects_resume_or_start_valid_when_for_record_return
test_typecheck_rejects_pointer_backed_resume_from
test_lowering_resume_or_start_registers_deterministic_loader_binding
test_validate_reusable_phase_state_rejects_contract_fingerprint_mismatch
test_load_canonical_phase_result_rejects_digest_mismatch_before_emit
test_plan_gate_recovery_normalizes_reused_and_fresh_results
```

- [ ] **Step 4: Run collection checks for touched modules**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_loader_validation.py tests/test_neurips_plan_gate_recovery.py -q
```

Expected:

- collection succeeds;
- newly added tests appear under the targeted modules;
- failures, if any, are assertion/implementation failures rather than import or collection errors.

## Task 2: Implement The Compile-Time Reusable-State Contract

**Files:**

- Modify: `orchestrator/workflow_lisp/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py` only if the existing catalog lacks required codes

- [ ] **Step 1: Make the reusable-state contract explicit in `phase_stdlib.py`**

Replace the underspecified contract shape with one that can carry all compile-time requirements:

- structured contract kind (`record` or `union`);
- derived contract fingerprint;
- reusable union variant set;
- derived reusable artifact requirements;
- fixed validator binding name;
- deterministic loader binding name;
- source-map behavior marker.

- [ ] **Step 2: Centralize contract/fingerprint derivation in `contracts.py`**

Add or extend helpers so `resume-or-start` reuses the same structured-result contract machinery already used by Stage 3:

- derive the normalized contract digest from the declared return type;
- fold it into the reusable-state fingerprint;
- derive reusable artifact requirements recursively from reusable result fields;
- reject pointer/report-shaped authority rather than trying to normalize it.

- [ ] **Step 3: Tighten `resume-or-start` typechecking**

In `orchestrator/workflow_lisp/typecheck.py`, enforce:

- `:returns` resolves to a record or union type;
- union returns require non-empty `:valid-when` and every named variant belongs to the return union;
- record returns reject `:valid-when`;
- `:resume-from` is a canonical relpath state value, not a pointer path;
- `:start` typechecks to the declared return type;
- validator and loader bindings resolve to certified adapter metadata rather than plain external-tool bindings.

- [ ] **Step 4: Add or confirm diagnostic coverage**

If the current diagnostic catalog is incomplete, add stable compile-time diagnostics for:

- `resume_or_start_contract_invalid`
- `resume_or_start_reusable_variant_invalid`
- `resume_or_start_record_valid_when_invalid`
- `resume_or_start_resume_path_invalid`
- `resume_or_start_uncertified_backend`

- [ ] **Step 5: Run the targeted phase-stdlib test module**

Run:

```bash
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -q
```

Expected:

- tests covering contract derivation and compile-time validation pass;
- any remaining failures are in adapter execution or lowering, not in syntax/type contract setup.

## Task 3: Finish The Certified Validator And Canonical Loader Backends

**Files:**

- Modify: `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- Modify: `orchestrator/workflow_lisp/adapters/load_canonical_phase_result.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Implement validator decision semantics**

In `validate_reusable_phase_state.py`, enforce the certified `resume_state_reuse` contract:

- path-safety check the canonical bundle path before opening it;
- reject pointer files as semantic authority;
- validate the structured bundle against the expected contract fingerprint;
- verify all compiler-derived reusable artifacts still exist;
- emit `START` only for missing bundle or non-reusable terminal variant;
- emit `REUSE` only with canonical bundle path, digest, and matched variant when applicable;
- map hard failures to the stable runtime error taxonomy.

- [ ] **Step 2: Implement loader digest revalidation and typed emission**

In `load_canonical_phase_result.py`, require:

- re-read canonical bundle from validator-approved path;
- recompute SHA-256 and reject mutation before emitting any outputs;
- validate the bundle against the same contract fingerprint;
- emit the authored return type through the existing top-level structured-result path for both record and union returns.

- [ ] **Step 3: Keep adapter boundaries certified and explicit**

Confirm both adapters preserve the command-adapter contract:

- stable `python -m` command path;
- declared typed inputs and outputs;
- no inline shell/Python semantics;
- read-only semantics aside from their declared structured outputs;
- source-map behavior tied back to the calling `resume-or-start` step.

- [ ] **Step 4: Run focused loader/adapter tests**

Run:

```bash
python -m pytest tests/test_loader_validation.py -q
```

Expected:

- validator and loader positive-path tests pass;
- stale, malformed, unsafe, pointer-backed, and digest-mismatched cases fail with stable error codes.

## Task 4: Wire Compiler Registration And Lowering Through The Typed Decision Path

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_structured_results.py` only if a focused failing test proves shared structured-result expectations must be updated

- [ ] **Step 1: Register deterministic certified bindings in `compiler.py`**

Ensure compilation installs:

- one shared validator binding named `validate_reusable_phase_state`;
- one deterministic fixed-output loader binding per return type named `load_canonical_phase_result__<ReturnTypeName>`;
- correct `output_type_name` on generated loader bindings;
- no duplicate or author-exposed loader calls.

- [ ] **Step 2: Lower `resume-or-start` through validator -> match -> loader/start**

In `orchestrator/workflow_lisp/lowering.py`, make the lowering sequence deterministic:

1. derive the reusable-state validation spec;
2. lower validator `command-result`;
3. lower `match` over `ResumeReuseDecision`;
4. on `REUSE`, lower loader `command-result`;
5. on `START`, lower the authored `:start` branch directly;
6. normalize both branches to the authored return type with no wrapper record or nested union.

- [ ] **Step 3: Preserve source maps and branch provenance**

Generated validator/loader steps, branch locals, and any remapped shared-validation errors must retain:

- the authored `resume-or-start` span;
- the standard-library form name in the expansion stack;
- deterministic step IDs suitable for fixture assertions.

- [ ] **Step 4: Run lowering/procedure regression coverage**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_procedures.py -q
```

Expected:

- generated validator/loader steps validate through the existing Stage 3 structured-result machinery;
- no regressions appear in procedure lowering or structured-result boundaries.

## Task 5: Prove The Selected Recovery Use Case End-To-End

**Files:**

- Modify: `tests/test_neurips_plan_gate_recovery.py`
- Modify: `tests/fixtures/workflow_lisp/valid/neurips_plan_gate_resume.orc` only if a focused failing test proves the fixture no longer matches the bounded contract
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] **Step 1: Add focused plan-gate recovery smoke coverage**

Extend the NeurIPS-style recovery test so it proves:

- missing reusable state falls back to `START`;
- non-reusable terminal variants fall back to `START`;
- stale or invalid reusable state hard-fails instead of silently starting fresh;
- resumed and fresh branches both normalize to the same authored result type.

- [ ] **Step 2: Keep the regression bounded to this slice**

Do not widen the smoke test into resource/drain semantics. The recovery proof should stop at typed plan-gate normalization and adapter/lowering evidence for this selected work item.

- [ ] **Step 3: Run the targeted recovery smoke test**

Run:

```bash
python -m pytest tests/test_neurips_plan_gate_recovery.py -q
```

Expected:

- the selected plan-gate recovery scenario passes in both fresh and resumed cases;
- failure cases remain stable and do not degrade into generic loader or pointer errors.

## Task 6: Run The Required Verification Commands In Exact Order

**Files:**

- No code changes; this task records verification evidence for the work item.

- [ ] **Step 1: Run the required command sequence exactly as authored**

Run these commands from the repo root, in this exact order:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_loader_validation.py tests/test_neurips_plan_gate_recovery.py -q
python -m pytest tests/test_workflow_lisp_phase_stdlib.py -q
python -m pytest tests/test_loader_validation.py -q
python -m pytest tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_procedures.py -q
python -m pytest tests/test_neurips_plan_gate_recovery.py -q
```

- [ ] **Step 2: Record evidence, do not paraphrase away failures**

Capture fresh command output for each run and record:

- pass/fail status;
- any unexpected skips or xfails;
- exact failing test names if something breaks.

Do not weaken or reorder verification to make a failure disappear.

## Completion Notes

Implementation is complete for this work item only when all of the following are true:

- `resume-or-start` has an explicit reusable-state validation contract with compiler-derived artifact requirements and structured-result fingerprint authority;
- validator and loader boundaries are certified command adapters, not plain external tools or inline glue;
- only missing bundle or non-reusable terminal variant produce `START`;
- all other stale/invalid prior-state conditions fail with stable error codes;
- resumed and fresh branches normalize to the same authored return type through the existing Stage 3 structured-result path;
- the five ordered verification commands above pass from the repo root.
