# Workflow Lisp Imported Review-Loop Module Path Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the `design_plan_impl_stack` example `.orc` workflow to import its sibling workflow-family modules through the normal Workflow Lisp module graph, while keeping imported `std/phase.review-revise-loop` compatible with family-owned review-report paths under `artifacts/review` and canonical findings paths under `artifacts/work`.

**Architecture:** Keep one module/import system and one imported-stdlib review-loop route. Extend compiler source-root inference so entrypoints inside a repo `workflows/` tree treat the nearest `workflows/` ancestor as the default project root, align the affected family module names and imports to that shared root, then tighten review-loop path compatibility so `last_review_report` can stay caller-owned under `artifacts/review` while `ReviewFindings.items_path` remains canonical under `artifacts/work`. Finish by splitting generated review-report seeding from findings seeding and proving the route through focused module, stdlib, migration compile, and dry-run checks.

**Tech Stack:** Workflow Lisp `.orc`, Python frontend modules in `orchestrator/workflow_lisp/`, `pytest`, `python -m orchestrator`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/steering.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/work_item_context.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-imported-review-loop-module-path-alignment/implementation_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`

Current checkout facts that must not be rediscovered during implementation:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is empty, so no later ledger event supersedes this slice.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `orchestrator/workflow_lisp/compiler.py::_effective_source_roots(...)` currently orders the inferred entry root first, then the built-in stdlib root, then explicit caller roots. It does not yet inject a shared `workflows/` project root for entrypoints under `workflows/examples/`.
- `orchestrator/workflow_lisp/modules.py::_resolve_import_path(...)` already resolves imports against a tuple of roots and reports `module_not_found` or `module_import_ambiguous`; this slice must reuse that system, not bypass it.
- `orchestrator/workflow_lisp/phase.py::PHASE_TARGET_SPECS` currently roots both `review-report` and `last-review-report` under `artifacts/work`.
- `orchestrator/workflow_lisp/typecheck.py::_initial_review_loop_report_expr(...)` still falls back to `PhaseTargetExpr(target_name="execution-report")` when it cannot infer a caller-owned review-report field.
- `orchestrator/workflow_lisp/typecheck.py` still seeds `initial_findings_expr.items_path` from `initial_last_review_report_expr`, and `_allow_stdlib_review_findings_seed_path(...)` exists as a narrow compatibility escape hatch.
- The affected family `.orc` modules still use bare module names:
  - `design_plan_impl_review_stack_v2_call`
  - `tracked_design_phase`
  - `tracked_plan_phase`
  - `design_plan_impl_implementation_phase`
- `tests/test_workflow_lisp_phase_stdlib.py` already contains focused regression coverage for review-loop seed separation, including `test_review_loop_seed_state_does_not_reuse_initial_report_as_findings_path(...)` and `test_review_loop_seed_state_uses_placeholder_for_noncanonical_completed_report_field(...)`.
- `tests/test_workflow_lisp_key_migrations.py` already contains migration-facing compile and resume-safe imported-stdlib fixtures, including `test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts(...)` and `test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route(...)`.

## Prerequisite And Scope Guardrails

Implement only this bounded shared prerequisite:

- add one bounded default source-root rule for workflow entrypoints under `workflows/`;
- align the affected family module declarations and imports to that shared `workflows/` root;
- allow imported review-loop terminal report fields to accept caller-owned review-report path types under `artifacts/review`;
- keep findings canonical on `std/phase.ReviewFindingsJsonPath` under `artifacts/work`;
- split report-path seeding from findings-path seeding so the imported route no longer reuses one work-report expression for both.

Explicit non-goals:

- do not rewrite the full `design_plan_impl_stack` family parity behavior;
- do not widen into reusable-state, workflow defaults, command-result ownership, migration-promotion policy, or runtime changes under `orchestrator/workflow/`;
- do not add generic relative imports, repo-wide arbitrary source-root configuration, or runtime module loading;
- do not introduce a shared stdlib `ReviewReportPath` type that replaces family-owned report-path contracts;
- do not restore pointer-as-authority behavior, report parsing, inline shell/Python glue, or a compiler-special review-loop branch.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/phase.py`
- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- `workflows/library/tracked_design_phase.orc`
- `workflows/library/tracked_plan_phase.orc`
- `workflows/library/design_plan_impl_implementation_phase.orc`
- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_key_migrations.py`

Inspect only for parity oracle or verification context:

- `workflows/examples/design_plan_impl_review_stack_v2_call.yaml`
- `workflows/library/tracked_design_phase.yaml`
- `workflows/library/tracked_plan_phase.yaml`
- `workflows/library/design_plan_impl_implementation_phase.yaml`

Do not modify unless a focused failing check proves this plan is incomplete:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py`
- `orchestrator/workflow_lisp/migration_parity.py`
- shared runtime modules under `orchestrator/workflow/`
- unrelated Workflow Lisp defaults, reusable-state, or promotion-report files

## Required Contract Deltas

These are fixed implementation targets for this slice:

- For an entrypoint path under a repo `workflows/` tree, the nearest ancestor directory named `workflows` becomes the default project source root ahead of the inferred entry-file root, unless an explicit caller-provided root already owns the entrypoint.
- The affected family Workflow Lisp module names become stable relative to that shared root:
  - `examples/design_plan_impl_review_stack_v2_call`
  - `library/tracked_design_phase`
  - `library/tracked_plan_phase`
  - `library/design_plan_impl_implementation_phase`
- Imported `std/phase.review-revise-loop` accepts caller-owned `review_report` and `last_review_report` terminal path types when they are relpaths rooted under `artifacts/review` with the expected existence contract.
- `std/phase.ReviewFindings.items_path` stays strict: it must remain compatible with `std/phase.ReviewFindingsJsonPath` under `artifacts/work`.
- Generated review-loop seed state uses separate sources:
  - `last_review_report` comes from a caller-compatible review-report field or a dedicated review-report phase target.
  - `latest_findings.items_path` comes from a dedicated findings seed compatible with `ReviewFindingsJsonPath`, never from the review-report expression.
- `phase.py::PHASE_TARGET_SPECS` exposes review-report targets under `artifacts/review` and keeps execution/progress/checks targets on their existing work-rooted surfaces.
- When review-loop path compatibility is violated, typecheck must fail with a stable contract/type diagnostic instead of silently falling back to a work-report path.

## Implementation Architecture

### Unit 1: Workflow-Project Source Root Inference

Owns:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/modules.py`
- `tests/test_workflow_lisp_modules.py`

Stable contract:

- entrypoints under `workflows/examples/` can import sibling modules under `workflows/library/` without extra CLI `source_roots`;
- explicit `source_roots=` remains authoritative when the caller already provides a broader project root;
- stdlib import visibility and `module_import_ambiguous` behavior stay unchanged.

### Unit 2: Family Module Naming Alignment

Owns:

- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- `workflows/library/tracked_design_phase.orc`
- `workflows/library/tracked_plan_phase.orc`
- `workflows/library/design_plan_impl_implementation_phase.orc`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_workflow_lisp_modules.py`

Stable contract:

- the example wrapper and sibling family modules declare names relative to `workflows/`;
- imports between them use ordinary Workflow Lisp import syntax through the shared root;
- no example-only import side channel or alternate loader is introduced.

### Unit 3: Review-Loop Mixed-Root Compatibility And Seed Separation

Owns:

- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/phase.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_key_migrations.py`

Stable contract:

- family-owned terminal review-report fields under `artifacts/review` remain valid for imported `review-revise-loop`;
- findings remain the bounded shared authority carrier under `artifacts/work`;
- report-path and findings-path generation use different helpers and different target semantics;
- fallback behavior stays review-specific and source-mapped, not execution-report-shaped.

### Unit 4: Shared Regression Proof

Owns:

- `tests/test_workflow_lisp_modules.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_key_migrations.py`

Stable contract:

- module-root inference succeeds because of the shared project-root rule;
- mixed-root review-loop usage succeeds only when review reports and findings stay on their distinct contracts;
- compile and dry-run of the example entrypoint succeed through the normal module graph and imported stdlib route.

## Task Checklist

### Task 1: Land The Bounded `workflows/` Project-Root Rule

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/modules.py`
- Modify: `tests/test_workflow_lisp_modules.py`

- [ ] Add a helper in `compiler.py` that detects the nearest ancestor directory named `workflows` for the compile entrypoint and inserts it as the default project source root ahead of the inferred entry-file root.
- [ ] Preserve existing precedence: if explicit `source_roots=` already includes a root that owns the entrypoint, keep that configured root authoritative and do not synthesize a second broader root ahead of it.
- [ ] Reuse the existing root-deduplication and `modules.py` import resolution path instead of adding a special import fast path for `workflows/examples`.
- [ ] Add focused module tests that prove:
  - an entrypoint under `workflows/examples/` can resolve a sibling module under `workflows/library/`;
  - an entrypoint outside any `workflows/` tree keeps current root inference;
  - ambiguous imports still raise `module_import_ambiguous` under the shared root rule.
- [ ] Keep `module_not_found` as the diagnostic when the shared project root still cannot resolve the requested family module.

**Blocking verification after Task 1:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_modules.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_modules.py -q`

Expected before implementation: no focused coverage yet proves the `workflows/examples` to `workflows/library` sibling import route under default source-root inference.

### Task 2: Align The Affected Family Modules To Shared `workflows/` Names

**Files:**

- Modify: `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- Modify: `workflows/library/tracked_design_phase.orc`
- Modify: `workflows/library/tracked_plan_phase.orc`
- Modify: `workflows/library/design_plan_impl_implementation_phase.orc`
- Modify: `tests/test_workflow_lisp_key_migrations.py`

- [ ] Rename the four affected `defmodule` declarations to shared-root-relative names:
  - `examples/design_plan_impl_review_stack_v2_call`
  - `library/tracked_design_phase`
  - `library/tracked_plan_phase`
  - `library/design_plan_impl_implementation_phase`
- [ ] Update the example wrapper to import the sibling family modules through those shared-root-relative names.
- [ ] Update any compile expectations in migration tests so bundle/module names match the renamed module paths.
- [ ] Keep the actual workflow names, exports, extern names, and runtime workflow boundary unchanged; only module identities and imports move in this task.
- [ ] Do not extract new modules or introduce additional library surfaces beyond the four already named in the work item context.

**Blocking verification after Task 2:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_key_migrations.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture" -q`

Expected before implementation: the example family still compiles under bare module names and cannot rely on a stable `workflows/`-relative import identity.

### Task 3: Split Review-Report Seeding From Findings Seeding And Tighten Mixed-Root Compatibility

**Files:**

- Modify: `orchestrator/workflow_lisp/contracts.py`
- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `orchestrator/workflow_lisp/phase.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`

- [ ] Add a bounded compatibility helper in `contracts.py` for caller-owned review-report path types so imported `review-revise-loop` accepts terminal `review_report` and `last_review_report` fields rooted under `artifacts/review` without requiring a shared stdlib review-report type.
- [ ] Update review-loop contract validation in `typecheck.py` to use that helper for terminal report fields while keeping `ReviewFindingsJsonPath` strict for findings.
- [ ] Change `_initial_review_loop_report_expr(...)` so its fallback becomes a dedicated review-report phase target, not `execution-report`.
- [ ] Introduce a separate generated findings seed helper for `ReviewFindings.items_path` that always produces a canonical `artifacts/work` findings path compatible with `std/phase.ReviewFindingsJsonPath`.
- [ ] Remove the current conflation where `initial_findings_expr.items_path` reuses `initial_last_review_report_expr`.
- [ ] Update `phase.py::PHASE_TARGET_SPECS` so `review-report` and `last-review-report` are typed and rooted under `artifacts/review`, while execution/progress/checks targets remain on their current work-rooted contracts.
- [ ] Narrow or delete `_allow_stdlib_review_findings_seed_path(...)` only after the explicit findings seed path makes that escape hatch unnecessary; do not leave the compatibility hole wider than the bounded mixed-root contract.
- [ ] Add or update stdlib regression tests that prove:
  - seeded findings paths are never copied from the review-report source;
  - noncanonical completed-report fields still produce the canonical findings placeholder;
  - invalid review-report/finding-path conflation fails with a stable diagnostic.

**Blocking verification after Task 3:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or findings" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "review_loop_parity_fixture" -q`

Expected before implementation: review-loop fallback still points at `execution-report`, and the initial findings seed still derives from the report expression.

### Task 4: Prove The Shared Route With The Recorded Compile And Dry-Run Checks

**Files:**

- Modify: `tests/test_workflow_lisp_modules.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`

- [ ] Re-run the focused module, stdlib, and migration tests after the source-root, module-name, and mixed-root compatibility work lands.
- [ ] Compile the example `design_plan_impl_stack` entry workflow with the recorded provider, prompt, and command manifests and confirm it resolves sibling family imports through the normal module graph.
- [ ] Dry-run the same example workflow with the recorded inputs and confirm the imported `review-revise-loop` route now accepts family-owned review-report paths while findings stay canonical under `artifacts/work`.
- [ ] If any check now fails for family-parity reasons beyond this slice, stop at the shared prerequisite boundary and record the remaining failure as downstream work for the family parity gap rather than widening this plan.

**Required verification commands:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_key_migrations.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_modules.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or findings" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture" -q`
- [ ] `python -m orchestrator compile workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json`
- [ ] `python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json --input brief_path=workflows/examples/inputs/major_project_brief.md --input design_target_path=docs/plans/parity-design.md --input design_review_report_target_path=artifacts/review/parity-design-review.md --input plan_target_path=docs/plans/parity-plan.md --input plan_review_report_target_path=artifacts/review/parity-plan-review.md --input execution_report_target_path=artifacts/work/parity-execution.md --input implementation_review_report_target_path=artifacts/review/parity-implementation-review.md --dry-run`

## Completion Evidence

Implementation is complete for this slice only when all of the following are true:

- the example entry workflow imports sibling family modules through the normal Workflow Lisp module graph without manual root overrides;
- the four family `.orc` module declarations and imports are aligned to the bounded shared `workflows/` root;
- imported `std/phase.review-revise-loop` accepts family-owned review-report path types rooted under `artifacts/review`;
- generated findings paths remain canonical `ReviewFindingsJsonPath` values under `artifacts/work`;
- report-path and findings-path seeding are provably separate in lowered review-loop seed state;
- the recorded collect-only, focused pytest, compile, and dry-run commands all pass from the repo root.
