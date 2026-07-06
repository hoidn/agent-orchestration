# Design Delta Parent Transition-Authoring Stale Allowed-Origins Repair Architecture

Status: authored implementation architecture (prerequisite gap record; 2026-07-06)
Design gap id: `workflow-lisp-runtime-native-drain-design-delta-parent-transition-authoring-stale-allowed-origins`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Sections 7.4, 8.1, 12.1, 13.4)
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`
Shared owner-lane authority: `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`

## Purpose

This gap is the declared prerequisite for
`workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression`.
That dependent slice re-verified its own owner-lane, Fallout-D, and guard
lanes green, then classified the first live downstream blocker as the
sibling transition-authoring lane's checked direct compile input, which its
approved plan's stop rule and ownership routing forbade it from repairing.

The recorded blocker evidence from the dependent slice's blocked run:

- `pytest tests/test_workflow_lisp_transition_authoring.py::test_transition_authoring_report_passes_for_checked_design_delta_family -q`
  failed; direct report inspection showed `status=fail` with
  `stale_allowed_origins` for the checked rows
  `low_level.imported_empty_drain_result`,
  `low_level.imported_blocked_drain_result`,
  `low_level.imported_completed_drain_result`, and
  `low_level.imported_finalize_selected_item`;
- the parent-drain direct compile
  (`python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain`
  with the checked provider/prompt/command-boundary inputs) failed closed with
  `[transition_authoring_invalid] design-delta transition authoring report
  failed: stale_allowed_origins` against
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`;
  and
- `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "parent_drain_build_and_execution_smoke" -q`
  failed on the same `transition_authoring_invalid ... stale_allowed_origins`
  gate during `build_frontend_bundle(...)`.

## Governing Contract

Per target design Sections 7.4 and 8.1, transition contracts carry source-map
provenance and the frontend must keep transition effects visible in source
maps and Semantic IR; evidence about transitions derives from the compiled
source map, never prompt text or rendered reports. Per the command-adapter
contract's checked-manifest discipline, the transition-authoring manifest is a
fail-closed checked direct input: rows change only when the live compiled
route proves them wrong, and the gate is never weakened to clear a failure.
Per target design Section 12.1, retiring a superseded evidence shape means
deleting the stale rows, not accumulating compatibility bookkeeping.

## Root-Cause Classification

The `stale_allowed_origins` failure decomposes into three defects, consistent
with the classification proven in the sibling
`workflow-lisp-design-delta-work-item-private-phasectx-boundary` slice:

1. **Generic source-map fallback misclassification (live defect).** The
   authored-mapping fallback in `orchestrator/workflow_lisp/source_map.py`
   had no step-kind mapping for lowered steps carrying a declared
   `resource_transition` config, so no-bundle finalizer workflows serialized
   those steps as kind `step`. The transition-authoring report's candidate
   filter then dropped the imported
   `std/resource::finalize-selected-item-proc` origins, leaving the correct
   checked row `low_level.imported_finalize_selected_item` unmatched (hence
   "stale"). The repair is generic: any lowered declared-transition step is
   kind `resource_transition` regardless of serialization route; no
   family-named branches.
2. **Three genuinely stale checked rows (stale artifact).** The rows
   `low_level.imported_empty_drain_result`,
   `low_level.imported_blocked_drain_result`, and
   `low_level.imported_completed_drain_result` expect `resource_transition`
   steps from the `std/drain` result procs, but on the live route those procs
   are pure typed constructors with `:effects ()`; the family's drain-terminal
   transition is the family transitions helper already covered by
   `low_level.record_drain_terminal_outcome`. Those rows can never match and
   must be removed from the checked manifest.
3. **Stale pass-case guard expectations (stale artifact).** The committed
   pass-case selector asserted drain-module origin attribution
   (`lisp_frontend_design_delta/drain` with a `std/drain.orc` path) that does
   not exist on the live route; after repairs 1 and 2 the compiled origin
   module set is `{lisp_frontend_design_delta/transitions,
   lisp_frontend_design_delta/work_item}` with report status `pass` and empty
   violation buckets. The guard must assert the live contract.

## Required Capability (Minimum To Unblock The Dependent)

The dependent slice needs exactly this: the checked
`design_delta_parent_drain.transition_authoring.json` manifest and the
transition-authoring report agree with the live compiled route, so the
parent-drain direct compile and the feasibility build no longer fail with
`transition_authoring_invalid: stale_allowed_origins`, with the fail-closed
gate fully intact.

## Verified Live Baseline

Fresh inspection of the working tree (2026-07-06) shows this repair largely
landed as uncommitted work owned by the live drain run:

- the checked manifest now contains the family transitions rows plus
  `low_level.imported_finalize_selected_item`
  (`step_id_contains: std_resource_finalize_selected_item_proc_`), and the
  three `imported_*_drain_result` rows are gone; and
- a blocked-run report from the sibling compatibility-carrier slice records
  `pytest tests/test_workflow_lisp_transition_authoring.py -q` passing on this
  checkout, with the parent-drain compile advancing to later checked-input
  gates (boundary authority, reference-family conformance) owned by other
  slices.

Implementation must therefore be verify-first: prove the acceptance
conditions with fresh command output before writing any code. If everything
is already green, record that evidence and complete without new edits.

## Ownership And Bounded Scope

This slice owns:

- the checked transition-authoring manifest rows for the design-delta parent
  family
  (`workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`);
- alignment of the transition-authoring guards in
  `tests/test_workflow_lisp_transition_authoring.py` with the live
  carrier-free contract;
- the minimal generic source-map fallback repair in
  `orchestrator/workflow_lisp/source_map.py` plus its focused behavioral
  regression in `tests/test_workflow_lisp_source_map.py`; and
- minimal generic filtering/matching repairs in
  `orchestrator/workflow_lisp/transition_authoring.py` only if manifest and
  guards already match compiled origins yet the report still disagrees.

This slice does not own and must not absorb:

- the boundary-authority, value-flow-census, consumer-rendering, or
  entry-publication checked-input lanes (owned by the phasectx-boundary
  sibling slice);
- the reference-family conformance lane and its runtime-owned evidence
  artifacts;
- the `std/drain` gap/loop-state carrier lane (sibling prerequisite gap
  `std-drain-backlog-drain-gap-continue-loop-state-run-state-carrier-retirement`);
- workflow-source edits to family or stdlib `.orc` modules (for example
  re-adding transitions to `std/drain` result procs to force the old evidence
  shape); and
- YAML-primary promotion or runtime smoke beyond the named compile/build
  entrypoints.

## Allowed Implementation Shapes

- adding the generic `resource_transition` mapping to the source-map fallback
  step-kind derivation plus a behavioral regression test;
- removing the three stale `low_level.imported_*_drain_result` rows while
  keeping `low_level.imported_finalize_selected_item` and the family
  transitions rows;
- rewriting stale pass-case guard assertions to the live contract (status
  `pass`, empty violation buckets, low-level classification, finalize rows
  anchored to `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`);
  and
- a minimal generic report-logic repair in `transition_authoring.py`, bounded
  by the shared-surface rules below.

Forbidden:

- weakening or bypassing the fail-closed `transition_authoring_invalid`
  compile gate, or downgrading `stale_allowed_origins` to a warning;
- deleting or skipping the failing guards instead of aligning them;
- keeping or re-adding allowed-origin rows for transitions that do not exist
  on the live compiled route;
- teaching `source_map.py`, `transition_authoring.py`, or `build.py` any
  Design Delta-specific branch or name test; and
- editing `.orc` sources to force the superseded evidence shape.

## Shared-Surface Rules

- `orchestrator/workflow_lisp/source_map.py` is a shared frontend surface: the
  fallback repair must apply to any lowered declared-transition step with no
  branch keyed to `lisp_frontend_design_delta/*`, `std/resource`, `std/drain`,
  or drain/phase concepts, and both serialization routes must agree on the
  kind.
- The transition-authoring manifest stays a fail-closed checked direct input;
  the report and gate in `orchestrator/workflow_lisp/build.py` remain
  authoritative.
- Guard edits assert report structure, origin attribution, and fail-closed
  behavior — never prompt text or rendered report prose.
- The stale-row rejection contract
  (`test_transition_authoring_report_rejects_stale_allowed_origin_rows`) must
  stay green: genuinely stale rows still fail closed after this repair.

## Acceptance Conditions

This gap is complete when all of the following hold on the working tree with
fresh command output:

- `pytest tests/test_workflow_lisp_transition_authoring.py::test_transition_authoring_report_passes_for_checked_design_delta_family -q`
  passes (report status `pass`, empty violation buckets for the checked
  family);
- `pytest tests/test_workflow_lisp_transition_authoring.py::test_transition_authoring_report_rejects_stale_allowed_origin_rows -q`
  passes (fail-closed contract preserved);
- `pytest tests/test_workflow_lisp_transition_authoring.py::test_transition_authoring_report_records_imported_finalize_selected_item_transition_origins -q`
  passes (imported finalize origins visible and attributed to
  `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`);
- `pytest tests/test_workflow_lisp_transition_authoring.py -q` is green (full
  suite);
- `pytest tests/test_workflow_lisp_source_map.py -q` is green, including the
  behavioral check that lowered declared-transition steps keep the
  `resource_transition` kind on the no-bundle serialization route; and
- the parent-drain direct compile no longer fails with
  `[transition_authoring_invalid]`. The compile may still fail closed on later
  checked-input gates owned by sibling slices (boundary authority,
  reference-family conformance); those failure classes are out of scope here
  and do not block this gap's completion, but the first failure must not be
  the transition-authoring gate.

Evidence rules: treat fresh command output as the only completion evidence; do
not hand-edit runtime-owned artifacts under `artifacts/work/`; report a
`semantic_conflict` between checked consumers if a durable authority requires
the superseded evidence shape instead of silently choosing a side.
