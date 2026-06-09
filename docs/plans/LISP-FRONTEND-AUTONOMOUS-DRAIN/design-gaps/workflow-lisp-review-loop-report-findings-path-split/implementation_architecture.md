# Workflow Lisp Review-Loop Report/Findings Path Split Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-review-loop-report-findings-path-split`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected prerequisite gap:

- split imported `std/phase.review-revise-loop` seed construction so
  `review_report` / `last_review_report` and `ReviewFindings.items_path` are
  initialized through separate compiler-owned paths;
- preserve caller-owned review-report contracts, including family-local
  relpaths under `artifacts/review`, while keeping
  `ReviewFindings.items_path` on the canonical `ReviewFindingsJsonPath`
  contract under `artifacts/work`;
- replace the current hidden alias route where findings seed state is typed
  from the report seed and only later rewritten during lowering;
- refresh the focused stdlib and migration fixtures so the shared route is
  exercised with mixed roots instead of same-root `WorkReport` shortcuts.

Out of scope for this slice:

- workflow-project source-root inference or sibling module import policy;
- redesign of the imported stdlib `review-revise-loop` specialization route,
  carried-findings validator policy, reusable-state validation, or workflow
  input defaults;
- new runtime/spec behavior, command bundle-path ownership changes,
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, or runtime-native effects;
- new public Workflow Lisp syntax, new authored path types, report parsing,
  pointer-as-authority behavior, or inline shell/Python glue.

This is a bounded implementation architecture for one selected gap only. It
does not replace the parent migration architecture, the umbrella frontend
specification, or the earlier generic review-loop composition slice.

## Problem Statement

The selected migration design now names a narrower prerequisite than the older
blocked family pass:

- imported review-loop specialization must keep review-report authority on
  caller-owned review-report paths;
- carried findings must remain on the bounded `ReviewFindingsJsonPath`
  contract under `artifacts/work`;
- the initial `ReviewFindings` carrier must not be built from the same
  expression used for `review_report` or `last_review_report`.

The current checkout already satisfies part of that contract:

- `std/phase.orc` exports `ReviewFindingsJsonPath` and `ReviewFindings`;
- `phase.py::PHASE_TARGET_SPECS` already maps `review-report` and
  `last-review-report` under `artifacts/review`.

But the remaining path split is still not modeled honestly:

1. `typecheck.py::_initial_review_loop_report_expr(...)` still builds one
   report-shaped seed expression and falls back to `execution-report`.
2. The generated `initial_findings_expr` still sets
   `ReviewFindings.items_path` to that same report-seed expression.
3. `lowering.py` then patches the seed later with
   `normalize_review_findings_seed_path=True`, hardcoding
   `artifacts/work/review-findings-seed.json`.
4. `loops.py` separately special-cases
   `state__latest_findings__items_path` as an optional relpath seed.
5. The prior blocked family report captured the user-visible failure:
   `record field items_path expected ReviewFindingsJsonPath but got WorkReportTarget`.

That is precisely the kind of hidden semantic repair the target design is
trying to eliminate. The report root is already correct in the checkout; the
remaining defect is that report-seed and findings-seed roles are still fused in
frontend typing and only separated later by lowering-time special cases.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Newly Exposed Prerequisite Gaps`
  - `Required Generic .orc Support`
  - `Compiler And Lowering Layer`
  - `Review Loop Contract`
  - `Dependencies And Sequencing`
  - `Evidence And Implementation Boundaries`
  - `Verification Strategy`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 7.3-7.6, 10-11, 16-18, 22-31, 45-57, 59-66, 74, 85, 95,
    102-104
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/prior-blocked-progress-report.md`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep imported `.orc` review loops on the generic stdlib composition route,
  not a compiler-special family branch;
- keep structured findings and typed artifact values authoritative, with
  reports remaining views;
- keep `ReviewFindings.items_path` canonical and strict under
  `artifacts/work`;
- keep caller-owned review-report contracts under caller control; this slice
  must not replace them with a shared stdlib review-report type;
- keep frontend-owned work in `orchestrator/workflow_lisp/` and avoid
  widening shared runtime ownership under `orchestrator/workflow/`;
- keep `docs/design/workflow_command_adapter_contract.md` authoritative for the
  already-selected findings validator boundary; this slice must not add hidden
  scripts or adapters;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full autonomous-drain index in
`state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/3/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defschema-reusable-field-schemas/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-imported-review-loop-module-path-alignment/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/implementation_architecture.md`

### Decisions Reused

- Reuse the imported stdlib `review-revise-loop` route and thin specialization
  model from the generic effectful-composition slice.
- Reuse the bounded findings carrier from the structured-dataflow slice:
  `ReviewFindings(schema_version, items_path)` remains the authoritative
  carried-findings surface.
- Reuse the current phase-context ownership and `PHASE_TARGET_SPECS` authority
  from the phase-context stdlib slice; report-path roots are not redesigned
  here.
- Reuse the existing source-map, expansion-stack, and generated-origin
  substrate; generated seed values must flow through the same provenance
  channel.
- Reuse compiler-owned generated-path policy and keep any new seed paths off
  the public workflow boundary.

### New Decisions In This Slice

- Replace the current alias-plus-lowering-rewrite path with two explicit
  compiler-owned seed roles:
  one for review-report seed state and one for findings-path seed state.
- Keep findings-path seeding strict and canonical: the generated findings seed
  must type as `ReviewFindingsJsonPath` and must never be derived from the
  report-seed expression.
- Treat initial review-loop seed paths as compiler-generated placeholder values
  with source-map provenance rather than as borrowed authored artifact paths.
- Update focused fixtures so review-loop report fields actually use a review
  root under `artifacts/review`; mixed-root compatibility must be proven by
  tests, not left implicit.

### Conflicts Or Revisions

The earlier
`workflow-lisp-imported-review-loop-module-path-alignment/implementation_architecture.md`
bundled three issues together:

- workflow-project source-root inference;
- review-report path-root parity;
- findings-path split.

This slice narrows that older bundle based on current checkout facts:

- the selected gap is now only the report/findings seed split;
- `phase.py` already places review-report targets under `artifacts/review`;
- this slice must not reopen workflow-project source-root behavior.

The current checkout also contains a lowering-time repair path
(`normalize_review_findings_seed_path`) that was useful as an interim patch.
This slice revises that decision: the split must become explicit in typed
specialization rather than remaining a hidden lowering rewrite.

## Ownership Boundaries

This slice owns:

- compiler-private review-loop seed-role modeling in
  `orchestrator/workflow_lisp/expressions.py` if a dedicated generated seed
  expression is introduced;
- report-seed and findings-seed construction in
  `orchestrator/workflow_lisp/typecheck.py`;
- lowering of generated seed roles and removal of the current hidden
  findings-path normalization path in `orchestrator/workflow_lisp/lowering.py`;
- loop seed optional-field handling in `orchestrator/workflow_lisp/loops.py`
  so missing placeholder files remain bounded to generated review-loop seed
  fields only;
- any small contract helpers required to distinguish canonical findings paths
  from caller-owned review-report paths in
  `orchestrator/workflow_lisp/contracts.py`;
- focused fixtures and tests proving mixed-root seed behavior in
  `tests/fixtures/workflow_lisp/` and the affected review-loop/migration test
  modules.

This slice intentionally does not own:

- built-in stdlib module loading, general module-root inference, or sibling
  import behavior;
- the `validate_review_findings_v1` adapter contract or its runtime execution;
- generic review-loop composition, carried-findings schema design, reusable
  state, or workflow input defaults;
- new public authoring syntax, runtime primitives, or spec deltas.

## Current Checkout Facts

The current checkout already contains the pieces this slice should reuse:

- `std/phase.orc` exports `ReviewFindingsJsonPath` and `ReviewFindings`;
- `phase.py::PHASE_TARGET_SPECS` already maps `review-report` and
  `last-review-report` under `artifacts/review`;
- `tests/test_workflow_lisp_phase_stdlib.py` already contains focused review
  loop seed assertions and a literal findings-seed expectation;
- the progress ledger is still empty, so no later recorded event supersedes
  the selector rationale.

The same checkout also shows the exact architectural debt still present:

- `_initial_review_loop_report_expr(...)` still falls back to
  `PhaseTargetExpr(target_name=\"execution-report\")`;
- `initial_findings_expr.items_path` is still built from
  `initial_last_review_report_expr`;
- `lowering.py` still rewrites that field later to the literal
  `artifacts/work/review-findings-seed.json`;
- `loops.py` still treats `state__latest_findings__items_path` as a special
  optional relpath field rather than as an explicitly modeled generated seed;
- the main valid review-loop fixture still uses `WorkReport` for
  `review_report` / `last_review_report`, so the focused stdlib route is not
  yet testing the mixed-root contract the family parity slice needs.

This makes the slice feasible without new runtime behavior: the missing work is
to move the split from hidden lowering repair into explicit frontend-owned seed
construction and to align the fixtures with the selected parity contract.

## Proposed Architecture

### 1. Introduce Explicit Compiler-Owned Seed Roles

Add one frontend-private representation for generated relpath seed values used
only by compiler-generated review-loop initial state.

Required properties:

- not reachable from authored `.orc` syntax;
- carries the intended target `TypeRef`;
- carries one deterministic literal workspace-relative path;
- carries a stable seed-role label for source maps and diagnostics.

Minimum seed roles in this slice:

- `review_loop_last_review_report_seed`
- `review_loop_findings_items_path_seed`

If implementation chooses not to add a distinct AST node, it must still create
an equivalent typed metadata object with the same properties. The important
contract is that these seed roles become explicit frontend authority rather
than a hidden lowering rewrite.

### 2. Seed Review Reports Independently From Findings

Review-loop specialization should stop borrowing `completed.execution_report`
or any other work-report-shaped field as the initial `last_review_report`
carrier.

Instead:

- generate one explicit report-seed value for the loop state's
  `last_review_report` slot;
- derive its literal path from the declared report field contract root so
  caller-owned review-report contracts under `artifacts/review` stay valid;
- keep that seed role independent from findings-path generation and from the
  completed artifact identity.

For the focused fixture and migration family, this means the generated report
seed lives under `artifacts/review`. For any remaining bounded compatibility
fixture whose declared report type still roots under `artifacts/work`, the seed
follows that declared root rather than silently coercing both roles to one
shared path.

### 3. Seed Findings Paths Through The Canonical Findings Contract Only

The initial `ReviewFindings` carrier must build `items_path` from a findings
seed role, not from the report-seed expression.

Required behavior:

- `items_path` typechecks directly as `ReviewFindingsJsonPath`;
- the generated placeholder path remains under `artifacts/work`;
- the initial carrier still sets `schema_version` to `ReviewFindings.v1`;
- no compatibility rule may treat a review-report-typed path as a valid
  findings seed.

The current literal `artifacts/work/review-findings-seed.json` is acceptable as
the deterministic placeholder path in this slice, provided it is attached to
an explicit findings-seed role rather than smuggled in during lowering.

### 4. Remove The Hidden Lowering Rewrite

Once seed roles are explicit, remove the current hidden repair path:

- retire `normalize_review_findings_seed_path=True` from review-loop seed
  lowering;
- stop building `initial_findings_expr.items_path` from the report expression
  in typecheck;
- retire or narrow `_allow_stdlib_review_findings_seed_path(...)` so it is no
  longer the mechanism that makes report and findings paths appear compatible;
- keep missing-file permissiveness bounded to generated seed-role fields in the
  loop seed step only.

This keeps the existing runtime contract unchanged while making the frontend
truthful about where the two seed values come from.

### 5. Update Fixtures To Exercise Mixed Roots Directly

The focused stdlib fixtures need to prove the selected contract, not the old
same-root shortcut.

Required fixture updates:

- the main valid review-loop fixture should declare a dedicated
  `ReviewReportPath` under `artifacts/review` for `review_report` and
  `last_review_report`;
- carried findings remain `ReviewFindings` with `items_path` on
  `ReviewFindingsJsonPath` under `artifacts/work`;
- the invalid findings fixture should use a review-report-rooted path for the
  wrong `items_path` field so the failure proves mixed-root aliasing is
  rejected, not just same-root name mismatch.

This keeps the shared gap narrow while producing the exact compile proof the
family parity slice needs before rerun.

## Acceptance Conditions

- imported review-loop specialization initializes `last_review_report` and
  `ReviewFindings.items_path` from distinct compiler-owned seed roles;
- `ReviewFindings.items_path` no longer depends on the report-seed expression
  anywhere in typecheck or lowering;
- lowering no longer relies on a hidden findings-path rewrite to repair the
  seed split;
- focused fixtures and tests prove review reports can remain under
  `artifacts/review` while findings stay under `artifacts/work`;
- the family-facing compile proof no longer fails with
  `record field items_path expected ReviewFindingsJsonPath but got WorkReportTarget`;
- no new public syntax, adapter, report parsing path, pointer-authority path,
  or runtime primitive is introduced.

## Verification Strategy

Use focused deterministic checks that exercise both the stdlib fixture and the
family-facing compile path:

- collect-only over the affected stdlib/build/migration test modules;
- phase-stdlib tests that assert:
  - distinct seed literals for report and findings roots;
  - no alias from findings seed to any report-seed source;
  - invalid mixed-root findings contracts fail predictably;
- build/lowering coverage that the generated seed roles are explicit in the
  lowered seed step rather than repaired later;
- migration compile coverage for `design_plan_impl_stack` proving the shared
  mixed-root path split no longer blocks the imported review-loop route.
