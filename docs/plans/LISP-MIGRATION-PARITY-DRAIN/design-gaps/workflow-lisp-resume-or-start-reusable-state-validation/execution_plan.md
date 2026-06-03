# Workflow Lisp Resume-Or-Start Reusable-State Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement summary-backed reusable-state validation for `resume-or-start` so Workflow Lisp phase reuse writes and validates compiler-owned `ReusablePhaseState.v1` sidecars while preserving the existing typed reuse-versus-fresh author surface.

**Architecture:** This slice keeps canonical phase-result bundles authoritative and adds a derived reusable-state sidecar plus explicit certified adapter boundaries for summary writing, summary validation, and canonical bundle loading. Frontend metadata derivation, lowering, and tests must move from the current bundle-only `REUSE`/`START` contract to the approved parity taxonomy without widening public workflow inputs, exposing managed paths, or shifting shared runtime ownership out of `orchestrator/workflow/`.

**Tech Stack:** Python, Workflow Lisp frontend/compiler (`orchestrator/workflow_lisp`), certified command adapters, `.orc` fixtures, `pytest`

---

## Scope

- Current implementation scope: the selected design-gap architecture in [docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-resume-or-start-reusable-state-validation/implementation_architecture.md](/home/ollie/Documents/agent-orchestration/docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-resume-or-start-reusable-state-validation/implementation_architecture.md) against the target migration design in [docs/design/workflow_lisp_key_migration_parity_architecture.md](/home/ollie/Documents/agent-orchestration/docs/design/workflow_lisp_key_migration_parity_architecture.md).
- Primary authority for baseline compatibility: [docs/design/workflow_lisp_frontend_specification.md](/home/ollie/Documents/agent-orchestration/docs/design/workflow_lisp_frontend_specification.md), especially the `resume-or-start` author contract and the frontend authority boundaries.
- Supporting authority: [docs/design/workflow_command_adapter_contract.md](/home/ollie/Documents/agent-orchestration/docs/design/workflow_command_adapter_contract.md), [docs/design/workflow_lisp_stdlib_lowering.md](/home/ollie/Documents/agent-orchestration/docs/design/workflow_lisp_stdlib_lowering.md), [docs/lisp_workflow_drafting_guide.md](/home/ollie/Documents/agent-orchestration/docs/lisp_workflow_drafting_guide.md), and the runtime specs under `specs/`.
- The drain progress ledger is still empty at [state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json](/home/ollie/Documents/agent-orchestration/state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json), so no later recorded event supersedes the selected architecture or its sequencing.
- This plan implements only the reusable-state parity slice: compiler-owned `ReusablePhaseState.v1` sidecars, richer reusable-state classification, summary-backed loader reuse, public-input/default hashing, producer fingerprinting, and migration-facing verification.
- This plan also refreshes the slice's authoritative deterministic verification artifact at `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json` so the recorded migration selector proves the new reusable-state parity path instead of only the pre-existing review-loop coverage.
- This plan does not cover review-loop semantics, findings dataflow, promotion reports, `non_regressive` policy, YAML deprecation, runtime-native reusable-state primitives, pointer-as-state compatibility, or report parsing.

## Explicit Implementation Decisions

- `ReusablePhaseState.v1` is always derived from the canonical result bundle and never becomes semantic authority itself.
- Fresh successful `resume-or-start` executions must always write the reusable-state sidecar adjacent to the canonical phase bundle.
- If the canonical bundle exists but the reusable-state sidecar is missing, classify that prior state as `FAILED_PRIOR_STATE` and route to the fresh branch. Do not add an adapter-local legacy mode.
- `SCHEMA_MISMATCH` and `UNSUPPORTED_VERSION` remain deterministic failures, not silent fresh starts.
- `source_inputs_hash` must be derived from the public workflow input view after authored defaults and caller overrides resolve; compiler-managed hidden inputs, write roots, run ids, timestamps, and absolute workspace prefixes are excluded.
- `producer_fingerprint` must include `.orc` source digest, imported stdlib digests, compiler version, target DSL version, executable-shape-affecting lowering options, and specialized provider/prompt/workflow/procedure refs.

## Implementation Architecture

### Unit 1: Reusable-State Contract Metadata

- Owns the compiler-side reusable-state specification carried from typecheck into lowering and build surfaces.
- Primary files:
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/stdlib_contracts.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/compiler.py`
- Stable responsibilities:
- expand `ReusableStateValidationSpec` beyond bundle fingerprinting to carry summary schema version, deterministic sidecar path metadata, public-input hash basis, producer fingerprint basis, reusable artifact checksum requirements, and validator/writer/loader binding names;
- derive reusable-state evidence from the compiled workflow boundary rather than hidden managed inputs;
- update the durable stdlib contract inventory so `resume-or-start`'s certified-adapter surface, source-map expectations, and helper ownership stay aligned with the new validator/writer/loader boundary set instead of the current two-binding inventory;
- keep the public/internal input split from the prior command-result and input-default parity slices.
- Must not own runtime execution policy outside the generated adapter contracts and generated lowering metadata.

### Unit 2: Certified Adapter Boundaries

- Owns the command-backed reusable-state semantics required by the command adapter contract.
- Primary files:
- `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- `orchestrator/workflow_lisp/adapters/write_reusable_phase_state_v1.py`
- `orchestrator/workflow_lisp/adapters/load_canonical_phase_result.py`
- `orchestrator/workflow_lisp/compiler.py`
- Stable responsibilities:
- validate sidecar schema/version/compatibility before bundle hash comparisons;
- compute and validate canonical bundle digests and reusable artifact checksums after path-safety checks;
- emit the approved reusable-state outcome taxonomy;
- keep the loader as a fixed-output typed result adapter that only revalidates approved bundle evidence, not reuse policy.
- Must not reintroduce inline Python/shell glue, pointer authority, or user-authored hidden paths.

### Unit 3: Lowering, Generated Paths, And Source Maps

- Owns the generated workflow shape for `resume-or-start` and the provenance surfaces that expose compiler-owned internals safely.
- Primary files:
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/compiler.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- Stable responsibilities:
- emit validator, writer, and loader command boundaries as explicit generated steps;
- preserve the existing authored `:returns` normalization while routing approved non-reusable outcomes to the start branch and deterministic incompatibilities to failure;
- keep compiler-owned summary paths off the public workflow boundary while surfacing them in source maps/build manifests with provenance;
- preserve the existing generated loader-binding family instead of widening the shared runtime executor.

### Unit 4: Fixtures, Regression Proof, And Migration Coverage

- Owns the durable tests and fixtures that prove this slice closes the selected parity gap without reopening adjacent ones.
- Primary files:
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_neurips_plan_gate_recovery.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
- `tests/fixtures/workflow_lisp/invalid/`
- Stable responsibilities:
- update old `REUSE`/`START` assertions to the new outcome taxonomy;
- prove sidecar generation, summary-backed validation, loader digest revalidation, public-input/default hashing, and migration-facing plan-gate reuse;
- keep tests behavioral and contract-shaped rather than checking prompt text or fragile internal prose.

### Dependency Direction

- Unit 1 comes first because the writer, validator, lowerer, and tests all depend on the new metadata contract.
- Unit 2 depends on Unit 1 because adapter payloads and outcome classification require the new summary metadata.
- Unit 3 depends on Units 1 and 2 because lowering must reference the finalized writer/validator/loader contracts and generated sidecar path strategy.
- Unit 4 depends on Units 1 through 3 because fixtures and migration tests should lock the delivered contract, not an intermediate state.

### Compatibility And Ownership Boundaries

- Keep Workflow Lisp authoring, contract derivation, lowering, compiler registration, and adapter ownership inside `orchestrator/workflow_lisp/`.
- Reuse `orchestrator/workflow/loaded_bundle.py`, `executor.py`, `signatures.py`, and `calls.py` without expanding shared runtime ownership into this slice.
- Keep canonical result bundles authoritative; the reusable-state sidecar is a derived validator aid only.
- Keep the existing generated loader-binding family and do not add new public workflow inputs or runtime-native reusable-state effects.

## Task Checklist

### Task 1: Expand The Reusable-State Metadata Contract

**Files:**
- Modify: `orchestrator/workflow_lisp/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/stdlib_contracts.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Extend `ReusableStateValidationSpec` so it can carry the approved reusable-state contract inputs: summary schema/version, deterministic sidecar sibling path strategy, public-input hash basis, producer fingerprint basis, reusable artifact checksum manifest, canonical bundle digest expectation, and validator/writer/loader binding names.
- [ ] Add or update the reusable-state contract helpers in `contracts.py` so the compiler can serialize a stable `ReusablePhaseState.v1` payload and validator payload without duplicating ad hoc JSON assembly in multiple layers.
- [ ] Update `orchestrator/workflow_lisp/stdlib_contracts.py` so the durable `resume-or-start` contract inventory advertises the writer binding alongside `validate_reusable_phase_state` and `load_canonical_phase_result__<ReturnType>`, and keeps helper ownership plus source-map expectations synchronized with the generated surface the tests assert.
- [ ] Revise the `resume-or-start` typecheck path to derive reusable-state evidence from the public workflow input view after default resolution, the reusable return contract, and the compiled producer identity instead of the current bundle-only fingerprint contract.
- [ ] Register the new `write_reusable_phase_state_v1` certified adapter binding in the compiler alongside the existing validator and typed loader bindings, with explicit effects, fixture ids, negative fixture ids, and step-level source-map behavior.
- [ ] Update focused stdlib tests to lock down the expanded compiled metadata, stdlib contract inventory tuple, and adapter-registration surface before changing lowering behavior.

**Blocking verification after Task 1:**

- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "resume_or_start or reusable_state or write_reusable_phase_state" -q`

### Task 2: Implement Summary Writing And Summary-Backed Validation

**Files:**
- Modify: `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- Create: `orchestrator/workflow_lisp/adapters/write_reusable_phase_state_v1.py`
- Modify: `orchestrator/workflow_lisp/adapters/load_canonical_phase_result.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_neurips_plan_gate_recovery.py`

- [ ] Implement `write_reusable_phase_state_v1` as the only new certified adapter in this slice. It must consume the validated fresh-branch bundle path plus compiler-derived summary payload, path-check all referenced artifacts, compute required checksums, write the sidecar atomically, and emit a small structured acknowledgment that can be fixture-tested.
- [ ] Revise `validate_reusable_phase_state` to derive the deterministic sidecar path from the canonical bundle handle, validate summary schema/version/compatibility before bundle comparisons, and classify outcomes as `REUSABLE`, `START`, `STALE`, `MISSING_ARTIFACT`, `FAILED_PRIOR_STATE`, `SCHEMA_MISMATCH`, or `UNSUPPORTED_VERSION`.
- [ ] Apply the explicit compatibility rule from this plan: missing bundle and missing sidecar are different. No prior bundle/sidecar returns compatibility `START`; an existing bundle without a sidecar returns `FAILED_PRIOR_STATE` and falls back to fresh execution.
- [ ] Keep `load_canonical_phase_result.py` focused on bundle-digest revalidation and structured bundle validation using the summary-approved bundle path/digest pair; it must not re-decide staleness, compatibility, or reusable variants.
- [ ] Add or update focused adapter tests for summary generation, checksum validation, pointer-authority rejection, missing-artifact classification, stale-input classification, failed-prior-state classification, schema/version incompatibility, and loader digest mismatch.

**Blocking verification after Task 2:**

- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "resume_or_start or reusable_state or load_canonical_phase_result or write_reusable_phase_state or schema_mismatch or unsupported_version or stale or missing_artifact" -q`
- [ ] `python -m pytest tests/test_neurips_plan_gate_recovery.py -k "resume_validator or reusable_state or plan_gate_recovery" -q`

### Task 3: Rewire `resume-or-start` Lowering Around The New Contract

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/` as needed for new negative coverage

- [ ] Replace the current validator payload generation in `lowering.py` so generated `resume-or-start` validator steps pass the expanded reusable-state contract instead of only contract fingerprint and artifact existence requirements.
- [ ] Update the generated validator `variant_output` contract and match lowering so `REUSABLE` routes through the typed loader, `START`/`STALE`/`MISSING_ARTIFACT`/`FAILED_PRIOR_STATE` route through the authored fresh branch, and `SCHEMA_MISMATCH`/`UNSUPPORTED_VERSION` fail deterministically without inventing a new public authored branch.
- [ ] Insert the new sidecar-writer adapter into the generated fresh branch after the canonical bundle exists and before final branch normalization completes, while keeping the authored `:returns` value unchanged.
- [ ] Preserve compiler-owned hidden path handling: the sidecar path and any writer acknowledgment path must remain generated internals surfaced only through source maps/build manifests with provenance.
- [ ] Update build-artifact and lowering assertions so source maps, generated internal inputs, command boundaries, and validation-subject lineage cover the validator, writer, loader, and sidecar path provenance.

**Blocking verification after Task 3:**

- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "resume_or_start or generated_internal_inputs or source_map or public_inputs" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "resume_or_start or reusable_state" -q`

### Task 4: Refresh Migration Fixtures And Run The Full Verification Set

**Files:**
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_neurips_plan_gate_recovery.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/` as needed
- Modify: `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json`

- [ ] Update the existing reusable-state and plan-gate recovery fixtures so they express the new summary-backed contract rather than the old bundle-only `START`/`VARIANT_NOT_REUSABLE` behavior.
- [ ] Add or update one explicit migration-facing parity test in `tests/test_workflow_lisp_key_migrations.py` named `test_resume_or_start_plan_gate_reusable_state_parity_path`, proving `resume-or-start` reuses approved prior state, starts fresh for stale or missing-artifact prior state, and preserves the typed return shape in the selected-item / plan-gate parity path.
- [ ] If any test names are added or renamed in the touched modules, collect them explicitly before running the full suite selectors, then update `check_commands.json` so its final key-migration entry points at the exact reusable-state parity nodeid instead of the current broad `-k "resume or plan_gate or selected_item or parity"` selector.
- [ ] Keep `check_commands.json` authoritative by changing only the migration command needed for this slice; the final recorded command must be `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_resume_or_start_plan_gate_reusable_state_parity_path -q` unless the implemented test is renamed, in which case record the renamed nodeid there and in this plan before final verification.
- [ ] Run the exact deterministic verification commands from the updated `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json` and do not claim completion without fresh passing output.
- [ ] Record the final implementation evidence in the work summary or completion notes for this slice, including the compatibility choice for missing sidecars and the exact commands run.

**Blocking verification after Task 4:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_build_artifacts.py tests/test_neurips_plan_gate_recovery.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "resume_or_start or reusable_state or load_canonical_phase_result or write_reusable_phase_state or schema_mismatch or unsupported_version or stale or missing_artifact" -q`
- [ ] `python -m pytest tests/test_neurips_plan_gate_recovery.py -k "resume_validator or reusable_state or plan_gate_recovery" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "resume_or_start or generated_internal_inputs or source_map or public_inputs" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_resume_or_start_plan_gate_reusable_state_parity_path -q`

## Explicit Non-Goals

- Do not broaden this slice into review-loop composition, structured findings propagation, workflow input-default authoring beyond consuming the already-approved default-resolution behavior, or migration promotion reporting.
- Do not add runtime-native reusable-state primitives, runtime closures, pointer-as-state compatibility, report parsing, or inline Python/shell glue.
- Do not widen public workflow inputs, expose compiler-owned write roots or sidecar paths at the workflow boundary, or move shared runtime/state authority out of `orchestrator/workflow/`.
- Do not treat a dry-run or compile-only result as parity evidence; this slice closes a reusable-state contract gap and must prove behavior through the focused runtime and migration tests above.
