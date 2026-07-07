# Design Delta Implementation-Phase Boundary Authority Registry Repair Architecture

Status: authored implementation architecture (verify-and-commit revision, 2026-07-06)
Design gap id: `workflow-lisp-design-delta-implementation-phase-boundary-authority-registry-repair`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Sections 12.1, 13.4)
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`
Shared owner-lane authority: `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`

## Purpose

This gap is the declared prerequisite for
`workflow-lisp-design-delta-compatibility-carrier-retirement`. That dependent
slice completed its approved carrier-retirement work and stopped `BLOCKED`
with recovery route `PREREQUISITE_GAP_REQUIRED` waiting on this exact gap id,
because the remaining red check was not a drain-carrier regression but
unrelated `implementation_phase` boundary-authority registry drift outside
its approved slice.

The recorded blocker evidence from the dependent slice's blocked run:

- the parent-drain direct compile
  (`python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain`
  with the checked provider/prompt/command-boundary inputs) and the
  feasibility selector
  (`pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q`)
  both stopped in the compile gate with the same validation error:
  `[workflow_boundary_authority_unclassified] stale boundary authority
  registry row does not match compiled evidence` against
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`;
- the stale row was a `managed_write_root` row for
  `lisp_frontend_design_delta/implementation_phase::implementation-phase`
  whose generated write-root field name was keyed to a superseded
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
registry at HEAD still carries `managed_write_root` rows keyed to the
superseded generated shape. The registry rows are the stale artifact to
reconcile; the compiled evidence and the fail-closed gate are correct.

The reconciliation itself has since been applied to the working tree by the
live drain run but exists only as uncommitted state. The residual gap is
therefore not authoring the repair; it is converting unverified working-tree
state into verified, committed, gate-green evidence.

## Verified Live Baseline

Fresh command output on this checkout (2026-07-06, this drafting pass)
confirms the reconciliation is present and green in the working tree:

- `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_boundary_authority_registry_covers_expected_rows tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_stale_boundary_authority_registry_row_mismatch -q`
  — 2 passed;
- `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_boundary_authority_report_for_all_target_workflows -q`
  — 1 passed;
- `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q`
  — 5 passed, 88 deselected;
- the selector's fresh direct parent-drain compile on this checkout
  (fingerprint `2524aa25a3869738`) passed all gates with only advisory
  warnings.

The uncommitted working-tree state carrying that repair:

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`
  is dirty: the superseded review-revise-loop write-root keys
  (`...proc_5588d9f88e40_6df541978dae_1...` for `implementation_phase`,
  `...proc_f3ae8cb36a98_ad08cd0f8aa8_1...` for `plan_phase`) are rebaselined
  to the current compiled shapes
  (`...proc_96de13fa5abd_4dd411f3a486_1...`,
  `...proc_b1ad4a920aa2_54115ccd3ac8_1...`), and rows whose compiled shapes
  no longer exist are deleted; and
- `tests/test_workflow_lisp_build_artifacts.py` is dirty with a large
  multi-lane diff in which boundary-authority guard expectations are
  interleaved with hunks owned by sibling in-flight work.

Implementation remains verify-first: prove the acceptance conditions with
fresh command output before and after any commit. Inspection alone is not
completion evidence, and an uncommitted green tree is not completion.

## Required Capability (Minimum To Unblock The Dependent)

The committed checked
`design_delta_parent_drain.boundary_authority.json` registry describes only
`(workflow_name, field_name, surface_kind)` rows that exist in the current
compiled evidence for every target workflow on the parent-drain route,
including `lisp_frontend_design_delta/implementation_phase::implementation-phase`,
so the parent-drain compile gate and the focused feasibility selector no
longer stop with `workflow_boundary_authority_unclassified` on an
`implementation_phase` registry row — with the fail-closed gate fully
intact, and with the reconciliation recorded as committed, gate-green
evidence rather than uncommitted working-tree drift.

## Ownership And Bounded Scope

This slice owns:

- the checked boundary-authority registry rows in
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`,
  reconciled against compiled expected rows for the live route, and the
  commit that lands that reconciliation;
- alignment of the focused boundary-authority guards in
  `tests/test_workflow_lisp_build_artifacts.py` only where an expectation
  encodes the superseded `implementation_phase` row shape or is required for
  the committed registry to pass the three named guard selectors; and
- fresh verification evidence for the acceptance conditions.

This slice does not own and must not absorb:

- the fail-closed gate logic in `orchestrator/workflow_lisp/build.py` and
  `orchestrator/workflow_lisp/phase_family_boundary.py` (read-only unless a
  genuine generic defect is proven, and never weakened);
- workflow-source edits to `implementation_phase.orc` or any family/stdlib
  `.orc` module to force the old registry shape;
- the value-flow census, consumer-rendering, transition-authoring,
  resume-plumbing, or reference-family checked-input lanes (owned by sibling
  gaps), including any sibling-owned hunks in shared dirty files;
- YAML-primary promotion or runtime smoke beyond the named
  compile/feasibility entrypoints.

## Commit Scope Rule

The commit boundary is a constraint of this slice, not a procedural note,
because the working tree carries in-flight work from other lanes:

- stage by explicit path only; never commit the whole working tree;
- the registry file may be committed wholesale only because its entire dirty
  diff is boundary-authority reconciliation, which the
  `registry_covers_expected_rows` guard proves against compiled evidence —
  if any non-reconciliation content appears in that file's diff, the slice
  must not commit it;
- in `tests/test_workflow_lisp_build_artifacts.py`, only hunks that encode
  boundary-authority expectations for the reconciled registry belong to this
  slice; sibling-lane hunks in the same file must be left uncommitted;
- if the boundary-authority hunks cannot be separated from sibling-lane
  hunks without semantic entanglement (a boundary-authority expectation that
  only passes together with a foreign change), report `semantic_conflict`
  between the checked consumers rather than committing foreign work or
  splitting a hunk into an untested intermediate state; and
- commit hooks must run; bypassing them is forbidden.

## Rule For Outside Uses

The registry file is consumed outside this slice's files: the parent-drain
build gate (`build.py` / `phase_family_boundary.py`), the build-artifact
guard tests, the feasibility selector lane, and every sibling slice whose
compile route loads the checked manifest set. Those outside uses follow one
rule: the registry stays a fail-closed checked direct input whose rows change
only with compiled-evidence proof (boundary-authority report plus
expected-row projection). Sibling slices must not opportunistically
rebaseline, relabel, or delete boundary-authority rows as a side effect of
their own lanes, and must not reintroduce dependence on the superseded
`implementation_phase` row shape.

## Allowed Implementation Shapes

- removing or updating only registry rows whose
  `(workflow_name, field_name, surface_kind)` key no longer appears in the
  compiled expected rows for the parent-drain route, including the stale
  `implementation_phase` `managed_write_root` rows named by the blocker;
- adding rows only for compiled evidence that genuinely exists on the live
  route and is currently unclassified;
- updating focused build-artifact guards to assert the reconciled registry
  (expected-row coverage, checkout-owned metadata, no stale/missing/path-like
  mismatches);
- verifying the already-applied working-tree reconciliation with fresh
  command output and committing it under the Commit Scope Rule with no
  content changes, when verification shows the acceptance conditions already
  hold — recording that evidence is the expected happy path for this slice.

## Forbidden Shapes

- weakening, bypassing, or making advisory the
  `workflow_boundary_authority_unclassified` gate or the stale-row rejection
  contract;
- keeping, re-adding, or relabeling registry rows for compiled shapes that no
  longer exist (for example reclassifying a stale row as a compatibility
  bridge or generated-internal value merely to satisfy the manifest);
- editing `.orc` sources to regenerate the superseded write-root shape;
- committing sibling-lane working-tree changes, whole dirty files outside
  the slice's ownership, or any hunk not traceable to this reconciliation;
- hand-editing runtime-owned artifacts under `artifacts/work/`; and
- claiming completion from an uncommitted green tree or from inspection
  without fresh command output.

## Acceptance Conditions

This gap is complete when all of the following hold, with fresh command
output, on the tree that results after the slice's commit:

- `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_boundary_authority_registry_covers_expected_rows -q`
  passes (checked registry matches compiled expected rows, no stale or
  missing rows);
- `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_boundary_authority_report_for_all_target_workflows -q`
  passes (report emitted for every target workflow including
  `implementation_phase`);
- `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_stale_boundary_authority_registry_row_mismatch -q`
  passes (fail-closed contract preserved: a genuinely stale row still fails);
- `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q`
  passes with no `workflow_boundary_authority_unclassified` failure;
- the parent-drain direct compile does not fail with
  `[workflow_boundary_authority_unclassified]` on an `implementation_phase`
  registry row (the current checkout evidence, fingerprint
  `2524aa25a3869738`, shows the full compile passing with advisory warnings
  only; if a later checked-input gate owned by a sibling slice regresses
  independently, that failure class does not block this gap, but the first
  failure must not be the boundary-authority gate);
- `git status --short` reports
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`
  clean, and the committed content contains no row keyed to the superseded
  `...proc_5588d9f88e40_6df541978dae_1...` or
  `...proc_f3ae8cb36a98_ad08cd0f8aa8_1...` shapes; and
- every hunk in the slice's commit is traceable to this reconciliation under
  the Commit Scope Rule.

All five check selectors above were verified live and green on this checkout
on 2026-07-06; none is a stale artifact.

## Residual Failure Routing

Evidence rules: treat fresh command output as the only completion evidence;
reconcile rows only against compiled evidence (boundary-authority report and
expected-row projection), never against the manifest's own history. If a
durable authority requires the superseded row, or a boundary-authority guard
can only pass together with a sibling-lane change, report a
`semantic_conflict` between the checked consumers instead of silently
choosing a side. Any post-commit failure in a class other than
`workflow_boundary_authority_unclassified` (for example reference-family
conformance or other checked-input gates) is routed to its owning sibling
lane through the recovery ledger, not absorbed into this slice.
