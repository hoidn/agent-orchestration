# Design Delta Work-Item Private Phase Context Boundary Architecture

Status: revised implementation architecture (sixth revision; consumer-rendering
blocker incorporated 2026-07-06)
Scope: `workflow-lisp-design-delta-work-item-private-phasectx-boundary`

## Purpose

The private-`PhaseCtx` work-item boundary itself is landed and green on the
current checkout: the parent drain compiles under shared validation, the
boundary-projection and runtime-context selectors pass, the work-item
feasibility lane passes, and the ordinary drain/work-item route is
carrier-free. The prior revision correctly identified the first causal repair:
the transition-authoring evidence contract for the work-item finalize route
needed to be reconciled with the carrier-free route:

- the parent-drain compile fails closed on the checked transition-authoring
  direct input with `transition_authoring_invalid: stale_allowed_origins`
  (enforced in `orchestrator/workflow_lisp/build.py`, design-delta build
  route); and
- three `tests/test_workflow_lisp_transition_authoring.py` selectors fail
  because the compiled origins no longer surface the imported
  `std/resource::finalize-selected-item-proc` transition sites the
  allowed-origins manifest and guards expect.

That transition-authoring repair is necessary but not sufficient for the
target Section 14 compile/build acceptance route. Implementation evidence has
now proved two consecutive scope gaps in the earlier revisions. Once the
transition report passed, the same compile/build route failed closed on stale
checked rows in the parent-drain value-flow census and boundary-authority
registry. After those rows were reconciled, the route advanced to a direct
consumer-rendering/entry-publication gate and failed closed on
`interior_publication` for the checked C0 row
`c0.std_drain_materialized_shared_drain_result_summary`. This revision keeps
the target and baseline designs unchanged and expands this gap only to direct
checked-input reconciliation on the same parent-drain acceptance route:
transition effects must stay visible in the source map, checked manifests must
describe only values/effects that exist on the live route, checked
consumer-rendering rows must classify only real consumer seams, and committed
guards must assert the live contract instead of a superseded intermediate
shape.

## Governing Contract

The owning target design is:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
  (Sections 7.4, 7.7, 8.1, 12.1, 13.4)

The baseline frontend contract remains:

- `docs/design/workflow_lisp_frontend_specification.md`

Command, adapter, transition, and checked-manifest boundaries follow:

- `docs/design/workflow_command_adapter_contract.md`

Shared owner-lane boundaries follow:

- `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`

The durable contract for this gap is unchanged from the prior revision:

- `run-work-item` remains the Design Delta work-item owner boundary and must
  not expose public `RunCtx`, `PhaseCtx`, generated roots, checkpoint paths,
  or `run_state_path` inputs. Its internal `PhaseCtx` parameter is supplied by
  hidden reusable-call binding per target design Section 7.7.
- The derived work-item phase context remains the private runtime binding
  `phase-ctx__work-item`, recorded in boundary projection.
- `run-selected-item-stdlib` remains the imported `std/drain` run-item route
  with the fixed `ItemCtx + typed payload` shape and typed
  `SelectedItemResult`.
- Durable work-item finalization is the imported
  `std/resource::finalize-selected-item-proc` typed transition, called from
  the family-native finalizer workflows in `work_item.orc`
  (`finalize-selected-item-from-completed-implementation`,
  `finalize-selected-item-from-blocked-implementation`).
- Internal composition passes typed values, never compatibility carriers.

Per target design Sections 7.4 and 8.1, transition contracts carry source-map
provenance and the frontend must emit source-map and Semantic IR entries for
transition effects. Evidence about those transitions is derived from the
compiled source map, never from prompt text, rendered reports, or pointer
files.

## Verified Live Baseline And Blocker (2026-07-05/2026-07-06)

Fresh checkout evidence establishes this split:

Green, preserved obligations (do not regress, do not redo):

- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item"`:
  17 passed.
- `tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_call_work_item_boundary_projection_records_derived_work_item_phase_binding`
  and `::test_design_delta_work_item_runtime_context_inputs_stay_internal`:
  pass.
- `tests/test_workflow_lisp_phase_stdlib.py` +
  `tests/test_workflow_lisp_resource_stdlib.py`: 137 passed.
- `tests/test_workflow_lisp_transition_authoring.py::test_design_delta_parent_drain_shared_validation_clears_direct_boundary_state_path_lints`:
  passes — shared validation compiles the parent drain entrypoint.
- The callable-child backlog-drain owner boundary is landed
  (`std/drain::backlog-drain` appears as an ordinary called child in the
  parent source map); that lane is not this slice's concern.

Red, owned by this slice:

- `python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain ...`
  (the target design Section 14 entrypoint) fails closed with
  `[transition_authoring_invalid] ... stale_allowed_origins` against the
  checked manifest
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`.
- `tests/test_workflow_lisp_transition_authoring.py`: 3 failed, 10 passed
  (`test_transition_authoring_report_passes_for_checked_design_delta_family`,
  `test_transition_authoring_report_rejects_stale_allowed_origin_rows`,
  `test_transition_authoring_report_records_imported_finalize_selected_item_transition_origins`).
- `tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_transition_authoring_report_artifact`:
  fails on the same fail-closed gate.

Committed `HEAD` alone is not a recovery route: in a clean `HEAD` clone the
transition-authoring suite fails 9 of 13. The working tree is strictly ahead;
the committed guards encode the intended live contract for the working-tree
route.

The implementation attempt for the fourth revision completed the
transition-authoring/source-map work and produced fresh green evidence:

- `tests/test_workflow_lisp_transition_authoring.py`: 13 passed.
- `tests/test_workflow_lisp_source_map.py`: 18 passed.
- the preserved private-context selectors and work-item feasibility lane stayed
  green.
- `tests/test_workflow_lisp_phase_stdlib.py` +
  `tests/test_workflow_lisp_resource_stdlib.py`: 137 passed.
- the ordinary route carrier scan still found no `run_state_path` matches.

The same attempt then exposed two fail-closed checked-input failures on the
required parent-drain acceptance route:

- `tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_transition_authoring_report_artifact`
  fails closed with `[value_flow_census_invalid]` on a stale checked row keyed
  to the old `std_drain_*_drain_result_proc_*__outcome__result_bundle`
  compiled boundary shape.
- the target Section 14 compile entrypoint fails closed with
  `[workflow_boundary_authority_unclassified]` on the corresponding stale
  `managed_write_root` row in
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`.

These are not a separate prerequisite lane for this work item: they are stale
checked manifestations of the same live-route change already accepted by this
gap. The checked-input gates remain correct; the stale manifest rows are the
artifact to reconcile.

The next implementation attempt reconciled those boundary-authority and
value-flow rows and verified the raw boundary registry against compiled
expected rows (`STALE 0`, `MISSING 0`). The target compile entrypoint then
progressed past both earlier gates and exposed a third checked-input failure on
the same direct build route:

- the target Section 14 compile entrypoint fails closed with
  `[interior_publication] design-delta entry publication report failed:
  interior_publication:
  c0.std_drain_materialized_shared_drain_result_summary` against
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json`.

This is still not a target-design conflict. Target design Sections 7.5, 8.1,
12.1, and 13.4 already require consumer-side rendering and entry-boundary
publication handling. The stale assumption was only in this gap architecture:
it treated the checked boundary/value-flow manifests as the final direct
checked inputs on the parent-drain route. The implementation route also loads
and enforces the checked consumer-rendering census and entry-publication report,
so the same stale-route reconciliation must include that lane.

## Root-Cause Classification

Each failing check was classified against the live checkout before inclusion:

1. **Generic source-map fidelity defect (live contract to satisfy).**
   `_step_kind_from_mapping` in `orchestrator/workflow_lisp/source_map.py`
   derives core-node step kinds for workflows without validated bundles and
   has no mapping for steps that carry a lowered `resource_transition`
   config; such steps serialize as kind `step`. Workflows with validated
   bundles take the core-AST route, whose statement metadata reports
   `resource_transition` correctly. The family finalizer workflows
   (`finalize-selected-item-from-{completed,blocked}-implementation`) have no
   validated bundles, so their inlined
   `std/resource::finalize-selected-item-proc` runtime-native transition
   steps (step ids containing `std_resource_finalize_selected_item_proc_`,
   step-origin path `std/resource.orc`) lose the `resource_transition` kind
   and are dropped by the transition-authoring report's candidate filter.
   This violates the target design Section 8.1 requirement that transition
   effects stay visible in source maps. The two derivation routes must agree.
   A read-only simulation confirms the generic repair: with the fallback
   classifying `resource_transition`-keyed steps as `resource_transition`,
   the report recovers exactly six finalize origins across the two family
   finalizer workflows, with `module_name == lisp_frontend_design_delta/work_item`,
   `path` anchored to `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`,
   and `classification == low_level_library` — exactly what the committed
   guard `test_transition_authoring_report_records_imported_finalize_selected_item_transition_origins`
   asserts.

2. **Three stale checked-manifest rows (stale artifact to exclude).**
   The uncommitted manifest rows `low_level.imported_empty_drain_result`,
   `low_level.imported_blocked_drain_result`, and
   `low_level.imported_completed_drain_result` expect `resource_transition`
   steps whose ids contain `std_drain_*_drain_result_proc_`. On the live
   route those `std/drain` procs are pure typed constructors with
   `:effects ()` and contain no `resource-transition` form; the family's
   drain-terminal transition is the family transitions helper
   (`record-drain-terminal-outcome-stdlib`), already covered by the
   `low_level.record_drain_terminal_outcome` row. The `std/drain`
   transitions that do exist (`consume-drain-terminal-effects`) are not part
   of the family's compiled closure. These three rows can never match and
   are what trips the fail-closed `stale_allowed_origins` gate. They must be
   removed from the manifest. The
   `low_level.imported_finalize_selected_item` row (no `module_name`
   constraint, `step_id_contains: std_resource_finalize_selected_item_proc_`)
   is correct and stays.

3. **Stale guard expectations in the committed pass-case selector (stale
   artifact to reconcile).**
   `test_transition_authoring_report_passes_for_checked_design_delta_family`
   asserts that compiled-origin `module_name` values include
   `lisp_frontend_design_delta/drain` and that some drain-module row has
   `path == .../std/drain.orc`. On the live route no imported `std/drain`
   transition is inlined into the drain module; the only transition site in
   `drain::drain` is the inlined family transitions helper, whose authored
   module attribution is `lisp_frontend_design_delta/transitions` (step-origin
   path `transitions.orc`). After repairs 1 and 2 the origin module set is
   exactly `{lisp_frontend_design_delta/transitions, lisp_frontend_design_delta/work_item}`
   and the report status is `pass` with empty violation buckets (verified by
   simulation). The pass-case guard's drain-module and `std/drain.orc`-path
   assertions must be aligned to the live contract (for example by asserting
   the `drain::drain` workflow row and its transitions-module attribution)
   rather than preserved as unsatisfiable expectations. The other two failing
   selectors need no edits: they pass once repairs 1 and 2 land.

4. **Under-scoped checked-input reconciliation (stale duplicate to remove).**
   The fourth revision treated transition-authoring as the only checked input
   affected by the live carrier-free route. Fresh implementation evidence
   contradicts that assumption: the parent-drain build and compile gates also
   load `design_delta_parent_drain.value_flow_census.json` and
   `design_delta_parent_drain.boundary_authority.json`, and both still contain
   rows for the superseded `std/drain` result-proc outcome bundle shape. On the
   live route those result procs are typed constructors, not managed-write-root
   or value-flow boundary producers for the family terminal transition. The
   compiled evidence is instead owned by the family transitions helper and the
   typed terminal projection path already covered by the current route. The
   repair is to reconcile those two checked manifests and their focused
   consumers against compiled boundary/source-map evidence, not to weaken the
   fail-closed `value_flow_census_invalid` or
   `workflow_boundary_authority_unclassified` gates.

5. **Under-scoped consumer-rendering checked-input reconciliation (stale
   publication classification to correct).**
   The fifth revision treated boundary authority and value flow as the final
   checked inputs affected by the live carrier-free route. Fresh implementation
   evidence contradicts that assumption: after those two manifests align, the
   parent-drain build and compile gates also load
   `design_delta_parent_drain.consumer_rendering_census.json` and build the
   entry-publication report. The report fails closed with
   `interior_publication` on
   `c0.std_drain_materialized_shared_drain_result_summary` because that checked
   C0 row is selected for entry publication even though its
   `workflow_surface` is the imported non-entry `std/drain::backlog-drain`
   workflow and live compiled evidence still includes body-level
   `materialize_view` effects for that workflow. Per the current
   `entry_publication` gate, selected entry-publication rows are legal only
   for the actual entry workflow's typed terminal variants; non-entry rows with
   body materialization are compatibility, observability, timed-body, or
   retirement evidence, not C3 entry publications. The repair is to reconcile
   the checked C0 row classification and any focused rendering-cleanup /
   entry-publication guard expectations against live consumer-rendering,
   materialize-view, and publication-policy evidence. Do not weaken
   `interior_publication`, do not make selected non-entry body views legal for
   entry publication, and do not edit `.orc` workflow sources just to force the
   old row shape.

If implementation uncovers a durable authority that contradicts this
classification — for example a spec that requires the `std/drain` result
procs to perform transitions, or a consumer that depends on the fallback
`step` kind for lowered transition steps — stop and report a
`semantic_conflict` between checked consumers instead of silently choosing a
side.

## Ownership And Bounded Scope

This slice owns:

- source-map serialization fidelity for lowered declared-transition steps in
  workflows without validated bundles (`orchestrator/workflow_lisp/source_map.py`,
  authored-mapping fallback route);
- the checked transition-authoring manifest rows for the design-delta parent
  family
  (`workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`);
- alignment of the committed transition-authoring guards in
  `tests/test_workflow_lisp_transition_authoring.py` with the live
  carrier-free contract;
- reconciliation of stale checked parent-drain boundary/value-flow rows in
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`
  and
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json`
  when fresh compiled evidence proves the rows no longer exist on the live
  route;
- reconciliation of stale checked parent-drain consumer-rendering rows in
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json`
  when fresh compiled materialize-view and entry-publication evidence proves a
  row is no longer a legal entry-publication candidate;
- alignment of the focused build-artifact guards for boundary-authority and
  value-flow census, consumer-rendering census, rendering-cleanup, and
  entry-publication reports in `tests/test_workflow_lisp_build_artifacts.py`
  with the reconciled checked inputs; and
- a generic behavioral regression check for the source-map repair (the
  natural home is `tests/test_workflow_lisp_source_map.py`).

This slice does not own and must not absorb:

- workflow-source edits to `drain.orc`, `work_item.orc`, `selector.orc`,
  `plan_phase.orc`, `implementation_phase.orc`, or the stdlib `.orc` modules
  — fresh evidence shows the boundary route is already correct for this
  slice;
- the substrate/parity bridge lane and its fixtures (compatibility-carrier
  retirement lane);
- report-generation policy changes in
  `orchestrator/workflow_lisp/transition_authoring.py` beyond what the
  classification above strictly requires (the candidate filter and matching
  rules are correct once the source map reports kinds faithfully);
- entry-publication or consumer-rendering policy changes in
  `orchestrator/workflow_lisp/build.py`,
  `orchestrator/workflow_lisp/entry_publication.py`, or
  `orchestrator/workflow_lisp/consumer_rendering_census.py` beyond a minimal
  generic defect repair proven by reconciled checked inputs; and
- YAML-primary promotion or parent-drain runtime smoke obligations beyond the
  compile/build entrypoints named in the acceptance conditions.

## Shared-Surface Rules

Files this slice touches that are used outside the gap follow these rules:

- `orchestrator/workflow_lisp/source_map.py` is a shared frontend surface.
  The repair must be generic: classify any lowered step mapping that carries
  a declared `resource_transition` config as step kind
  `resource_transition`, so the authored-mapping fallback agrees with the
  validated-bundle core-AST route. No branch, name test, or special case
  keyed to `lisp_frontend_design_delta/*`, `std/resource`, `std/drain`, or
  drain/phase concepts may be added. Outside uses: source-map core-node step
  kinds are consumed by `orchestrator/workflow_lisp/transition_authoring.py`
  (verified as the only core-node consumer in the current checkout); any
  future consumer must receive the same rule — a lowered declared-transition
  step is kind `resource_transition` regardless of which serialization route
  produced it.
- The transition-authoring manifest is a checked direct input with
  fail-closed validation (per the command-adapter contract's checked-manifest
  discipline). Rows change only when the live compiled route proves them
  wrong, as classified above. The fail-closed gate in
  `orchestrator/workflow_lisp/build.py` must not be weakened, bypassed, or
  made advisory to clear the failure.
- The boundary-authority registry and value-flow census are checked direct
  inputs on the same parent-drain build route. Their fail-closed checks in
  `orchestrator/workflow_lisp/build.py`,
  `orchestrator/workflow_lisp/phase_family_boundary.py`, and
  `orchestrator/workflow_lisp/value_flow_census.py` must remain authoritative.
  Rows may be deleted or reclassified only when the compiled
  boundary-authority report, source map, and value-flow reconciliation prove the
  old row is stale. Do not classify an obsolete row as a compatibility bridge or
  generated internal value merely to satisfy the manifest.
- The consumer-rendering census is also a checked direct input on the same
  parent-drain build route. Its fail-closed checks in
  `orchestrator/workflow_lisp/build.py`,
  `orchestrator/workflow_lisp/consumer_rendering_census.py`, and
  `orchestrator/workflow_lisp/entry_publication.py` must remain authoritative.
  Rows may be reclassified, removed, or split only when live value-flow rows,
  materialize-view effects, boundary-authority rows, and entry-publication
  policy prove the old C0 classification is stale. Do not classify a non-entry
  body materialization as an entry publication merely because it replaces a
  retired terminal summary; C3 entry publication belongs to the selected entry
  workflow's typed terminal variants.
- `tests/test_workflow_lisp_transition_authoring.py` guards are behavioral
  contract checks shared with the substrate/parity lane. The five
  substrate/parity selectors that pass today
  (`test_transition_authoring_manifest_rejects_high_level_allowed_origin_rows`,
  the three selected-item summary-path selectors, and the report
  fail-buckets selectors) must stay green; edits are limited to the stale
  expectations named in the classification.
- Updated tests must assert report structure, origin attribution, and
  fail-closed behavior — never prompt text or rendered report prose.

## Allowed Implementation Shapes

Allowed:

- adding the `resource_transition` mapping to the source-map fallback
  step-kind derivation, plus a generic behavioral test proving a lowered
  declared-transition step in a workflow without a validated bundle
  serializes with kind `resource_transition`;
- removing the three `low_level.imported_*_drain_result` rows from the
  checked manifest while keeping `low_level.imported_finalize_selected_item`
  and all family-transitions rows;
- rewriting the stale pass-case guard assertions to the live contract:
  status `pass`, empty violation buckets, low-level classification for all
  origins, presence of the `drain::drain` terminal-outcome row and the
  work-item finalize rows anchored to
  `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`;
- if the guard edits reveal a true report-code defect (not just stale
  expectations), the minimal generic repair in
  `orchestrator/workflow_lisp/transition_authoring.py`, bounded by the
  shared-surface rules;
- reconciling the boundary-authority registry by removing or updating only
  rows whose `(workflow_name, field_name, surface_kind)` key no longer appears
  in the compiled expected rows for the parent-drain route, including the stale
  `std_drain_*_drain_result_proc_*__outcome__result_bundle`
  `managed_write_root` rows identified by the implementation blocker;
- reconciling the value-flow census by removing or updating only rows whose
  checked source/target evidence no longer matches the compiled
  boundary-authority report, including stale rows for the same superseded
  `std/drain` result-proc outcome bundle shape;
- reconciling the consumer-rendering census by removing, splitting, or
  reclassifying only rows whose checked C0 consumer lane no longer matches the
  live consumer seam, including the stale
  `c0.std_drain_materialized_shared_drain_result_summary` entry-publication
  classification if compiled evidence proves it is a non-entry body
  materialization / retirement-candidate row rather than an entry-terminal
  publication; and
- updating focused build-artifact tests to assert pass-status, empty stale /
  missing / invalid buckets, provenance of the checked manifests, the live
  terminal/finalize ownership shape, and the live C0/C3
  rendering-publication classification.

Forbidden:

- weakening or bypassing the fail-closed `transition_authoring_invalid`
  compile gate, or downgrading `stale_allowed_origins` to a warning;
- weakening or bypassing the fail-closed `value_flow_census_invalid` or
  `workflow_boundary_authority_unclassified` gates, or converting stale checked
  rows into warnings;
- weakening or bypassing the fail-closed `consumer_rendering_census_invalid`,
  `entry_publication_c0_row_missing`, or `interior_publication` gates, or
  converting stale checked consumer-rendering rows into warnings;
- deleting or skipping the three failing guards instead of aligning them
  with the live contract;
- keeping (or re-adding) allowed-origin rows for transitions that do not
  exist on the live compiled route;
- keeping, re-adding, or relabeling boundary-authority/value-flow rows for
  path-like values that do not exist on the live compiled route;
- keeping, re-adding, or relabeling consumer-rendering rows as
  `entry_publication` when live compiled evidence shows the row belongs to a
  non-entry workflow or still lowers body-level materialization;
- teaching `source_map.py`, `transition_authoring.py`, or `build.py` any
  Design Delta-specific branch, workflow-name special case, or path
  convention inference;
- editing family or stdlib `.orc` workflow sources to force the old evidence
  shape (for example re-adding transitions to the `std/drain` result procs
  or re-routing finalization away from the imported
  `finalize-selected-item-proc`);
- exposing `PhaseCtx`, `RunCtx`, `run_state_path`, generated roots, or
  checkpoint paths anywhere on the work-item route (the preserved boundary
  contract); and
- widening shared-validation reachability just so the finalizer workflows
  gain validated bundles — the fallback route must be correct on its own.

## Acceptance Conditions

This gap is complete when all of the following hold on the working tree:

- `tests/test_workflow_lisp_transition_authoring.py` is green (13 passed),
  proving the pass-case report contract, the stale-row rejection contract,
  and the imported finalize-selected-item origin contract against the live
  route (target design Sections 7.4 and 13.4);
- the target design Section 14 compile entrypoint
  (`python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain`
  with the checked provider/prompt/command-boundary inputs) succeeds, with the
  transition-authoring, boundary-authority, value-flow census,
  consumer-rendering census, and entry-publication reports emitted at passing
  status and the fail-closed gates still active for genuinely stale rows;
- `tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_transition_authoring_report_artifact`
  passes, proving the checked build-artifact consumer sees the reconciled
  report;
- `tests/test_workflow_lisp_build_artifacts.py` focused boundary-authority and
  value-flow census selectors pass, proving the checked parent-drain
  `boundary_authority.json` and `value_flow_census.json` manifests have no
  stale, missing, invalid, or unclassified rows for the live route;
- `tests/test_workflow_lisp_build_artifacts.py` focused consumer-rendering,
  rendering-cleanup, and entry-publication selectors pass, proving the checked
  parent-drain `consumer_rendering_census.json` manifest has no stale, missing,
  invalid, or illegal non-entry publication rows for the live route;
- `tests/test_workflow_lisp_source_map.py` is green including a new
  behavioral check that lowered declared-transition steps keep the
  `resource_transition` kind on the no-bundle serialization route (target
  design Section 8.1 transition-effect visibility);
- the preserved boundary lanes stay green:
  `tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_call_work_item_boundary_projection_records_derived_work_item_phase_binding`,
  `::test_design_delta_work_item_runtime_context_inputs_stay_internal`, and
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item"`
  (17 passed) — proving the private `phase-ctx__work-item` binding and the
  carrier-free typed route are unchanged (target design Section 7.7);
- the ordinary drain/work-item route modules
  (`drain.orc`, `work_item.orc`, `plan_phase.orc`,
  `implementation_phase.orc`, `stdlib_adapters.orc`, `stdlib_payloads.orc`,
  `selector.orc`, `types.orc`, `projections.orc`, `bootstrap.orc`) still
  contain no `run_state_path` carrier (deterministic scan); and
- the shared owner-lane guard suites stay green
  (`tests/test_workflow_lisp_phase_stdlib.py`,
  `tests/test_workflow_lisp_resource_stdlib.py`).

Out of scope and excluded from this slice's evidence: the view-dual-run and
migration-parity substrate fixtures (compatibility-carrier retirement lane),
broader conversion-lane redness in `tests/test_workflow_lisp_drain_stdlib.py`
beyond its current green state, live-run evidence-binding checks in
`tests/test_workflow_lisp_reference_family_conformance.py`, the parent-drain
runtime smoke beyond the named compile/build entrypoints, and YAML-primary
promotion.

Compile success alone is not sufficient: the evidence must prove that
transition effects on the work-item finalize route are visible, checked, and
attributed to the imported typed transition, that the checked boundary/value-flow
manifests describe the live parent-drain boundary surface, and that checked
consumer-rendering rows describe the live rendering/publication seams — not that
report files merely exist.
