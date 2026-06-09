# Workflow Lisp Design/Plan/Impl Stack Parity Surface Recovery Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-design-plan-impl-stack-parity-surface-recovery`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected parity-surface recovery gap:

- recover the `design_plan_impl_stack` family parity surface so
  `deprecated_yaml_mechanics` ownership and computed `non_regressive` status
  reflect the completed family parity evidence instead of stale manifest
  metadata;
- keep the checked-in family manifest, focused parity assertions, canonical
  parity JSON report, derived markdown, and aggregate parity index in one
  truthful state;
- reconcile any checked-in summary doc that still contradicts the regenerated
  canonical report for this family.

Out of scope for this slice:

- rewriting `workflows/examples/design_plan_impl_review_stack_v2_call.orc`,
  imported stdlib review-loop lowering, structured findings transport,
  `resume-or-start`, workflow defaults, or any other Workflow Lisp/runtime
  behavior that the completed family slice already owned;
- redesigning `orchestrator/workflow_lisp/migration_parity.py` or the
  migration-report schema unless a narrow defect in the existing parity tool
  prevents truthful regeneration;
- editing `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`, backlog
  queues, or `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`;
- inventing new command adapters, runtime-native effects, report parsing, or
  pointer-authority exceptions.

This is a bounded implementation architecture for one family parity-surface
recovery gap only. It does not replace the parent migration architecture or
reopen the completed family behavior slice.

## Problem Statement

The selected target design already defines the promotion contract clearly:

- `non_regressive` is computed by the migration-parity tool from evidence;
- canonical JSON parity reports are authority and markdown/index views are
  derived from them;
- deprecated YAML mechanics may remain in parity metadata only when they name
  a concrete replacement or an accepted waiver; unresolved stale mechanics keep
  a candidate regressive.

The current checkout still violates that contract in one narrow but decisive
way:

1. `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
   shows `compile`, `shared_validation`, `dry_run`, `smoke_or_integration`,
   `output_contract_parity`, `terminal_state_parity`, `artifact_parity`, and
   `resume_parity` all passing, and its required compile artifacts are all
   `pass`.
2. The same report still computes `non_regressive=false` because
   `deprecated_yaml_mechanics` carries the unresolved entry
   `full YAML review-revise loop with carried findings extraction`.
3. `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
   still authors that same mechanic without a replacement, so the current
   `compute_non_regressive(...)` contract correctly keeps the family
   regressive.
4. `tests/test_workflow_lisp_migration_parity.py` currently asserts that the
   stale unresolved mechanic remains present, so the checked-in regression
   surface is aligned to stale metadata instead of the completed family proof.
5. `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json` records both
   `workflow-lisp-design-plan-impl-stack-review-loop-parity` and
   `workflow-lisp-design-plan-impl-stack-parity-evidence-refresh` as completed,
   but those run-state events are only historical evidence and cannot override
   the checked-in manifest/report contract.

The gap is therefore not “rerun all family implementation work.” The gap is to
make the parity surface truthful again: either the stale YAML-loop mechanic is
marked replaced by the completed `.orc` family route and the report becomes
non-regressive, or a new real blocker is named explicitly instead.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Dependencies And Sequencing`
  - `Migration Evidence Layer`
  - `Evidence And Implementation Boundaries`
  - `Success Criteria`
  - `Stop / Revise Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 2.2, 16-18, 45-48, 59-66, 74, 95, 103-105
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`
- `docs/steering.md`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-parity-evidence-refresh/implementation_architecture.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/prior-blocked-gap-architecture.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/prior-blocked-gap-execution-plan.md`

The slice must preserve these guardrails:

- keep `orchestrator/workflow_lisp/migration_parity.py` and the CLI command
  `python -m orchestrator migration-parity` as the only authority for
  `non_regressive` computation and report regeneration;
- keep canonical parity JSON authoritative and treat markdown, aggregate index,
  historical execution summaries, run-state notes, and drain narratives as
  derived views;
- keep the current family-specific evidence selectors and explicit dry-run
  route unless the audit shows they are themselves stale;
- keep command-boundary and structured-result rules from
  `docs/design/workflow_command_adapter_contract.md` authoritative even though
  this slice should not add or redesign command adapters;
- do not treat the empty `docs/steering.md` file as permission to broaden the
  slice.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defschema-reusable-field-schemas/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defun-pure-helper-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-cli-artifact-emission/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-required-lints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/generic-collection-types/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/if-conditionals-pure-proven-values/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/rich-semantic-effect-graph/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/semantic-workflow-ir-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-parity-evidence-refresh/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-promoted-entry-hidden-reusable-call-binding/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the migration-parity tool as the single authority for report execution,
  JSON report generation, markdown rendering, aggregate index generation, and
  `non_regressive` computation.
- Reuse the completed family parity slice as the owner of actual
  `design_plan_impl_stack` Workflow Lisp behavior; this slice only consumes the
  already-completed evidence route.
- Reuse the report/index derived-view rule from the earlier evidence-refresh
  slice; no hand-authored parity outcome is allowed.
- Reuse the selected prerequisite slices for report/findings split, imported
  review-loop resume identity, promoted-entry hidden binding, reusable-state
  validation, and command-result bundle ownership without reopening them.
- Reuse the current manifest-backed family evidence selectors and explicit
  dry-run invocation unless the audit proves they are untruthful.

### New Decisions In This Slice

- Treat `deprecated_yaml_mechanics` for `design_plan_impl_stack` as part of the
  family promotion contract, not as commentary. If the family proof is
  complete, the stale unresolved YAML-loop mechanic must be removed or marked
  replaced in the manifest before report regeneration.
- Keep the family’s evidence commands stable unless the audit shows a real
  mismatch. This slice is about stale parity-surface ownership, not about
  rediscovering a new proof route.
- Make the focused parity assertion in
  `tests/test_workflow_lisp_migration_parity.py` check the truthful post-repair
  family state: no stale unresolved YAML-loop mechanic remains, and the family
  evidence selectors still point at the concrete `design_plan_impl_stack`
  proofs.
- If audit shows a real remaining blocker, name that blocker explicitly in the
  manifest/report instead of preserving the stale
  `full YAML review-revise loop with carried findings extraction` entry.

### Conflicts Or Revisions

The earlier parity-evidence-refresh slice owned broader manifest/report/index
refresh after family work completed. This new slice narrows the remaining gap:

- the family-specific selectors and explicit dry-run route already exist and do
  not need to be redesigned by default;
- the remaining defect is the stale unresolved deprecated mechanic and the test
  surface that still expects it;
- run-state completion markers remain historical context only and cannot
  override the checked-in manifest or canonical report.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, family review-loop behavior, and
runtime execution ownership remain with their existing owners.

## Ownership Boundaries

This slice owns:

- the `design_plan_impl_stack` entry in
  `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`,
  specifically its `deprecated_yaml_mechanics` contract and any narrowly
  required explanatory replacement text;
- focused parity assertions in `tests/test_workflow_lisp_migration_parity.py`;
- regenerated family parity artifacts:
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md`
  - `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
  only if its family status text contradicts the regenerated canonical report.

This slice intentionally does not own:

- `workflows/examples/design_plan_impl_review_stack_v2_call.orc` or the
  library `.orc` family modules;
- generic parity-engine semantics or CLI surface, except for a narrow defect
  that prevents truthful report recomputation;
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`,
  `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`, backlog manifests,
  or queue state;
- new adapters, new scripts, runtime-native effects, or Workflow Lisp
  semantics.

## Current Checkout Facts

The current checkout already contains the substrate this slice should reuse:

- `orchestrator/workflow_lisp/migration_parity.py` already loads the checked-in
  manifest, runs deterministic evidence commands, writes per-family JSON
  reports and derived markdown/index views, and computes `non_regressive`.
- the `design_plan_impl_stack` manifest entry already points its behavioral
  evidence roles at family-specific selectors rather than at the old
  `review_loop_parity_fixture` placeholder.
- the family parity report generated at `2026-06-03T12:14:57Z` already shows
  all required evidence roles and required compile artifacts passing.
- `compute_non_regressive(...)` returns `false` whenever a deprecated YAML
  mechanic has neither `replacement` nor valid `waiver`.
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is still empty, so
  no later ledger event supersedes the selected ordering.

The same checkout also shows the exact stale parity surface:

- the manifest still authors the unresolved mechanic
  `full YAML review-revise loop with carried findings extraction`;
- the canonical family JSON report, derived markdown, and aggregate index still
  project `non_regressive=false` because of that single unresolved mechanic;
- `tests/test_workflow_lisp_migration_parity.py` still asserts that the stale
  unresolved mechanic remains present;
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
  still reports the family as regressive.

This makes the slice feasible without reopening generic Workflow Lisp behavior:
the parity tool already works, the family proof commands already pass, and the
remaining defect is stale parity-surface metadata.

## Feasibility Proof

This slice depends on one narrow claim: replacing or removing the stale
unresolved deprecated mechanic is sufficient to change the family report from
regressive to non-regressive, unless the audit reveals another truthful
blocker.

That claim is already supported by the current checkout:

- the generated family report shows every required evidence role passing;
- the report shows every required compile artifact passing;
- `compute_non_regressive(...)` checks unresolved deprecated mechanics only
  after those evidence and artifact gates have already passed;
- the current family report contains exactly one unresolved deprecated
  mechanic entry.

Therefore:

- if the audit confirms that the completed family parity evidence really does
  replace the old YAML review-revise mechanic, then normalizing that manifest
  entry and regenerating the report is enough to make `non_regressive=true`;
- if the audit reveals a different real blocker, this slice must record that
  blocker explicitly rather than fabricate success.

## Proposed Architecture

### 1. Audit The Stale-Mechanic Ownership Before Editing The Manifest

Start with one bounded audit over:

- the current `design_plan_impl_stack` manifest entry;
- the current canonical family parity JSON report;
- the focused parity tests;
- the historical completion markers in `run_state.json`.

The audit outcome must answer only two questions:

1. Do the current family proof commands and current report already demonstrate
   that the `.orc` family replaced the old YAML review-revise mechanic?
2. Is the stale unresolved deprecated mechanic the only remaining reason the
   family report is regressive?

If the answer to both is yes, this slice proceeds with manifest normalization.
If not, this slice records the real blocker and keeps the report truthful.

### 2. Normalize The `design_plan_impl_stack` Deprecated-Mechanics Contract

The family manifest entry remains the source of truth for what deprecated YAML
mechanics still matter to promotion.

For `design_plan_impl_stack`, this slice should:

- keep `manual markdown parity summary -> machine-readable parity JSON report`
  unchanged;
- replace the stale unresolved
  `full YAML review-revise loop with carried findings extraction` entry with a
  concrete replacement that points at the completed `.orc` family route, or
  remove the entry entirely if the replacement would be redundant;
- if the audit shows a different real blocker, encode that blocker explicitly
  instead of preserving the stale YAML-loop wording.

Recommended normalization:

- keep the mechanic named, but add a replacement string so parity metadata
  preserves migration lineage while no longer forcing a false regression;
- the replacement should reference the implemented `.orc` parity route in
  generic terms, not a transient run id or ad hoc prose.

### 3. Align The Focused Parity Assertion To The Truthful Family Route

`tests/test_workflow_lisp_migration_parity.py` should verify the truthful
checked-in family parity contract after this repair:

- the family behavioral evidence selectors remain family-specific;
- the explicit dry-run route stays consistent with the actual wrapper boundary;
- the stale YAML-loop mechanic is no longer unresolved.

This slice should not broaden that test into a second parity engine. It should
only assert the bounded contract this slice owns.

If a rename of the focused test improves clarity because the old name still
describes stale behavior, that rename is in scope.

### 4. Regenerate Canonical Family Parity Artifacts Through The Existing CLI

After manifest and test alignment, rerun:

`python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity --target design_plan_impl_stack`

This CLI rerun is the only allowed mechanism for refreshing:

- `design_plan_impl_stack.json`
- `design_plan_impl_stack.md`
- the aggregate `index.json`

Do not hand-edit generated parity artifacts.

Expected branches:

- if the stale unresolved mechanic was the only blocker, the recomputed report
  becomes non-regressive;
- if a new truthful blocker exists, the recomputed report remains regressive
  but now names the real blocker instead of the stale YAML-loop mechanic.

### 5. Reconcile Derived Summary Docs Only After Report Regeneration

`docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md` is a
derived narrative surface. Update it only if its current family wording
contradicts the regenerated canonical report.

The summary doc should stay high-level:

- reflect the report’s family status;
- reflect the report’s blocker rationale if the family remains regressive;
- never claim promotion or parity status that the canonical report does not.

## Verification Strategy

Verification for this slice stays narrow:

- collect the focused parity and family-evidence tests;
- run the focused parity-manifest test;
- rerun the focused family evidence bundle that the manifest depends on;
- rerun the family-only migration-parity CLI;
- assert that the regenerated family report and aggregate index are internally
  consistent and that the stale YAML-loop mechanic is no longer unresolved.

The exact deterministic command list for implementation belongs in:

`state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/9/design-gap-architect/check_commands.json`

## Acceptance Conditions

- the `design_plan_impl_stack` manifest entry no longer carries the stale
  unresolved `full YAML review-revise loop with carried findings extraction`
  mechanic;
- the focused parity assertion in `tests/test_workflow_lisp_migration_parity.py`
  matches the truthful post-repair family contract;
- the canonical family JSON report is regenerated through the migration-parity
  CLI rather than hand-edited;
- the derived markdown and aggregate index agree with the regenerated JSON
  report;
- if the family report remains regressive, it names a real remaining blocker
  rather than the stale YAML-loop mechanic;
- no run-state edits, progress-ledger edits, Workflow Lisp behavior rewrites,
  adapter additions, or unrelated frontend/runtime refactors are introduced.
