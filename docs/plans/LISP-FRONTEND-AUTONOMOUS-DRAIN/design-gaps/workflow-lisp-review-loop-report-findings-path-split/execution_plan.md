# Workflow Lisp Review-Loop Report/Findings Path Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining mixed-root seed alias in imported `std/phase.review-revise-loop` specialization so caller-owned review-report paths stay under `artifacts/review`, `ReviewFindings.items_path` stays canonical under `artifacts/work`, and the `design_plan_impl_stack` migration route no longer depends on a hidden lowering-time findings-path repair.

**Architecture:** Reuse the existing imported stdlib `review-revise-loop` route, the already-landed `ReviewFindings` carrier, and the already-landed review-report target roots in `phase.py`. The implementation should make report-seed and findings-seed roles explicit in frontend-owned typing/lowering, remove the current `initial_last_review_report_expr` alias plus `normalize_review_findings_seed_path` repair, narrow loop missing-file permissiveness to generated findings seed fields only, and update focused fixtures/tests so mixed-root compatibility is exercised directly instead of inferred through same-root `WorkReport` shortcuts.

**Tech Stack:** Workflow Lisp `.orc` fixtures and stdlib modules, Python frontend/compiler modules in `orchestrator/workflow_lisp/`, `pytest`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `docs/steering.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/prior-blocked-progress-report.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/3/design-gap-architect/work_item_context.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/implementation_architecture.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/3/design-gap-architect/check_commands.json`

Current checkout facts that must not be rediscovered during implementation:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is still empty, so no later ledger event supersedes this slice.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` already exports `ReviewFindingsJsonPath` and `ReviewFindings`; this slice must not reopen the findings-carrier design.
- `orchestrator/workflow_lisp/phase.py` already roots `review-report` and `last-review-report` under `artifacts/review`; this slice must not re-argue those target roots.
- `tests/test_workflow_lisp_phase_stdlib.py` already contains focused regression tests for review-loop seed behavior, including `test_review_loop_seed_state_does_not_reuse_initial_report_as_findings_path(...)` and `test_review_loop_seed_state_uses_placeholder_for_noncanonical_completed_report_field(...)`, but it does not yet directly assert that the noncanonical `last_review_report` fallback stays on a dedicated review-root placeholder.
- `tests/test_workflow_lisp_build_artifacts.py` already contains `test_review_loop_command_boundary_surfaces_validate_review_findings_adapter(...)`; the command-boundary adapter itself is not the gap here.
- `tests/test_workflow_lisp_key_migrations.py::test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route(...)` is the existing migration-facing compile proof that actually exercises the imported `std/phase.review-revise-loop` route for this slice.
- `tests/test_workflow_lisp_key_migrations.py::test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts(...)` compiles the broader `design_plan_impl_stack` family example but does not itself import or call `review-revise-loop`; it is downstream family regression coverage, not the imported-route proof for this gap.
- The remaining debt is still present in frontend implementation:
  - `typecheck.py::_initial_review_loop_report_expr(...)` still falls back to `PhaseTargetExpr(target_name="execution-report")`.
  - `typecheck.py` still builds `initial_findings_expr.items_path` from `initial_last_review_report_expr`.
  - `typecheck.py::_allow_stdlib_review_findings_seed_path(...)` still exists as a compatibility escape hatch.
  - `lowering.py` still invokes `_loop_projection_materialize_values(..., normalize_review_findings_seed_path=True, ...)` and rewrites `state.latest_findings.items_path` to `artifacts/work/review-findings-seed.json`.
  - `loops.py::_review_findings_seed_optional_fields(...)` still hard-codes `state__latest_findings__items_path` as a special optional relpath field.
- The valid and invalid review-loop fixtures still model report paths with work-rooted types (`WorkReport` / `ReviewReport`) instead of directly proving the mixed-root contract needed by the selected gap.

## Prerequisite And Scope Guardrails

Implement only this bounded shared prerequisite:

- separate review-report seed construction from findings-path seed construction inside imported `review-revise-loop` specialization;
- keep `review_report` and `last_review_report` compatible with caller-owned relpath contracts under `artifacts/review`;
- keep `ReviewFindings.items_path` strict on `ReviewFindingsJsonPath` under `artifacts/work`;
- remove the hidden alias-plus-lowering-rewrite path for the findings seed;
- refresh focused stdlib/build-artifact/migration fixtures so mixed-root behavior is asserted directly.

Explicit non-goals:

- do not modify shared runtime execution or state ownership under `orchestrator/workflow/`;
- do not redesign the imported stdlib `review-revise-loop` route, findings validator policy, reusable-state validation, workflow defaults, or migration-promotion policy;
- do not add new public Workflow Lisp syntax, new authored path types, report parsing, pointer-authority behavior, or inline shell/Python glue;
- do not reopen workflow-project import-root behavior or entrypoint context bootstrap;
- do not loosen `ReviewFindingsJsonPath`, move findings under review-report roots, or accept family-local coercion helpers as the parity route.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/loops.py`
- `orchestrator/workflow_lisp/contracts.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- `tests/fixtures/workflow_lisp/invalid/review_loop_findings_contract_invalid.orc`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_key_migrations.py`

Inspect only if a focused failing test proves the need:

- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`

Do not modify unless verification proves this plan is incomplete:

- shared runtime modules under `orchestrator/workflow/`
- `specs/`
- unrelated reusable-state, promotion-report, or workflow-project import-root files

## Required Contract Deltas

These are fixed implementation targets for this slice:

- Imported review-loop specialization must own two distinct compiler-private seed roles, or equivalent explicit metadata, for generated relpath placeholders:
  - `review_loop_last_review_report_seed`
  - `review_loop_findings_items_path_seed`
- `last_review_report` seed construction must no longer borrow `completed.execution_report_path` or other work-report-shaped values when no caller-owned review-report field matches. The fallback must be a dedicated review-report target compatible with `artifacts/review`.
- `ReviewFindings.items_path` must typecheck directly against `ReviewFindingsJsonPath` and must be seeded from a findings-specific generated path under `artifacts/work`, using the existing deterministic placeholder `artifacts/work/review-findings-seed.json` unless a better compiler-private equivalent is already supported.
- `initial_findings_expr.items_path` must never reference `initial_last_review_report_expr`.
- `lowering.py` must stop relying on `normalize_review_findings_seed_path=True` to repair seed state after typecheck.
- `_allow_stdlib_review_findings_seed_path(...)` must be removed or narrowed so it is no longer the mechanism that makes report-root and findings-root paths appear compatible.
- Missing-file permissiveness for review-loop seed state must stay bounded to compiler-generated placeholder fields only; it must not become a general compatibility rule for report-rooted findings paths.
- The valid review-loop fixture must declare review-report fields under `artifacts/review` while carried findings remain under `artifacts/work`.
- The invalid findings fixture must fail because `items_path` uses a review-report-rooted type, not because of an unrelated shape mismatch.

## Implementation Architecture

### Unit 1: Explicit Seed-Role Modeling

Owns:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/contracts.py`

Stable contract:

- generated review-loop seed placeholders are frontend-private and unreachable from authored `.orc`;
- report-seed and findings-seed values are distinct objects with distinct semantic roles, not two later interpretations of one expression;
- seed-role provenance remains source-mapped and deterministic.

### Unit 2: Truthful Lowering And Loop Seed Optionality

Owns:

- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/loops.py`
- `tests/test_workflow_lisp_build_artifacts.py`

Stable contract:

- lowering materializes the typed seed expressions it receives and does not rewrite report-rooted values into findings-rooted values later;
- generated loop seed optionality remains narrow and review-loop-specific;
- structured build artifacts expose the explicit generated seed roles or generated internal inputs rather than a hidden repair step.

### Unit 3: Mixed-Root Fixture And Contract Proof

Owns:

- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- `tests/fixtures/workflow_lisp/invalid/review_loop_findings_contract_invalid.orc`
- `tests/test_workflow_lisp_phase_stdlib.py`

Stable contract:

- valid review-loop contracts exercise review-report roots under `artifacts/review` and findings roots under `artifacts/work`;
- invalid contracts fail when `items_path` points at a review-report-rooted path type;
- existing review-loop result vocabulary and findings-carrier semantics stay unchanged.

### Unit 4: Migration-Facing Compile Proof

Owns:

- `tests/test_workflow_lisp_key_migrations.py`

Stable contract:

- the dedicated imported-stdlib parity fixture remains the direct compile proof that the shared review-loop route no longer fails with `record field items_path expected ReviewFindingsJsonPath but got WorkReportTarget`;
- the `design_plan_impl_stack` fixture continues to compile through the same module graph after this shared prerequisite is fixed, without claiming that it directly exercises the imported review-loop route;
- this slice proves the path split only; it does not claim wrapper/bootstrap parity beyond that.

## Task Checklist

### Task 1: Freeze The Mixed-Root Regression Surface In Fixtures And Tests

**Files:**

- Modify: `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- Modify: `tests/fixtures/workflow_lisp/invalid/review_loop_findings_contract_invalid.orc`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Update the valid review-loop fixture so `review_report` and `last_review_report` use a dedicated review-report relpath type rooted under `artifacts/review`, while findings remain `ReviewFindings`.
- [ ] Update the invalid fixture so `WrongFindings.items_path` uses that review-report-rooted path type, proving that mixed-root aliasing is rejected directly.
- [ ] Add or tighten focused tests around:
  - `test_typecheck_rejects_invalid_review_loop_findings_contract(...)`
  - `test_review_loop_seed_state_does_not_reuse_initial_report_as_findings_path(...)`
  - `test_review_loop_seed_state_uses_placeholder_for_noncanonical_completed_report_field(...)`
  - `test_review_loop_seed_state_uses_review_report_placeholder_for_noncanonical_completed_report_field(...)`, asserting `state__last_review_report` falls back to a dedicated `artifacts/review/...` placeholder instead of reusing `inputs.completed__execution_report_path` or another work-rooted report field
  - `test_review_loop_valid_fixture_preserves_review_report_and_findings_roots(...)`, asserting the valid fixture lowers review-report fields under `artifacts/review` while findings stay under `artifacts/work`
- [ ] Keep the current terminal `ReviewLoopResult` vocabulary and findings field names unchanged; this task exists only to freeze the mixed-root contract.

**Blocking verification after Task 1:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop and (seed_state or findings or report_path or exhaustion)" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "mixed_root or findings_contract or review_loop" -q`

Expected before implementation: the mixed-root fixture assertions should expose that typecheck still seeds findings from the report expression and that the noncanonical `last_review_report` fallback still points at `execution-report` instead of a dedicated review-root placeholder.

### Task 2: Make Review-Report And Findings Seeds Explicit In Frontend Typing

**Files:**

- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Introduce one frontend-private representation for generated relpath seed placeholders, or equivalent explicit metadata, that can carry:
  - the target `TypeRef`
  - the deterministic literal path
  - the seed-role label
  - source-map provenance
- [ ] Use that representation to build a dedicated review-report seed expression for `last_review_report`.
- [ ] Change `_initial_review_loop_report_expr(...)` so it prefers caller-owned review-report fields and otherwise falls back to a dedicated review-report target under `artifacts/review`, not `execution-report`.
- [ ] Build `initial_findings_expr.items_path` from a findings-specific generated seed compatible with `ReviewFindingsJsonPath`, not from `initial_last_review_report_expr`.
- [ ] Delete or narrow `_allow_stdlib_review_findings_seed_path(...)` so report-rooted path types no longer pass by escape hatch.
- [ ] Add direct tests for the two generated seed roles so the typechecked/lowered seed state proves both obligations before lowering repair could hide them:
  - `state__last_review_report` uses a dedicated review-root placeholder when the completed record lacks a canonical review-report field
  - `state__latest_findings__items_path` remains distinct from the report seed and stays on the findings-root placeholder

**Blocking verification after Task 2:**

- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop and (seed_state or findings or report_path or exhaustion)" -q`

Expected before implementation: the phase-stdlib seed-state tests should still show aliasing between `initial_last_review_report_expr` and `initial_findings_expr.items_path`.

### Task 3: Remove The Hidden Lowering Repair And Narrow Loop Optionality

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/loops.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Remove `normalize_review_findings_seed_path=True` from the review-loop seed lowering path and delete the associated `state.latest_findings.items_path` literal rewrite inside `_loop_projection_materialize_values(...)`.
- [ ] Update lowering to emit the explicit findings seed expression it receives from typecheck, preserving generated provenance in structured build artifacts.
- [ ] Narrow `_review_findings_seed_optional_fields(...)` so missing-file permissiveness stays tied to generated findings-seed fields only and does not silently bless report-rooted relpaths.
- [ ] Add or tighten build-artifact assertions so the lowered seed state shows separate generated report/finding sources instead of one aliased report source plus a later normalization.
- [ ] Keep the findings validator command-boundary behavior intact; this task must not change the adapter contract, only the source of the seed placeholder values feeding loop state.

**Blocking verification after Task 3:**

- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "review_findings or generated_internal_inputs or review_loop" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop and (seed_state or findings or report_path or exhaustion)" -q`

Expected before implementation: build-artifact coverage should still reveal the hidden normalization path or equivalent repaired seed behavior.

### Task 4: Re-Prove The Imported Route And Keep The Family Compile Guard Honest

**Files:**

- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] Tighten `test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route(...)` so it remains the named direct proof that the imported `std/phase.review-revise-loop` route still lowers to the same repeat-until family after the seed-role cleanup, and so it guards the historical `items_path` type mismatch at the route that actually exercises this gap.
- [ ] Tighten `test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts(...)` only as downstream family regression coverage: it should continue to prove the broader family module graph still compiles and preserves its caller-owned review-report outputs after the shared seed split lands, without asserting that this example imports or calls `review-revise-loop`.
- [ ] Keep the plan text, test names, and assertions explicit about the proof split: imported-route parity belongs to the dedicated stdlib parity fixture; family compile stability belongs to `design_plan_impl_stack`.
- [ ] Keep the migration proof compile-focused for this slice because ownership stays inside `orchestrator/workflow_lisp/` and the shared runtime / command-boundary adapter surface is explicitly out of scope; do not widen into the entrypoint bootstrap blocker unless implementation unexpectedly touches runtime-owned behavior.
- [ ] Re-run the exact deterministic migration-facing compile command from `check_commands.json` as the final paired proof that the imported route compiles directly and the downstream family example remains green after the shared seed split:
  `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture" -q`

**Blocking verification after Task 4:**

- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture" -q`

Expected before implementation: the imported-route parity fixture is the relevant place to expose the historical `items_path` mismatch for this gap, while `design_plan_impl_stack` should remain treated as a separate downstream family compile guard.

## Final Verification

Run these exact checks before claiming the slice complete:

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop and (seed_state or findings or report_path or exhaustion)" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "mixed_root or findings_contract or review_loop" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "review_findings or generated_internal_inputs or review_loop" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture" -q`

These five commands must remain identical to `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/3/design-gap-architect/check_commands.json`. Narrower ad hoc selectors are fine for local debugging, but they do not replace the recorded deterministic verification set for this slice.

The final migration-facing proof for this plan is the last command above, which
is the deterministic paired compile check currently recorded in
`state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/3/design-gap-architect/check_commands.json`: it runs the direct imported-route parity fixture together with the downstream `design_plan_impl_stack` family compile guard.

No separate runtime smoke or integration command is required for this bounded
plan revision. The selected gap only changes frontend-private seed-role
construction, typecheck, lowering provenance, and loop-seed optionality inside
`orchestrator/workflow_lisp/`; it does not modify shared runtime execution,
state ownership under `orchestrator/workflow/`, or the findings-validator
command adapter boundary. The focused stdlib assertions, build-artifact
coverage, and migration-facing compile proof together exercise the imported
review-loop route that previously failed on the mixed-root `items_path`
contract. If implementation expands beyond those frontend-owned files or
changes runtime-observable command/state behavior, this rationale no longer
applies and a targeted integration run becomes mandatory before completion.

Record in the implementation handoff:

- which helpers or private expression types now own `review_loop_last_review_report_seed` and `review_loop_findings_items_path_seed`;
- that `normalize_review_findings_seed_path` was removed rather than bypassed;
- that valid review reports now stay under `artifacts/review` in the fixture proof while findings stay under `artifacts/work`;
- the exact pytest commands above and whether any were collect-only versus behavioral compile checks.
