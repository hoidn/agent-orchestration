# Workflow Lisp Imported Review-Loop Module Path Alignment Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-imported-review-loop-module-path-alignment`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected shared prerequisite gap:

- add one bounded workflow-project source-root rule so workflow entrypoints
  under `workflows/examples/` can import sibling family modules under
  `workflows/library/` through the existing Workflow Lisp module graph;
- align the imported `std/phase.review-revise-loop` compatibility contract with
  family-owned review-report paths under `artifacts/review` while keeping
  carried findings on the bounded `std/phase.ReviewFindingsJsonPath` contract
  under `artifacts/work`;
- split review-report seeding from findings-path seeding inside the shared
  review-loop specialization path so the imported route no longer reuses one
  work-report expression for both;
- keep the fix bounded to shared frontend/typecheck/path-compatibility support
  plus the affected family module declarations and imports.

Out of scope for this slice:

- the full `design_plan_impl_stack` family parity rewrite;
- reusable-state orchestration, authored workflow defaults, command-result
  bundle-path ownership, or promotion-report policy;
- generic relative import syntax, arbitrary repo-wide source-root
  configuration, or runtime module loading;
- a shared stdlib `ReviewReportPath` type that would replace caller-owned
  family review-report types;
- findings-validator redesign, report parsing, pointer-as-authority behavior,
  inline shell/Python glue, or runtime-native effects.

This is a bounded implementation architecture for one selected gap only. It
does not replace the parent migration architecture, the umbrella Workflow Lisp
frontend contract, or the earlier family-parity slice.

## Problem Statement

The selected target design already depends on a shared route that the current
checkout does not yet provide:

- imported `.orc` review-loop usage should flow through one normal module graph,
  not an example-only import side channel;
- family wrappers under `workflows/examples/` should be able to import sibling
  library modules under `workflows/library/`;
- imported `std/phase.review-revise-loop` should remain compatible with family
  review reports stored under `artifacts/review`;
- carried findings should remain on the bounded `ReviewFindingsJsonPath`
  contract under `artifacts/work`.

The blocked family attempt exposed two concrete shared mismatches:

1. `_effective_source_roots(...)` currently infers the entry root from the
   entry file path. For
   `workflows/examples/design_plan_impl_review_stack_v2_call.orc`, that makes
   `workflows/examples` authoritative, so sibling imports from
   `workflows/library` fail with `module_not_found`.
2. The current review-loop specialization path still couples review-report and
   findings-path seeding:
   - `phase.py::PHASE_TARGET_SPECS` maps `review-report` and
     `last-review-report` under `artifacts/work`;
   - `_initial_review_loop_report_expr(...)` falls back to a work-report-shaped
     target when no caller-owned review-report field match is found;
   - `initial_findings_expr` then reuses that same report expression as
     `ReviewFindings.items_path`.

That coupling is incompatible with the selected design:

- `last_review_report` may be a family-owned relpath under `artifacts/review`;
- `ReviewFindings.items_path` must remain the canonical bounded findings path
  under `artifacts/work`.

The gap is therefore not another family-local migration task. The missing work
is one bounded shared frontend and stdlib-compatibility contract that makes
workflow-family modules visible and keeps review-report authority separate from
findings-path authority.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Minimum Migration Slice`
  - `Generic .orc Expansion Contract`
  - `Required Generic .orc Support`
  - `Review Loop Contract`
  - `Dependencies And Sequencing`
  - `Verification Strategy`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 4-6, 7.3-7.6, 8.9, 10-11, 16-18, 22-31, 45-57, 59-66, 74, 85,
    95, 103-105
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/prior-blocked-progress-report.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/prior-blocked-recovery-decision.json`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep imported `.orc` definitions flowing through one parser, module graph,
  typechecker, source-map, and lowering pipeline;
- keep `std/phase.review-revise-loop` on the imported specialization route
  rather than reopening a compiler-special review-loop branch;
- keep reports as views, typed bundles and artifact values as authority, and
  carried findings on the bounded `std/phase.ReviewFindings` contract;
- keep findings validation behind the existing explicit certified-adapter
  boundary; this slice must not add hidden shell/Python glue;
- keep family-owned review-report types caller-controlled rather than replacing
  them with a shared stdlib review-report type;
- keep frontend-owned logic under `orchestrator/workflow_lisp/` and avoid
  widening shared runtime ownership under `orchestrator/workflow/`;
- do not treat the empty `docs/steering.md` file as permission to broaden the
  slice.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-defworkflow-input-default-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-migration-promotion-parity-report-gate/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`

### Decisions Reused

- Reuse the imported-stdlib `review-revise-loop` route and thin
  specialization model from the generic effectful-composition slice; this gap
  must not add a second review-loop path.
- Reuse the bounded findings carrier from the structured-findings slice:
  `std/phase.ReviewFindings(schema_version, items_path)` remains the carried
  findings authority surface.
- Reuse the command-result slice's public/internal input split and managed
  write-root ownership; any generated findings-path or review-loop helper path
  remains compiler/runtime-owned.
- Reuse the family-parity slice's ownership split: library `.orc` phase
  workflows remain the reusable family surface and the example `.orc` workflow
  remains the thin boundary wrapper that imports them.
- Reuse the current module graph, export surfaces, built-in stdlib root, and
  source-map provenance machinery rather than inventing a second workflow
  import system.

### New Decisions In This Slice

- Treat the nearest ancestor `workflows/` directory as a bounded default
  project source root for workflow-entry compiles when no broader explicit
  project root is already configured.
- Require affected family modules to use stable module names relative to that
  shared `workflows/` root, for example `library/...` and `examples/...`.
- Accept caller-owned review-report path types for review-loop terminal
  `review_report` and `last_review_report` fields when they remain relpaths
  under `artifacts/review` with the expected existence contract.
- Keep findings-path compatibility strict: `ReviewFindings.items_path` remains
  the canonical `std/phase.ReviewFindingsJsonPath` contract under
  `artifacts/work`.
- Split review-loop seeding into two generated surfaces: one review-report seed
  for `last_review_report`, and one findings-path seed for
  `ReviewFindings.items_path`.

### Conflicts Or Revisions

The earlier family-parity slice assumed two prerequisites that the blocked run
showed were not yet true:

- example entrypoints could already import sibling family library modules
  through the normal module graph;
- the imported review loop could already consume family review-report path
  types without falling back to work-report paths.

This slice narrows and revises that assumption:

- the shared import-root and path-compatibility work moves into its own bounded
  prerequisite slice ahead of the family migration;
- the family slice remains valid, but it depends on this shared prerequisite
  before it can compile through the imported route.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, certified command-adapter policy,
and runtime execution ownership remain with their existing owners.

## Ownership Boundaries

This slice owns:

- bounded workflow-entry source-root inference and module-root selection in
  `orchestrator/workflow_lisp/compiler.py`;
- focused module-graph expectations and diagnostics for workflow-project
  imports in `orchestrator/workflow_lisp/modules.py` and
  `tests/test_workflow_lisp_modules.py`;
- family module naming alignment in the owned workflow-lisp migration surfaces
  under `workflows/examples/` and `workflows/library/` only to the extent
  needed to match the shared `workflows/` import root;
- review-loop report/findings path compatibility helpers in
  `orchestrator/workflow_lisp/contracts.py`, `orchestrator/workflow_lisp/typecheck.py`,
  and `orchestrator/workflow_lisp/phase.py`;
- shared review-loop seeding updates in `typecheck.py` so report-path and
  findings-path initialization no longer reuse one expression;
- focused compile and migration regression coverage proving the shared route.

This slice intentionally does not own:

- the full family-level parity rewrite, reusable-state orchestration, or input
  default restoration;
- findings-validator implementation policy beyond consuming the existing
  certified adapter boundary;
- runtime command execution, command bundle-path injection, or state-layout
  redesign;
- a repo-wide general import-root configuration surface for arbitrary
  non-workflow projects;
- a shared stdlib review-report type that would replace caller-owned family
  review-report contracts.

## Current Checkout Facts

The current checkout already contains the substrate this slice should reuse:

- `compiler.py::_effective_source_roots(...)` already merges an inferred entry
  root, the built-in stdlib root, and any explicit caller-provided roots while
  preserving first-match order.
- `modules.py::_resolve_import_path(...)` already resolves module names against
  a tuple of source roots and raises stable `module_not_found` diagnostics.
- `std/phase.orc` already exports the bounded findings carrier:
  `ReviewFindingsJsonPath` and `ReviewFindings`.
- the generic review-loop specialization route already exists in
  `typecheck.py`; this slice extends that route rather than replacing it with a
  new branch.

The same checkout also shows the exact missing behavior:

- entrypoint files under `workflows/examples/` currently infer
  `workflows/examples` as the project root, so imports of sibling library
  modules under `workflows/library/` fail unless extra roots are supplied;
- the family `.orc` files still declare bare module names such as
  `tracked_design_phase` and `design_plan_impl_review_stack_v2_call`, which do
  not describe a shared root under `workflows/`;
- `phase.py::PHASE_TARGET_SPECS` currently maps `review-report` and
  `last-review-report` to `artifacts/work`, not `artifacts/review`;
- `_initial_review_loop_report_expr(...)` can still fall back to a work-report
  target when it cannot find a caller-owned review-report-shaped field;
- the generated `initial_findings_expr` still reuses that report expression as
  `ReviewFindings.items_path`;
- `_allow_stdlib_review_findings_seed_path(...)` exists only as a narrow escape
  hatch for `items_path` compatibility and therefore confirms that the seed
  path split is not yet modeled cleanly.

This makes the slice feasible without a new runtime primitive. The missing work
is one bounded workflow-project import-root rule plus one bounded review-loop
path-compatibility correction.

## Proposed Architecture

### 1. Add One Bounded Workflow-Project Source Root

Keep the existing general import mechanism and add one narrow workflow-project
inference rule.

Implementation direction:

- when the compile entrypoint path is under a directory named `workflows`,
  include that nearest `workflows/` ancestor as the default project-local
  source root ahead of the inferred entry-file root;
- keep explicit `source_roots=` authoritative if the caller already supplied a
  broader project root; the new behavior fills the current CLI/default gap, it
  does not replace explicit configuration;
- keep the built-in stdlib root as a separate later source root exactly as
  today.

This preserves the existing module system while making repo-local workflow
families importable from example wrappers without bespoke CLI wiring.

### 2. Align Family Module Names To The Shared `workflows/` Root

The shared root is only useful if module identities match it.

Implementation direction:

- rename the affected family Workflow Lisp module declarations to stable names
  relative to `workflows/`, for example:
  - `examples/design_plan_impl_review_stack_v2_call`
  - `library/tracked_design_phase`
  - `library/tracked_plan_phase`
  - `library/design_plan_impl_implementation_phase`
- update family imports to use those module names through ordinary Workflow
  Lisp import syntax;
- keep this naming rule bounded to workflow-family `.orc` surfaces under
  `workflows/`; this slice does not introduce a new repo-wide naming policy for
  arbitrary fixture directories.

This yields a coherent compile-time story:

```text
workflows/  -> project source root
examples/... -> entry wrapper module
library/...  -> sibling reusable family modules
std/...      -> built-in stdlib root
```

### 3. Keep Review Reports Caller-Owned And Findings Canonical

Do not solve the family mismatch by inventing a second shared report/findings
surface or by forcing family review reports onto the current work-report
fallback.

Implementation direction:

- add one bounded structural compatibility helper for review-report paths:
  terminal `review_report` and `last_review_report` fields used by
  `review-revise-loop` may use caller-owned path types so long as they remain
  relpaths under `artifacts/review` with the expected terminal existence
  contract;
- keep `ReviewFindings.items_path` strict and canonical:
  it must still resolve to `std/phase.ReviewFindingsJsonPath` under
  `artifacts/work`;
- update review-loop contract validation to reject accidental conflation of
  review-report paths and findings paths rather than silently falling back to a
  work-report target.

This preserves the selected architecture from the parent design:

- reports remain family-local views;
- findings remain shared structured authority.

### 4. Split Review-Loop Report Seeding From Findings Seeding

The current specialization path uses one expression for both, which is the
direct cause of the blocked mismatch.

Implementation direction:

- keep `_initial_review_loop_report_expr(...)` responsible only for choosing a
  caller-compatible review-report value for `last_review_report`;
- introduce a separate generated findings-path seed helper that chooses an
  items-path value compatible with `std/phase.ReviewFindingsJsonPath`;
- add one dedicated frontend phase-target name for generated findings JSON
  allocation under `artifacts/work`, rather than reusing `execution-report` or
  `review-report`;
- keep the initial findings carrier generated as `ReviewFindings`, but source
  its `items_path` from the findings-path seed, not from a report expression.

This yields the bounded separation the parent design requires:

- `last_review_report` may remain `artifacts/review/...`;
- `findings.items_path` remains `artifacts/work/...`.

### 5. Narrow The Review-Report Fallback To Review Semantics

The existing fallback to an execution/work report target is only incidentally
correct for some demo surfaces. It is not correct for imported review loops
whose terminal report contract is review-specific.

Implementation direction:

- when no caller field provides a matching `last_review_report` value, fall
  back to a dedicated review-report phase target rather than to the generic
  execution-report target;
- correct the frontend phase-target mapping so review-report targets are typed
  and rooted under `artifacts/review` for review-loop use;
- keep execution/progress report targets on their existing `artifacts/work`
  surfaces.

This is a bounded correction to the shared phase-target vocabulary, not a
general redesign of phase layouts or state ownership.

### 6. Preserve Source Maps And Diagnostics Through The Shared Route

The shared-route fix is only useful if failures stay attributable.

Implementation direction:

- keep `module_not_found` as the user-facing diagnostic when a family import
  truly cannot resolve after the new `workflows/` root rule;
- keep generated review-loop path helpers source-mapped to the imported
  `std/phase.review-revise-loop` definition and the authored call site;
- add focused regression fixtures that prove the route is generic: module
  imports succeed because of the shared project-root rule, and path mismatches
  fail with stable diagnostics rather than hidden fallback conversions.

## Package And File Footprint

Likely owned implementation files:

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

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py`
- `orchestrator/workflow/`
- migration promotion tooling under `orchestrator/workflow_lisp/migration_parity.py`
- reusable-state and workflow-default parity modules

## Failure Modes And Diagnostics

- If a workflow entrypoint is outside any `workflows/` tree and does not supply
  explicit `source_roots`, the compiler keeps current behavior; this slice does
  not guess arbitrary broader roots.
- If two different configured roots would both resolve the same workflow-family
  module, the existing `module_import_ambiguous` diagnostic remains the
  authority.
- If a family review-loop result uses a report-path type outside
  `artifacts/review`, review-loop contract validation should fail with
  `review_loop_result_contract_invalid` rather than quietly routing to
  `artifacts/work`.
- If findings seeding again tries to use a review-report path, the compiler
  should fail with a stable type/contract diagnostic rather than accepting a
  structurally wrong path.

## Acceptance Conditions

- `workflows/examples/design_plan_impl_review_stack_v2_call.orc` can import the
  sibling family library `.orc` modules through the normal module graph without
  manual CLI source-root overrides.
- the family module declarations and imports align with the bounded
  `workflows/` project root and no longer rely on bare local-only module names.
- imported `std/phase.review-revise-loop` accepts family-owned terminal
  review-report path types under `artifacts/review`.
- the shared review-loop path seeding no longer uses one expression for both
  `last_review_report` and `ReviewFindings.items_path`.
- generated findings paths remain compatible with
  `std/phase.ReviewFindingsJsonPath` under `artifacts/work`.
- focused module, stdlib, and migration tests prove the shared prerequisite is
  satisfied before the broader `design_plan_impl_stack` parity rewrite resumes.

## Verification Strategy

Required checks for this slice should stay focused:

- collect-only over the module, stdlib review-loop, and key migration tests;
- focused module tests proving workflow-project root inference and sibling
  workflow-family imports;
- focused review-loop tests proving review-report/finding-path separation and
  stable diagnostics;
- compile and dry-run of the example `design_plan_impl_stack` `.orc` entry
  workflow through the existing extern manifests.

The broader parity report rerun belongs to the family slice that depends on
this prerequisite; this slice only needs to prove the shared compile route is
available.

## Sequencing

1. Land the bounded workflow-project source-root rule and family module naming
   alignment.
2. Land the shared review-loop path-compatibility and seeding split.
3. Prove the example wrapper can compile through imported family modules.
4. Resume the family-level `design_plan_impl_stack` parity implementation on
   top of this prerequisite.

## Bottom Line

The blocked migration attempt did not invalidate the parent parity design. It
showed that one shared prerequisite was still missing: imported family workflow
modules need a stable `workflows/` source root, and the imported review loop
must treat review-report paths and findings paths as different contracts.

This slice adds only that missing shared contract, so the family parity work can
continue without reopening the whole migration architecture.
