# Workflow Lisp Review Findings Structured Dataflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the bounded carried-findings parity slice to the imported `std/phase` review-loop route by defining a typed `ReviewFindings` carrier, validating it through one explicit certified adapter, storing only validated findings in loop state, revalidating persisted findings before resume-sensitive consumption, and passing validated findings into fix and terminal projection without reopening runtime or review-loop-architecture work.

**Architecture:** Reuse the current imported-stdlib review-loop specialization route and the compiler-owned managed-write-root policy from the command-result slice. `std/phase.orc` gains only the findings carrier contract; `contracts.py` and `typecheck.py` tighten the caller-supplied terminal union plus the internal generated review-decision contract to require findings; `compiler.py` registers `validate_review_findings_v1` as a certified adapter; `lowering.py` inserts explicit validator steps before loop-state publication and before resumed findings consumption, writes validated findings into loop-frame outputs, and routes only validated findings into the generated fix path and terminal projection. Build artifacts and source maps must expose that validator boundary, and tests must prove malformed findings fail as contract/adapter errors rather than semantic review outcomes.

**Tech Stack:** Workflow Lisp `.orc` stdlib modules, Python frontend/compiler modules in `orchestrator/workflow_lisp/`, certified command adapters, `pytest`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/steering.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/2/design-gap-architect/work_item_context.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `specs/dsl.md`
- `specs/io.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/2/design-gap-architect/check_commands.json`

Current checkout facts that must not be rediscovered during implementation:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is empty, so no later ledger event supersedes this slice.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` currently exports only `ReviewDecision` and `review-revise-loop`; it does not define or export a carried-findings contract.
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc` still models `ReviewLoopResult` without a `findings` field on any terminal variant.
- `orchestrator/workflow_lisp/typecheck.py::_validate_review_loop_result_contract(...)` still enforces only the current report/blocker/reason fields and does not require `findings`.
- `orchestrator/workflow_lisp/lowering.py` still projects `last_review_report` through loop outputs but does not thread validated findings through loop state or terminal projection.
- `orchestrator/workflow_lisp/stdlib_contracts.py` still records `review-revise-loop` with `backend_kinds == ("provider",)` and no certified adapter binding names.
- `orchestrator/workflow_lisp/adapters/` does not yet contain `validate_review_findings_v1.py`.
- The current review-loop implementation already uses the imported `std/phase` macro plus specialization route. This slice must extend that route, not redesign it.

## Prerequisite And Scope Guardrails

Prerequisite:

- This plan assumes the managed-write-root boundary from `workflow-lisp-command-result-compiler-owned-bundle-paths` is already available or is landed first in the implementation branch. The findings validator introduces another command boundary with generated bundle paths. Do not work around a missing prerequisite by exposing validator write roots as public workflow inputs.

Implement only this bounded slice:

- add the `ReviewFindings` carrier contract and its path-safe JSON reference type;
- require findings on review-loop terminal contracts and internal review-decision variants;
- add one explicit certified adapter boundary, `validate_review_findings_v1`;
- validate findings before loop-state publication;
- revalidate persisted findings before resumed fix or equivalent resumed consumption;
- pass validated findings into fix in structured form;
- expose the validator step in command-boundary manifests and source-map/build artifacts;
- extend focused tests and fixtures for findings validation, lowering, resume-sensitive revalidation, and migration-facing review-loop coverage.

Explicit non-goals:

- do not replace or re-argue the imported-stdlib review-loop architecture;
- do not modify shared runtime execution/state modules under `orchestrator/workflow/`;
- do not introduce generic runtime execution for `defschema`;
- do not add first-class list-valued findings collections or a general schema-language runtime;
- do not widen into `resume-or-start`, reusable-state summaries, workflow input defaults, parity-report generation, or promotion policy;
- do not change `specs/dsl.md`, `specs/io.md`, `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, or public/internal managed-write-root ownership rules;
- do not add report parsing, pointer-as-authority compatibility, inline Python/shell glue, or hidden `subprocess.run` semantics.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/stdlib_contracts.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- `tests/fixtures/workflow_lisp/invalid/review_loop_findings_contract_invalid.orc`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_structured_results.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_key_migrations.py`

Inspect only if a focused failing test proves the need:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/procedure_refs.py`
- `orchestrator/workflow_lisp/source_map.py`

Do not modify unless verification proves this plan is incomplete:

- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/executor.py`
- `specs/dsl.md`
- `specs/io.md`
- unrelated Workflow Lisp defaults, reusable-state, or migration-promotion modules

## Required Contract Deltas

These are part of the implementation contract and should be treated as fixed:

- `std/phase.orc` exports a bounded findings carrier:
  - `ReviewFindingsJsonPath`
    - `:kind relpath`
    - `:under "artifacts/work"`
    - `:must-exist true`
  - `ReviewFindings`
    - `schema_version String`
    - `items_path ReviewFindingsJsonPath`
- The caller-supplied terminal `:returns` union for `review-revise-loop` keeps the current result vocabulary and existing required fields, but now must also include `findings` on every terminal variant:
  - `APPROVED`
  - `BLOCKED`
  - `EXHAUSTED`
- The internal generated review-decision contract used by the review provider step must also require `findings ReviewFindings` on `APPROVE`, `REVISE`, and `BLOCKED`.
- `schema_version` must validate as `ReviewFindings.v1`; `items_path` must remain a workspace-relative artifact path and must not be a pointer-like scalar payload.
- Loop state may store only the validated findings carrier, never raw provider JSON or prose.
- Same-iteration `REVISE` passes validator output directly into fix; resumed `REVISE` revalidates persisted findings before fix consumes them.
- Exhausted terminal projection must carry the last validated findings. If implementation cannot prove same-checkpoint safety on resumed projection, revalidate persisted findings on the exhausted path as well.
- `review-revise-loop` build metadata must expose the validator as a certified adapter dependency with source-map lineage and managed-write-root provenance.
- `review-revise-loop` stdlib contract inventory must stop claiming a provider-only lowering shape once the validator exists:
  - `backend_kinds` includes the certified-adapter boundary alongside provider execution;
  - `required_statement_families` includes the generated validator `command_step`;
  - `source_map_expectations` include the validator-step lineage surface in addition to the existing hidden-input and hidden-path spans;
  - `adapter_binding_names` include `validate_review_findings_v1`.

## Implementation Architecture

### Unit 1: Findings Surface And Terminal Contract

- Owns the authored findings carrier and type-level contract checks:
  - `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
  - `orchestrator/workflow_lisp/contracts.py`
  - `orchestrator/workflow_lisp/typecheck.py`
  - `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
  - `tests/fixtures/workflow_lisp/invalid/review_loop_findings_contract_invalid.orc`
  - `tests/test_workflow_lisp_phase_stdlib.py`

- Stable contract:
  - the review-loop public surface and caller-supplied `:returns` remain unchanged except for the required `findings` field;
  - equivalent imported aliases for `ReviewFindings` remain acceptable if they resolve to the same record contract;
  - this slice does not rename report-path vocabulary or remove existing required result fields.

### Unit 2: Certified Validator Boundary And Build Metadata

- Owns the explicit findings validator command boundary and its surfaced metadata:
  - `orchestrator/workflow_lisp/compiler.py`
  - `orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py`
  - `orchestrator/workflow_lisp/stdlib_contracts.py`
  - `tests/test_workflow_lisp_structured_results.py`
  - `tests/test_workflow_lisp_build_artifacts.py`

- Stable contract:
  - the validator binding name is `validate_review_findings_v1`;
  - the stable command is `python -m orchestrator.workflow_lisp.adapters.validate_review_findings_v1`;
  - the adapter returns the validated `ReviewFindings` carrier shape rather than inventing a second semantic representation;
  - review-loop build artifacts and command-boundary manifests surface the validator explicitly as a certified adapter boundary;
  - the `review-revise-loop` stdlib contract tuple and observed lowered workflow stay aligned once the validator step exists, including `backend_kinds`, `required_statement_families`, `source_map_expectations`, and `adapter_binding_names`.

### Unit 3: Lowering, Revalidation, And Fix Dataflow

- Owns the generated validator steps, loop-state outputs, and fix-input routing:
  - `orchestrator/workflow_lisp/typecheck.py`
  - `orchestrator/workflow_lisp/lowering.py`
  - `tests/test_workflow_lisp_phase_stdlib.py`
  - `tests/test_workflow_lisp_procedures.py`
  - `tests/test_workflow_lisp_key_migrations.py`

- Stable contract:
  - findings validate before they enter loop-frame state;
  - persisted findings revalidate before resumed fix consumption;
  - final projection reads findings from validated loop outputs, not from the raw review provider bundle;
  - fix receives structured findings, never raw JSON strings, raw artifact paths without validation, or markdown prose;
  - carried evidence identities such as `checks_report` still come from loop state or consumed inputs, not from review-provider output.

### Unit 4: Regression Proof And Migration-Facing Evidence

- Owns the narrow regression proof that the bounded slice works end-to-end:
  - `tests/test_workflow_lisp_phase_stdlib.py`
  - `tests/test_workflow_lisp_procedures.py`
  - `tests/test_workflow_lisp_structured_results.py`
  - `tests/test_workflow_lisp_build_artifacts.py`
  - `tests/test_workflow_lisp_key_migrations.py`

- Stable contract:
  - malformed findings fail as output-contract or adapter validation errors, not as semantic `APPROVE`/`REVISE`/`BLOCKED`;
  - build/source-map evidence shows the findings validator boundary;
  - migration-facing review-loop fixtures compile and resume through the findings-aware route.

## Task Checklist

### Task 1: Add The Findings Surface And Lock The Contract Regressions

**Files:**

- Modify: `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/review_loop_findings_contract_invalid.orc`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Extend `std/phase.orc` with `ReviewFindingsJsonPath` and `ReviewFindings`, and export the new findings carrier without changing the public `review-revise-loop` keyword surface.
- [ ] Update the valid review-loop fixture so every terminal `ReviewLoopResult` variant includes `findings ReviewFindings`, and add fixture data for a concrete `ReviewFindings.v1` artifact path.
- [ ] Add an invalid fixture where the review-loop terminal contract omits `findings` or uses the wrong type, and wire it into the phase-stdlib contract tests.
- [ ] Add a helper in `contracts.py` that recognizes whether a type is exactly `std/phase.ReviewFindings` or an equivalent imported alias, so typecheck can enforce compatibility without string-matching only one module path.
- [ ] Tighten `_validate_review_loop_result_contract(...)` in `typecheck.py` to require `findings` on `APPROVED`, `BLOCKED`, and `EXHAUSTED` while preserving the current report/blocker/reason requirements from the prior slice.
- [ ] Add or update focused tests that prove missing findings fail typecheck, equivalent aliases succeed, and the current report-path vocabulary remains intact.
- [ ] Do not normalize the broader target-design `ReviewLoopResult` vocabulary in this task; only add the findings obligation.

**Blocking verification after Task 1:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop and (findings or stdlib_module)" -q`

Expected before implementation: the new findings-required contract tests fail because `std/phase` lacks the findings carrier and the review-loop return-contract checker still accepts result unions without `findings`.

### Task 2: Add The Certified Findings Validator Boundary

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Create: `orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py`
- Modify: `orchestrator/workflow_lisp/stdlib_contracts.py`
- Modify: `tests/test_workflow_lisp_structured_results.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Implement `validate_review_findings_v1.py` as a certified adapter that:
  - accepts a structured object equivalent to `ReviewFindings`;
  - requires `schema_version == "ReviewFindings.v1"`;
  - rejects absolute paths, `..` escapes, missing files, malformed JSON, and pointer-like scalar payloads;
  - echoes the validated `ReviewFindings` carrier shape as its structured output.
- [ ] Register `validate_review_findings_v1` in `compiler.py` using `CertifiedAdapterBinding`, matching the existing adapter-registration pattern used for reusable-state and resource-transition helpers.
- [ ] Set binding metadata explicitly:
  - `stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1")`
  - `input_contract={"type": "object"}`
  - `output_type_name="ReviewFindings"`
  - `effects=("structured_result",)`
  - `path_safety={"kind": "workspace_relpath"}`
  - `source_map_behavior="step"`
  - positive and negative fixture ids for valid findings, wrong schema version, path escape, pointer-authority rejection, and malformed JSON.
- [ ] Update `stdlib_contracts.py` so `review-revise-loop` no longer advertises a provider-only lowering shape:
  - add the validator dependency to `backend_kinds`;
  - add `command_step` to `required_statement_families` for the generated validator step;
  - extend `source_map_expectations` with the validator command-step lineage expectation required by the implementation architecture;
  - add `validate_review_findings_v1` to `adapter_binding_names`.
- [ ] Add or update tests that prove the command-boundary environment accepts the new certified adapter metadata, the build manifest surfaces the validator boundary, and missing adapter metadata still fails validation.
- [ ] Update the phase-stdlib contract inventory assertion so it checks the revised `review-revise-loop` tuple and proves the observed lowered families/source-map lineage still match the declared contract after the validator step is introduced.
- [ ] Preserve the managed-write-root policy from the prerequisite slice; do not expose validator bundle roots as public inputs.

**Blocking verification after Task 2:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_build_artifacts.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_contract_inventory_matches_lowering_families -q`
- [ ] `python -m pytest tests/test_workflow_lisp_structured_results.py -k "command_boundary or certified_adapter or output_bundle" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "command_boundary or generated_internal_inputs or review_loop" -q`

Expected after Task 2: the compiler can surface a certified findings validator boundary, the stdlib contract inventory truthfully records the generated command boundary, and build artifacts can prove the review loop depends on that adapter rather than hidden inline glue.

### Task 3: Thread Validated Findings Through Review, Resume, And Fix

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify if needed for fixture data only: `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`

- [ ] Tighten the internal generated review-decision contract so `APPROVE`, `REVISE`, and `BLOCKED` all carry `findings ReviewFindings`.
- [ ] Insert an explicit validator step after each generated review-provider step and before loop-state publication or branch routing.
- [ ] Add generated loop outputs for the validated findings carrier and make final projection read findings from those validated outputs instead of from the raw review-provider bundle.
- [ ] Update same-iteration `REVISE` lowering so the generated fix path consumes validator output directly.
- [ ] Add explicit revalidation on every resume-sensitive consumption edge where findings come from persisted loop state, at minimum the `REVISE -> fix` path. Revalidate the exhausted terminal projection path as well unless implementation proves same-checkpoint safety and documents that proof in code comments/tests.
- [ ] Keep carried evidence identities such as `checks_report` sourced from loop state or consumed inputs; do not let review-provider output replace them while findings are added.
- [ ] Update procedure tests so generated/private review-loop helpers prove fix receives structured findings rather than raw path strings or prose.
- [ ] Update the migration-facing review-loop resume fixture so the first review returns `REVISE` plus findings, the resumed path revalidates persisted findings before fix, and the final approve path still completes through the imported stdlib route.

**Blocking verification after Task 3:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop and (findings or exhaustion or write_root or stdlib_module)" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_procedures.py -k "review_loop and (findings or proc_ref or private_workflow)" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "review_loop or design_plan_impl or parity" -q`

Expected after Task 3: only validated findings enter loop state, resumed fix paths revalidate persisted findings before use, and migration-facing review-loop fixtures prove findings reach fix and terminal projection in structured form.

### Task 4: Run The Recorded Narrow Verification Set

**Files:**

- No additional maintained source files; this task proves the bounded slice with the recorded commands.

- [ ] Run the exact collect-only command from `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/2/design-gap-architect/check_commands.json`:
  - `python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] Run the recorded focused phase-stdlib command:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop and (findings or exhaustion or write_root or stdlib_module)" -q`
- [ ] Run the direct phase-stdlib contract inventory assertion that the `-k` filter does not guarantee:
  - `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_contract_inventory_matches_lowering_families -q`
- [ ] Run the recorded focused procedures command:
  - `python -m pytest tests/test_workflow_lisp_procedures.py -k "review_loop and (findings or proc_ref or private_workflow)" -q`
- [ ] Run the recorded focused structured-results command:
  - `python -m pytest tests/test_workflow_lisp_structured_results.py -k "command_boundary or certified_adapter or output_bundle" -q`
- [ ] Run the recorded focused build-artifacts command:
  - `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "command_boundary or generated_internal_inputs or review_loop" -q`
- [ ] Run the recorded focused key-migrations command:
  - `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "review_loop or design_plan_impl or parity" -q`
- [ ] If any test names are added or renamed in the touched modules, rerun `pytest --collect-only` for those modules before the full module command.

Success criteria for this task:

- `std/phase.orc` exports a bounded findings carrier usable by review-loop fixtures.
- review-loop terminal contracts reject missing or malformed findings.
- the compiler surfaces `validate_review_findings_v1` as an explicit certified adapter boundary.
- the `review-revise-loop` stdlib contract inventory truthfully records the validator command boundary and still matches the observed lowered workflow families/source-map lineage.
- lowering emits validator steps and validated findings loop outputs.
- resumed review-loop consumption revalidates persisted findings before fix or equivalent resumed consumption.
- build/source-map artifacts show the findings validator boundary and managed generated inputs.
- migration-facing review-loop fixtures still compile and resume through the imported stdlib route.

## Acceptance Checklist

- [ ] `ReviewFindingsJsonPath` and `ReviewFindings` exist in `std/phase.orc` and are exportable for review-loop use.
- [ ] Caller-supplied review-loop terminal unions must include `findings` on `APPROVED`, `BLOCKED`, and `EXHAUSTED`.
- [ ] Internal generated review decisions must include `findings` on `APPROVE`, `REVISE`, and `BLOCKED`.
- [ ] `validate_review_findings_v1` exists as an explicit certified adapter with stable command, typed output, fixture metadata, and workspace-relpath safety.
- [ ] The review loop validates findings before writing them into loop state.
- [ ] Persisted findings revalidate before resumed fix or equivalent resumed consumption.
- [ ] Fix consumes validated structured findings, not prose or unvalidated raw paths.
- [ ] Final projection carries validated findings from loop state, not from the first raw review step.
- [ ] Command-boundary manifests and source maps record the validator step and its generated managed bundle path lineage.
- [ ] `review-revise-loop` stdlib contract metadata no longer claims a provider-only lowering shape after the validator command step is added.
- [ ] No hidden public inputs, report parsing, pointer-as-authority shortcuts, or shared-runtime redesigns are introduced.

## Explicit Non-Goals

- Do not redesign `review-revise-loop`, retire its current specialization route, or mix in the separate primitive-removal work from the generic-composition slice.
- Do not touch `orchestrator/workflow/` runtime execution, resume internals, or shared validation behavior.
- Do not add a generic findings collection type, generic schema executor, or public findings JSON schema language.
- Do not rename the current report-path or result-field vocabulary beyond adding the required `findings` field.
- Do not reopen workflow input defaults, reusable-state validation, promotion reporting, or YAML deprecation mechanics in this item.
