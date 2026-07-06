# Design Delta Implementation-Phase Boundary Authority Registry Repair Architecture

Status: authored implementation architecture (prerequisite gap record; 2026-07-06)
Design gap id: `workflow-lisp-design-delta-implementation-phase-boundary-authority-registry-repair`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Sections 12.1, 13.4)
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`
Shared owner-lane authority: `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`

## Purpose

This gap is the declared prerequisite for
`workflow-lisp-design-delta-compatibility-carrier-retirement`. That dependent
slice completed its approved carrier-retirement work (run-state carrier
retired from `std/drain` result, terminal, and loop-state contracts; shared
lowering plumbing removed; bridge lane collapsed; checked resume-plumbing and
parity manifests realigned) and then stopped `BLOCKED` with recovery route
`PREREQUISITE_GAP_REQUIRED` waiting on this exact gap id, because the
remaining red check was not a drain-carrier regression but unrelated
`implementation_phase` boundary-authority registry drift outside its approved
slice.

The recorded blocker evidence from the dependent slice's blocked run:

- the parent-drain direct compile
  (`python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain`
  with the checked provider/prompt/command-boundary inputs) and the
  feasibility selector
  (`pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q`)
  both stop in the compile gate with the same validation error:
  `[workflow_boundary_authority_unclassified] stale boundary authority
  registry row does not match compiled evidence` against
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`;
- the stale row is a `managed_write_root` row for
  `lisp_frontend_design_delta/implementation_phase::implementation-phase`
  whose generated write-root field name is keyed to a superseded
  review-revise-loop proc shape on the `match_attempt -> completed -> review
  -> approve -> validated_findings` route
  (`...validate_review_findings_v1__result_bundle`); and
- that row belongs to the `implementation_phase` boundary-authority registry
  surface, which was outside the approved compatibility-carrier retirement
  slice.

The declared prerequisite scope, quoted from the recovery ledger:

> Repair or rebaseline
> workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json
> for the current lisp_frontend_design_delta/implementation_phase compiled
> evidence, then rerun the parent-drain compile gate and the focused
> feasibility selector that currently stop at the stale registry row.

## Governing Contract

Per the command-adapter contract's checked-manifest discipline, the
boundary-authority registry is a fail-closed checked direct input on the
parent-drain build route: its gate
(`workflow_boundary_authority_unclassified`, enforced through
`orchestrator/workflow_lisp/build.py` and
`orchestrator/workflow_lisp/phase_family_boundary.py`) must remain
authoritative. Rows may be deleted, updated, or reclassified only when the
compiled boundary-authority report and expected-row projection prove the old
row is stale. Per target design Section 12.1, reconciling a superseded
checked row means rebaselining it to live compiled evidence, not weakening
the gate or relabeling the row to keep it alive.

## Root-Cause Classification

Checkout drift, not a live workflow defect: the
`lisp_frontend_design_delta/implementation_phase` compiled boundary evidence
changed (the review-revise-loop proc-ref call shape for the
`validate_review_findings_v1` result bundle on the completed-review approve
route now lowers under different generated identifiers), while the checked
registry still carried the `managed_write_root` row keyed to the superseded
generated shape. The registry row is the stale artifact to reconcile; the
compiled evidence and the fail-closed gate are correct.

## Required Capability (Minimum To Unblock The Dependent)

The checked
`design_delta_parent_drain.boundary_authority.json` registry describes only
`(workflow_name, field_name, surface_kind)` rows that exist in the current
compiled evidence for every target workflow on the parent-drain route,
including `lisp_frontend_design_delta/implementation_phase::implementation-phase`,
so the parent-drain compile gate and the focused feasibility selector no
longer stop with `workflow_boundary_authority_unclassified` on an
`implementation_phase` registry row — with the fail-closed gate fully intact.

## Verified Live Baseline

Fresh read-only inspection of the working tree (2026-07-06) shows the repair
likely landed as uncommitted work owned by the live drain run:

- the checked registry is dirty in the working tree and no longer contains
  the stale row's generated hash segments cited by the blocker evidence; and
- the registry's `implementation_phase` rows are keyed to the current
  compiled shapes (for example the `fix-implementation.v1` and
  `review-implementation.v1` write-root rows).

Implementation must therefore be verify-first: prove the acceptance
conditions with fresh command output before writing any edit. If everything
is already green, record that evidence and complete without new edits.
Inspection alone is not completion evidence.

## Ownership And Bounded Scope

This slice owns:

- the checked boundary-authority registry rows in
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`,
  reconciled against compiled expected rows for the live route; and
- alignment of the focused boundary-authority guards in
  `tests/test_workflow_lisp_build_artifacts.py` only where an expectation
  encodes the superseded `implementation_phase` row shape.

This slice does not own and must not absorb:

- the fail-closed gate logic in `orchestrator/workflow_lisp/build.py` and
  `orchestrator/workflow_lisp/phase_family_boundary.py` (read-only unless a
  genuine generic defect is proven, and never weakened);
- workflow-source edits to `implementation_phase.orc` or any family/stdlib
  `.orc` module to force the old registry shape;
- the value-flow census, consumer-rendering, transition-authoring,
  resume-plumbing, or reference-family checked-input lanes (owned by sibling
  gaps); and
- YAML-primary promotion or runtime smoke beyond the named compile/feasibility
  entrypoints.

## Allowed Implementation Shapes

- removing or updating only registry rows whose
  `(workflow_name, field_name, surface_kind)` key no longer appears in the
  compiled expected rows for the parent-drain route, including the stale
  `implementation_phase` `managed_write_root` row named by the blocker;
- adding rows only for compiled evidence that genuinely exists on the live
  route and is currently unclassified; and
- updating focused build-artifact guards to assert the reconciled registry
  (expected-row coverage, checkout-owned metadata, no stale/missing/path-like
  mismatches).

Forbidden:

- weakening, bypassing, or making advisory the
  `workflow_boundary_authority_unclassified` gate or the stale-row rejection
  contract;
- keeping, re-adding, or relabeling registry rows for compiled shapes that no
  longer exist (for example reclassifying the stale row as a compatibility
  bridge or generated-internal value merely to satisfy the manifest);
- editing `.orc` sources to regenerate the superseded write-root shape; and
- hand-editing runtime-owned artifacts under `artifacts/work/`.

## Acceptance Conditions

This gap is complete when all of the following hold on the working tree with
fresh command output:

- `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_boundary_authority_registry_covers_expected_rows -q`
  passes (checked registry matches compiled expected rows, no stale or
  missing rows);
- `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_boundary_authority_report_for_all_target_workflows -q`
  passes (report emitted for every target workflow including
  `implementation_phase`);
- `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_stale_boundary_authority_registry_row_mismatch -q`
  passes (fail-closed contract preserved: a genuinely stale row still fails);
- `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q`
  no longer fails on `workflow_boundary_authority_unclassified`; and
- the parent-drain direct compile no longer fails with
  `[workflow_boundary_authority_unclassified]` on an `implementation_phase`
  registry row. The compile may still fail closed on later checked-input
  gates owned by sibling slices (for example reference-family conformance);
  those failure classes are out of scope here and do not block this gap's
  completion, but the first failure must not be the boundary-authority gate.

Evidence rules: treat fresh command output as the only completion evidence;
reconcile rows only against compiled evidence (boundary-authority report and
expected-row projection), never against the manifest's own history; report a
`semantic_conflict` between checked consumers if a durable authority requires
the superseded row instead of silently choosing a side.
