# Workflow Lisp Design/Plan/Impl Stack Review-Loop Parity Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-design-plan-impl-stack-review-loop-parity`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected migration-parity gap:

- convert the still single-pass library Workflow Lisp phase modules
  `workflows/library/tracked_design_phase.orc`,
  `workflows/library/tracked_plan_phase.orc`, and
  `workflows/library/design_plan_impl_implementation_phase.orc` into ordinary
  `.orc` review/revise workflows that consume the imported stdlib
  `review-revise-loop` route;
- route carried findings through the already-selected structured findings
  contract so revise/fix behavior consumes validated findings state instead of
  YAML-era extraction glue;
- add approved-only `resume-or-start` reuse in the thin example wrapper
  `workflows/examples/design_plan_impl_review_stack_v2_call.orc`;
- restore the YAML example workflow's public input defaults on that wrapper;
- refresh the focused migration tests and family parity evidence after the
  family actually consumes the generic review-loop, findings, reusable-state,
  and default slices.

Out of scope for this slice:

- implementing the generic imported-module/source-root, mixed-root
  report-versus-findings compatibility, review-loop specialization, carried
  findings validation, reusable-state sidecars, workflow-input defaults, or
  parity-report machinery themselves;
- changing runtime/spec ownership for `output_bundle`, managed write roots,
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, or `repeat_until`;
- editing the YAML baseline workflows, adding new runtime-native effects, or
  reintroducing inline shell/Python semantic glue;
- widening the promoted public boundary with new semantic outputs for findings
  or reusable-state summaries;
- unrelated workflow families, backlog state, or general Workflow Lisp design.

This is a bounded implementation architecture for one workflow family. It
consumes prior parity slices; it does not replace them.

## Problem Statement

The selected target design already narrowed the remaining parity work for the
`design_plan_impl_stack` family:

- ordinary `.orc` review/revise behavior must replace the YAML family's
  handwritten `repeat_until` plus inline findings extraction;
- carried findings must become validated structured state;
- approved reusable phase state must be handled through `resume-or-start`;
- the `.orc` entry workflow must preserve the YAML boundary defaults and feed
  the promotion report with non-regressive evidence.

The current checkout still falls short at the family surface:

1. The library `.orc` phases remain single-pass:
   - `tracked_design_phase.orc` drafts once, reviews once, and returns the
     first decision;
   - `tracked_plan_phase.orc` drafts once, reviews once, and returns the first
     decision;
   - `design_plan_impl_implementation_phase.orc` executes once, reviews once,
     and returns the first decision.
2. None of those `.orc` phases currently consume structured carried findings or
   route revise/fix behavior through the imported stdlib loop.
3. The thin example wrapper still just calls the three phases directly and
   still requires every public input explicitly. It does not yet add
   `resume-or-start` reuse or authored defaults.
4. The YAML baseline still owns the real iterative behavior:
   - bounded `repeat_until` review/revise loops;
   - design-block failure;
   - carried open-findings extraction through inline Python command glue.
5. The promotion report already isolates the unresolved debt:
   `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
   still records `non_regressive=false` and still lists
   `full YAML review-revise loop with carried findings extraction` as the
   unresolved deprecated mechanic.

The important boundary change since the earlier blocked attempt is that the
shared prerequisites are now their own slices:

- imported example-to-library module resolution under the shared `workflows/`
  root;
- mixed-root review-report versus findings-path compatibility;
- generic stdlib review-loop lowering;
- structured findings validation;
- reusable-state validation;
- authored Workflow Lisp defaults;
- migration parity reporting.

The missing work is now the family-level integration that consumes those
surfaces in the library phases and wrapper without reopening them.

## Design Constraints

This slice must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Required Generic .orc Support`
  - `Review Loop Contract`
  - `Reusable State Contract`
  - `Workflow Input Defaults`
  - `Dependencies And Sequencing`
  - `Evidence And Implementation Boundaries`
  - `Success Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 10, 11, 14, 16-18, 22-31, 50-58, 74, 85, 89-91, 95, 103-105
- `docs/design/workflow_command_adapter_contract.md`
  - authoritative because this slice consumes command-adapter-backed findings
    and reusable-state seams and must not recreate hidden semantic glue
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `docs/steering.md`

Guardrails:

- keep `review-revise-loop` on the imported stdlib/generic composition route,
  not on a compiler-special family branch;
- keep findings authoritative as structured state and reports as views;
- keep reusable-state validation behind the selected `resume-or-start` and
  certified adapter contracts;
- keep the example wrapper thin and the library phases reusable;
- keep compiler-managed write roots and other generated paths off the promoted
  public boundary;
- keep existing extern names and prompt asset layout unless a narrow family
  incompatibility forces a change;
- if a family-local helper still needs an executable validator/failure step, it
  must be a certified adapter or existing runtime surface consistent with the
  command-adapter contract, never inline Python or shell glue;
- do not let the empty `docs/steering.md` file broaden the work.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-defworkflow-input-default-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-imported-review-loop-module-path-alignment/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-migration-promotion-parity-report-gate/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`

### Decisions Reused

- Reuse the shared `workflows/` source-root and stable module-name route from
  the imported-review-loop module-path slice; this family should continue using
  `examples/...` and `library/...` modules through the ordinary Workflow Lisp
  import system.
- Reuse the mixed-root review-loop compatibility rule: family-owned review
  reports stay under `artifacts/review`, while carried findings remain on
  `std/phase.ReviewFindingsJsonPath` under `artifacts/work`.
- Reuse the imported stdlib `review-revise-loop` surface and thin
  specialization model from the generic effectful-composition slice; this
  family does not introduce a second loop path.
- Reuse the `ReviewFindings(schema_version, items_path)` carrier plus the
  `validate_review_findings_v1` adapter route from the structured findings
  slice.
- Reuse approved-only reusable-state validation through `resume-or-start` and
  `ReusablePhaseState.v1` sidecars from the reusable-state slice.
- Reuse authored `defworkflow` defaults from the input-default slice and the
  public/internal input ownership rule from the command-result slice.
- Reuse the promotion-report command and JSON report surface from the
  migration-parity gate slice.

### New Decisions In This Slice

- Keep the reusable family surface in the library Workflow Lisp modules and
  keep the example workflow as the thin boundary wrapper that imports and calls
  them.
- Add family-local internal review-loop state and terminal-result contracts per
  phase so the family can consume the stdlib loop without widening its public
  outputs.
- Keep structured findings internal to phase loop state and revise/fix inputs;
  do not surface findings on the example workflow outputs.
- Apply `resume-or-start` around the three phase calls in the example wrapper
  and treat only approved terminal results as reusable.
- If the current `resume-or-start` lowering still needs explicit canonical
  state-bundle handles, keep those handles as family-local plumbing rather than
  promoted user-facing outputs.
- Keep the current providers/prompts manifest names and the empty
  `design_plan_impl_stack.commands.json` file unless a concrete family
  incompatibility forces a narrow update.

### Conflicts Or Revisions

The checked-in iteration-0 work-item artifacts still describe the earlier
shared prerequisite gap
`workflow-lisp-imported-review-loop-module-path-alignment`. This slice
supersedes that older selection because the current selector now points at the
family parity gap after the shared prerequisite slices were split out.

This slice also explicitly revises any earlier family-local recovery direction
that kept parity entirely inside the example module. That deferral made sense
only while example-to-library imports and mixed-root report/findings handling
were still unproven. The reviewed prerequisite slices now own those concerns,
and the current selector explicitly identifies the remaining debt as the still
single-pass library phases plus the thin wrapper.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, and runtime execution ownership
remain with their existing owners.

## Ownership Boundaries

This slice owns:

- the family-level parity rewrite in:
  - `workflows/library/tracked_design_phase.orc`
  - `workflows/library/tracked_plan_phase.orc`
  - `workflows/library/design_plan_impl_implementation_phase.orc`
  - `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- family-local internal review-loop result contracts and terminal routing back
  to the current family output records;
- any narrow family-local extern-manifest adjustments under
  `workflows/examples/inputs/workflow_lisp_migrations/` if they are required to
  keep the existing provider/prompt names coherent;
- focused tests and parity-report refresh proving this family now consumes the
  already-landed generic review-loop, findings, reusable-state, and default
  surfaces.

This slice intentionally does not own:

- generic `std/phase.review-revise-loop` specialization, shared compiler
  lowering, or module-resolution behavior;
- structured findings validator implementation, reusable-state adapters, or
  migration-parity command logic;
- new runtime-native effects, spec deltas, or YAML baseline edits;
- unrelated workflow families, backlog state, or promotion policy beyond
  rerunning the existing command/report surface.

## Current Checkout Facts

The current checkout already contains the substrate this slice should reuse:

- the example Workflow Lisp wrapper already imports the three library modules
  using stable `library/...` module names;
- the promotion report already records compile and dry-run evidence for
  `workflows/examples/design_plan_impl_review_stack_v2_call.orc`;
- the providers manifest already declares all nine family providers:
  design draft/review/revise, plan draft/review/revise, and implementation
  execute/review/fix;
- the prompts manifest already declares the matching prompt assets;
- the family command-boundaries manifest is currently `{}`, which means this
  family does not yet rely on extra manifest-declared adapters beyond the
  shared compiler-installed ones.

The same checkout also shows the exact remaining family gap:

- the three library `.orc` phases still lower to one draft/execute pass and one
  review pass only;
- none of those `.orc` phases thread structured findings into revise/fix
  behavior;
- the example wrapper still exposes seven required public inputs and plain
  phase calls, with no authored defaults and no `resume-or-start`;
- the YAML baseline phases still own the bounded `repeat_until` review loops
  and the inline `ExtractOpen*Findings` command steps;
- the parity report remains regressive only because the full YAML review/revise
  mechanic has not yet moved into ordinary `.orc` composition;
- the progress ledger for this drain is still empty, so nothing later in repo
  state supersedes the selector rationale.

This makes the slice feasible without new runtime or spec work. The missing
component is the family integration that rewrites the library phases and thin
wrapper to consume the already-selected generic surfaces.

## Proposed Architecture

### 1. Keep The Library Phase Modules As The Reusable Parity Surface

Rewrite the three library `.orc` phase workflows in place:

- `library/tracked_design_phase`
- `library/tracked_plan_phase`
- `library/design_plan_impl_implementation_phase`

Implementation direction:

- keep their module names stable under the shared `workflows/` source root;
- keep the example workflow importing and calling them rather than cloning
  phase logic back into the example module;
- preserve their current user-facing phase output record names so the example
  wrapper and parity report can stay stable.

This keeps the family aligned with the selector: the remaining debt is in the
single-pass library phases, not in import plumbing or example-local copy code.

### 2. Add Family-Local Internal Loop Contracts Before Public Projection

Each library phase should introduce its own internal review-loop contracts that
match the imported stdlib loop surface while preserving family-local path
types:

- review reports and last-review reports use the family path types rooted under
  `artifacts/review`;
- findings use `std/phase.ReviewFindings`, with `items_path` rooted under
  `artifacts/work`;
- evidence artifact identities such as `design_path`, `plan_path`, or
  `execution_report_path` stay carried from authoritative prior phase state or
  phase step outputs, not from review-provider-authored replacement paths.

The family should not try to feed its existing outward output records directly
into `review-revise-loop`. Instead, each phase should:

- define internal completed/input records as needed for the loop call;
- define an internal terminal union that can represent approved, blocked, and
  exhausted outcomes in the vocabulary expected by the imported stdlib route;
- project only approved terminal results back onto the existing outward phase
  output record.

If the current stdlib route still requires a `BLOCKED` variant for plan or
implementation even though the family's providers currently use only
`APPROVE/REVISE`, keep that variant internal and route it as explicit
non-success. Do not reopen the generic stdlib contract in this family slice.

### 3. Replace Single-Pass Review With Imported Stdlib Review Loops

Each phase should keep its authoritative production step, then route review and
revise/fix behavior through the imported stdlib loop:

- design phase:
  - draft once;
  - run imported `review-revise-loop` with review and revise hooks bound to
    `providers.design.review`, `providers.design.revise`,
    `prompts.design.review`, and `prompts.design.revise`;
  - carry validated findings into each revise iteration;
  - keep the current design-block behavior as an explicit non-success route.
- plan phase:
  - draft once;
  - run imported `review-revise-loop` with the plan review/revise provider and
    prompt bindings;
  - carry validated findings into each revise iteration;
  - treat exhaustion or any non-approved terminal result as non-success rather
    than exporting a successful `REVISE` surface.
- implementation phase:
  - execute once;
  - run imported `review-revise-loop` with implementation review/fix bindings;
  - carry validated findings into each fix iteration;
  - keep the execution report as carried authoritative evidence while review
    judges it.

This rewrite replaces the YAML family's inline `ExtractOpen*Findings` command
glue with structured findings transport. No new family-local inline Python or
shell should be introduced.

### 4. Keep Structured Findings Internal And Remove Extraction Glue

The family should consume the structured findings slice exactly where the YAML
baseline currently relies on inline extraction:

- review procedures return validated findings through the bounded
  `ReviewFindings` carrier;
- revise/fix procedures receive that carrier as structured input;
- phase-local loop state carries findings between iterations and across resume;
- the old YAML-style `open_findings.json` extraction/republication pattern
  disappears from the `.orc` family.

Findings remain internal phase state. The public example workflow outputs stay
limited to the current design/plan/implementation artifact paths and scalar
review-decision fields.

### 5. Route Terminal Outcomes Back To The Current Family Boundary

After the imported stdlib loop returns, each phase should use ordinary `.orc`
control flow to preserve the family's current outward behavior:

- `APPROVED` projects back onto the existing outward phase output record and
  current public report-path fields;
- design-blocked review remains a deterministic phase failure, consistent with
  the YAML baseline's `FailBlockedDesign` route;
- plan and implementation exhaustion remain deterministic non-success outcomes
  rather than exporting a successful `REVISE` result;
- successful outward phase outputs remain YAML-compatible and should continue
  to expose the current path/decision fields even if the only successful
  decision is now `APPROVE`.

This is family-local routing logic. It must use ordinary `.orc` statements or
existing certified helper seams, not ad hoc command glue.

### 6. Apply Approved-Only `resume-or-start` At The Thin Wrapper Boundary

The example wrapper should own phase reuse, not the library phase bodies.

Implementation direction:

- wrap the design, plan, and implementation phase calls in `resume-or-start`;
- treat only approved terminal phase results as reusable for this family;
- keep resumed and fresh branches normalized to the same outward phase output
  records that the wrapper already exports.

The wrapper will also need canonical phase-state handles for those
`resume-or-start` calls. This slice should not reopen reusable-state design to
invent a new family-specific mechanism. Use the already-selected reusable-state
surface:

- if the current lowering can consume existing deterministic handle refs, use
  that path directly;
- if the current lowering still requires explicit canonical bundle handle
  inputs, keep them as family-local plumbing with deterministic defaults rather
  than promoted user-facing outputs.

Either way, reusable-state handles are implementation plumbing. They are not
new semantic outputs for the promoted workflow family.

### 7. Restore YAML-Compatible Authored Defaults On The Example Entrypoint

The example `.orc` wrapper should restore the YAML example's current authored
defaults for these seven public inputs:

- `brief_path`
- `design_target_path`
- `design_review_report_target_path`
- `plan_target_path`
- `plan_review_report_target_path`
- `execution_report_target_path`
- `implementation_review_report_target_path`

Use the same literal defaults currently declared in
`workflows/examples/design_plan_impl_review_stack_v2_call.yaml`.

This slice should not push defaults down into the library phase modules. The
wrapper owns boundary parity; the library phases stay reusable and explicit.

### 8. Keep Extern Manifests Stable And Refresh Promotion Evidence

The current family manifests already declare the needed provider and prompt
names, and the command-boundaries manifest is empty.

Implementation rule:

- preserve the current provider/prompt names unless an actual mismatch appears
  during family integration;
- do not add family-local command-boundary entries just to recover review-loop
  behavior that the structured findings and reusable-state slices already own;
- update focused migration tests so they prove:
  - the library phases are no longer single-pass;
  - revise/fix receives structured findings;
  - approved-only phase reuse flows through the wrapper;
  - defaulted wrapper inputs allow dry-run without explicit input flags;
- rerun `orchestrator migration-parity` to refresh the family report.

After this slice lands, the refreshed
`design_plan_impl_stack.json` report should no longer list
`full YAML review-revise loop with carried findings extraction` as the open
deprecated mechanic. If `non_regressive` remains `false`, the remaining blocker
must be another explicit evidence axis named by the existing promotion report.

## Proposed Code Footprint

Primary files owned by this slice:

- `workflows/library/tracked_design_phase.orc`
- `workflows/library/tracked_plan_phase.orc`
- `workflows/library/design_plan_impl_implementation_phase.orc`
- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_neurips_plan_gate_recovery.py`
- `tests/test_workflow_lisp_migration_parity.py`

Expected to remain unchanged unless family wiring proves otherwise:

- `workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json`

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/adapters/validate_review_findings_v1.py`
- `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- `orchestrator/workflow_lisp/adapters/write_reusable_phase_state_v1.py`
- `orchestrator/workflow_lisp/migration_parity.py`
- shared runtime/state handling under `orchestrator/workflow/`

## Dependency And Sequencing

This family slice should consume earlier parity work; it should not silently
reimplement it.

Required prerequisite slices:

1. `workflow-lisp-imported-review-loop-module-path-alignment`
2. `workflow-lisp-review-loop-generic-effectful-composition`
3. `workflow-lisp-review-findings-structured-dataflow`
4. `workflow-lisp-resume-or-start-reusable-state-validation`
5. `workflow-lisp-defworkflow-input-default-parity`
6. `workflow-lisp-command-result-compiler-owned-bundle-paths`
7. `workflow-lisp-migration-promotion-parity-report-gate`

Readiness gate:

- the imported example-to-library module route must already compile;
- mixed-root review-report and findings compatibility must already be accepted
  by the shared review-loop path;
- if the family still hits those shared failures, stop and revise the
  prerequisite slice rather than papering over it in family-local code.

Recommended execution order:

1. Rewrite the three library phase modules around imported stdlib loops and
   family-local internal terminal routing.
2. Add approved-only `resume-or-start` plus authored defaults in the example
   wrapper, including any family-local canonical-state handle plumbing the
   current reusable-state surface still requires.
3. Update focused stdlib, recovery, migration, and parity-report tests.
4. Compile and dry-run the example wrapper with defaults.
5. Refresh the promotion report through the existing parity command.

## Acceptance Conditions

- the three library `.orc` phase workflows no longer perform single-pass
  review-only behavior;
- imported stdlib `review-revise-loop` owns the design, plan, and
  implementation revise/fix flow for this family;
- structured findings flow into revise/fix without YAML-style inline
  extraction glue;
- approved-only phase reuse is applied at the example wrapper boundary through
  `resume-or-start`;
- the example wrapper can dry-run with the YAML-compatible public defaults
  instead of requiring seven explicit input flags;
- the public example outputs remain aligned with the current YAML boundary;
- the refreshed family parity report no longer names the unresolved full YAML
  review/revise mechanic as open debt, or else any remaining blocker is a
  different explicit evidence axis owned outside this slice.

## Verification Strategy

Use the deterministic commands recorded in:

`state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`

They should cover:

- collect-only over the focused stdlib, recovery, migration, and parity test
  modules;
- focused stdlib coverage for review-loop, findings, and exhaustion behavior;
- focused reusable-state coverage for `resume-or-start`;
- focused `design_plan_impl_stack` migration tests;
- compile of the example `.orc` entry workflow with the current extern
  manifests;
- dry-run of the example `.orc` entry workflow without explicit public inputs
  so authored defaults are exercised;
- rerunning the migration-parity command so the family evidence is refreshed
  through the existing promotion gate.

## Summary

The remaining `design_plan_impl_stack` parity gap is no longer generic frontend
design. The shared import, review-loop, findings, reusable-state, default, and
promotion surfaces already have their own bounded slices. This slice should use
them to rewrite the three library phases plus the thin example wrapper so the
family stops depending on YAML review/revise loops and can be judged by the
existing parity report on actual family behavior.
